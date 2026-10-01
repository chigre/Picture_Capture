from __future__ import annotations

"""Local Y refinement for ordinary lines selected by final Layout roles.

Role assignment is authoritative.  This module never adds/removes/reclassifies
rows; it only moves the separator for an already-classified ``entry`` row to the
nearest real inter-line whitespace band.
"""

from typing import Any

import numpy as np
from PIL import Image

from .layout_detection import analysis_ink_mask


def _canonical_ink(image: Image.Image, understanding: Any) -> np.ndarray:
    """Return the same canonical ink domain used by dictionary page layout."""
    from . import dictionary_page_design as page_design

    settings = understanding.page_settings
    _source, canonical, _transform, effective = page_design._analysis_page(
        image,
        settings,
        int(getattr(understanding, "page_index", 0) or 0),
    )
    gray = np.asarray(canonical.convert("L"), dtype=np.uint8)
    return analysis_ink_mask(gray, effective)


def _smooth(values: np.ndarray) -> np.ndarray:
    if values.size < 3:
        return values.astype(float)
    kernel = np.asarray([0.25, 0.50, 0.25], dtype=float)
    return np.convolve(values.astype(float), kernel, mode="same")


def refine_entry_separator_y(
    ink: np.ndarray,
    *,
    column_left: int,
    column_right: int,
    body_top: int,
    body_bottom: int,
    line: Any,
    previous_line: Any | None,
    line_height: float,
) -> int:
    """Refine one entry row to the centre of the whitespace immediately above it."""
    height, width = ink.shape[:2]
    coarse = int(body_top) + int(getattr(line, "y0", 0) or 0)
    coarse = max(0, min(height - 1, coarse))
    ref = max(6.0, float(line_height or 0.0))

    x0 = max(0, min(width - 1, int(column_left)))
    x1 = max(x0 + 1, min(width, int(column_right)))
    if x1 - x0 < 4:
        return coarse

    lower = max(int(body_top), coarse - max(3, round(ref * 0.42)))
    if previous_line is not None:
        previous_bottom = int(body_top) + int(getattr(previous_line, "y1", 0) or 0)
        if previous_bottom < coarse:
            lower = max(lower, previous_bottom)
    upper = min(int(body_bottom), coarse + max(1, round(ref * 0.06)))
    upper = min(height, max(lower + 1, upper))
    if upper - lower < 2:
        return coarse

    # Ignore a tiny margin at each side so column rules/edge dirt cannot decide Y.
    margin = max(1, min(round((x1 - x0) * 0.025), round(ref * 0.35)))
    sx0 = min(x1 - 1, x0 + margin)
    sx1 = max(sx0 + 1, x1 - margin)
    density = np.asarray(ink[lower:upper, sx0:sx1], dtype=np.uint8).sum(axis=1)
    if density.size == 0:
        return coarse
    smoothed = _smooth(density)

    # A separator should sit in a real valley, not merely move to another text row.
    minimum = float(np.min(smoothed))
    median = float(np.median(smoothed))
    if median <= 0:
        threshold = minimum
    else:
        threshold = minimum + max(0.5, (median - minimum) * 0.18)
    blank = smoothed <= threshold

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, active in enumerate(blank.tolist()):
        if active and start is None:
            start = index
        elif not active and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(blank)))
    if not runs:
        return coarse

    # Prefer the blank band immediately preceding the entry.  Width and lower
    # ink break ties; support/semantic role never enter this refinement.
    coarse_local = coarse - lower
    candidates = [run for run in runs if run[0] <= coarse_local + 1]
    if not candidates:
        return coarse

    def score(run: tuple[int, int]) -> tuple[float, float, float]:
        a, b = run
        centre = (a + b - 1) / 2.0
        gap_to_entry = abs(float(coarse_local) - centre)
        run_density = float(np.mean(smoothed[a:b])) if b > a else float("inf")
        run_width = float(max(1, b - a))
        return (gap_to_entry, run_density, -run_width)

    best = min(candidates, key=score)
    refined_local = int(round((best[0] + best[1] - 1) / 2.0))
    refined = lower + refined_local

    # Keep Y refinement local; a role row is never allowed to jump to another row.
    max_move = max(3, round(ref * 0.36))
    refined = max(coarse - max_move, min(coarse + max(1, round(ref * 0.05)), refined))
    return max(int(body_top), min(int(body_bottom) - 1, int(refined)))


def refined_entry_y_by_line(image: Image.Image, understanding: Any) -> dict[int, int]:
    """Return canonical refined Y for each already-classified entry line."""
    try:
        ink = _canonical_ink(image, understanding)
    except Exception:
        return {}

    layout = understanding.layout
    line_height = float(
        getattr(layout, "ordinary_line_height", 0.0)
        or getattr(understanding, "line_height", 0.0)
        or 0.0
    )
    result: dict[int, int] = {}
    for column in list(getattr(layout, "columns", []) or []):
        lines = list(getattr(column, "lines", []) or [])
        for index, line in enumerate(lines):
            if str(getattr(line, "role", "") or "") != "entry":
                continue
            previous = lines[index - 1] if index > 0 else None
            result[id(line)] = refine_entry_separator_y(
                ink,
                column_left=int(getattr(column, "left", 0) or 0),
                column_right=int(getattr(column, "right", 0) or 0),
                body_top=int(getattr(layout, "body_top", 0) or 0),
                body_bottom=int(getattr(layout, "body_bottom", ink.shape[0]) or ink.shape[0]),
                line=line,
                previous_line=previous,
                line_height=line_height,
            )
    return result
