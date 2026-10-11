"""Conservative, image-backed veto of CJK body-indent role contradictions.

An indent mode groups rows by a *measured anchor*, but an oversized glyph,
illustration fragment or mixed punctuation can anchor a line at the outer
lane although its real text begins in the inset body lane. Never promote
an entire such mode into entries without checking the actual ink start.

Only a column with MANY independently observable contradictions is repaired.
Isolated ambiguous rows and other indentation grammars keep old behavior.
Positive bracket/large-head evidence is applied *after* this veto and may
promote a genuinely confirmed head again.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from .models import AppSettings
from .page_understanding import uses_cjk_role_model


def _visible_first_x(
    gray: np.ndarray, column: Any, top: int, line: Any, reference: float,
) -> float | None:
    """Measure the first sustained ink column in this *physical row*."""
    y0 = top + int(getattr(line, "y0", 0))
    row_height = max(1, int(getattr(line, "y1", 0)) - int(getattr(line, "y0", 0)))
    sample_height = min(row_height, max(8, round(reference * 1.05)))
    y1 = min(gray.shape[0], y0 + sample_height)
    x0 = max(0, int(column.left) - max(2, round(reference * .20)))
    x1 = min(
        gray.shape[1], int(column.right),
        int(column.left) + max(110, round(reference * 5.0)),
    )
    if y0 < 0 or y1 <= y0 or x1 <= x0:
        return None
    ink = gray[y0:y1, x0:x1] < 170
    min_rows = max(3, round((y1 - y0) * .14))
    sustained = np.flatnonzero(ink.sum(axis=0) >= min_rows)
    if sustained.size == 0:
        return None
    return float(x0 + int(sustained[0]) - int(column.left))


def suppress_contradictory_cjk_body_lane_entries(
    image: Image.Image, settings: AppSettings, layout: Any,
) -> dict[str, int]:
    """Demote *only* batches of alleged entries visibly in the body lane.

    A page needs two well-separated repeated indent families. Per-column,
    at least six alleged entries and at least 20% of its candidates must
    independently start on the inset body side of the lane separator.
    This gate prevents one unusual valid lemma from changing a normal page.
    """
    stats = {"checked_columns": 0, "repaired_columns": 0, "demoted_rows": 0, "repaired_indices": []}
    if (
        not uses_cjk_role_model(settings)
        or str(getattr(layout, "indent_type", "")) != "body"
    ):
        return stats

    reference = max(8.0, float(getattr(layout, "ordinary_line_height", 1.0)))
    candidates: list[tuple[Any, list[Any], float]] = []
    for column_index, column in enumerate(list(getattr(layout, "columns", ()) or ())):
        lines = list(getattr(column, "lines", ()) or ())
        entries = [
            line for line in lines
            if str(getattr(line, "role", "") or "") == "entry"
        ]
        body = getattr(column, "body_mode", None)
        modes = list(getattr(column, "entry_modes", ()) or ())
        if body is None or len(lines) < 18 or len(entries) < 12 or not modes:
            continue
        # Use the outermost REPEATED entry family. A singleton printed
        # ornament must not define a column's presumed headword edge.
        peak = max(int(getattr(mode, "support", 0) or 0) for mode in modes)
        stable = [
            mode for mode in modes
            if int(getattr(mode, "support", 0) or 0)
            >= max(3, round(peak * .12))
        ]
        if not stable:
            continue
        entry_center = min(float(mode.center) for mode in stable)
        body_center = float(body.center)
        if body_center - entry_center < reference * .75:
            continue
        threshold = entry_center + (body_center - entry_center) * .55
        candidates.append((column_index, column, entries, threshold))
    if not candidates:
        return stats

    # This is the same canonical coordinate frame as layout columns/rows.
    canonical = layout.transform.canonical_image_for_analysis(image.convert("RGB"))
    try:
        gray = np.asarray(canonical.convert("L"), dtype=np.uint8)
        top = int(getattr(layout, "body_top", 0))
        for column_index, column, entries, threshold in candidates:
            stats["checked_columns"] += 1
            contradictions = []
            for line in entries:
                first = _visible_first_x(gray, column, top, line, reference)
                if first is not None and first > threshold:
                    contradictions.append(line)
            if len(contradictions) < max(6, round(len(entries) * .20)):
                continue
            for line in contradictions:
                line.role = "body"
            stats["repaired_columns"] += 1
            stats["repaired_indices"].append(column_index)
            stats["demoted_rows"] += len(contradictions)
    finally:
        canonical.close()
    return stats


__all__ = ["suppress_contradictory_cjk_body_lane_entries"]
