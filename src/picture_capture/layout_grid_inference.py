from __future__ import annotations

"""Grid-based line recovery and indent-width clustering for Page Understanding.

A dictionary body already supplies a vertical extent and a reliable ordinary
character/line scale.  Treating each connected row-projection run as a line is
therefore unnecessarily fragile: scan dust can bridge adjacent rows and make a
tall run disappear entirely.  This module instead establishes repeated row
slots from the known line scale, aligns slot boundaries to low-ink valleys, and
then measures the real ink inside each slot.

Indent modes are likewise physical layout quantities.  They are clustered from
``LayoutLine.first_x`` (the actual visible indent width inside one column), not
from semantic ``anchor_x``.  Anchor geometry remains available as secondary
structural evidence, but no longer determines the lane assignment.
"""

from typing import Any

import numpy as np


def grid_line_runs(ink: np.ndarray, scale: float) -> list[tuple[int, int]]:
    """Return text-line runs recovered from a body-height/line-height grid.

    ``ink`` is one column's leading body strip in body-local coordinates.  The
    expected slot pitch is the detected ordinary line height plus a minimal
    inter-line gap.  A phase search chooses boundaries with the least ink, so
    descenders/ascenders are kept on the appropriate side without allowing a
    few bridging specks to merge two complete rows.
    """
    if ink.ndim != 2 or ink.size == 0:
        return []

    height, width = ink.shape
    reference = max(6.0, float(scale))
    # character_height is the application-level row text scale.  The historical
    # default row_padding is one pixel; allow a tiny proportional allowance so
    # high-DPI pages do not accumulate phase error over the whole body.
    pitch = max(4, int(round(reference + max(1.0, reference * 0.025))))
    pitch = min(pitch, max(4, height))

    row_ink = np.asarray(ink, dtype=np.uint8).sum(axis=1).astype(np.float64)
    active_threshold = max(2.0, float(width) * 0.003)

    # Pick a repeated slot boundary through low-ink valleys.  Use a three-row
    # boundary cost so one noisy pixel row cannot dictate the phase.
    best_phase = 0
    best_cost: float | None = None
    for phase in range(pitch):
        positions = np.arange(phase, height, pitch, dtype=int)
        positions = positions[(positions > 1) & (positions < height - 2)]
        if positions.size < 2:
            continue
        cost = float(np.mean(
            row_ink[positions - 1] + row_ink[positions] + row_ink[positions + 1]
        ))
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_phase = phase

    boundaries = list(range(best_phase, height + pitch, pitch))
    boundaries = [value for value in boundaries if 0 < value < height]
    edges = [0, *boundaries, height]

    runs: list[tuple[int, int]] = []
    minimum_height = max(3, int(round(reference * 0.20)))
    minimum_area = max(6, int(round(reference * reference * 0.025)))

    for slot0, slot1 in zip(edges, edges[1:]):
        if slot1 - slot0 < minimum_height:
            continue
        slot = ink[slot0:slot1]
        row_active = slot.sum(axis=1) >= active_threshold
        ys = np.flatnonzero(row_active)
        if ys.size == 0 or int(slot.sum()) < minimum_area:
            continue

        y0 = slot0 + int(ys[0])
        y1 = slot0 + int(ys[-1]) + 1
        # Keep sparse punctuation-only slots out, but do not impose the old
        # upper-height cutoff: the grid itself already prevents two rows from
        # becoming one giant run.
        if y1 - y0 < minimum_height:
            continue
        runs.append((int(y0), int(y1)))

    return runs


def indent_width_modes(lines: list[Any], reference: float) -> list[Any]:
    """Cluster one column's lines by physical indent width (``first_x``)."""
    from . import dictionary_page_design as page_design

    if not lines:
        return []

    clusters: list[list[Any]] = []
    tolerance = max(3.0, float(reference) * 0.24)
    for line in sorted(lines, key=lambda item: int(getattr(item, "first_x", 0) or 0)):
        value = float(getattr(line, "first_x", 0) or 0)
        target: list[Any] | None = None
        for cluster in clusters:
            center = float(np.median([
                float(getattr(item, "first_x", 0) or 0) for item in cluster
            ]))
            if abs(value - center) <= tolerance:
                target = cluster
                break
        if target is None:
            clusters.append([line])
        else:
            target.append(line)

    result: list[Any] = []
    for cluster in clusters:
        values = np.asarray([
            float(getattr(line, "first_x", 0) or 0) for line in cluster
        ], dtype=float)
        center = float(np.median(values))
        deviation = np.abs(values - center)
        q90 = float(np.quantile(deviation, 0.90)) if deviation.size else 0.0
        result.append(page_design.IndentMode(
            center=center,
            tolerance=max(
                float(reference) * 0.14,
                min(float(reference) * 0.34, q90 + float(reference) * 0.08),
            ),
            lines=list(cluster),
            shape_consensus=page_design._shape_consensus(cluster),
        ))
    return sorted(result, key=lambda mode: mode.center)


def install_grid_line_and_indent_inference() -> None:
    """Install grid line recovery and physical-indent clustering exactly once."""
    from . import dictionary_page_design as page_design

    if getattr(page_design, "_grid_line_indent_inference_installed", False):
        return

    page_design._line_runs = grid_line_runs
    page_design._indent_modes = indent_width_modes
    page_design._grid_line_indent_inference_installed = True
