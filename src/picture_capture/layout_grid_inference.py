from __future__ import annotations

"""Projection-led line recovery and physical indent-lane semantics.

Dictionary rows are first detected from real horizontal ink projection runs.
The detected ordinary line height is only a structural prior: it rejects tiny
noise runs and helps split an abnormally tall connected run at a low-ink valley.
It does *not* impose a repeated fixed row grid on the page.

Indent modes are physical layout quantities and are clustered independently in
each column from ``LayoutLine.first_x`` (the visible indent width).  Row roles
are then assigned from those physical lanes.  ``anchor_x`` and small-prefix
metadata remain secondary evidence only; they do not determine lane membership
or lane role.
"""

from typing import Any

import numpy as np


def _raw_projection_runs(ink: np.ndarray, scale: float) -> tuple[list[tuple[int, int]], np.ndarray, float]:
    """Return real row-projection runs before height-based interpretation."""
    from .ordinary_visual import _runs

    if ink.ndim != 2 or ink.size == 0:
        return [], np.zeros(0, dtype=float), 0.0

    width = max(1, int(ink.shape[1]))
    row_ink = np.asarray(ink, dtype=np.uint8).sum(axis=1).astype(np.float64)
    threshold = max(2.0, float(width) * 0.003)
    active = row_ink >= threshold

    max_gap = max(0, min(2, int(round(max(6.0, float(scale)) * 0.035))))
    if max_gap > 0:
        indices = np.flatnonzero(active)
        if indices.size >= 2:
            for left, right in zip(indices, indices[1:]):
                gap = int(right - left - 1)
                if 0 < gap <= max_gap:
                    active[left:right + 1] = True

    return [(int(a), int(b)) for a, b in _runs(active)], row_ink, threshold


def _split_tall_run(
    y0: int,
    y1: int,
    row_ink: np.ndarray,
    threshold: float,
    reference: float,
) -> list[tuple[int, int]]:
    """Split a connected multi-line run only when a convincing ink valley exists."""
    height = int(y1 - y0)
    ref = max(6.0, float(reference))
    if height <= ref * 1.70:
        return [(int(y0), int(y1))]

    lo = max(y0 + 2, int(round(y0 + ref * 0.62)))
    hi = min(y1 - 2, int(round(y0 + ref * 1.38)))
    if hi <= lo:
        return [(int(y0), int(y1))]

    best_y: int | None = None
    best_cost: float | None = None
    for y in range(lo, hi + 1):
        a = max(y0, y - 1)
        b = min(y1, y + 2)
        cost = float(np.mean(row_ink[a:b])) if b > a else float(row_ink[y])
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_y = y

    if best_y is None or best_cost is None:
        return [(int(y0), int(y1))]

    body = row_ink[y0:y1]
    active_values = body[body >= threshold]
    typical = float(np.median(active_values)) if active_values.size else threshold
    valley_limit = max(threshold * 1.8, typical * 0.18)
    if best_cost > valley_limit:
        return [(int(y0), int(y1))]

    left = (int(y0), int(best_y))
    right = (int(best_y), int(y1))
    minimum = max(3, int(round(ref * 0.20)))
    if left[1] - left[0] < minimum or right[1] - right[0] < minimum:
        return [(int(y0), int(y1))]

    result: list[tuple[int, int]] = []
    for part0, part1 in (left, right):
        result.extend(_split_tall_run(part0, part1, row_ink, threshold, ref))
    return result


def projection_line_runs(ink: np.ndarray, scale: float) -> list[tuple[int, int]]:
    """Detect rows from observed ink runs, using line height only for validation/splitting."""
    raw, row_ink, threshold = _raw_projection_runs(ink, scale)
    if not raw:
        return []

    ref = max(6.0, float(scale))
    minimum = ref * 0.26
    maximum_single = ref * 1.90
    result: list[tuple[int, int]] = []

    for y0, y1 in raw:
        height = y1 - y0
        if height < minimum:
            continue
        parts = (
            _split_tall_run(y0, y1, row_ink, threshold, ref)
            if height > maximum_single
            else [(y0, y1)]
        )
        for part0, part1 in parts:
            part_height = part1 - part0
            if minimum <= part_height <= maximum_single:
                result.append((int(part0), int(part1)))

    return result


grid_line_runs = projection_line_runs


def indent_width_modes(lines: list[Any], reference: float) -> list[Any]:
    """Cluster one column's rows by physical indent width (``first_x``).

    The old 0.24×line-height radius was broad enough to merge visibly different
    lanes on high-DPI dictionary pages (for example a flush-left headword lane
    and a nearby ``~`` continuation lane).  Physical indentation is now treated
    as the primary classification signal, so the lane radius is deliberately
    tighter: about 0.12×line-height, with a 3-pixel floor.
    """
    from . import dictionary_page_design as page_design

    if not lines:
        return []

    clusters: list[list[Any]] = []
    tolerance = max(3.0, float(reference) * 0.12)
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
                float(reference) * 0.07,
                min(float(reference) * 0.18, q90 + float(reference) * 0.04),
            ),
            lines=list(cluster),
            shape_consensus=page_design._shape_consensus(cluster),
        ))
    return sorted(result, key=lambda mode: mode.center)


def assign_physical_indent_roles(column: Any, indent_type: str, reference: float) -> None:
    """Assign body/entry/unknown roles from physical-indent lanes only."""
    modes = list(getattr(column, "indent_modes", []) or [])
    column.body_mode = None
    column.entry_modes = []
    if not modes:
        return

    for mode in modes:
        mode.role = "unknown"

    total = max(1, sum(int(getattr(mode, "support", 0) or 0) for mode in modes))
    stable_min = max(3, round(total * 0.12))
    stable = [
        mode for mode in modes
        if int(getattr(mode, "support", 0) or 0) >= stable_min
    ]
    if not stable:
        stable = [max(modes, key=lambda mode: int(getattr(mode, "support", 0) or 0))]

    if str(indent_type) == "headword":
        body = min(stable, key=lambda mode: float(mode.center))
        entry_direction = 1.0
    else:
        body = max(stable, key=lambda mode: float(mode.center))
        entry_direction = -1.0

    body.role = "body"
    column.body_mode = body

    ref = max(6.0, float(reference))
    minimum_separation = ref * 0.30
    maximum_separation = ref * 5.0
    entries: list[Any] = []

    for mode in modes:
        if mode is body:
            continue
        separation = entry_direction * (float(mode.center) - float(body.center))
        support = int(getattr(mode, "support", 0) or 0)
        if minimum_separation <= separation <= maximum_separation and support >= 2:
            mode.role = "entry"
            entries.append(mode)

    column.entry_modes = entries


def install_grid_line_and_indent_inference() -> None:
    """Install projection-led rows plus physical-indent lane semantics once."""
    from . import dictionary_page_design as page_design

    if getattr(page_design, "_grid_line_indent_inference_installed", False):
        return

    page_design._line_runs = projection_line_runs
    page_design._indent_modes = indent_width_modes
    page_design._assign_indent_semantics = assign_physical_indent_roles
    page_design._grid_line_indent_inference_installed = True
