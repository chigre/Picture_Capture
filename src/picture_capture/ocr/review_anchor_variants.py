"""Review-only alternate image-anchor position creation.

The refined and original variants share an ID group but keep independent
selection states; historical mutation, order, and return-count semantics stay.
"""
from __future__ import annotations
from typing import Any


def expand_original_y_fallback_candidates(review_candidates: list[dict[str, Any]]) -> int:
    """Expose an image-derived anchor Y as the unchecked fallback position.

    v2.8.19 keeps three distinct vertical facts: ``original_box`` / OCR coarse Y
    for diagnosis, ``anchor_source_y`` derived from local image ink geometry,
    and the final refined Y.  The blue fallback checkbox uses the image anchor
    when available; this avoids returning to an OCR box top that may itself have
    leaked into the preceding line.  OCR coarse Y remains preserved in cache.
    """
    additions: list[dict[str, Any]] = []
    created = 0
    for item in list(review_candidates):
        if str(item.get("position_variant", "refined")) != "refined":
            continue
        try:
            refined_y = int(item.get("source_y", 0))
            refined_x = int(item.get("source_x", 0))
            coarse_y = int(item.get("coarse_source_y", refined_y))
            coarse_x = int(item.get("coarse_source_x", refined_x))
            anchor_y = int(item.get("anchor_source_y", coarse_y))
            anchor_x = int(item.get("anchor_source_x", coarse_x))
            refined_v = int(item.get("_axis_v", refined_y))
            coarse_v = int(item.get("_coarse_axis_v", refined_v))
            anchor_v = int(item.get("_anchor_axis_v", coarse_v))
        except (TypeError, ValueError):
            continue
        if refined_y <= 0 or anchor_y <= 0 or anchor_y == refined_y:
            continue
        base_id = str(item.get("candidate_id", ""))
        if not base_id:
            continue
        group_id = str(item.get("position_group_id") or base_id)
        item["position_group_id"] = group_id
        item["refined_source_y"] = refined_y
        item["coarse_source_y"] = coarse_y
        item["anchor_source_y"] = anchor_y
        item["position_variant"] = "refined"

        fallback = dict(item)
        fallback["candidate_id"] = f"{base_id}-rawy"
        fallback["source_x"] = anchor_x
        fallback["source_y"] = anchor_y
        fallback["_axis_v"] = anchor_v
        fallback["refined_source_y"] = refined_y
        fallback["coarse_source_x"] = coarse_x
        fallback["coarse_source_y"] = coarse_y
        fallback["_coarse_axis_v"] = coarse_v
        fallback["anchor_source_x"] = anchor_x
        fallback["anchor_source_y"] = anchor_y
        fallback["_anchor_axis_v"] = anchor_v
        fallback["position_group_id"] = group_id
        fallback["position_variant"] = "original"
        fallback["selected"] = False
        fallback["manual_override"] = False
        fallback["needs_review"] = False
        fallback["decision_reason"] = "image_anchor_y_fallback"
        fallback["fallback_kind"] = "image_anchor"
        fallback["issue_types"] = list(item.get("issue_types", []) or [])
        additions.append(fallback)
        created += 1
    review_candidates.extend(additions)
    review_candidates.sort(
        key=lambda row: (
            int(row.get("column", 0)),
            int(row.get("canonical_v", row.get("source_y", 0))),
            str(row.get("position_variant", "")),
        )
    )
    return created
