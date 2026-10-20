"""Strict, page-local half-gutter X band for explicit fast PDIC Y refinement.

Widths are the saved Profile's fixed physical column widths, not an
estimated page layout. Neighbouring text columns are hard exclusion bounds.
This helper does not touch source pixels or persist any geometry.
"""
from __future__ import annotations


def fixed_half_gutter_band(
    geometry, column: int, canonical_y: int, page_width: int,
    column_width: int, gutter: int,
) -> tuple[int, int]:
    """Return [left, right) including at most half the gutter on either side.

    The band covers the physical text column first; it never enters the body
    of its immediate left or right neighbour even with corrupt/uneven offsets.
    """
    count = len(geometry.column_widths)
    if not 0 <= column < count:
        raise ValueError("精修栏序号无效")

    x = round(geometry.x_at(column, canonical_y))
    body_width = max(1, min(int(geometry.column_widths[column]), int(column_width)))
    half_left = max(0, int(gutter)) // 2
    half_right = (max(0, int(gutter)) + 1) // 2

    left = max(0, x - half_left)
    right = min(int(page_width), x + body_width + half_right)

    if column > 0:
        prev_x = round(geometry.x_at(column - 1, canonical_y))
        prev_width = max(
            1, min(int(geometry.column_widths[column - 1]), int(column_width))
        )
        left = max(left, prev_x + prev_width)
    if column + 1 < count:
        next_x = round(geometry.x_at(column + 1, canonical_y))
        right = min(right, next_x)

    # On a badly configured page, fail closed rather than inspect another
    # column or silently fall back to full-page detection.
    if not 0 <= left < right <= int(page_width):
        raise ValueError("固定栏宽/栏间距不适用于当前页，拒绝跨栏精修")
    return left, right
