"""Conservative, read-only links between human events and final OCR decisions.

This module never infers gold truth or overwrites manual PDIC/OCR state.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from .proofreading_events import audit_events


def link_event_to_final(
    event: dict[str, Any], final_report: dict[str, Any] | None,
    *, current_ocr_signature: str | None,
) -> dict[str, Any]:
    """Return matched, stale, ambiguous or unknown; never guess by list index."""
    result = {
        "operation_id": event.get("operation_id"),
        "status": "unknown",
        "training_label": None,
        "reason": "no_fresh_final_decisions",
    }
    if final_report is None or final_report.get("format") != "picture-capture-final-ocr-decisions-v1":
        return result
    expected_ocr = event.get("ocr_signature")
    expected_snapshot = event.get("final_snapshot_sha256")
    if not expected_ocr or not expected_snapshot:
        # An event with no verified pre-human OCR/final snapshot can be kept
        # locally, but must never be attached to a later unrelated OCR run.
        return {**result, "reason": "missing_provenance_fingerprint"}
    actual_ocr = final_report.get("ocr_cache_signature")
    if expected_ocr != actual_ocr or expected_ocr != current_ocr_signature:
        return {**result, "status": "stale", "reason": "ocr_signature_changed"}
    if expected_snapshot != final_report.get("pdic_snapshot_sha256"):
        return {**result, "status": "stale", "reason": "final_pdic_snapshot_changed"}
    candidate_id = str(event.get("candidate_id") or "")
    if not candidate_id:
        return {**result, "reason": "no_candidate_id"}
    rows = final_report.get("candidate_decisions")
    if not isinstance(rows, list):
        return {**result, "reason": "missing_candidate_decisions"}
    if not all(isinstance(row, dict) for row in rows):
        return {**result, "reason": "invalid_candidate_decisions"}
    counts = Counter(str(row.get("candidate_id") or "") for row in rows)
    if counts[candidate_id] != 1:
        return {
            **result,
            "status": "ambiguous" if counts[candidate_id] > 1 else "unknown",
            "reason": "duplicate_candidate_id" if counts[candidate_id] > 1 else "candidate_not_found",
        }
    candidate = next(row for row in rows if str(row.get("candidate_id") or "") == candidate_id)
    # A unique source candidate does not imply a verified true positive:
    # final-only Layout lines, post-OCR moves and manual edits remain separate.
    return {
        **result,
        "status": "matched",
        "reason": "unique_candidate_id",
        "final_status": candidate.get("final_status"),
        "final_selected": candidate.get("final_selected"),
        "training_label": None,
    }


def summarize_proofreading_evidence(
    events: list[dict[str, Any]], *,
    current_pdic_sha256: str | None,
    current_ocr_signature: str | None,
    final_report: dict[str, Any] | None,
) -> dict[str, Any]:
    """Read-only quality audit; summary never contains patient or page text."""
    status = audit_events(
        events,
        current_pdic_sha256=current_pdic_sha256,
        current_ocr_signature=current_ocr_signature,
    )
    links = [
        link_event_to_final(event, final_report, current_ocr_signature=current_ocr_signature)
        for event in events
    ]
    frequencies = Counter(link["status"] for link in links)
    return {
        "format": "picture-capture-proofreading-evidence-audit-v1",
        "event_count": len(events),
        "provenance": status,
        "link_status_counts": {
            key: frequencies.get(key, 0)
            for key in ("matched", "unknown", "ambiguous", "stale")
        },
        "training_labels_exported": 0,
        "warning": "Manual action and uniquely linked OCR candidate do not establish ground truth.",
    }
