from __future__ import annotations

"""Semantic-aware horizontal registration for dictionary page instances.

``manual_x`` is a Project Profile template coordinate. Per-page adaptation is
therefore a small page-wide translation of that stable template, never a fresh
column-origin estimate. Multiple columns should support the same translation;
a sparse first column must not drag every column to a new X position.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from . import dictionary_page_design as base
from .layout_detection import LayoutEstimate, analysis_ink_mask
from .models import AppSettings
from .profile_indent_ui import indent_type_label


# Preserve the legacy installed/uninstalled runtime when no explicit ops are passed.


@dataclass(frozen=True, slots=True)
class XRegistrationResult:
    value: int
    delta: int
    method: str
    lane_candidates: tuple[int, ...] = ()
    projection_x: int | None = None


def _column_offsets(settings: AppSettings, count: int) -> list[int]:
    raw = list(getattr(settings, "column_start_offsets", []) or [])
    result: list[int] = []
    for index in range(count):
        try:
            result.append(int(round(float(raw[index]))) if index < len(raw) else 0)
        except (TypeError, ValueError):
            result.append(0)
    return result


def _nominal_starts(settings: AppSettings) -> list[int]:
    count = max(1, min(12, int(getattr(settings, "columns", 1) or 1)))
    width = max(8, int(getattr(settings, "column_width", 700) or 700))
    gutter = max(0, int(getattr(settings, "gutter", 0) or 0))
    manual_x = max(0, int(getattr(settings, "manual_x", 0) or 0))
    offsets = _column_offsets(settings, count)
    return [
        manual_x + index * (width + gutter) + offsets[index]
        for index in range(count)
    ]


def _line_family_candidate(
    ink: np.ndarray,
    *,
    top: int,
    bottom: int,
    nominal_x: int,
    column_width: int,
    seed: float,
    semantics: str,
    search_left_floor: int = 0,
    ops: base.LayoutPrimitiveOps | None = None,
) -> tuple[int, int] | None:
    ops = base.current_layout_ops() if ops is None else ops
    height, width = ink.shape
    if bottom <= top or width <= 1:
        return None

    shift_window = max(14, round(seed * 2.2), round(max(1, column_width) * 0.035))
    shift_window = min(shift_window, max(18, round(max(1, column_width) * 0.12)))
    left = max(0, int(search_left_floor), int(nominal_x) - shift_window)
    lead = max(round(seed * 6.0), round(max(1, column_width) * 0.24), 96)
    right = min(width, int(nominal_x) + lead)
    if right - left < 12:
        return None

    local_top = max(0, int(top) - max(4, round(seed * 1.25)))
    local_bottom = min(height, int(bottom))
    strip = ink[local_top:local_bottom, left:right]
    if strip.size == 0:
        return None

    runs = ops.line_runs(strip, seed)
    reference = base._normal_height([runs], seed)
    runs = ops.line_runs(strip, reference)
    lines: list[base.LayoutLine] = []
    previous_end = 0
    for y0, y1 in runs:
        line = ops.line_feature(0, strip, y0, y1, reference, previous_end)
        previous_end = max(previous_end, y1)
        if line is not None and reference * 0.45 <= line.height <= reference * 1.55:
            lines.append(line)
    if len(lines) < 4:
        return None

    modes = ops.indent_modes(lines, reference)
    if not modes:
        return None

    chosen: base.IndentMode | None = None
    if semantics == "正文缩进":
        column = base.ColumnDesign(0, left, right, 0)
        column.lines = list(lines)
        column.indent_modes = list(modes)
        ops.assign_indent_semantics(column, "body", reference)
        eligible = [mode for mode in column.entry_modes if mode.support >= 2]
        if eligible:
            chosen = max(
                eligible,
                key=lambda mode: (
                    min(12, int(mode.support)),
                    -abs((left + float(mode.center)) - float(nominal_x)),
                ),
            )
    elif semantics == "词头缩进":
        column = base.ColumnDesign(0, left, right, 0)
        column.lines = list(lines)
        column.indent_modes = list(modes)
        ops.assign_indent_semantics(column, "headword", reference)
        chosen = column.body_mode
    else:
        total = max(1, sum(mode.support for mode in modes))
        stable = [mode for mode in modes if mode.support >= max(2, round(total * 0.08))] or list(modes)
        chosen = max(stable, key=lambda mode: mode.support)

    if chosen is None or chosen.support < 2:
        return None
    firsts = [float(line.first_x) for line in chosen.lines]
    if not firsts:
        return None
    candidate = int(round(left + float(np.median(firsts))))
    max_shift = max(round(reference * 2.6), round(max(1, column_width) * 0.065), 18)
    if abs(candidate - int(nominal_x)) > max_shift:
        return None
    return candidate, int(chosen.support)


def _consensus_delta(
    deltas: list[int],
    *,
    max_shift: int,
    tolerance: int,
) -> tuple[int | None, int]:
    """Return the strongest page-wide delta cluster and its column support."""
    if not deltas:
        return None, 0
    ordered = sorted(int(value) for value in deltas if abs(int(value)) <= max_shift)
    if not ordered:
        return None, 0
    best: list[int] = []
    for value in ordered:
        cluster = [other for other in ordered if abs(other - value) <= tolerance]
        if len(cluster) > len(best):
            best = cluster
        elif len(cluster) == len(best) and cluster:
            if abs(float(np.median(cluster))) < abs(float(np.median(best))):
                best = cluster
    if not best:
        return None, 0
    return int(round(float(np.median(np.asarray(best, dtype=float))))), len(best)


def _robust_page_delta(
    candidates: list[tuple[int, int, int]],
    *,
    projection_deltas: list[int],
    semantics: str,
    max_shift: int,
    expected_columns: int,
    seed: float,
) -> tuple[int, str]:
    """Reduce observations to one bounded page translation.

    A single sparse column can no longer move the whole page. With two or more
    expected columns, at least two column observations must agree before lane
    evidence is allowed to translate the Project/Profile template. Projection
    starts provide an independent multi-column fallback.
    """
    lane_deltas = [
        int(candidate_x) - int(nominal_x)
        for nominal_x, candidate_x, _support in candidates
        if abs(int(candidate_x) - int(nominal_x)) <= max_shift
    ]
    tolerance = max(3, min(12, int(round(max(8.0, seed) * 0.22))))
    lane_delta, lane_support = _consensus_delta(
        lane_deltas,
        max_shift=max_shift,
        tolerance=tolerance,
    )
    required = 1 if int(expected_columns) <= 1 else 2
    if lane_delta is not None and lane_support >= required:
        return max(-max_shift, min(max_shift, int(lane_delta))), "multi_column_semantic"

    projection_delta, projection_support = _consensus_delta(
        list(projection_deltas),
        max_shift=max_shift,
        tolerance=tolerance,
    )
    if projection_delta is not None and projection_support >= required:
        return max(-max_shift, min(max_shift, int(projection_delta))), "multi_column_projection"

    # If no multi-column agreement exists, keep the stable Profile X. A lone
    # first-column observation is exactly the failure mode seen on sparse opening
    # pages and is not sufficient evidence for a page-wide translation.
    return 0, "profile_anchor"


def _narrow_persistent_rule_columns(body: np.ndarray, seed: float) -> np.ndarray:
    raw = base._persistent_rule_mask(body, seed)
    if raw.size == 0 or not bool(raw.any()):
        return raw
    result = np.zeros_like(raw, dtype=bool)
    max_rule_width = max(3, round(seed * 0.28))
    for x0, x1 in base._runs(raw):
        if x1 - x0 <= max_rule_width:
            result[x0:x1] = True
    return result


def register_page_manual_x(
    canonical: Image.Image,
    settings: AppSettings,
    estimate: LayoutEstimate,
    *,
    ops: base.LayoutPrimitiveOps | None = None,
) -> XRegistrationResult:
    """Register current-page X as one shared translation of Profile columns."""
    ops = base.current_layout_ops() if ops is None else ops
    project_x = max(0, int(getattr(settings, "manual_x", 0) or 0))
    nominal = _nominal_starts(settings)
    if not nominal:
        return XRegistrationResult(project_x, 0, "profile_anchor")

    gray = np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8)
    ink = analysis_ink_mask(gray, settings)
    seed = max(8.0, float(getattr(settings, "character_height", 26) or 26))
    top = max(0, int(getattr(settings, "start_y", 0) or 0))
    bottom = min(canonical.height, max(top + 1, int(getattr(estimate, "bottom_y", canonical.height))))
    semantics = indent_type_label(settings)
    column_width = max(8, int(getattr(settings, "column_width", 700) or 700))
    gutter = max(0, int(getattr(settings, "gutter", 0) or 0))

    rule_body = ink[max(0, top):max(top + 1, bottom), :]
    rules = _narrow_persistent_rule_columns(rule_body, seed)
    if rules.size and bool(rules.any()):
        ink = ink.copy()
        ink[:, rules] = False

    lane_candidates: list[tuple[int, int, int]] = []
    for index, expected in enumerate(nominal):
        search_left_floor = 0
        if index > 0:
            previous_right = nominal[index - 1] + column_width
            search_left_floor = previous_right + max(1, round(gutter * 0.10))
        observed = _line_family_candidate(
            ink,
            top=top,
            bottom=bottom,
            nominal_x=expected,
            column_width=column_width,
            seed=seed,
            semantics=semantics,
            search_left_floor=search_left_floor,
            ops=ops,
        )
        if observed is not None:
            candidate_x, support = observed
            lane_candidates.append((expected, candidate_x, support))

    detected = list(tuple(getattr(estimate, "column_starts", ()) or ()))
    projection_deltas = [
        int(detected[index]) - int(expected)
        for index, expected in enumerate(nominal)
        if index < len(detected)
    ]

    # Translation is intentionally much tighter than raw layout-search windows:
    # the Project/Profile already defines the dictionary template. Auto X only
    # registers scan movement around that stable template.
    max_shift = max(8, min(24, round(seed * 0.45), round(column_width * 0.018)))
    delta, method = _robust_page_delta(
        lane_candidates,
        projection_deltas=projection_deltas,
        semantics=semantics,
        max_shift=max_shift,
        expected_columns=len(nominal),
        seed=seed,
    )
    value = max(0, project_x + int(delta))
    return XRegistrationResult(
        value=value,
        delta=int(delta),
        method=method,
        lane_candidates=tuple(candidate for _expected, candidate, _support in lane_candidates),
        projection_x=int(getattr(estimate, "manual_x", project_x)),
    )
