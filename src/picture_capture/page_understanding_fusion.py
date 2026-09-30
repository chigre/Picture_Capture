from __future__ import annotations

"""Arbitrate detector observations with the shared Page Understanding layer.

Page understanding is not treated as an extra detector vote.  It supplies a
separate evidence family: page/column geometry and the designed role of the
block below a candidate.  VB remains geometric boundary evidence; OCR remains
semantic evidence.
"""

from dataclasses import replace

from .models import Entry
from .page_understanding import (
    PageUnderstanding,
    _column_for_source_point,
    block_evidence_for_entry,
)


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


def _merge_layout_position(detector: Entry, layout_entry: Entry) -> Entry:
    """Use layout geometry while preserving OCR/combined semantic metadata."""
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

        def priority(item: Entry) -> tuple[int, int, int, float]:
            source = str(item.ocr_source or "")
            semantic = bool(item.word or item.candidate_id or item.final_engine)
            layout_confirmed = "PAGE_UNDERSTANDING_CONFIRMED" in str(item.issue_type or "")
            rescue = source.startswith("page_understanding:")
            return (
                1 if item.manually_selected else 0,
                1 if semantic else 0,
                1 if layout_confirmed else (0 if rescue else 0),
                float(item.confidence if item.confidence is not None else -1.0),
            )

        if priority(incoming) > priority(current):
            result[duplicate_index] = incoming
    return result


def _generic_body_indent_filter(
    entries: list[Entry],
    understanding: PageUnderstanding,
) -> tuple[list[Entry], int]:
    """Remove only candidates proven to start on the inward body lane."""
    if not understanding.generic_body_indent_reliable:
        return list(entries), 0
    reference = understanding.line_height
    kept: list[Entry] = []
    suppressed = 0
    for entry in entries:
        if entry.manually_selected:
            kept.append(entry)
            continue
        evidence = block_evidence_for_entry(understanding, entry)
        if (
            evidence is not None
            and evidence.boundary_distance <= reference * 0.80
            and evidence.on_body_lane
            and evidence.role == "body"
        ):
            suppressed += 1
            continue
        kept.append(entry)
    return kept, suppressed


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
            "hard_negative_blocked_rescue": 0,
        }

    reference = understanding.line_height
    design = list(understanding.semantic_entries)
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
    confirmed = rescued = suppressed = blocked = 0
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
        if (
            evidence is not None
            and evidence.boundary_distance <= reference * 0.68
            and evidence.role in {"body", "other_indent"}
            and not evidence.in_entry_direction
        ):
            suppressed += 1
            continue
        output.append(detector)

    # Layout can rescue OCR misses, but never overrule a high-confidence OCR
    # hard-negative consensus at the same physical event.  This preserves the
    # existing combined-mode safety contract while still allowing parser/lemma
    # failures (soft negatives) to be recovered by independent layout evidence.
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
        "hard_negative_blocked_rescue": blocked,
    }


def apply_page_understanding(
    entries: list[Entry],
    understanding: PageUnderstanding,
    *,
    mode: str,
    hard_negative_rows: list[tuple[int, int]] | None = None,
) -> list[Entry]:
    """Apply layout-role evidence without conflating detector vote counts.

    ``mode`` is one of ``ordinary``, ``ocr`` or ``combined``.  ``hard_negative_rows``
    contains canonical (column, V) positions where OCR review evidence reached
    the existing hard-negative consensus; layout rescue is forbidden there.
    """
    normalized_mode = str(mode or "ordinary").strip().lower()
    if normalized_mode not in {"ordinary", "ocr", "combined"}:
        normalized_mode = "ordinary"

    current = list(entries)
    stats = {
        "input": len(current),
        "generic_body_suppressed": 0,
        "layout_confirmed": 0,
        "layout_rescued": 0,
        "layout_suppressed": 0,
        "hard_negative_blocked_rescue": 0,
    }

    # Generic/non-CJK sharing is deliberately conservative: only an explicitly
    # proven inward body lane is allowed to veto a candidate.  No new Latin
    # entry is synthesized here.
    current, generic_suppressed = _generic_body_indent_filter(
        current, understanding,
    )
    stats["generic_body_suppressed"] = generic_suppressed

    if understanding.role_model == "cjk":
        current, cjk_stats = _cjk_semantic_arbitration(
            current,
            understanding,
            mode=normalized_mode,
            hard_negative_rows=hard_negative_rows,
        )
        stats.update(cjk_stats)

    current = _deduplicate(current, understanding)
    stats["output"] = len(current)
    understanding.arbitration_stats.clear()
    understanding.arbitration_stats.update(stats)
    return current
