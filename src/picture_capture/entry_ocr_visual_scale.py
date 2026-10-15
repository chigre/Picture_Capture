"""Local OCR-only visual height evidence for an existing marker.

A manually placed marker can belong to a large display head even if its
persisted role/scale is regular or unknown. Probe the *image* in a small
leading-glyph lane, using the established ordinary-large-head geometry
detector, without modifying Layout roles, separator coordinates or PDIC.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from .models import AppSettings, Entry
from .ordinary_large_head_evidence import _candidate_boxes, _uses_cjk_large_heads
from .ordinary_visual import _otsu


def visual_oversized_head_height(
    canonical_image: Image.Image,
    entry: Entry,
    geometry: Any,
    settings: AppSettings,
    *,
    line_height: float,
) -> int:
    """Observed glyph height below the marker, or zero when unconvincing.

    Use only CJK horizontal dictionary pages. No Layout role is consulted.
    Require a near-front glyph starting on this marker row, at least 1.65
    ordinary lines high. A narrow probe cannot accidentally use ink from a
    whole definition or the opposite column to enlarge this entry's crop.
    """
    if (
        str(getattr(settings, "layout_writing_mode", "")) != "horizontal-tb"
        or not _uses_cjk_large_heads(settings)
    ):
        return 0
    reference = max(1.0, float(line_height))
    try:
        marker_u, marker_v = geometry.source_to_canonical(
            int(entry.x), int(entry.y),
        )
        starts = list(geometry.column_starts)
        widths = list(geometry.column_widths)
        column = min(
            range(len(starts)),
            key=lambda i: abs(int(marker_u) - int(geometry.x_at(i, int(marker_v)))),
        )
        column_left = int(geometry.x_at(column, int(marker_v)))
        column_right = column_left + int(widths[column])
    except (AttributeError, IndexError, ValueError, TypeError):
        return 0

    left = max(0, round(column_left - reference * 0.20))
    right = min(canonical_image.width, column_right,
                round(column_left + reference * 4.25))
    top = max(0, round(marker_v - reference * 0.36))
    bottom = min(canonical_image.height, round(marker_v + reference * 3.65))
    if right - left < reference * 0.75 or bottom - top < reference * 1.65:
        return 0

    gray = np.asarray(
        canonical_image.crop((left, top, right, bottom)).convert("L"),
        dtype=np.uint8,
    )
    if gray.size == 0 or int(gray.min()) >= 245:
        return 0
    ink = gray <= min(220, int(_otsu(gray)))
    boxes = _candidate_boxes(ink, reference)
    observed: list[tuple[float, int]] = []
    for x0, y0, _x1, y1 in boxes:
        absolute_x = left + int(x0)
        absolute_top = top + int(y0)
        absolute_bottom = top + int(y1)
        actual_height = absolute_bottom - absolute_top
        # Never promote a glyph that starts well below the current marker or
        # belongs to the following physical line in the same column.
        if not (marker_v - reference * 0.35 <= absolute_top
                <= marker_v + reference * 0.38):
            continue
        if not (column_left - reference * 0.20 <= absolute_x
                <= column_left + reference * 2.00):
            continue
        if not (reference * 1.65 <= actual_height <= reference * 3.45):
            continue
        requested_height = int(round(absolute_bottom - marker_v))
        if requested_height >= reference * 1.65:
            observed.append((abs(absolute_top - marker_v), requested_height))
    return min(observed)[1] if observed else 0
