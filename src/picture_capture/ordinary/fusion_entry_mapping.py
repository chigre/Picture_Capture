from __future__ import annotations

"""Combined-mode metadata mapping and latent review-candidate conversion.

This leaf constructs runtime Entries only. It does not decide candidate
selection or change PDIC/PPP schemas. The core injects its current Entry
constructor at call time to preserve historical identity and patch seams.
"""

from ..models import Entry


def entry_with_fused_metadata(
    position: Entry,
    semantic: Entry,
    *,
    use_semantic_position: bool = False,
    entry_cls: type[Entry],
) -> Entry:
    """Keep one canonical marker while inheriting OCR semantics/review metadata."""
    source = str(semantic.ocr_source or semantic.final_engine or "ocr")
    anchor = semantic if use_semantic_position else position
    return entry_cls(
        word=str(semantic.word or position.word or ""),
        x=int(anchor.x),
        y=int(anchor.y),
        current_page=str(semantic.current_page or position.current_page or ""),
        previous_page=str(semantic.previous_page or position.previous_page or "@"),
        next_page=str(semantic.next_page or position.next_page or "@"),
        confidence=semantic.confidence,
        ocr_source=f"combined:{source}",
        alphabetical_warning=str(semantic.alphabetical_warning or ""),
        candidate_id=str(semantic.candidate_id or ""),
        final_engine=str(semantic.final_engine or ""),
        issue_type=str(semantic.issue_type or ""),
        parser_score=semantic.parser_score,
        manually_selected=bool(semantic.manually_selected),
        ocr_box_height=semantic.ocr_box_height,
        ocr_line_height_reference=semantic.ocr_line_height_reference,
        ocr_visual_run_height=semantic.ocr_visual_run_height,
        ocr_leading_height_ratio=semantic.ocr_leading_height_ratio,
        ocr_single_cjk=bool(semantic.ocr_single_cjk),
        ocr_oversized_cjk=bool(semantic.ocr_oversized_cjk),
    )


def review_candidate_to_entry(candidate: dict, *, entry_cls: type[Entry]) -> Entry | None:
    """Convert one OCR review candidate into runtime Entry metadata."""
    if str(candidate.get("position_variant", "refined")) != "refined":
        return None
    try:
        x = int(candidate.get("source_x"))
        y = int(candidate.get("source_y"))
    except (TypeError, ValueError):
        return None
    if y <= 0:
        return None

    engine = str(candidate.get("final_engine") or "")
    side = candidate.get(engine, {}) if engine else {}
    side = side if isinstance(side, dict) else {}
    features = side.get("features", {}) if isinstance(side, dict) else {}
    features = features if isinstance(features, dict) else {}
    box = candidate.get("box") or side.get("box") or []
    box_height = None
    if isinstance(box, (list, tuple)) and len(box) == 4:
        try:
            box_height = float(max(1, int(box[3]) - int(box[1])))
        except (TypeError, ValueError):
            box_height = None

    issue_types = [
        str(value) for value in list(candidate.get("issue_types", []) or [])
        if str(value)
    ]
    return entry_cls(
        word=str(candidate.get("word") or side.get("lemma") or ""),
        x=x,
        y=y,
        confidence=(
            float(candidate.get("confidence"))
            if candidate.get("confidence") is not None else None
        ),
        ocr_source=f"latent:{engine or 'ocr'}",
        alphabetical_warning=str(candidate.get("alphabetical_warning") or ""),
        candidate_id=str(candidate.get("candidate_id") or ""),
        final_engine=engine,
        issue_type=",".join(issue_types),
        parser_score=(
            float(candidate.get("score"))
            if candidate.get("score") is not None else None
        ),
        manually_selected=bool(candidate.get("manual_override")),
        ocr_box_height=box_height,
        ocr_line_height_reference=(
            float(features.get("line_height_reference"))
            if features.get("line_height_reference") is not None else None
        ),
        ocr_visual_run_height=(
            float(features.get("cjk_visual_run_height"))
            if features.get("cjk_visual_run_height") is not None else None
        ),
        ocr_leading_height_ratio=(
            float(features.get("leading_record_height_ratio"))
            if features.get("leading_record_height_ratio") is not None else None
        ),
        ocr_single_cjk=bool(features.get("cjk_single_visual")),
        ocr_oversized_cjk=bool(
            features.get("cjk_oversized_recovery")
            or features.get("cjk_visual_projection_rescue")
            or features.get("cjk_single_strong_visual")
        ),
    )
