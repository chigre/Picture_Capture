from __future__ import annotations

"""Generic/non-CJK block-role evidence from a proven body-indent page design.

The detector event is a separator, but the semantic unit is the *visual block
that begins after that separator*.  This module therefore never classifies a
marker by comparing it to an abstract midpoint boundary.  Instead it follows
the marker downward to the next observed text block and asks which repeated
indent lane that block belongs to.

For an explicit ``正文缩进`` profile, once Page Understanding has independently
proved a stable inward body lane plus a repeated outer lane, the two directions
can be used symmetrically:

* a detector separator followed by a body-lane block is negative layout
  evidence;
* a repeated outer-lane block start is positive layout evidence and may rescue
  a detector miss.

This remains an evidence family rather than an authoritative detector.  OCR
hard negatives can still block layout-only rescue in OCR/combined mode, and no
entry-role inference is made for ``无明显缩进`` pages.
"""

from dataclasses import dataclass

from . import dictionary_page_design as base
from .models import Entry
from .page_understanding import PageUnderstanding, _column_for_source_point


@dataclass(frozen=True, slots=True)
class GenericBlockEvidence:
    column_index: int
    role: str
    block_top_y: int
    block_distance: float
    on_body_lane: bool
    on_entry_lane: bool
    anchor_offset_ratio: float | None


def _stable_outer_mode(
    column: base.ColumnDesign,
    reference: float,
) -> base.IndentMode | None:
    """Return one repeated outer lane opposite a proven inward body lane."""
    body = column.body_mode
    if body is None or body.support < 3:
        return None
    total = max(1, sum(mode.support for mode in column.indent_modes))
    minimum_support = max(3, round(total * 0.08))
    eligible = [
        mode
        for mode in column.indent_modes
        if mode is not body
        and float(body.center) - float(mode.center) >= reference * 0.30
        and mode.support >= minimum_support
    ]
    if not eligible:
        return None
    # Repetition establishes the family; the outermost position breaks support
    # ties.  We intentionally do not use a fixed absolute-X threshold.
    return max(
        eligible,
        key=lambda mode: (int(mode.support), -float(mode.center)),
    )


def _line_ids(mode: base.IndentMode | None) -> set[int]:
    if mode is None:
        return set()
    return {id(line) for line in mode.lines}


def block_after_separator(
    understanding: PageUnderstanding,
    entry: Entry,
) -> GenericBlockEvidence | None:
    """Classify the first real text block after one detector separator.

    VB and OCR separators do not necessarily use the same midpoint convention as
    Page Design.  Matching a separator to the nearest theoretical boundary can
    therefore select the wrong row.  We instead find the first observed line
    whose top is at, or just below, the marker.
    """
    if (
        understanding.role_model != "generic"
        or not understanding.physical_reliable
        or not understanding.generic_body_indent_reliable
        or understanding.layout.indent_type != "body"
    ):
        return None

    located = _column_for_source_point(
        understanding, int(entry.x), int(entry.y),
    )
    if located is None:
        return None
    column_index, _u, v = located
    layout = understanding.layout
    if not (0 <= column_index < len(layout.columns)):
        return None
    column = layout.columns[column_index]
    if not column.lines:
        return None

    reference = understanding.line_height
    local_v = float(v - int(layout.body_top))
    # A rendered separator can land a few pixels into anti-aliased/overshoot
    # pixels of the next row.  Permit a small negative slack, but never jump to a
    # previous text row merely because its old midpoint boundary is closer.
    slack = reference * 0.18
    following = [
        line for line in column.lines
        if float(line.y0) >= local_v - slack
    ]
    if not following:
        return None
    line = min(following, key=lambda item: float(item.y0))
    distance = max(0.0, float(line.y0) - local_v)

    body = column.body_mode
    outer = _stable_outer_mode(column, reference)
    body_ids = _line_ids(body)
    outer_ids = _line_ids(outer)
    on_body = id(line) in body_ids
    on_entry = id(line) in outer_ids

    anchor_offset_ratio: float | None = None
    if body is not None and line.anchor_x is not None:
        anchor_offset_ratio = (
            float(line.anchor_x) - float(body.center)
        ) / max(1.0, reference)

    _x, source_y = layout.transform.canonical_to_source_point(
        int(column.left),
        int(layout.body_top) + int(line.y0),
        layout.source_size,
    )
    role = "entry" if on_entry else "body" if on_body else "other_indent"
    return GenericBlockEvidence(
        column_index=int(column_index),
        role=role,
        block_top_y=int(source_y),
        block_distance=float(distance),
        on_body_lane=bool(on_body),
        on_entry_lane=bool(on_entry),
        anchor_offset_ratio=anchor_offset_ratio,
    )


def generic_entry_candidates(
    understanding: PageUnderstanding,
) -> list[Entry]:
    """Return repeated outer-lane block starts as layout-only entry candidates."""
    if (
        understanding.role_model != "generic"
        or not understanding.physical_reliable
        or not understanding.generic_body_indent_reliable
        or understanding.layout.indent_type != "body"
    ):
        return []

    layout = understanding.layout
    reference = understanding.line_height
    result: list[Entry] = []
    for column in layout.columns:
        outer = _stable_outer_mode(column, reference)
        if outer is None:
            continue
        for line in sorted(outer.lines, key=lambda item: int(item.y0)):
            boundary_local = int(base._boundary_before(
                column.lines, int(line.y0), reference,
            ))
            source_x, source_y = layout.transform.canonical_to_source_point(
                int(column.left),
                int(layout.body_top) + boundary_local,
                layout.source_size,
            )
            result.append(Entry(
                word="",
                x=int(source_x),
                y=int(source_y),
                confidence=None,
                ocr_source="page_understanding:generic_entry_lane",
                issue_type="PAGE_UNDERSTANDING_GENERIC_ENTRY_LANE",
            ))
    return result
