from __future__ import annotations

"""Projection-led row recovery and binary physical-indent roles.

Horizontal indentation is inferred from each column's physical leading-whitespace
measurements. Before clustering, a common per-column X drift is removed from
``first_x`` so a slightly tilted scan does not split one real indent lane into
many artificial lanes. Character height is a vertical prior for row recovery
only; it is not used to cluster horizontal indentation or assign entry/body
roles.
"""

from typing import Any, Callable

import numpy as np


_BASE_LINE_FEATURE: Callable[..., Any] | None = None


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
    """Expand one continuous oversized text run into logical row spans."""
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
    """Detect rows from observed ink runs, including oversized logical rows."""
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


def _credible_first_ink_x(line: np.ndarray, reference: float) -> int | None:
    """Return the first real leading mark, including thin horizontal glyphs."""
    from .ordinary_visual import _fill_short_gaps, _runs

    if line.ndim != 2 or line.size == 0:
        return None

    ref = max(6.0, float(reference))
    active = np.asarray(line, dtype=bool).any(axis=0)
    active = _fill_short_gaps(active, max(1, round(ref * 0.025)))
    minimum_area = max(2, int(round(ref * 0.04)))
    minimum_wide = max(3, int(round(ref * 0.10)))
    minimum_tall = max(3, int(round(ref * 0.22)))

    for x0, x1 in _runs(active):
        component = np.asarray(line[:, x0:x1], dtype=bool)
        if component.size == 0:
            continue
        area = int(component.sum())
        if area < minimum_area:
            continue
        ys = np.flatnonzero(component.any(axis=1))
        if ys.size == 0:
            continue
        width = int(x1 - x0)
        height = int(ys[-1] - ys[0] + 1)
        if width >= minimum_wide or (width >= 2 and height >= minimum_tall):
            return int(x0)
    return None


def physical_line_feature(
    column: int,
    ink: np.ndarray,
    y0: int,
    y1: int,
    reference: float,
    previous_end: int,
) -> Any | None:
    """Measure one row with raw-leading-ink and robust-anchor semantics."""
    from . import dictionary_page_design as page_design

    line_ink = ink[y0:y1]
    first_x = _credible_first_ink_x(line_ink, reference)

    result = (
        _BASE_LINE_FEATURE(column, ink, y0, y1, reference, previous_end)
        if _BASE_LINE_FEATURE is not None
        else None
    )
    if result is None:
        if first_x is None:
            return None
        return page_design.LayoutLine(
            column=column,
            y0=int(y0),
            y1=int(y1),
            first_x=int(first_x),
            anchor_x=None,
            anchor_width=0,
            anchor_height=0,
            gap_before=max(0, int(y0) - int(previous_end)),
            patch=np.zeros((0, 0), dtype=bool),
            has_small_prefix=False,
        )

    if first_x is not None and int(first_x) < int(result.first_x):
        result.first_x = int(first_x)
        result.has_small_prefix = bool(
            result.anchor_x is not None
            and int(first_x) < float(result.anchor_x) - float(reference) * 0.12
        )
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
    """Estimate common horizontal drift per vertical pixel for one column."""
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


def _mode_range(mode: Any, normalized: dict[int, float]) -> tuple[float, float]:
    values = [
        float(normalized[id(line)])
        for line in list(getattr(mode, "lines", []) or [])
        if id(line) in normalized
    ]
    if values:
        return float(min(values)), float(max(values))
    center = _center(mode)
    tolerance = float(getattr(mode, "tolerance", 1.0) or 1.0)
    return center - tolerance, center + tolerance


def _body_envelope_gap(reference: float | None) -> float:
    """Maximum edge-to-edge gap that still belongs to ordinary body jitter."""
    if reference is None:
        return 6.0
    ref = max(6.0, float(reference))
    return float(max(4.0, min(12.0, ref * 0.16)))


def _body_semantic_modes(
    column: Any,
    body: Any,
    reference: float | None,
) -> set[int]:
    """Grow the body semantic envelope across nearby physical lanes.

    Physical clustering remains intentionally fine grained.  Semantic body
    assignment starts from the dominant lane and absorbs neighboring lanes whose
    *actual edge-to-edge gap* is small.  Expansion is capped so a chain of tiny
    lanes cannot walk all the way into a genuinely indented headword region.
    """
    modes = list(getattr(column, "indent_modes", []) or [])
    lines = list(getattr(column, "lines", []) or [])
    normalized = normalized_physical_indents(lines)
    ranges = {id(mode): _mode_range(mode, normalized) for mode in modes}
    body_lo, body_hi = ranges.get(id(body), (_center(body), _center(body)))
    body_center = _center(body)
    gap_limit = _body_envelope_gap(reference)
    ref = max(6.0, float(reference)) if reference is not None else 40.0
    max_extension = max(12.0, min(24.0, ref * 0.35))

    absorbed: set[int] = {id(body)}
    changed = True
    while changed:
        changed = False
        for mode in modes:
            mode_id = id(mode)
            if mode_id in absorbed:
                continue
            lo, hi = ranges[mode_id]
            if hi < body_lo:
                gap = body_lo - hi
            elif lo > body_hi:
                gap = lo - body_hi
            else:
                gap = 0.0
            proposed_lo = min(body_lo, lo)
            proposed_hi = max(body_hi, hi)
            if (
                gap <= gap_limit
                and body_center - max_extension <= proposed_lo
                and proposed_hi <= body_center + max_extension
            ):
                absorbed.add(mode_id)
                body_lo, body_hi = proposed_lo, proposed_hi
                changed = True
    return absorbed


def assign_binary_roles(
    column: Any,
    indent_type: str,
    _reference: float | None = None,
) -> None:
    """Assign entry/body from a dominant body envelope and indent direction.

    The most-supported physical-indent lane seeds the body class. Nearby lanes
    whose *actual ranges* are separated from that body range by only a small gap
    are absorbed into the body envelope. Only lanes clearly beyond the final
    body envelope in the configured indent direction become entry. Support never
    gates entry eligibility.
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

    body = max(
        modes,
        key=lambda mode: (_support(mode), -abs(_center(mode))),
    )
    column.body_mode = body
    body_ids = _body_semantic_modes(column, body, _reference)

    body_centers = [_center(mode) for mode in modes if id(mode) in body_ids]
    body_min = min(body_centers) if body_centers else _center(body)
    body_max = max(body_centers) if body_centers else _center(body)

    if str(indent_type) == "headword":
        entry_modes = [
            mode for mode in modes
            if id(mode) not in body_ids and _center(mode) > body_max
        ]
    else:
        entry_modes = [
            mode for mode in modes
            if id(mode) not in body_ids and _center(mode) < body_min
        ]

    for mode in entry_modes:
        mode.role = "entry"
        for line in list(getattr(mode, "lines", []) or []):
            line.role = "entry"
    column.entry_modes = list(entry_modes)


def _suppress_display_head_duplicate_entries(layout: Any) -> None:
    """Keep one entry boundary for one oversized display head."""
    columns = list(getattr(layout, "columns", []) or [])
    heads = list(getattr(layout, "display_heads", []) or [])
    if not columns or not heads:
        return

    for head in heads:
        try:
            column_index = int(getattr(head, "column"))
            head_y0 = int(getattr(head, "y0"))
            head_y1 = int(getattr(head, "y1"))
        except (AttributeError, TypeError, ValueError):
            continue
        if not (0 <= column_index < len(columns)):
            continue

        column = columns[column_index]
        overlapping = [
            line
            for line in list(getattr(column, "lines", []) or [])
            if str(getattr(line, "role", "body")) == "entry"
            and int(getattr(line, "y1", 0)) > head_y0
            and int(getattr(line, "y0", 0)) < head_y1
        ]
        if len(overlapping) <= 1:
            continue

        overlapping.sort(key=lambda line: (int(line.y0), int(line.y1)))
        for line in overlapping[1:]:
            line.role = "body"


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

    reference = float(getattr(layout, "ordinary_line_height", 0.0) or 0.0)
    reference_arg = reference if reference > 0 else None
    for column in list(getattr(layout, "columns", []) or []):
        assign_binary_roles(column, indent_type, reference_arg)
    _suppress_display_head_duplicate_entries(layout)
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

    global _BASE_LINE_FEATURE
    if getattr(page_design, "_physical_indent_inference_installed", False):
        return

    install_profile_layout_anchor()
    if _BASE_LINE_FEATURE is None:
        _BASE_LINE_FEATURE = page_design._line_feature
    page_design._line_runs = projection_line_runs
    page_design._line_feature = physical_line_feature
    page_design._indent_modes = physical_indent_modes
    page_design._assign_indent_semantics = assign_binary_roles
    _install_policy_finalization()
    _install_page_understanding_finalization()
    page_design._physical_indent_inference_installed = True
