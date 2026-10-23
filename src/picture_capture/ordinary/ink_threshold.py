from __future__ import annotations

"""Ordinary-drawing foreground thresholding without core import cycles."""

from collections.abc import Callable
from typing import Any
import numpy as np
from PIL import Image, ImageFilter
from ..models import AppSettings


def otsu_threshold(gray: np.ndarray, *, np_module: Any = np) -> int:
    """Return a stable Otsu threshold for ordinary left-edge detection."""
    hist = np_module.bincount(gray.ravel(), minlength=256).astype(np_module.float64)
    total = float(hist.sum())
    if total <= 0:
        return 127
    probability = hist / total
    omega = np_module.cumsum(probability)
    means = np_module.cumsum(probability * np_module.arange(256, dtype=np_module.float64))
    global_mean = means[-1]
    denominator = omega * (1.0 - omega)
    score = np_module.zeros(256, dtype=np_module.float64)
    valid = denominator > 1e-12
    score[valid] = ((global_mean * omega[valid] - means[valid]) ** 2) / denominator[valid]
    return int(min(235, max(40, int(np_module.argmax(score)))))


def ink_mask(
    gray: np_module.ndarray,
    settings: AppSettings,
    *,
    otsu_fn: Callable[[np_module.ndarray], int] = otsu_threshold,
    np_module: Any = np,
    image_class: Any = Image,
    image_filter: Any = ImageFilter,
) -> np_module.ndarray:
    """Compatibility foreground mask for layout-analysis regressions.

    Restored VB ordinary drawing no longer uses this Otsu/adaptive path for its
    headword anchor or separator decision. Draw_Auto uses the fixed RGB-sum
    threshold directly on full-resolution source pixels, matching the VB code.
    """
    mode = str(getattr(settings, "analysis_threshold_mode", "auto") or "auto").strip().lower()
    if mode == "fixed":
        threshold = int(round(float(getattr(settings, "darkness_threshold", 600)) / 3.0))
        return gray < min(255, max(0, threshold))
    if mode == "adaptive":
        radius = max(3, round(min(gray.shape[:2]) * 0.008))
        local = np_module.asarray(
            image_class.fromarray(gray, mode="L").filter(image_filter.BoxBlur(radius=radius)),
            dtype=np_module.int16,
        )
        return gray.astype(np_module.int16) < (local - 10)
    return gray < otsu_fn(gray)

