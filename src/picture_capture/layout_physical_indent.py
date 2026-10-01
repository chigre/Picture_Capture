from __future__ import annotations

"""Projection-led row recovery and binary physical-indent roles.

Horizontal indentation is inferred only from each column's observed ``first_x``
distribution. Character height is a vertical prior for row recovery only; it is
not used to cluster horizontal indentation or assign entry/body roles.
"""

from typing import Any, Callable

import numpy as np


_ENTRY_Y_BY_UNDERSTANDING: dict[int, dict[int, int]] = {}


def _raw_projection_runs(ink: np.ndarray, scale: float) -> tuple[list[tuple[int, int]], np.ndarray, float]:
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


def projection_line_runs(ink: np.ndarray, scale: float) -> list[tuple[int, int]]:
    """Detect rows from observed horizontal ink runs."""
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


def physical_indent_modes(lines: list[Any], _reference: float | None = None) -> list[Any]:
    """Cluster one column using only physical leading whitespace (``first_x``)."""
    from . import dictionary_page_design as page_design

    if not lines:
        return []

    ordered = sorted(lines, key=lambda item: float(getattr(item, "first_x", 0) or 0))
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
        if current and previous_value is not None and value - previous_value > gap_threshold:
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


def assign_binary_roles(column: Any, indent_type: str, _reference: float | None = None) -> None:
    """Choose the directional outer physical lane as entry; all others are body.

    Support count is diagnostic only. A section-opening page may contain just one
    real headword, so an already separated physical-indent lane remains a valid
    entry lane even when ``support == 1``. The only all-body case is a column
    with fewer than two distinct physical-indent lanes.
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

    entry = None
    if len(modes) >= 2:
        entry = (
            max(modes, key=_center)
            if str(indent_type) == "headword"
            else min(modes, key=_center)
        )

    if entry is not None:
        entry.role = "entry"
        for line in list(getattr(entry, "lines", []) or []):
            line.role = "entry"
        column.entry_modes = [entry]

    body_modes = [mode for mode in modes if mode is not entry]
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


def _remember_refined_entry_y(image: Any, understanding: Any, *, page_index: int) -> None:
    """Cache refined canonical separator Y without mutating Layout row geometry."""
    try:
        from .layout_entry_y_refinement import refined_entry_y_by_line

        values = refined_entry_y_by_line(
            image,
            understanding,
            page_index=int(page_index),
        )
    except Exception:
        values = {}
    _ENTRY_Y_BY_UNDERSTANDING[id(understanding)] = dict(values)
    # Keep the cache bounded in long GUI sessions.
    if len(_ENTRY_Y_BY_UNDERSTANDING) > 16:
        for key in list(_ENTRY_Y_BY_UNDERSTANDING)[:-8]:
            _ENTRY_Y_BY_UNDERSTANDING.pop(key, None)


def _install_page_understanding_finalization() -> None:
    from . import page_understanding

    if getattr(page_understanding, "_physical_indent_finalizer_installed", False):
        return

    original: Callable[..., Any] = page_understanding.understand_page

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        understanding = original(*args, **kwargs)
        normalize_layout_roles(understanding.layout)
        image = args[0] if args else kwargs.get("image")
        if image is not None:
            _remember_refined_entry_y(
                image,
                understanding,
                page_index=int(kwargs.get("page_index", 0) or 0),
            )
        return understanding

    page_understanding.understand_page = wrapped
    page_understanding._physical_indent_finalizer_installed = True


def _install_processing_entry_materializer() -> None:
    """Make ordinary drawing consume refined Y while preserving Layout roles."""
    from . import processing

    if getattr(processing, "_layout_entry_y_refinement_installed", False):
        return

    original: Callable[..., Any] = processing._ordinary_entries_from_layout_roles

    def materialize(understanding: Any):
        refined = _ENTRY_Y_BY_UNDERSTANDING.pop(id(understanding), {})
        if not refined:
            return original(understanding)

        layout = understanding.layout
        result = []
        for column in list(getattr(layout, "columns", []) or []):
            for line in list(getattr(column, "lines", []) or []):
                if str(getattr(line, "role", "") or "") != "entry":
                    continue
                canonical_y = int(
                    refined.get(
                        id(line),
                        int(layout.body_top) + int(getattr(line, "y0", 0) or 0),
                    )
                )
                source_x, source_y = layout.transform.canonical_to_source_point(
                    int(column.left),
                    canonical_y,
                    layout.source_size,
                )
                result.append(processing.Entry(
                    word="",
                    x=int(source_x),
                    y=int(source_y),
                    confidence=None,
                    ocr_source="page_understanding:ordinary_layout_role_y_refined",
                    issue_type="PAGE_UNDERSTANDING_ORDINARY_LAYOUT_ROLE_Y_REFINED",
                ))
        return result

    processing._ordinary_entries_from_layout_roles = materialize
    processing._layout_entry_y_refinement_installed = True


def install_physical_indent_inference() -> None:
    """Install the single physical-indent implementation used by all consumers."""
    from . import dictionary_page_design as page_design
    from .layout_profile_anchor import install_profile_layout_anchor

    if getattr(page_design, "_physical_indent_inference_installed", False):
        return

    # Profile analysis already aggregates multiple representative pages. Make
    # those stable project values the anchor before any per-page layout policy
    # is resolved in GUI, ordinary drawing, or spawned workers.
    install_profile_layout_anchor()

    page_design._line_runs = projection_line_runs
    page_design._indent_modes = physical_indent_modes
    page_design._assign_indent_semantics = assign_binary_roles
    _install_policy_finalization()
    _install_page_understanding_finalization()
    _install_processing_entry_materializer()
    page_design._physical_indent_inference_installed = True
