"""Placement of separate REF OCR text labels in displayed canvas pixels."""
from __future__ import annotations

from math import ceil
from unicodedata import east_asian_width


def estimated_text_width(text: str, font_size: int) -> int:
    """Conservative glyph estimate for layout without a Tcl interpreter."""
    size = max(6, int(font_size))
    return max(1, max((
        round(sum(size if east_asian_width(ch) in "WF" else
                  size * (0.56 if ch != " " else 0.30)
                  for ch in line))
        for line in (str(text or "").splitlines() or [""])
    ), default=1))


def ref_text_label_rect(
    box: tuple[int, int, int, int],
    page_size: tuple[int, int],
    *,
    text: str,
    scale: float,
    font_size: int,
    gap: int = 6,
    padding: int = 4,
) -> tuple[int, int, int, int]:
    """Calculate label bounds (x,y,w,h); prefer right, then left, then below.

    Physical REF coordinates and text label geometry stay independent. Always
    keep label fully inside the displayed page; never mutate stored REF boxes.
    """
    x, y, w, h = box
    factor = max(0.01, float(scale))
    page_w = max(1, round(page_size[0] * factor))
    page_h = max(1, round(page_size[1] * factor))
    px = max(0, min(page_w - 1, round(x * factor)))
    py = max(0, min(page_h - 1, round(y * factor)))
    pw = max(1, round(w * factor))
    ph = max(1, round(h * factor))
    gap = max(0, int(gap))
    pad = max(0, int(padding))
    text_width = estimated_text_width(text, font_size)
    desired_w = max(30, min(text_width + 2 * pad + 4, max(45, round(page_w * 0.42))))
    right_space = max(0, page_w - (px + pw + gap))
    left_space = max(0, px - gap)
    if right_space >= desired_w or (right_space >= 40 and right_space >= left_space):
        lx = px + pw + gap
        available = right_space
    elif left_space >= 40:
        available = left_space
        lx = max(0, px - gap - min(desired_w, available))
    elif right_space >= 20:
        lx = px + pw + gap
        available = right_space
    else:
        # REF extends across the page: below/above is the only safe fallback.
        lx = px
        available = max(1, page_w - lx)
    lw = max(1, min(desired_w, available))
    usable = max(1, lw - 2 * pad)
    lines = sum(max(1, ceil(estimated_text_width(line, font_size) / usable))
                for line in (str(text or "").splitlines() or [""]))
    lh = min(page_h, max(12, round(lines * font_size * 1.55) + pad * 2))
    ly = py if right_space >= 20 or left_space >= 40 else py + ph + gap
    if ly + lh > page_h:
        ly = max(0, py - lh - gap) if py >= lh + gap else page_h - lh
    return min(lx, page_w - lw), max(0, ly), lw, lh
