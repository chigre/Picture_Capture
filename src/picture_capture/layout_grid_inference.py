from __future__ import annotations

"""Projection-led line recovery and data-driven physical-indent lanes.

Rows are detected from real horizontal ink projection.  Character height is a
vertical prior used only for row validation/splitting; it is deliberately not
used to cluster horizontal indentation.

Indent modes are inferred independently in each column from the observed
``LayoutLine.first_x`` distribution.  Lane membership and lane roles therefore
come from physical leading whitespace only, not from line height, ``anchor_x``
or small-prefix metadata.
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
    """Detect rows from observed ink runs, using line height only vertically."""
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


def _indent_gap_threshold(values: np.ndarray) -> float:
    """Estimate the within-lane gap tolerance from one column's indent samples.

    Only horizontal sample spacing is used.  Dense physical lanes usually have
    repeated/nearby integer ``first_x`` values, while genuine lane boundaries
    appear as much larger gaps.  The threshold is estimated from the lower half
    of positive adjacent gaps so sparse outliers cannot inflate it.
    """
    if values.size < 2:
        return 2.0

    unique = np.unique(np.sort(values.astype(float)))
    if unique.size < 2:
        return 2.0
    gaps = np.diff(unique)
    positive = gaps[gaps > 0]
    if positive.size == 0:
        return 2.0

    median_gap = float(np.median(positive))
    local = positive[positive <= median_gap]
    if local.size == 0:
        local = np.asarray([float(np.min(positive))], dtype=float)
    typical = float(np.median(local))
    mad = float(np.median(np.abs(local - typical))) if local.size else 0.0

    # Pixel-domain measurement noise is normally only a few columns.  The cap
    # prevents a sparse page with only two remote lanes from merging them.
    return float(max(2.0, min(6.0, typical + 2.0 * mad + 1.0)))


def indent_width_modes(lines: list[Any], reference: float | None = None) -> list[Any]:
    """Cluster one column by its own physical-indent distribution.

    ``reference`` is accepted only for API compatibility and is intentionally
    ignored: horizontal indent clustering must not depend on vertical line
    height.
    """
    from . import dictionary_page_design as page_design

    if not lines:
        return []

    ordered = sorted(
        lines,
        key=lambda item: float(getattr(item, "first_x", 0) or 0),
    )
    values = np.asarray(
        [float(getattr(item, "first_x", 0) or 0) for item in ordered],
        dtype=float,
    )
    gap_threshold = _indent_gap_threshold(values)

    clusters: list[list[Any]] = []
    current: list[Any] = []
    previous_value: float | None = None
    for line in ordered:
        value = float(getattr(line, "first_x", 0) or 0)
        if (
            current
            and previous_value is not None
            and (value - previous_value) > gap_threshold
        ):
            clusters.append(current)
            current = []
        current.append(line)
        previous_value = value
    if current:
        clusters.append(current)

    result: list[Any] = []
    for cluster in clusters:
        cluster_values = np.asarray(
            [float(getattr(line, "first_x", 0) or 0) for line in cluster],
            dtype=float,
        )
        center = float(np.median(cluster_values))
        lo = float(np.min(cluster_values))
        hi = float(np.max(cluster_values))
        tolerance = max(1.0, max(center - lo, hi - center) + 1.0)
        result.append(
            page_design.IndentMode(
                center=center,
                tolerance=tolerance,
                lines=list(cluster),
                shape_consensus=page_design._shape_consensus(cluster),
            )
        )
    return sorted(result, key=lambda mode: mode.center)


def assign_physical_indent_roles(column: Any, indent_type: str, reference: float | None = None) -> None:
    """Assign body/entry/unknown roles from physical lanes only.

    The dominant lane (largest support) is body.  On the configured entry side,
    the outermost sufficiently supported lane is entry.  Intermediate lanes and
    sparse outliers remain unknown.  No vertical scale is used.
    """
    modes = list(getattr(column, "indent_modes", []) or [])
    column.body_mode = None
    column.entry_modes = []
    if not modes:
        return

    for mode in modes:
        mode.role = "unknown"

    def support(mode: Any) -> int:
        try:
            return int(getattr(mode, "support", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def center(mode: Any) -> float:
        try:
            return float(getattr(mode, "center", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    body = max(modes, key=lambda mode: (support(mode), -abs(center(mode))))
    body.role = "body"
    column.body_mode = body

    total = max(1, sum(support(mode) for mode in modes))
    entry_min_support = max(2, int(np.ceil(total * 0.06)))

    if str(indent_type) == "headword":
        candidates = [
            mode
            for mode in modes
            if mode is not body
            and center(mode) > center(body)
            and support(mode) >= entry_min_support
        ]
        entry = max(candidates, key=center) if candidates else None
    else:
        candidates = [
            mode
            for mode in modes
            if mode is not body
            and center(mode) < center(body)
            and support(mode) >= entry_min_support
        ]
        entry = min(candidates, key=center) if candidates else None

    if entry is not None:
        entry.role = "entry"
        column.entry_modes = [entry]


def install_grid_line_and_indent_inference() -> None:
    """Install projection-led rows and pure physical-indent lane semantics."""
    from . import dictionary_page_design as page_design

    if getattr(page_design, "_grid_line_indent_inference_installed", False):
        return

    page_design._line_runs = projection_line_runs
    page_design._indent_modes = indent_width_modes
    page_design._assign_indent_semantics = assign_physical_indent_roles
    page_design._grid_line_indent_inference_installed = True
