from __future__ import annotations

"""Semantic-aware horizontal registration for dictionary page instances.

``manual_x`` is a Project Profile template coordinate.  Per-page adaptation must
therefore estimate how the *scan* moved relative to that template, not ask which
text lane has the most ink.  The distinction matters for body-indented
Latin dictionaries: definition/continuation rows greatly outnumber entry rows,
so a raw projection can mistake the inward body lane for the physical column
edge.

This module keeps registration OCR-free.  It inspects repeated visual line-start
families around the expected Project column locations, interprets them using the
explicit three-state indentation semantics, and reduces the observations to one
page-wide translation.  Individual columns are not allowed to invent unrelated
X origins.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from . import dictionary_page_design as base
from .layout_detection import LayoutEstimate, analysis_ink_mask
from .models import AppSettings
from .profile_indent_ui import indent_type_label


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
) -> tuple[int, int] | None:
    """Return (absolute outer-lane X, support) for one expected column.

    The search window is deliberately centered on the Project template rather
    than on the projection detector's left edge.  That lets a body-indented
    page recover a sparse outer entry lane even when the dominant body lane is
    dozens of pixels inward.  Later columns are additionally prevented from
    reaching back into the preceding Project column.
    """
    height, width = ink.shape
    if bottom <= top or width <= 1:
        return None

    shift_window = max(
        14,
        round(seed * 2.2),
        round(max(1, column_width) * 0.035),
    )
    shift_window = min(shift_window, max(18, round(max(1, column_width) * 0.12)))
    left = max(0, int(search_left_floor), int(nominal_x) - shift_window)
    lead = max(
        round(seed * 6.0),
        round(max(1, column_width) * 0.24),
        96,
    )
    right = min(width, int(nominal_x) + lead)
    if right - left < 12:
        return None

    # Include a little context above an automatically detected body top so the
    # first entry on a section-opening page remains observable.
    local_top = max(0, int(top) - max(4, round(seed * 1.25)))
    local_bottom = min(height, int(bottom))
    strip = ink[local_top:local_bottom, left:right]
    if strip.size == 0:
        return None

    runs = base._line_runs(strip, seed)
    reference = base._normal_height([runs], seed)
    runs = base._line_runs(strip, reference)
    lines: list[base.LayoutLine] = []
    previous_end = 0
    for y0, y1 in runs:
        line = base._line_feature(0, strip, y0, y1, reference, previous_end)
        previous_end = max(previous_end, y1)
        if line is not None and reference * 0.45 <= line.height <= reference * 1.55:
            lines.append(line)
    if len(lines) < 4:
        return None

    modes = base._indent_modes(lines, reference)
    if not modes:
        return None

    chosen: base.IndentMode | None = None
    if semantics == "正文缩进":
        column = base.ColumnDesign(0, left, right, 0)
        column.lines = list(lines)
        column.indent_modes = list(modes)
        base._assign_indent_semantics(column, "body", reference)
        # The physical/entry lane is outside the dominant inward body lane.
        # Prefer a repeated entry family; do not infer an outer edge from a
        # single speck or punctuation fragment.
        eligible = [mode for mode in column.entry_modes if mode.support >= 2]
        if eligible:
            # Stronger repetition wins; distance to the Project edge only breaks
            # ties.  This avoids a two-row noise lane stealing the registration.
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
        base._assign_indent_semantics(column, "headword", reference)
        # For headword-indent pages the ordinary body lane is the outer physical
        # lane and is therefore the correct column registration anchor.
        chosen = column.body_mode
    else:
        # No-indent pages have no directional entry/body meaning.  The most
        # repeated line-start family is the best registration anchor.
        total = max(1, sum(mode.support for mode in modes))
        stable = [
            mode for mode in modes
            if mode.support >= max(2, round(total * 0.08))
        ] or list(modes)
        chosen = max(stable, key=lambda mode: mode.support)

    if chosen is None or chosen.support < 2:
        return None

    # ``anchor_x`` groups full-height glyphs.  Once the family is selected, use
    # first ink to recover the visual outer lane, preserving small prefixes.
    firsts = [float(line.first_x) for line in chosen.lines]
    if not firsts:
        return None
    candidate = int(round(left + float(np.median(firsts))))
    max_shift = max(
        round(reference * 2.6),
        round(max(1, column_width) * 0.065),
        18,
    )
    if abs(candidate - int(nominal_x)) > max_shift:
        return None
    return candidate, int(chosen.support)


def _robust_page_delta(
    candidates: list[tuple[int, int, int]],
    *,
    projection_deltas: list[int],
    semantics: str,
    max_shift: int,
) -> tuple[int, str]:
    """Reduce column observations to one page-wide scan translation."""
    usable = [
        (int(candidate_x) - int(nominal_x), int(support))
        for nominal_x, candidate_x, support in candidates
        if abs(int(candidate_x) - int(nominal_x)) <= max_shift
    ]
    if usable:
        # Repeat each delta only up to a modest cap: support should stabilize a
        # lane, not let one verbose column dominate the whole page.
        expanded: list[int] = []
        for delta, support in usable:
            expanded.extend([delta] * max(1, min(4, support)))
        values = np.asarray(expanded, dtype=float)
        if semantics == "正文缩进":
            # Even the selected outer entry family measures first printed ink,
            # which can sit a few pixels inside the Project boundary.  Use the
            # lower cross-column consensus so that glyph inset cannot become a
            # fake page translation; inward body contamination is even farther
            # right and therefore cannot win this statistic.
            delta = int(round(float(np.quantile(values, 0.20))))
            method = "semantic_outer_lane"
        else:
            delta = int(round(float(np.median(values))))
            method = "semantic_lane"
        return max(-max_shift, min(max_shift, delta)), method

    fallback = [delta for delta in projection_deltas if abs(delta) <= max_shift]
    if fallback:
        if semantics == "正文缩进":
            # A raw projection can land on the inward body lane, which can only
            # move the detected start further into the column.  The outermost
            # plausible projection delta is therefore the safe fallback.
            delta = min(fallback)
            method = "projection_outer"
        else:
            delta = int(round(float(np.median(np.asarray(fallback, dtype=float)))))
            method = "projection_consensus"
        return max(-max_shift, min(max_shift, int(delta))), method

    return 0, "project_fallback"


def _narrow_persistent_rule_columns(body: np.ndarray, seed: float) -> np.ndarray:
    """Keep only narrow persistent-X runs that plausibly represent divider rules.

    A broad aligned text band can also have high vertical persistence on
    synthetic pages or unusually repetitive dictionaries.  Removing every
    persistent column would erase the very line-start families needed for X
    registration.  Printed divider rules are narrow; broad runs stay as text.
    """
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
) -> XRegistrationResult:
    """Register current-page X as a translation of the Project template.

    ``settings.manual_x`` must still contain the Project/Profile value.  Other
    selected auto fields may already have been applied; this is intentional, so
    a page whose width/gutter scale was explicitly allowed to change uses that
    resolved pitch while still preserving one shared X origin.
    """
    project_x = max(0, int(getattr(settings, "manual_x", 0) or 0))
    nominal = _nominal_starts(settings)
    if not nominal:
        return XRegistrationResult(project_x, 0, "project_fallback")

    gray = np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8)
    ink = analysis_ink_mask(gray, settings)
    seed = max(8.0, float(getattr(settings, "character_height", 26) or 26))
    top = max(0, int(getattr(settings, "start_y", 0) or 0))
    bottom = min(canonical.height, max(top + 1, int(getattr(estimate, "bottom_y", canonical.height))))
    semantics = indent_type_label(settings)
    column_width = max(8, int(getattr(settings, "column_width", 700) or 700))
    gutter = max(0, int(getattr(settings, "gutter", 0) or 0))

    # Persistent divider rules can turn every row in a leading strip "active".
    # Remove only narrow persistent runs.  Broad persistent regions may simply
    # be repeated text columns and must remain available to lane inference.
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
            # Stay out of the previous text column while retaining most of the
            # gutter as room for legitimate scan translation.
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
    max_shift = max(
        20,
        round(seed * 2.7),
        round(column_width * 0.075),
    )
    delta, method = _robust_page_delta(
        lane_candidates,
        projection_deltas=projection_deltas,
        semantics=semantics,
        max_shift=max_shift,
    )
    value = max(0, project_x + int(delta))
    return XRegistrationResult(
        value=value,
        delta=int(delta),
        method=method,
        lane_candidates=tuple(candidate for _expected, candidate, _support in lane_candidates),
        projection_x=int(getattr(estimate, "manual_x", project_x)),
    )
