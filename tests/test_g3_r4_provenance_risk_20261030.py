"""R4.1 fail-first: only current, unique, source-anchored OCR evidence may rank review.

Synthetic fixtures assert review *priority*, never true OCR errors or human labels.
No Tk, files, private page images, or settings writes are involved.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import copy
import json

from picture_capture.proofreading.review_risk import (
    ReviewRiskProvenance,
    classify_review_risk,
)


H = "a" * 64
J = "b" * 64


def provenance(**changes):
    return replace(ReviewRiskProvenance(
        project_key="project-1", page_key="page-001", section_key="section-1",
        candidate_id="c1-y100",
        evidence_project_key="project-1", evidence_page_key="page-001",
        evidence_section_key="section-1",
        evidence_cache_sha256=H, current_cache_sha256=H,
        evidence_pdic_sha256=J, current_pdic_sha256=J,
        unique_matches=1, pdic_source_x=12, pdic_source_y=100,
    ), **changes)


def candidate(**changes):
    base = {
        "candidate_id": "c1-y100", "position_variant": "refined",
        "coordinate_space": "source_image_pixels", "source_x": 12, "source_y": 100,
        "selected": True, "needs_review": False, "issue_types": [],
        "decision_reason": "dual_agree_higher_quality",
        "final_engine": "paddle",
        "paddle": {"accepted": True, "lemma": "casa", "confidence": 0.95},
        "tesseract": {"accepted": True, "lemma": "casa", "confidence": 0.94},
    }
    base.update(changes)
    return base


def test_fresh_dual_agreement_is_normal_and_pure():
    row = candidate()
    before = copy.deepcopy(row)
    p = provenance()
    result = classify_review_risk(row, provenance=p)
    assert result.tier == "normal"
    assert result.reasons == ("CURRENT_DUAL_AGREEMENT",)
    assert row == before
    assert json.loads(json.dumps(asdict(result)))["tier"] == "normal"


def test_current_disagreement_review_and_repairs_are_explainable_not_error_labels():
    row = candidate(
        needs_review=True,
        issue_types=["OCR_REPAIR", "OCR_CONFLICT", "OCR_CONFLICT", "LOW_CONFIDENCE"],
        decision_reason="conflict_higher_quality",
    )
    result = classify_review_risk(row, provenance=provenance())
    assert result.tier == "priority"
    assert result.reasons == ("NEEDS_REVIEW", "OCR_CONFLICT", "LOW_CONFIDENCE", "OCR_REPAIR")
    assert "error" not in str(asdict(result)).lower()


def test_stale_cache_or_pdic_never_ranked_as_confirmed_priority():
    for changes in (
        {"current_cache_sha256": J},
        {"current_pdic_sha256": H},
        {"evidence_cache_sha256": ""},
        {"current_pdic_sha256": "not-a-sha"},
    ):
        result = classify_review_risk(candidate(issue_types=["OCR_CONFLICT"]), provenance=provenance(**changes))
        assert result.tier == "unknown"
        assert result.reasons == ("STALE_OR_UNVERIFIED_SOURCE",)


def test_cross_page_project_section_and_ambiguous_identity_fail_closed():
    for changes in (
        {"evidence_project_key": "other"},
        {"evidence_page_key": "page-002"},
        {"evidence_section_key": "section-2"},
        {"unique_matches": 0},
        {"unique_matches": 2},
        {"section_key": ""},
    ):
        assert classify_review_risk(candidate(needs_review=True), provenance=provenance(**changes)).tier == "unknown"


def test_xy_and_candidate_identity_cannot_be_guessed_from_nearest_row():
    for changes in (
        {"candidate_id": "c1-y110"},
        {"source_x": 13},
        {"source_y": 101},
        {"coordinate_space": "canonical_pixels"},
        {"position_variant": "original"},
    ):
        assert classify_review_risk(candidate(needs_review=True, **changes), provenance=provenance()).tier == "unknown"
    assert classify_review_risk(candidate(needs_review=True), provenance=provenance(pdic_source_y=110)).tier == "unknown"


def test_lens_diagnostic_only_and_nonselected_do_not_become_confirmed_errors():
    for row in (
        candidate(selected=False, needs_review=True),
        candidate(final_engine="", decision_reason="lens_diagnostic_only", needs_review=True),
        candidate(final_engine="lens", decision_reason="lens_diagnostic_only", needs_review=True),
    ):
        assert classify_review_risk(row, provenance=provenance()).tier == "unknown"


def test_missing_or_unknown_diagnostics_are_not_silent_normal():
    for row in (
        None, {}, candidate(issue_types=None), candidate(needs_review=None),
        candidate(issue_types=["FUTURE_UNDOCUMENTED_ISSUE"]),
        candidate(decision_reason="new_reason"),
        candidate(paddle={}), candidate(tesseract={"accepted": True, "lemma": "otro", "confidence": 0.99}),
    ):
        assert classify_review_risk(row, provenance=provenance()).tier == "unknown"


def test_known_weak_structure_and_forced_review_rescues_are_priority_not_truth():
    for issue in ("MISSING_STRUCTURE", "LOW_PARSER_SCORE", "DUAL_BOUNDARY_RESCUE", "MULTI_EVIDENCE_RESCUE", "LENS_DISAGREEMENT"):
        result = classify_review_risk(candidate(issue_types=[issue]), provenance=provenance())
        assert result.tier == "priority"
        assert result.reasons == (issue,)


def test_bad_provenance_types_fail_closed_without_exception_or_mutation():
    for changes in (
        {"unique_matches": True}, {"pdic_source_x": "12"}, {"pdic_source_y": None},
        {"current_cache_sha256": H.upper()},
    ):
        assert classify_review_risk(candidate(), provenance=provenance(**changes)).tier == "unknown"
