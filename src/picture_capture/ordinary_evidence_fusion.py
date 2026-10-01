from __future__ import annotations

"""OR-promote OCR-independent ordinary evidence onto physical Layout rows.

Universal ordinary drawing keeps one canonical output model: final Layout
``line.role`` values.  Independent evidence families (indent topology, sampled
symbols, oversized display heads) therefore meet here by one-way promotion.
No evidence family may demote or veto another, and separator Y remains owned by
the shared Y-refinement module after role materialization.

The same fusion point also records *why* a row became an entry and whether it is
regular or oversized.  This structural metadata is consumed later by OCR crops
and proofreading; it never changes the role decision itself.
"""

from typing import Any, Iterable

from .entry_classification import register_layout_line_classification
from .models import Entry


def promote_evidence_to_layout_roles(
    understanding: Any,
    evidence_entries: Iterable[Entry],
) -> int:
    """Promote nearest physical rows to entry and retain evidence classification."""
    layout = understanding.layout
    line_height = max(4.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    max_distance = max(5.0, line_height * 0.90)
    promoted = 0

    # Evidence modules emit source-image points while Layout rows live in the
    # canonical page space.  Build one source-space row index so rotation and
    # mirroring remain transparent to every evidence family.
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
        # this row an entry.  In particular, large-head evidence must be able to
        # upgrade a previously indented/symbol row from regular to oversized.
        register_layout_line_classification(line, evidence)
        if str(getattr(line, "role", "") or "") != "entry":
            line.role = "entry"
            promoted += 1

    return promoted
