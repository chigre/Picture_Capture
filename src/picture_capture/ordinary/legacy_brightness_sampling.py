"""Exact legacy VB separator brightness sampling primitives.

Preserve inclusive rows, bounds and Python round semantics. NumPy is supplied
by the historical processing core at call time.
"""
from __future__ import annotations
from typing import Any


def legacy_is_point(
    rgb_sum: Any,
    x: int,
    y: int,
    area_x: int,
    area_y: int,
    max_brightness_percent: float,
    *,
    direction: int = 1,
    np_module: Any,
) -> bool:
    """Faithful full-resolution port of VB.NET IsPoint().

    VB sampled area_x pixels to the reading-right of the anchor and rows from
    -area_y/2 through +area_y/2. Its denominator intentionally remained
    area_x * area_y even though the inclusive row loop can contain one extra
    row. Keeping that detail preserves the old 90% gate.
    """
    height, width = rgb_sum.shape[:2]
    area_x = max(1, int(area_x))
    area_y = max(1, int(area_y))
    direction = 1 if int(direction) >= 0 else -1
    half = max(0, round(area_y * 0.5))
    y0 = int(y) - half
    y1 = int(y) + half
    if y0 < 0 or y1 >= height:
        return False

    xs = int(x) + direction * np_module.arange(1, area_x + 1, dtype=np_module.int64)
    if xs.size == 0 or int(xs.min()) < 0 or int(xs.max()) >= width:
        return False
    region = rgb_sum[y0:y1 + 1, xs]
    if region.size == 0:
        return False
    denominator = float(area_x * area_y * 255 * 3)
    brightness_percent = round(float(region.astype(np_module.float64).sum()) / denominator * 100.0)
    return brightness_percent <= float(max_brightness_percent)


def legacy_row_brightness_1000(
    rgb_sum: Any,
    y: int,
    x: int,
    width: int,
    *,
    direction: int = 1,
    np_module: Any,
) -> int | None:
    """Return the VB row-brightness score on its original 0..1000 scale."""
    height, image_width = rgb_sum.shape[:2]
    if not (0 <= int(y) < height):
        return None
    width = max(1, int(width))
    direction = 1 if int(direction) >= 0 else -1
    xs = int(x) + direction * np_module.arange(1, width + 1, dtype=np_module.int64)
    if xs.size == 0 or int(xs.min()) < 0 or int(xs.max()) >= image_width:
        return None
    total = float(rgb_sum[int(y), xs].astype(np_module.float64).sum())
    return int(round(total / float(765 * width) * 1000.0))
