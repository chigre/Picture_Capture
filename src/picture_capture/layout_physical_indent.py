from __future__ import annotations

"""Projection-led row recovery and binary physical-indent roles.

Horizontal indentation is inferred from each column's physical leading-whitespace
measurements.  Before clustering, a common per-column X drift is removed from
``first_x`` so a slightly tilted scan does not split one real indent lane into
many artificial lanes.  Character height remains a vertical prior for row
recovery only; it is not used to cluster horizontal indentation or assign
entry/body roles.
"""

from typing import Any, Callable

import numpy as np


def _raw_projection_runs(
    ink: np.ndarray,
    scale: float,
) -> tuple[list[tuple[int, int]], np.ndarray, float]:
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


def _logical_slots_for_oversized_run(
    y0: int,
    y1: int,
    reference: float,
) -> list[tuple[int, int]]:
    """Expand one continuous oversized text run into logical row spans.

    Display-size headwords can remain vertically connected for roughly two or
    three ordinary rows, so a valley-only splitter cannot separate them.  Once
    the observed run is clearly taller than one ordinary row, recover the row
    *slots* it occupies from the stable ordinary-line reference.  The later
    line-feature stage still measures real ink independently inside each slot;
    this function never assigns semantic roles by itself.
    """
    height = max(0, int(y1) - int(y0))
    ref = max(6.0, float(reference))
    if height < ref * 1.55:
        return [(int(y0), int(y1))]

    count = int(round(height / ref))
    count = max(2, min(4, count))
    if height / float(count) < ref * 0.48:
        return [(int(y0), int(y1))]

    edges = np.linspace(float(y0), float(y1), count + 1)
    slots: list[tuple[int, int]] = []
    for index in range(count):
        a = int(round(edges[index]))
        b = int(round(edges[index + 1]))
        if b > a:
            slots.append((a, b))
    return slots or [(int(y0), int(y1))]


def projection_line_runs(ink: np.ndarray, scale: float) -> list[tuple[int, int]]:
    """Detect rows from observed horizontal ink runs.

    Ordinary text remains projection-led.  A continuous oversized typography
    run that cannot be separated by a real horizontal valley is expanded into
    the logical ordinary-row spans it occupies, so each span can still receive
    an independent physical-indent measurement.
    """
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
                continue
            if part_height > maximum_single:
                for slot0, slot1 in _logical_slots_for_oversized_run(
                    part0, part1, ref
                ):
                    slot_height = slot1 - slot0
                    if minimum <= slot_height <= maximum_single:
                        result.append((int(slot0), int(slot1)))

    return result


def _indent_gap_threshold(values: np.ndarray) -> float:
    """Estimate a within-lane X-gap threshold from one column's samples."""
    if values.size < 2:
        return 2.0

    unique = np.unique(np.sort(values.astype(float)))
    if unique.size < 2:
        return 2.0
    positive = np.diff(unique)
    positive = positive[positive > 0]
    if positive.size == 0:
        return 2.0

    median_gap = float(np.median(positive))
    local = positive[positive <= median_gap]
    if local.size == 0:
        local = np.asarray([float(np.min(positive))], dtype=float)
    typical = float(np.median(local))
    mad = float(np.median(np.abs(local - typical))) if local.size else 0.0
    return float(max(2.0, min(6.0, typical + 2.0 * mad + 1.0)))


def _line_mid_y(line: Any) -> float | None:
    try:
        y0 = float(getattr(line, "y0"))
        y1 = float(getattr(line, "y1"))
    except (AttributeError, TypeError, ValueError):
        return None
    return (y0 + y1) / 2.0


def estimate_column_slant(lines: list[Any]) -> float:
    """Estimate common horizontal drift per vertical pixel for one column.

    The estimate is intentionally based on pairwise slopes rather than an
    ordinary least-squares fit.  Different indent lanes have different
    intercepts; their shared page tilt is the robust median slope after removing
    implausibly steep cross-lane pairs.
    """
    samples: list[tuple[float, float]] = []
    for line in lines:
        y = _line_mid_y(line)
        if y is None:
            continue
        try:
            x = float(getattr(line, "first_x", 0) or 0)
        except (TypeError, ValueError):
            continue
        samples.append((y, x))

    if len(samples) < 6:
        return 0.0

    samples.sort(key=lambda item: item[0])
    ys = np.asarray([item[0] for item in samples], dtype=float)
    span = float(ys[-1] - ys[0])
    if span < 80.0:
        return 0.0

    minimum_dy = max(24.0, span * 0.08)
    slopes: list[float] = []
    for i, (y0, x0) in enumerate(samples[:-1]):
        for y1, x1 in samples[i + 1:]:
            dy = float(y1 - y0)
            if dy < minimum_dy:
                continue
            slope = float((x1 - x0) / dy)
            if abs(slope) <= 0.03:
                slopes.append(slope)

    if len(slopes) < 5:
        return 0.0

    values = np.asarray(slopes, dtype=float)
    center = float(np.median(values))
    deviation = np.abs(values - center)
    mad = float(np.median(deviation)) if deviation.size else 0.0
    if mad > 0:
        kept = values[deviation <= max(0.0015, 3.5 * mad)]
        if kept.size >= 3:
            center = float(np.median(kept))
    return float(max(-0.03, min(0.03, center)))


def normalized_physical_indents(lines: list[Any]) -> dict[int, float]:
    """Return first-X values after removing one column's shared X-vs-Y drift."""
    if not lines:
        return {}
    slope = estimate_column_slant(lines)
    ys = [y for line in lines if (y := _line_mid_y(line)) is not None]
    y_ref = float(np.median(np.asarray(ys, dtype=float))) if ys else 0.0

    result: dict[int, float] = {}
    for line in lines:
        raw = float(getattr(line, "first_x", 0) or 0)
        y = _line_mid_y(line)
        corrected = raw if y is None else raw - slope * (float(y) - y_ref)
        result[id(line)] = float(corrected)
    return result


def physical_indent_modes(lines: list[Any], _reference: float | None = None) -> list[Any]:
    """Cluster one column by slant-normalized physical leading whitespace."""
    from . import dictionary_page_design as page_design

    if not lines:
        return []

    normalized = normalized_physical_indents(lines)

    def value(line: Any) -> float:
        return float(normalized.get(id(line), float(getattr(line, "first_x", 0) or 0)))

    ordered = sorted(lines, key=value)
    values = np.asarray([value(line) for line in ordered], dtype=float)
    gap_threshold = _indent_gap_threshold(values)

    clusters: list[list[Any]] = []
    current: list[Any] = []
    previous_value: float | None = None
    for line in ordered:
        current_value = value(line)
        if (
            current
            and previous_value is not None
            and current_value - previous_value > gap_threshold
        ):
            clusters.append(current)
            current = []
        current.append(line)
        previous_value = current_value
    if current:
        clusters.append(current)

    result: list[Any] = []
    for cluster in clusters:
        cluster_values = np.asarray([value(line) for line in cluster], dtype=float)
        center = float(np.median(cluster_values))
        lo = float(np.min(cluster_values))
        hi = float(np.max(cluster_values))
        result.append(
            page_design.IndentMode(
                center=center,
                tolerance=max(1.0, max(center - lo, hi - center) + 1.0),
                lines=list(cluster),
                shape_consensus=page_design._shape_consensus(cluster),
            )
        )
    return sorted(result, key=lambda mode: mode.center)


def _support(mode: Any) -> int:
    return int(getattr(mode, "support", 0) or 0)


def _center(mode: Any) -> float:
    return float(getattr(mode, "center", 0.0) or 0.0)


def _weighted_sse(modes: list[Any]) -> float:
    if not modes:
        return 0.0
    weights = np.asarray([max(1, _support(mode)) for mode in modes], dtype=float)
    centers = np.asarray([_center(mode) for mode in modes], dtype=float)
    mean = float(np.average(centers, weights=weights))
    return float(np.sum(weights * (centers - mean) ** 2))


def _binary_mode_groups(modes: list[Any]) -> tuple[list[Any], list[Any]]:
    """Partition physical lanes into lower- and higher-indent classes."""
    ordered = sorted(modes, key=_center)
    if len(ordered) < 2:
        return ordered, []

    best_index = 1
    best_cost: float | None = None
    for index in range(1, len(ordered)):
        low = ordered[:index]
        high = ordered[index:]
        cost = _weighted_sse(low) + _weighted_sse(high)
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_index = index
    return ordered[:best_index], ordered[best_index:]


def assign_binary_roles(
    column: Any,
    indent_type: str,
    _reference: float | None = None,
) -> None:
    """Assign exactly two semantic classes from physical-indent lanes.

    ``headword`` means the higher-indent class is entry; ``body`` means the
    lower-indent class is entry.  Support is used only to stabilize the two-class
    partition, never as a minimum-support gate, so a legitimate singleton entry
    remains possible.  Every remaining line is body.
    """
    modes = list(getattr(column, "indent_modes", []) or [])
    lines = list(getattr(column, "lines", []) or [])

    for line in lines:
        line.role = "body"
    for mode in modes:
        mode.role = "body"

    column.entry_modes = []
    column.body_mode = None
    if not modes:
        return
    if len(modes) == 1:
        column.body_mode = modes[0]
        return

    low, high = _binary_mode_groups(modes)
    entry_modes = high if str(indent_type) == "headword" else low
    body_modes = low if str(indent_type) == "headword" else high

    for mode in entry_modes:
        mode.role = "entry"
        for line in list(getattr(mode, "lines", []) or []):
            line.role = "entry"

    column.entry_modes = list(entry_modes)
    column.body_mode = max(
        body_modes or modes,
        key=lambda mode: (_support(mode), -abs(_center(mode))),
    )


def normalize_layout_roles(layout: Any) -> Any:
    """Rebuild final entry/body roles from physical-indent lanes only."""
    indent_type = str(getattr(layout, "indent_type", "body") or "body")
    if indent_type == "none":
        for column in list(getattr(layout, "columns", []) or []):
            for line in list(getattr(column, "lines", []) or []):
                line.role = "body"
            for mode in list(getattr(column, "indent_modes", []) or []):
                mode.role = "body"
            column.entry_modes = []
            if column.indent_modes:
                column.body_mode = max(column.indent_modes, key=_support)
        return layout

    for column in list(getattr(layout, "columns", []) or []):
        assign_binary_roles(column, indent_type)
    return layout


def _install_policy_finalization() -> None:
    from . import dictionary_page_layout_policy as policy

    if getattr(policy, "_physical_indent_finalizer_installed", False):
        return

    original: Callable[..., Any] = policy.infer_dictionary_page_layout

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        layout, page_settings, applied = original(*args, **kwargs)
        normalize_layout_roles(layout)
        return layout, page_settings, applied

    policy.infer_dictionary_page_layout = wrapped
    policy._physical_indent_finalizer_installed = True


def _install_page_understanding_finalization() -> None:
    from . import page_understanding

    if getattr(page_understanding, "_physical_indent_finalizer_installed", False):
        return

    original: Callable[..., Any] = page_understanding.understand_page

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        understanding = original(*args, **kwargs)
        normalize_layout_roles(understanding.layout)
        return understanding

    page_understanding.understand_page = wrapped
    page_understanding._physical_indent_finalizer_installed = True


def install_physical_indent_inference() -> None:
    """Install the single physical-indent implementation used by all consumers."""
    from . import dictionary_page_design as page_design
    from .layout_profile_anchor import install_profile_layout_anchor

    if getattr(page_design, "_physical_indent_inference_installed", False):
        return

    install_profile_layout_anchor()
    page_design._line_runs = projection_line_runs
    page_design._indent_modes = physical_indent_modes
    page_design._assign_indent_semantics = assign_binary_roles
    _install_policy_finalization()
    _install_page_understanding_finalization()
    page_design._physical_indent_inference_installed = True