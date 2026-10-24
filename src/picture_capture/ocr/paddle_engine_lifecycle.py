"""Paddle engine lifecycle, single active cache, runtime bootstrap and GPU safety.

No PaddleOCR import occurs until create_paddle_engine_impl is called.  Root
ocr_channel retains public cache and monkeypatch hooks and supplies them live.
"""
from __future__ import annotations

from typing import Any

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
