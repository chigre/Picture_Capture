"""Noise-aware contiguous left whitespace of an unlined row's original crop.

This intentionally affects only the export filter's *measurement*. Never
despeckle, trim or rewrite the output pixels / original dictionary scans.
"""
from __future__ import annotations

from collections import deque
import math

import numpy as np
from PIL import Image


def _has_meaningful_component(
    ink: np.ndarray, seen: np.ndarray, y: int, x: int,
    *, min_area: int, min_span: int,
) -> bool:
    """Eight-connected foreground component; ignore only tiny isolated spots."""
    height, width = ink.shape
    queue = deque([(y, x)])
    seen[y, x] = True
    size = 0
    min_x = max_x = x
    min_y = max_y = y
    while queue:
        cy, cx = queue.popleft()
        size += 1
        min_x, max_x = min(min_x, cx), max(max_x, cx)
        min_y, max_y = min(min_y, cy), max(max_y, cy)
        # Thin long text strokes and horizontal dashes can be legitimate even
        # when their area is small. Dense short text also counts as foreground.
        if (size >= min_area or max_x - min_x + 1 >= min_span
                or max_y - min_y + 1 >= min_span):
            return True
        for yy in range(max(0, cy - 1), min(height, cy + 2)):
            for xx in range(max(0, cx - 1), min(width, cx + 2)):
                if ink[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    queue.append((yy, xx))
    return False


def noise_tolerant_left_white_percent(image: Image.Image) -> float:
    """Measure first meaningful ink column, treating mild isolated dust as blank.

    Background-relative threshold retains aged/tinted paper compatibility.
    A preliminary 5%-height column vote suppresses sparse hot pixels; an
    8-connected area/extent vote additionally ignores clustered 2–3px dust.
    Low-height (under 12px) crops use the original column vote because small
    print cannot safely be distinguished from dust at that scale.
    """
    gray_image = image.convert("L")
    try:
        pixels = np.asarray(gray_image, dtype=np.uint8)
    finally:
        gray_image.close()
    if pixels.ndim != 2 or pixels.size == 0 or pixels.shape[1] == 0:
        return 0.0
    height, width = pixels.shape
    background = float(np.percentile(pixels, 90.0))
    cutoff = int(max(0.0, min(235.0, background - 18.0)))
    ink = pixels <= cutoff
    minimum_column_ink = max(2, int(math.ceil(height * 0.05)))
    candidate_columns = np.flatnonzero(np.count_nonzero(ink, axis=0) >= minimum_column_ink)
    if not candidate_columns.size:
        return 100.0
    if height < 12:
        return 100.0 * int(candidate_columns[0]) / width

    minimum_area = max(12, int(math.ceil(height * 0.15)))
    minimum_span = max(6, min(12, int(math.ceil(height * 0.25))))
    seen = np.zeros((height, width), dtype=bool)
    for x in candidate_columns:
        for y in np.flatnonzero(ink[:, x]):
            if not seen[y, x] and _has_meaningful_component(
                ink, seen, int(y), int(x), min_area=minimum_area,
                min_span=minimum_span,
            ):
                return 100.0 * int(x) / width
    return 100.0
