"""PaddleOCR engine lifecycle, 3.x prediction and cache eviction.

Historical paddle_headwords_core keeps engine cache identity and runtime hooks.
All production callbacks and mutable cache structures are injected per call.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import Image
    from ..models import AppSettings
    from .headword_models import OCRRecord


def clear_paddle_engine_cache_impl(*, keep_key: tuple[str, str, str, bool] | None = None, cache: dict[Any, Any], lock: Any, gc_module: Any) -> None:
    """Drop cached Paddle engines that are no longer the active configuration.

    Local references held by an in-flight OCR call remain valid, so cache
    eviction cannot invalidate a page currently being recognized.  We avoid
    device-specific forced memory flushes here because those can interfere
    with an engine still executing in another worker/thread.
    """
    _ENGINE_CACHE = cache
    _ENGINE_CACHE_LOCK = lock
    gc = gc_module
    with _ENGINE_CACHE_LOCK:
        stale = [key for key in _ENGINE_CACHE if key != keep_key]
        for key in stale:
            _ENGINE_CACHE.pop(key, None)
    if stale:
        gc.collect()


def get_paddle_engine_impl(settings: AppSettings, *, deps: dict[str, Any]) -> Any:
    """Lazily create and reuse one active PaddleOCR 3.x general OCR pipeline."""
    _paddle_language = deps["_paddle_language"]
    resolve_paddle_device = deps["resolve_paddle_device"]
    _ENGINE_CACHE = deps["_ENGINE_CACHE"]
    _ENGINE_CACHE_LOCK = deps["_ENGINE_CACHE_LOCK"]
    clear_paddle_engine_cache = deps["clear_paddle_engine_cache"]
    os = deps["os"]
    language = _paddle_language(settings)
    orientation = bool(settings.paddle_use_textline_orientation)
    device = resolve_paddle_device()
    key = (language, device, settings.paddle_ocr_version, orientation)
    with _ENGINE_CACHE_LOCK:
        cached = _ENGINE_CACHE.get(key)
    if cached is not None:
        return cached
    # Layout analysis and full OCR use separate Paddle pipelines. Once formal
    # OCR starts, the detection-only model is no longer needed and may otherwise
    # pin a second large CPU/GPU allocation for the rest of the session.
    from ..layout.detection import clear_text_detection_cache
    clear_text_detection_cache()
    # Avoid the PaddlePaddle 3.3.x CPU PIR/oneDNN incompatibility also for
    # ordinary OCR, not only the separate layout detector.
    os.environ["FLAGS_enable_pir_api"] = "0"
    from ..runtime.windows_gpu import configure_windows_nvidia_dlls
    configure_windows_nvidia_dlls()
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError(
            "尚未安装 PaddleOCR。请运行当前平台的 OCR 安装脚本，或在受支持平台执行：uv sync --extra ocr-cpu"
        ) from exc
    try:
        kwargs = dict(
            lang=language,
            ocr_version=settings.paddle_ocr_version,
            device=device,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=orientation,
            enable_mkldnn=False,
        )
        try:
            engine = PaddleOCR(**kwargs)
        except TypeError:
            # Compatibility with older PaddleOCR 3.x builds that do not expose
            # enable_mkldnn on PaddleOCR itself.
            kwargs.pop("enable_mkldnn", None)
            engine = PaddleOCR(**kwargs)
    except Exception as exc:
        raise RuntimeError(
            f"PaddleOCR 初始化失败（语言={language}，设备={device}，"
            f"版本={settings.paddle_ocr_version}）：{exc}"
        ) from exc
    # Only one configuration needs to remain strongly referenced by the cache.
    # An older engine that is still in use elsewhere stays alive through that
    # caller's local reference and is collected only after the call finishes.
    clear_paddle_engine_cache(keep_key=key)
    with _ENGINE_CACHE_LOCK:
        existing = _ENGINE_CACHE.get(key)
        if existing is not None:
            return existing
        _ENGINE_CACHE[key] = engine
    return engine


def run_paddle_band_impl(band: Image.Image, settings: AppSettings, engine: Any | None = None, *, deps: dict[str, Any]) -> list[OCRRecord]:
    get_paddle_engine = deps["get_paddle_engine"]
    prepare_ocr_band = deps["prepare_ocr_band"]
    np = deps["np"]
    _RAW_OCR_THRESHOLD = deps["_RAW_OCR_THRESHOLD"]
    extract_ocr_records = deps["extract_ocr_records"]
    OCRRecord = deps["OCRRecord"]
    engine = engine or get_paddle_engine(settings)
    prepared, input_scale = prepare_ocr_band(
        band,
        max_long_side=getattr(settings, "paddle_max_input_side", 2800),
        mode=getattr(settings, "paddle_preprocessing", "original"),
    )
    try:
        results = list(engine.predict(
            np.asarray(prepared),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=bool(settings.paddle_use_textline_orientation),
            # Keep low-confidence fragments in the raw cache. Syllabified bold
            # headwords are sometimes harder to recognize than the following
            # POS/definition; candidate confidence is evaluated after same-line
            # fragments have been merged.
            text_rec_score_thresh=_RAW_OCR_THRESHOLD,
        ))
    except Exception as exc:
        raise RuntimeError(f"PaddleOCR 推理失败：{exc}") from exc
    if not results:
        return []
    records = extract_ocr_records(results[0])
    if input_scale == 1.0:
        return records
    inverse = 1.0 / input_scale
    return [
        OCRRecord(row.text, row.confidence, tuple(round(value * inverse) for value in row.box))
        for row in records
    ]


# OCR-channel engine ownership: separate cache, shared lifecycle domain.
def clear_cached_engines(
    *,
    keep_key: tuple[str, str, str, bool] | None = None,
    cache, lock, gc_module,
) -> None:
    """Drop channel-owned Paddle engines that are no longer active.

    Local references held by in-flight OCR calls remain valid. Keeping only one
    strongly cached configuration preserves the mature runner's memory behavior
    when users switch language/model/device settings.
    """

    with lock:
        stale = [key for key in cache if key != keep_key]
        for key in stale:
            cache.pop(key, None)
    if stale:
        gc_module.collect()

def create_paddle_engine_impl(
    settings: Any, *, paddle_language_fn, resolve_inference_policy_fn,
    constructor_variants_fn, cache, cache_lock, clear_cache_fn,
) -> Any:
    language = paddle_language_fn(settings)
    orientation = bool(getattr(settings, "paddle_use_textline_orientation", False))
    policy = resolve_inference_policy_fn()
    device = policy.device
    version = str(getattr(settings, "paddle_ocr_version", "PP-OCRv5") or "PP-OCRv5")
    key = (language, device, version, orientation, policy.mkldnn, policy.cpu_threads)
    with cache_lock:
        existing = cache.get(key)
        if existing is not None:
            return existing

    # Preserve the mature runner's process bootstrap before constructing a new
    # PaddleOCR pipeline. TextDetection and general OCR keep separate caches;
    # dropping the former avoids retaining two heavyweight Paddle pipelines.
    from ..layout.detection import clear_text_detection_cache
    clear_text_detection_cache()

    # Paddle 3.x may otherwise re-enable the PIR path after another pipeline has
    # run in the same process. Windows pip-wheel CUDA DLLs also need their
    # directories registered before importing PaddleOCR.
    import os
    os.environ["FLAGS_enable_pir_api"] = "0"
    from ..runtime.windows_gpu import configure_windows_nvidia_dlls
    configure_windows_nvidia_dlls()

    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise RuntimeError(
            "尚未安装 PaddleOCR。请运行当前平台的 OCR 安装脚本，或在受支持平台执行："
            "uv sync --extra ocr-cpu"
        ) from exc
    kwargs = dict(
        lang=language,
        ocr_version=version,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=orientation,
    )
    last_exc: Exception | None = None
    engine = None
    for candidate in constructor_variants_fn(kwargs, policy):
        try:
            engine = PaddleOCR(**candidate)
            break
        except TypeError as exc:
            # Older builds may lack acceleration tuning arguments. Preserve
            # the selected device instead of silently defaulting to GPU.
            last_exc = exc
            legacy = {k: v for k, v in candidate.items()
                      if k not in {"enable_mkldnn", "cpu_threads"}}
            if legacy == candidate:
                continue
            try:
                engine = PaddleOCR(**legacy)
                break
            except Exception as retry_exc:
                last_exc = retry_exc
        except Exception as exc:
            last_exc = exc
            # When Auto oneDNN fails, the next candidate disables it.
            continue
    if engine is None:
        raise RuntimeError(
            f"PaddleOCR 初始化失败（语言={language}，设备={device}，版本={version}）：{last_exc}"
        ) from last_exc

    from ..quality.inference_monitor import record_model_event
    record_model_event("PaddleOCR", policy.device, policy.mkldnn, policy.cpu_threads)

    clear_cache_fn(keep_key=key)
    with cache_lock:
        existing = cache.get(key)
        if existing is not None:
            return existing
        cache[key] = engine
    return engine
