"""Robust per-column line-pitch evidence from Paddle text-detection boxes.

Do NOT sort all text-box tops across a two-column dictionary: staggered
columns interleave rows and systematically underestimate vertical leading.
This estimator clusters box tops within each separately detected column, then
requires enough consistent adjacent physical rows to compute legacy padding.
"""
from __future__ import annotations

import statistics
from typing import Iterable


def estimate_row_padding_from_boxes(
    column_groups: Iterable[Iterable[tuple[int, int, int, int]]],
    character_height: int,
) -> tuple[int | None, int]:
    """Return (legacy half-gap in pixels, supporting row-pitch pairs).

    Existing Paddle-derived row_padding represented half of the excess
    top-to-top interval over glyph-box height. Preserve that contract; do not
    conflate it with full physical line spacing or overwrite it from guesses.
    """
    height = max(1.0, float(character_height))
    spacing: list[float] = []
    for boxes in column_groups:
        tops = sorted(
            float(b[1]) for b in boxes
            if 0.55 * height <= float(b[3] - b[1]) <= 1.65 * height
        )
        if len(tops) < 5:
            continue
        clusters: list[list[float]] = []
        for top in tops:
            if clusters and top - statistics.median(clusters[-1]) <= max(3.0, .40 * height):
                clusters[-1].append(top)
            else:
                clusters.append([top])
        row_tops = [statistics.median(c) for c in clusters]
        for a, b in zip(row_tops, row_tops[1:]):
            pitch = b - a
            if 1.05 * height <= pitch <= 2.80 * height:
                spacing.append(pitch)
    if len(spacing) < 8:
        return None, len(spacing)
    center = float(statistics.median(spacing))
    close = [v for v in spacing if abs(v - center) <= max(3.0, center * .18)]
    if len(close) < max(8, round(len(spacing) * .65)):
        return None, len(close)
    center = float(statistics.median(close))
    if max(close) - min(close) > max(7.0, center * .28):
        return None, len(close)
    return max(1, round((center - height) / 2.0)), len(close)
