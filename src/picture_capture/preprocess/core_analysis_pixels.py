from __future__ import annotations

"""Processing-core image analysis resizing and local adaptive-ink primitives.

Core wrappers supply live pixel normalization, Pillow and NumPy operations.
No page state, layout class, persistence schema or source image is relocated.
"""

from collections.abc import Callable
from typing import Any
import numpy as np
from PIL import Image, ImageFilter


def analysis_image(
    image: Image.Image,
    max_width: int,
    *,
    normalize_rgb_fn: Callable[[Image.Image], Image.Image],
    image_cls: Any = Image,
) -> tuple[Image.Image, float]:
    source = normalize_rgb_fn(image)
    if source.width <= max_width:
        return source.copy(), 1.0
    scale = max_width / source.width
    return source.resize((max_width, max(1, round(source.height * scale))), image_cls.Resampling.LANCZOS), scale


def adaptive_dark_mask(
    gray_image: Image.Image,
    block_size: int,
    c_value: int,
    *,
    np_module: Any = np,
    image_filter: Any = ImageFilter,
) -> np.ndarray:
    """Create an adaptive dark-ink mask without requiring OpenCV."""
    block_size = max(3, int(block_size))
    if block_size % 2 == 0:
        block_size += 1
    radius = max(1, block_size // 2)
    gray = np_module.asarray(gray_image, dtype=np_module.int16)
    local_mean = np_module.asarray(gray_image.filter(image_filter.BoxBlur(radius)), dtype=np_module.int16)
    return gray < (local_mean - max(0, int(c_value)))
