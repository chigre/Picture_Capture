from __future__ import annotations

import gc
import os
from typing import Any

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .runtime_environment import resolve_paddle_device


_DOC_PREPROCESSOR_CACHE: dict[str, Any] = {}


def clear_document_unwarping_cache() -> None:
    if _DOC_PREPROCESSOR_CACHE:
        _DOC_PREPROCESSOR_CACHE.clear()
        gc.collect()


def _get_doc_preprocessor() -> Any:
    """Return the PaddleOCR/PaddleX document preprocessor with UVDoc enabled.

    Picture Capture already ships PaddleOCR/PaddleX in its OCR profiles.  The
    official doc_preprocessor pipeline uses UVDoc for its DocUnwarping module,
    so no second deep-learning stack is needed here.
    """
    device = resolve_paddle_device()
    key = f"{device}|uvdoc|nomkldnn"
    cached = _DOC_PREPROCESSOR_CACHE.get(key)
    if cached is not None:
        return cached

    # Match the compatibility guard used by detection-only layout analysis.
    # Some Paddle 3.3 CPU environments can otherwise enter a PIR/oneDNN path
    # that is unstable for inference pipelines.
    os.environ["FLAGS_enable_pir_api"] = "0"
    from .windows_gpu import configure_windows_nvidia_dlls
    configure_windows_nvidia_dlls()

    try:
        from paddleocr import DocPreprocessor
    except ImportError as exc:
        raise RuntimeError(
            "当前环境未安装支持文档展平的 PaddleOCR。请先通过环境中心安装 OCR 组件。"
        ) from exc

    base = {
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": True,
        "device": device,
        "enable_mkldnn": False,
    }
    attempts = [
        base,
        {k: v for k, v in base.items() if k != "enable_mkldnn"},
        {k: v for k, v in base.items() if k not in {"enable_mkldnn", "device"}},
        {},
    ]
    last_exc: Exception | None = None
    seen: set[tuple[tuple[str, str], ...]] = set()
    for kwargs in attempts:
        marker = tuple(sorted((str(k), repr(v)) for k, v in kwargs.items()))
        if marker in seen:
            continue
        seen.add(marker)
        try:
            pipeline = DocPreprocessor(**kwargs)
            _DOC_PREPROCESSOR_CACHE.clear()
            _DOC_PREPROCESSOR_CACHE[key] = pipeline
            return pipeline
        except TypeError as exc:
            last_exc = exc
            continue
        except Exception as exc:
            last_exc = exc
            break
    raise RuntimeError(f"Paddle UVDoc 文档展平模型初始化失败：{last_exc}") from last_exc


def _result_output_image(result: Any) -> Image.Image:
    """Extract the unwarped image from PaddleX result objects across 3.x builds."""
    try:
        visual = getattr(result, "img", None)
        if callable(visual):
            visual = visual()
        if isinstance(visual, dict):
            candidate = visual.get("preprocessed_img")
            if isinstance(candidate, Image.Image):
                return normalize_page_rgb(candidate)
            if isinstance(candidate, np.ndarray):
                array = np.asarray(candidate)
                if array.ndim == 3 and array.shape[2] >= 3:
                    return Image.fromarray(
                        np.clip(array[..., :3], 0, 255).astype(np.uint8),
                        mode="RGB",
                    )
    except Exception:
        pass

    candidate = None
    try:
        candidate = result["output_img"]
    except Exception:
        if isinstance(result, dict):
            candidate = result.get("output_img")

    if candidate is None:
        payload = getattr(result, "json", None)
        if callable(payload):
            payload = payload()
        if isinstance(payload, dict):
            nested = payload.get("res")
            if isinstance(nested, dict):
                candidate = nested.get("output_img")
            if candidate is None:
                candidate = payload.get("output_img")

    if isinstance(candidate, Image.Image):
        return normalize_page_rgb(candidate)
    if not isinstance(candidate, np.ndarray):
        raise RuntimeError("Paddle UVDoc 未返回可用的展平图像")

    array = np.asarray(candidate)
    if array.ndim == 2:
        return Image.fromarray(
            np.clip(array, 0, 255).astype(np.uint8), mode="L"
        ).convert("RGB")
    if array.ndim != 3 or array.shape[2] < 3:
        raise RuntimeError(f"Paddle UVDoc 返回了异常图像形状：{array.shape}")

    # PaddleX inference results use OpenCV/BGR image semantics internally.
    rgb = np.clip(array[..., :3][..., ::-1], 0, 255).astype(np.uint8)
    return Image.fromarray(rgb, mode="RGB")


def unwarp_document_image(image: Image.Image) -> Image.Image:
    """Run PaddleOCR's official UVDoc-backed document image unwarping."""
    source = normalize_page_rgb(image)
    pipeline = _get_doc_preprocessor()
    os.environ["FLAGS_enable_pir_api"] = "0"
    array = np.asarray(source)
    try:
        results = list(
            pipeline.predict(
                array,
                use_doc_orientation_classify=False,
                use_doc_unwarping=True,
            )
        )
    except TypeError:
        results = list(pipeline.predict(array))
    if not results:
        raise RuntimeError("Paddle UVDoc 文档展平没有返回结果")
    output = _result_output_image(results[0])
    if output.size != source.size:
        # Keep the preprocessing coordinate contract stable. UVDoc commonly
        # preserves dimensions, but normalize any backend/version differences.
        output = output.resize(source.size, Image.Resampling.BICUBIC)
    return output
