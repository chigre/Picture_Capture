"""Engine-input OCR preprocessing; old facade injects live pixel providers."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import Image
    import numpy as np
    from ..models import AppSettings

def paddle_language(settings: AppSettings) -> str:
    """Preserve the mature core's Paddle language/model resolution exactly."""

    configured = str(getattr(settings, "paddle_language", "") or "").strip()
    if configured:
        return configured
    mapping = {
        "eng": "en",
        "ita": "it",
        "spa": "es",
        "fra": "fr",
        "por": "pt",
        "deu": "de",
        "chi_sim": "ch",
        "chi_tra": "chinese_cht",
    }
    # Tesseract accepts composite packs such as spa+eng; Paddle expects one
    # language/model family. Prefer the first recognized component. A separate
    # tesseract_language setting must never alter Paddle model selection.
    raw_language = str(getattr(settings, "ocr_language", "") or "").strip()
    parts = [part.strip() for part in raw_language.split("+") if part.strip()]
    for part in parts:
        if part in mapping:
            return mapping[part]
    return mapping.get(raw_language, raw_language)

def otsu_threshold(gray: np_module.ndarray, *, np_module) -> int:
    """Return the same conservative Otsu threshold used by the mature runner."""

    if gray.size == 0:
        return 180
    hist = np_module.bincount(gray.astype(np_module.uint8).ravel(), minlength=256).astype(np_module.float64)
    total = float(gray.size)
    weighted_total = float(np_module.dot(np_module.arange(256, dtype=np_module.float64), hist))
    background_weight = 0.0
    background_sum = 0.0
    best_variance = -1.0
    best_threshold = 180
    for threshold in range(256):
        background_weight += hist[threshold]
        if background_weight <= 0:
            continue
        foreground_weight = total - background_weight
        if foreground_weight <= 0:
            break
        background_sum += threshold * hist[threshold]
        background_mean = background_sum / background_weight
        foreground_mean = (weighted_total - background_sum) / foreground_weight
        between = background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
        if between > best_variance:
            best_variance = between
            best_threshold = threshold
    return int(min(220, max(80, best_threshold)))

def prepare_ocr_input_impl(
    image: Image.Image,
    *,
    max_long_side: int = 2800,
    mode: str = "original",
    normalize_rgb_fn,
    image_ops,
    image_cls,
    np_module,
    otsu_fn,
) -> tuple[Image.Image, float]:
    """Prepare a Paddle crop and return source-to-input coordinate scale.

    This is the engine-level preprocessing formerly reached indirectly through
    ``paddle_headwords_core.run_paddle_band``. Keeping it in the shared channel
    preserves marker-only OCR behavior without importing the mature parser.
    """

    source = normalize_rgb_fn(image)
    normalized_mode = str(mode or "original").strip().lower()
    if normalized_mode in {"grayscale", "gray", "auto_contrast", "binary"}:
        gray = image_ops.grayscale(source)
        if normalized_mode in {"auto_contrast", "binary"}:
            gray = image_ops.autocontrast(gray)
        if normalized_mode == "binary":
            array = np_module.asarray(gray)
            threshold = otsu_fn(array)
            gray = image_cls.fromarray(
                np_module.where(array > threshold, 255, 0).astype(np_module.uint8),
                mode="L",
            )
        source = gray.convert("RGB")
    limit = max(256, int(max_long_side or 2800))
    scale = min(1.0, limit / max(source.size))
    if scale < 1.0:
        source = source.resize(
            (
                max(1, round(source.width * scale)),
                max(1, round(source.height * scale)),
            ),
            image_cls.Resampling.LANCZOS,
        )
    return source, scale
