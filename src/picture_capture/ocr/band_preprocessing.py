from __future__ import annotations

"""Source-safe Paddle OCR band input preparation and page-local Otsu threshold.

The Paddle historical core supplies current normalization and threshold hooks,
preserving existing binary-image and scale/coordinate behavior.
"""

from collections.abc import Callable
from typing import Any
import numpy as np
from PIL import Image, ImageOps


def prepare_ocr_band(
    band: Image.Image, *, max_long_side: int = 2800, mode: str = "original",
    normalize_rgb_fn: Callable[[Image.Image], Image.Image],
    otsu_fn: Callable[[np.ndarray], int],
    image_ops: Any = ImageOps,
    image_cls: Any = Image,
    np_module: Any = np,
) -> tuple[Image.Image, float]:
    """Return a temporary OCR image and source-to-input coordinate scale."""
    source = normalize_rgb_fn(band)
    mode = str(mode or "original").strip().lower()
    if mode in {"grayscale", "gray", "auto_contrast", "binary"}:
        gray = image_ops.grayscale(source)
        if mode in {"auto_contrast", "binary"}:
            gray = image_ops.autocontrast(gray)
        if mode == "binary":
            array = np_module.asarray(gray)
            threshold = otsu_fn(array)
            gray = image_cls.fromarray(np_module.where(array > threshold, 255, 0).astype(np_module.uint8), mode="L")
        source = gray.convert("RGB")
    limit = max(256, int(max_long_side or 2800))
    scale = min(1.0, limit / max(source.size))
    if scale < 1.0:
        source = source.resize(
            (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
            image_cls.Resampling.LANCZOS,
        )
    return source, scale


def otsu_threshold(gray: np.ndarray, *, np_module: Any = np) -> int:
    """Return a conservative page-local black/white threshold.

    Dictionary scans are usually high contrast, but paper tone and antialiasing
    vary by source. Otsu keeps the separator refinement independent of a
    project-specific hardcoded gray value. The clamp prevents an unusually
    bright or dark crop from turning most of the paper into ink.
    """
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
