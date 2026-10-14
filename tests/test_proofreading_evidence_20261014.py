"""Conservative linking of proofreading events to final OCR stage."""
from __future__ import annotations

from picture_capture.proofreading_evidence import (
    link_event_to_final, summarize_proofreading_evidence,
)


def _event(**kwargs):
    data = {
        "operation_id": "op-1",
        "candidate_id": "candidate-1",
        "verification_status": "explicit_action_unverified_page",
        "pdic_sha256": "a" * 64,
        "ocr_signature": "recognition-1",
        "final_snapshot_sha256": "final-1",
        "entry_id": "stable-entry-1",
        "action": "rename",
    }
    data.update(kwargs)
    return data


def _final(candidate_rows=None):
    return {
        "format": "picture-capture-final-ocr-decisions-v1",
        "ocr_cache_signature": "recognition-1",
        "pdic_snapshot_sha256": "final-1",
        "candidate_decisions": (
            [{"candidate_id": "candidate-1", "final_status": "retained", "final_selected": True}]
            if candidate_rows is None else candidate_rows
        ),
    }


def test_provenance_link_unique_candidate_still_is_not_ground_truth():
    output = link_event_to_final(_event(), _final(), current_ocr_signature="recognition-1")
    assert output["status"] == "matched"
    assert output["final_selected"] is True
    assert output["training_label"] is None


def test_duplicate_candidate_ids_never_guess_a_final_mapping():
    rows = [
        {"candidate_id": "candidate-1", "final_selected": True},
        {"candidate_id": "candidate-1", "final_selected": False},
    ]
    output = link_event_to_final(_event(), _final(rows), current_ocr_signature="recognition-1")
    assert output["status"] == "ambiguous"
    assert output["training_label"] is None


def test_stale_signatures_are_not_linked_or_trained():
    result = link_event_to_final(
        _event(ocr_signature="recognition-old"), _final(),
        current_ocr_signature="recognition-1",
    )
    assert result["status"] == "stale"
    assert link_event_to_final(
        _event(final_snapshot_sha256="old-final"), _final(),
        current_ocr_signature="recognition-1",
    )["status"] == "stale"


def test_legacy_missing_provenance_cannot_be_promoted():
    result = link_event_to_final(
        _event(candidate_id=None), _final(), current_ocr_signature="recognition-1",
    )
    assert result["status"] == "unknown"
    assert result["training_label"] is None


def test_aggregate_reports_counts_only_and_never_exports_labels():
    events = [_event(), _event(operation_id="op-2", candidate_id=None)]
    summary = summarize_proofreading_evidence(
        events, current_pdic_sha256="a" * 64,
        current_ocr_signature="recognition-1", final_report=_final(),
    )
    assert summary["event_count"] == 2
    assert summary["link_status_counts"] == {
        "matched": 1, "unknown": 1, "ambiguous": 0, "stale": 0,
    }
    assert summary["training_labels_exported"] == 0
    assert "candidate-1" not in str(summary)


def test_old_pdic_fingerprint_cannot_count_as_matched_ocr_link():
    old_event = _event(pdic_sha256="a" * 64)
    summary = summarize_proofreading_evidence(
        [old_event], current_pdic_sha256="b" * 64,
        current_ocr_signature="recognition-1", final_report=_final(),
    )
    assert summary["provenance"]["stale_events"] == 1
    assert summary["link_status_counts"]["stale"] == 1
    assert summary["link_status_counts"]["matched"] == 0
    assert summary["training_labels_exported"] == 0
