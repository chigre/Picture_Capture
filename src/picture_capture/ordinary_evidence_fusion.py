from __future__ import annotations

"""Fuse OCR-independent ordinary evidence onto physical Layout rows.

Universal ordinary drawing keeps one canonical output model: final Layout
``line.role`` values. Independent evidence families (indent topology, sampled
symbols, oversized display heads) therefore meet here.

Regular evidence is one-way promotion: it may promote a physical row to entry
but never demotes another family. Positively detected oversized display heads
are the deliberate exception because their physical extent already tells us the
row semantics: the first/top logical row is the headword boundary and every
later logical row inside the same glyph is continuation/body. That structural
fact must override indentation, including cases where the first-row indent is
small or body-like.

The same fusion point also records *why* a row became an entry and whether it is
regular or oversized. This structural metadata is consumed later by OCR crops
and proofreading; it never changes separator-Y refinement.
"""

from typing import Any, Iterable

from .entry_classification import register_layout_line_classification
from .models import Entry
from .ordinary_large_head_role_guard import strong_ordinary_large_head


def _is_oversized_head_evidence(evidence: Entry) -> bool:
    source = str(getattr(evidence, "ocr_source", "") or "")
    issue = str(getattr(evidence, "issue_type", "") or "")
    return bool(
        getattr(evidence, "ocr_oversized_cjk", False)
        or "ordinary_large_head_evidence" in source
        or "OVERSIZED_DISPLAY_HEAD" in issue
    )


def _force_oversized_head_rows(
    understanding: Any,
    evidence: Entry,
) -> tuple[bool, int]:
    """Force one positively detected large head to ``entry + body...`` rows.

    Returns ``(handled, promoted_count)``. ``handled`` is false only when the
    evidence cannot be mapped to any plausible Layout row, in which case the
    caller may fall back to ordinary nearest-row promotion.
    """
    layout = understanding.layout
    columns = list(getattr(layout, "columns", []) or [])
    if not columns:
        return False, 0

    line_height = max(4.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    observed_height = float(getattr(evidence, "ocr_visual_run_height", 0.0) or 0.0)
    if observed_height < line_height * 1.20:
        return False, 0

    source_size = tuple(getattr(layout, "source_size", (0, 0)) or (0, 0))
    body_top = float(getattr(layout, "body_top", 0) or 0)
    try:
        canonical_x, canonical_y = layout.transform.source_to_canonical_point(
            int(evidence.x), int(evidence.y), source_size
        )
        canonical_x = float(canonical_x)
        top = float(canonical_y) - body_top
    except (AttributeError, TypeError, ValueError):
        return False, 0

    containing = [
        column
        for column in columns
        if float(getattr(column, "left", 0) or 0) - 1.0
        <= canonical_x
        <= float(getattr(column, "right", 0) or 0) + 1.0
    ]
    column = min(
        containing or columns,
        key=lambda item: abs(float(getattr(item, "left", 0) or 0) - canonical_x),
    )

    bottom = top + observed_height
    top_tolerance = min(line_height * 0.45, max(3.0, observed_height * 0.15))
    lines = list(getattr(column, "lines", []) or [])
    inside = [
        line
        for line in lines
        if float(getattr(line, "y0", 0) or 0) >= top - top_tolerance
        and float(getattr(line, "y0", 0) or 0) < bottom
    ]
    if not inside:
        return False, 0

    # The headword boundary belongs to the first logical row at the glyph top,
    # not whichever row happens to have the strongest/nearest indent evidence.
    # Prefer the earliest row whose start is within the top tolerance. This
    # intentionally makes a tiny/body-like indent irrelevant once the glyph has
    # been independently identified as oversized.
    keeper = min(
        inside,
        key=lambda line: (
            float(getattr(line, "y0", 0) or 0),
            float(getattr(line, "y1", 0) or 0),
        ),
    )

    was_entry = str(getattr(keeper, "role", "") or "") == "entry"
    keeper.role = "entry"
    register_layout_line_classification(keeper, evidence)

    # Every later logical row that starts within the observed glyph extent is a
    # continuation row. Demote it even if indent/symbol evidence previously
    # promoted it; the positive large-head box is stronger structural evidence.
    keeper_y0 = float(getattr(keeper, "y0", 0) or 0)
    for line in inside:
        if line is keeper:
            continue
        if float(getattr(line, "y0", 0) or 0) > keeper_y0:
            line.role = "body"

    return True, 0 if was_entry else 1


def promote_evidence_to_layout_roles(
    understanding: Any,
    evidence_entries: Iterable[Entry],
) -> int:
    """Promote evidence to Layout roles, with hard large-head row semantics."""
    layout = understanding.layout
    line_height = max(4.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    max_distance = max(5.0, line_height * 0.90)
    promoted = 0

    # Evidence modules emit source-image points while Layout rows live in the
    # canonical page space. Build one source-space row index so rotation and
    # mirroring remain transparent to regular evidence families.
    row_index: list[tuple[Any, Any, int, int]] = []
    for column in list(getattr(layout, "columns", []) or []):
        for line in list(getattr(column, "lines", []) or []):
            canonical_y = int(layout.body_top) + int(line.y0)
            source_x, source_y = layout.transform.canonical_to_source_point(
                int(column.left),
                canonical_y,
                layout.source_size,
            )
            row_index.append((column, line, int(source_x), int(source_y)))

    for evidence in evidence_entries:
        if _is_oversized_head_evidence(evidence):
            # Weak ordinary-large-head observations are deliberately consumed
            # here. Letting them fall through to generic nearest-row promotion
            # would recreate the false-positive -> extra-entry amplification
            # that the former runtime wrapper blocked.
            if not strong_ordinary_large_head(evidence, layout):
                continue

            handled, added = _force_oversized_head_rows(understanding, evidence)
            if handled:
                promoted += added
                continue

        best: tuple[float, Any, Any] | None = None
        for column, line, source_x, source_y in row_index:
            dx = abs(int(evidence.x) - source_x)
            dy = abs(int(evidence.y) - source_y)
            if dy > max_distance:
                continue
            if dx > max(line_height * 2.0, 12.0):
                continue
            score = float(dy) + 0.15 * float(dx)
            if best is None or score < best[0]:
                best = (score, column, line)
        if best is None:
            continue
        _score, _column, line = best
        # Metadata is recorded even when another evidence family already made
        # this row an entry. Large-head fallback evidence can still upgrade a
        # previously indented/symbol row from regular to oversized.
        register_layout_line_classification(line, evidence)
        if str(getattr(line, "role", "") or "") != "entry":
            line.role = "entry"
            promoted += 1

    return promoted
