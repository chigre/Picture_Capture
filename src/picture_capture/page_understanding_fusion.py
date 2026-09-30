from __future__ import annotations

"""Arbitrate detector observations with shared page/symbol understanding.

Page understanding is not treated as an extra detector vote.  Evidence families
stay distinct:

* VB supplies geometric boundary evidence;
* Page Understanding supplies physical layout and designed block role;
* sampled Symbol Evidence supplies project-specific printed entry/bracket cues;
* OCR supplies semantic/textual evidence.

A conflict between independent positive evidence is preserved for review rather
than letting one family silently erase another.
"""

from dataclasses import replace

from .models import Entry
from .page_understanding import (
    PageUnderstanding,
    _column_for_source_point,
    block_evidence_for_entry,
)
from .symbol_evidence import fuse_symbol_evidence, is_symbol_positive_entry


def _append_issue(entry: Entry, issue: str) -> Entry:
    parts = [part for part in str(entry.issue_type or "").split(",") if part]
    if issue not in parts:
        parts.append(issue)
    return replace(entry, issue_type=",".join(parts))


def _entry_column(understanding: PageUnderstanding, entry: Entry) -> int:
    located = _column_for_source_point(
        understanding, int(entry.x), int(entry.y),
    )
    return int(located[0]) if located is not None else -1


def _entry_canonical_v(understanding: PageUnderstanding, entry: Entry) -> int:
    _u, v = understanding.layout.transform.source_to_canonical_point(
        int(entry.x), int(entry.y), understanding.layout.source_size,
    )
    return int(v)


def _semantic_positive(entry: Entry) -> bool:
    """Accepted OCR semantics are independent positive evidence."""
    return bool(
        str(entry.word or "").strip()
        and (
            str(entry.final_engine or "").strip()
            or str(entry.candidate_id or "").strip()
            or any(token in str(entry.ocr_source or "").lower() for token in (
                "paddle", "tesseract", "lens", "combined",
            ))
        )
    )


def _independent_positive(entry: Entry) -> bool:
    return _semantic_positive(entry) or is_symbol_positive_entry(entry)


def _merge_layout_position(detector: Entry, layout_entry: Entry) -> Entry:
    """Use layout geometry while preserving detector semantic/symbol metadata."""
    merged = replace(
        detector,
        x=int(layout_entry.x),
        y=int(layout_entry.y),
    )
    return _append_issue(merged, "PAGE_UNDERSTANDING_CONFIRMED")


def _layout_rescue(entry: Entry, mode: str) -> Entry:
    rescued = replace(
        entry,
        ocr_source=f"page_understanding:{mode}_layout_rescue",
    )
    return _append_issue(rescued, "PAGE_UNDERSTANDING_LAYOUT_RESCUE")


def _deduplicate(
    entries: list[Entry],
    understanding: PageUnderstanding,
) -> list[Entry]:
    reference = understanding.line_height
    ordered = sorted(
        entries,
        key=lambda item: (
            _entry_column(understanding, item),
            int(item.y),
            int(item.x),
        ),
    )
    result: list[Entry] = []
    for incoming in ordered:
        incoming_column = _entry_column(understanding, incoming)
        duplicate_index = next((
            index for index, current in enumerate(result)
            if _entry_column(understanding, current) == incoming_column
            and abs(int(current.y) - int(incoming.y)) <= reference * 0.28
        ), None)
        if duplicate_index is None:
            result.append(incoming)
            continue
        current = result[duplicate_index]

        def priority(item: Entry) -> tuple[int, int, int, int, float]:
            source = str(item.ocr_source or "")
            semantic = _semantic_positive(item)
            symbol = is_symbol_positive_entry(item)
            layout_confirmed = "PAGE_UNDERSTANDING_CONFIRMED" in str(item.issue_type or "")
            rescue = source.startswith("page_understanding:")
            return (
                1 if item.manually_selected else 0,
                1 if semantic else 0,
                1 if symbol else 0,
                1 if layout_confirmed else (0 if rescue else 0),
                float(item.confidence if item.confidence is not None else -1.0),
            )

        if priority(incoming) > priority(current):
            result[duplicate_index] = incoming
    return result


def _generic_body_indent_filter(
    entries: list[Entry],
    understanding: PageUnderstanding,
    *,
    mode: str,
) -> tuple[list[Entry], int, int]:
    """Use a proven inward body lane as negative layout evidence.

    Pure geometric candidates may be removed.  An already accepted OCR semantic
    positive or sampled explicit entry marker is independent contradictory
    evidence and therefore survives with a conflict marker.
    """
    if not understanding.generic_body_indent_reliable:
        return list(entries), 0, 0
    reference = understanding.line_height
    kept: list[Entry] = []
    suppressed = conflicts = 0
    for entry in entries:
        if entry.manually_selected:
            kept.append(entry)
            continue
        evidence = block_evidence_for_entry(understanding, entry)
        body_conflict = bool(
            evidence is not None
            and evidence.boundary_distance <= reference * 0.80
            and evidence.on_body_lane
            and evidence.role == "body"
        )
        if not body_conflict:
            kept.append(entry)
            continue
        if _independent_positive(entry):
            kept.append(_append_issue(entry, "PAGE_UNDERSTANDING_LAYOUT_CONFLICT"))
            conflicts += 1
            continue
        suppressed += 1
    return kept, suppressed, conflicts


def _hard_negative_blocks_layout_entry(
    layout_entry: Entry,
    understanding: PageUnderstanding,
    hard_negative_rows: list[tuple[int, int]],
) -> bool:
    if not hard_negative_rows:
        return False
    column = _entry_column(understanding, layout_entry)
    v = _entry_canonical_v(understanding, layout_entry)
    tolerance = understanding.line_height * 0.72
    return any(
        int(row_column) == column and abs(int(row_v) - v) <= tolerance
        for row_column, row_v in hard_negative_rows
    )


def _cjk_semantic_arbitration(
    entries: list[Entry],
    understanding: PageUnderstanding,
    *,
    mode: str,
    hard_negative_rows: list[tuple[int, int]] | None = None,
) -> tuple[list[Entry], dict[str, int]]:
    """Match detector events to authoritative CJK layout events one-to-one."""
    if not understanding.semantic_reliable:
        return list(entries), {
            "layout_confirmed": 0,
            "layout_rescued": 0,
            "layout_suppressed": 0,
            "layout_conflicts": 0,
            "hard_negative_blocked_rescue": 0,
        }

    reference = understanding.line_height
    # CJK ordinary fast-path stores sampled marker entries alongside layout
    # entries so it can return them without detector-specific arbitration.
    # Exclude those marker entries here: Symbol Evidence is fused independently
    # below and must not be counted again as Page Layout evidence.
    design = [
        entry for entry in understanding.semantic_entries
        if not is_symbol_positive_entry(entry)
    ]
    edges: list[tuple[int, int, int]] = []
    for detector_index, detector in enumerate(entries):
        detector_column = _entry_column(understanding, detector)
        if detector_column < 0:
            continue
        for design_index, layout_entry in enumerate(design):
            if _entry_column(understanding, layout_entry) != detector_column:
                continue
            delta = abs(int(detector.y) - int(layout_entry.y))
            if delta <= reference * 0.78:
                edges.append((delta, detector_index, design_index))
    edges.sort()

    detector_to_design: dict[int, int] = {}
    used_design: set[int] = set()
    for _delta, detector_index, design_index in edges:
        if detector_index in detector_to_design or design_index in used_design:
            continue
        detector_to_design[detector_index] = design_index
        used_design.add(design_index)

    output: list[Entry] = []
    confirmed = rescued = suppressed = conflicts = blocked = 0
    no_indent = understanding.layout.indent_type == "none"
    for detector_index, detector in enumerate(entries):
        design_index = detector_to_design.get(detector_index)
        if design_index is not None:
            output.append(_merge_layout_position(detector, design[design_index]))
            confirmed += 1
            continue
        if detector.manually_selected:
            output.append(detector)
            continue
        evidence = block_evidence_for_entry(understanding, detector)
        layout_negative = bool(
            not no_indent
            and evidence is not None
            and evidence.boundary_distance <= reference * 0.68
            and evidence.role in {"body", "other_indent"}
            and not evidence.in_entry_direction
        )
        if layout_negative:
            if _independent_positive(detector):
                output.append(_append_issue(
                    detector, "PAGE_UNDERSTANDING_LAYOUT_CONFLICT"
                ))
                conflicts += 1
            else:
                suppressed += 1
            continue
        output.append(detector)

    # Layout can rescue OCR misses, but never overrule a high-confidence OCR
    # hard-negative consensus at the same physical event.  Sampled explicit
    # entry markers are handled separately and therefore are not mistaken for a
    # layout-only rescue.
    negatives = list(hard_negative_rows or [])
    if mode in {"ocr", "combined", "ordinary"}:
        for design_index, layout_entry in enumerate(design):
            if design_index in used_design:
                continue
            if (
                mode in {"ocr", "combined"}
                and _hard_negative_blocks_layout_entry(
                    layout_entry, understanding, negatives,
                )
            ):
                blocked += 1
                continue
            output.append(_layout_rescue(layout_entry, mode))
            rescued += 1

    return output, {
        "layout_confirmed": confirmed,
        "layout_rescued": rescued,
        "layout_suppressed": suppressed,
        "layout_conflicts": conflicts,
        "hard_negative_blocked_rescue": blocked,
    }


def apply_page_understanding(
    entries: list[Entry],
    understanding: PageUnderstanding,
    *,
    mode: str,
    hard_negative_rows: list[tuple[int, int]] | None = None,
) -> list[Entry]:
    """Fuse Symbol + layout-role evidence without conflating detector votes.

    ``mode`` is one of ``ordinary``, ``ocr`` or ``combined``.  ``hard_negative_rows``
    contains canonical (column, V) positions where OCR review evidence reached
    the existing hard-negative consensus; layout-only rescue is forbidden there.
    """
    normalized_mode = str(mode or "ordinary").strip().lower()
    if normalized_mode not in {"ordinary", "ocr", "combined"}:
        normalized_mode = "ordinary"

    current = list(entries)
    stats = {
        "input": len(current),
        "symbol_confirmed": 0,
        "symbol_bracket_confirmed": 0,
        "symbol_rescued": 0,
        "generic_body_suppressed": 0,
        "layout_confirmed": 0,
        "layout_rescued": 0,
        "layout_suppressed": 0,
        "layout_conflicts": 0,
        "hard_negative_blocked_rescue": 0,
    }

    # Symbol Evidence is a separate family and is fused before layout-role
    # arbitration so subsequent conflicts can recognize a sampled entry marker
    # as an independent positive rather than plain geometry.
    current, symbol_stats = fuse_symbol_evidence(
        current,
        understanding.symbol_evidence,
        understanding,
    )
    stats.update({key: int(value) for key, value in symbol_stats.items()})

    # Generic/non-CJK sharing is deliberately conservative: only an explicitly
    # proven inward body lane is allowed to veto a geometric candidate.  OCR or
    # sampled-marker positives survive disagreement as explicit conflicts.
    current, generic_suppressed, generic_conflicts = _generic_body_indent_filter(
        current, understanding, mode=normalized_mode,
    )
    stats["generic_body_suppressed"] = generic_suppressed
    stats["layout_conflicts"] += generic_conflicts

    if understanding.role_model == "cjk":
        current, cjk_stats = _cjk_semantic_arbitration(
            current,
            understanding,
            mode=normalized_mode,
            hard_negative_rows=hard_negative_rows,
        )
        for key, value in cjk_stats.items():
            if key == "layout_conflicts":
                stats[key] += int(value)
            else:
                stats[key] = int(value)

    current = _deduplicate(current, understanding)
    stats["output"] = len(current)
    understanding.arbitration_stats.clear()
    understanding.arbitration_stats.update(stats)
    return current
