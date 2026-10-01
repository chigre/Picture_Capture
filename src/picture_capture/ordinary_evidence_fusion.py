from __future__ import annotations

"""Fuse OCR-independent ordinary-mode entry evidence.

The universal ordinary mode is intentionally an OR-fusion of independent page
structures:

* final Layout line role (physical indentation/topology);
* sampled structural symbols at a row start;
* oversized display-head typography.

No evidence family is allowed to veto another.  The canonical ordinary output
still materializes Layout rows, so non-indent evidence is promoted onto the
nearest physical row before separator-Y refinement.
"""

from typing import Any, Iterable

from .models import Entry


def _priority(entry: Entry) -> tuple[int, float]:
    source = str(getattr(entry, "ocr_source", "") or "")
    if source == "ordinary_symbol_evidence":
        family = 3
    elif source == "ordinary_large_head_evidence":
        family = 2
    elif "ordinary_layout_role" in source:
        family = 1
    else:
        family = 0
    confidence = float(entry.confidence) if entry.confidence is not None else 0.0
    return family, confidence


def fuse_ordinary_entry_evidence(
    groups: Iterable[Iterable[Entry]],
    *,
    line_height: float,
) -> list[Entry]:
    """OR-fuse ordinary candidates while collapsing the same physical entry."""
    candidates = [entry for group in groups for entry in group]
    if not candidates:
        return []

    y_tolerance = max(3, round(float(line_height) * 0.58))
    x_tolerance = max(4, round(float(line_height) * 1.10))

    candidates.sort(key=lambda item: (item.y, item.x, -_priority(item)[0]))
    fused: list[Entry] = []
    for candidate in candidates:
        duplicate_index: int | None = None
        for index, existing in enumerate(fused):
            if (
                abs(int(candidate.y) - int(existing.y)) <= y_tolerance
                and abs(int(candidate.x) - int(existing.x)) <= x_tolerance
            ):
                duplicate_index = index
                break
        if duplicate_index is None:
            fused.append(candidate)
            continue
        existing = fused[duplicate_index]
        if _priority(candidate) > _priority(existing):
            fused[duplicate_index] = candidate

    return fused


def promote_evidence_to_layout_roles(
    understanding: Any,
    evidence_entries: Iterable[Entry],
) -> int:
    """Promote nearest physical rows to entry without changing row geometry.

    This is deliberately one-way: visual symbol / large-head evidence may add
    an entry role, but can never turn an indent-derived entry back into body.
    The final separator Y is still refined later by the shared Y-refinement
    module when the row is materialized.
    """
    layout = understanding.layout
    line_height = max(4.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    max_distance = max(5.0, line_height * 0.90)
    promoted = 0

    # Build a source-space index because evidence modules emit source PDIC-like
    # coordinates while Layout rows live in canonical coordinates.
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
            # Same-column rows should have a source-edge X close to the evidence
            # marker.  A generous allowance handles rotated/mirrored pages.
            if dx > max(line_height * 2.0, 12.0):
                continue
            score = float(dy) + 0.15 * float(dx)
            if best is None or score < best[0]:
                best = (score, column, line)
        if best is None:
            continue
        _score, _column, line = best
        if str(getattr(line, "role", "") or "") != "entry":
            line.role = "entry"
            promoted += 1

    return promoted
