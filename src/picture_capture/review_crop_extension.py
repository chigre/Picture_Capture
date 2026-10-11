"""Source-space crop extension for the fixed proofreading word preview.

The upper Y is exactly the same as the inline ordinary word slice. Extending
only the bottom avoids showing preceding entries when the active row changes.
"""
from __future__ import annotations

from math import isfinite


def parse_review_crop_multiplier(value: object) -> float:
    """Accept a finite 1–10x vertical factor; 2.5 is the project default."""
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("切片高度倍数必须是 1–10 之间的数字") from exc
    if not isfinite(result) or not (1.0 <= result <= 10.0):
        raise ValueError("切片高度倍数必须在 1–10 之间")
    return result


def extended_review_crop_box(
    ordinary_box: tuple[int, int, int, int],
    image_height: int,
    multiplier: float,
) -> tuple[int, int, int, int]:
    """Grow downward, preserving source X and the exact ordinary crop top Y."""
    factor = parse_review_crop_multiplier(multiplier)
    left, top, right, bottom = (int(n) for n in ordinary_box)
    ordinary_height = max(1, bottom - top)
    expanded_bottom = top + max(1, round(ordinary_height * factor))
    return left, top, right, min(int(image_height), expanded_bottom)
