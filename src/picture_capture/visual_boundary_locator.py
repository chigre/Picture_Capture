"""OCR-free, line-preserving separator locator for independently found heads.

Physical character ink, not a guessed fraction of font height, selects the Y
between the preceding text line and a new word. This is intentionally a pure
local helper: it never asserts that a word is a dictionary entry.
"""
from __future__ import annotations

import numpy as np


def safe_gap_above(
    gray: np.ndarray,
    head_top: int,
    typical_line_height: float,
    *,
    threshold: int = 170,
) -> int:
    """Return a safe local Y above head_top for a column-width grayscale image.

    Work in *canonical reading coordinates* (y increases along text flow).
    Search <=0.55 line-height above the new head and exclude any candidate
    touching dark ink in a 3-row neighborhood. When no full-width white gap is
    present (e.g. a photograph overlaps the margin), fall back to a small,
    bounded offset rather than relocating the boundary across another line.
    """
    if gray.ndim != 2:
        raise ValueError("Expected two-dimensional grayscale input")
    height, width = gray.shape
    if height == 0 or width == 0:
        return max(0, int(head_top) - 2)
    head = max(0, min(height - 1, int(head_top)))
    pitch = max(6.0, float(typical_line_height))
    low = max(0, head - max(4, round(pitch * 0.55)))
    high = max(low, head - 2)
    if high <= low:
        return max(0, head - 2)

    # Count dark pixels across the actual *line width*, so a short pale OCR
    # fragment cannot be mistaken for a totally blank separator row.
    black_fraction = np.mean(gray[low:head, :] < int(threshold), axis=1)
    desired = max(low, min(high, round(head - pitch * 0.12)))
    allowable = max(0.006, 1.0 / width)
    choices = [
        y for y in range(low + 1, high + 1)
        if max(black_fraction[y - low - 1:y - low + 2]) <= allowable
    ]
    if choices:
        return min(choices, key=lambda y: (abs(y - desired), -y))
    return max(low, desired)
