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


def resize_fixed_review_preview(
    size: tuple[int, int],
    previous_zoom: float | None,
    current_zoom: float,
) -> tuple[int, int]:
    """Scale pinned-preview dimensions when the shared review zoom changes.

    The top preview remains a fixed-sized frame while navigating headwords,
    but it must respond to the same percentage/auto zoom as ordinary and
    oversized inline crops. Scaling the prior frame (not the newly selected
    row height) preserves its fixed dimensions across word changes.
    """
    width, height = (max(1, int(n)) for n in size)
    current = float(current_zoom)
    if not isfinite(current) or current <= 0:
        raise ValueError("Review zoom must be finite and positive")
    if previous_zoom is None:
        return width, height
    previous = float(previous_zoom)
    if not isfinite(previous) or previous <= 0:
        raise ValueError("Previous review zoom must be finite and positive")
    ratio = current / previous
    return max(1, round(width * ratio)), max(1, round(height * ratio))
