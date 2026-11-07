"""G3 R4.2 fail-first: source-attested read-only review priority and order.

Synthetic fixtures are not human-verified labels, scans, or a performance claim.
"""
from __future__ import annotations

from dataclasses import asdict, FrozenInstanceError, replace
from hashlib import sha256
import json

import pytest

from picture_capture.io.formats import write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading.review_risk import ReviewRisk
from picture_capture.proofreading.review_risk_queue import (
    ReviewRiskWitness, review_risk_from_files, order_review_targets,
)


def _source(tmp_path, *, issues=(), section=None):
    pdic = tmp_path / "p001.pdic"
    cache = tmp_path / "OCRCache" / "p001.json"
    section_file = tmp_path / "p001_sections.json"
    cache.parent.mkdir()
    write_pdic(pdic, [Entry(word="atlas", x=12, y=100)], 400, ("p001", "@", "@"))
    candidate = {
        "candidate_id": "c1-y100", "source_x": 12, "source_y": 100,
        "coordinate_space": "source_image_pixels", "position_variant": "refined",
        "selected": True, "final_engine": "paddle",
        "decision_reason": "dual_agree_higher_quality", "needs_review": bool(issues),
        "issue_types": list(issues),
        "paddle": {"accepted": True, "lemma": "atlas", "confidence": .98},
        "tesseract": {"accepted": True, "lemma": "atlas", "confidence": .97},
    }
    cache.write_text(json.dumps({"signature": "synthetic", "review_candidates": [candidate]}))
    if section is not None:
        section_file.write_text(json.dumps({"sections": [section]}))
    witness = ReviewRiskWitness(
        project_key="project-abc", page_key="p001", section_key=section or "whole-page",
        candidate_id="c1-y100", source_x=12, source_y=100,
        cache_sha256=sha256(cache.read_bytes()).hexdigest(),
        pdic_sha256=sha256(pdic.read_bytes()).hexdigest(),
        section_sha256=(
            sha256(section_file.read_bytes()).hexdigest() if section is not None else None
        ),
    )
    return pdic, cache, section_file, witness, candidate


def _run(source, *, witness=None, project="project-abc", page="p001",
         section=None, section_at_xy=None):
    pdic, cache, section_file, original, _ = source
    return review_risk_from_files(
        pdic_path=pdic, cache_path=cache, section_path=section_file,
        witness=witness, project_key=project, page_key=page,
        section_key=section if section is not None else original.section_key,
        section_at_source_xy=section_at_xy,
    )


def test_witness_is_required_and_no_source_file_is_ever_rewritten(tmp_path):
    source = _source(tmp_path)
    before = [p.read_bytes() for p in source[:2]]
    assert _run(source).tier == "unknown"
    assert [p.read_bytes() for p in source[:2]] == before
    assert _run(source, witness=source[3]).tier == "normal"
    assert [p.read_bytes() for p in source[:2]] == before
    assert json.loads(json.dumps(asdict(source[3])))["page_key"] == "p001"
    with pytest.raises(FrozenInstanceError):
        source[3].page_key = "modified"


def test_current_explainable_conflict_is_review_priority_not_error_label(tmp_path):
    source = _source(tmp_path, issues=("OCR_CONFLICT",))
    result = _run(source, witness=source[3])
    assert result == ReviewRisk("priority", ("NEEDS_REVIEW", "OCR_CONFLICT"))


def test_missing_stale_cache_pdic_or_invalid_origin_fails_closed(tmp_path):
    source = _source(tmp_path)
    good = source[3]
    for field, value in [
        ("project_key", "other"), ("page_key", "other"),
        ("section_key", "section-9"), ("candidate_id", "other"),
        ("source_x", 13), ("source_y", 101),
        ("cache_sha256", "f" * 64), ("pdic_sha256", "0" * 64),
    ]:
        assert _run(source, witness=replace(good, **{field: value})).tier == "unknown"
    assert _run(source, witness=good, project="other").tier == "unknown"
    assert _run(source, witness=good, page="other").tier == "unknown"
    source[1].write_text(source[1].read_text() + " ")
    assert _run(source, witness=good).tier == "unknown"
    source[1].unlink()
    assert _run(source, witness=good).tier == "unknown"


def test_duplicate_candidate_id_same_xy_or_pdic_identity_is_unknown(tmp_path):
    source = _source(tmp_path)
    pdic, cache, sections, witness, candidate = source
    payload = json.loads(cache.read_text())
    payload["review_candidates"].append(dict(candidate))
    cache.write_text(json.dumps(payload))
    witness = replace(witness, cache_sha256=sha256(cache.read_bytes()).hexdigest())
    assert _run(source, witness=witness).tier == "unknown"

    payload["review_candidates"][1]["candidate_id"] = "other"
    cache.write_text(json.dumps(payload))
    witness = replace(witness, cache_sha256=sha256(cache.read_bytes()).hexdigest())
    assert _run(source, witness=witness).tier == "unknown"

    payload["review_candidates"] = [candidate]
    cache.write_text(json.dumps(payload))
    witness = replace(witness, cache_sha256=sha256(cache.read_bytes()).hexdigest())
    write_pdic(pdic, [Entry(word="atlas", x=12, y=100),
                      Entry(word="other", x=12, y=100)], 400, ("p001", "@", "@"))
    witness = replace(witness, pdic_sha256=sha256(pdic.read_bytes()).hexdigest())
    assert _run(source, witness=witness).tier == "unknown"


def test_section_crossovers_and_changed_section_bytes_are_unknown(tmp_path):
    source = _source(tmp_path, section="section-A")
    w = source[3]
    assert _run(source, witness=w).tier == "unknown"  # no geometry proof
    assert _run(source, witness=w, section_at_xy=lambda x, y: "section-A").tier == "normal"
    assert _run(source, witness=w, section_at_xy=lambda x, y: "section-B").tier == "unknown"
    assert _run(source, witness=w, section="section-B",
                section_at_xy=lambda x, y: "section-B").tier == "unknown"
    source[2].write_text('{"sections":["section-B"]}')
    assert _run(source, witness=w, section_at_xy=lambda x, y: "section-A").tier == "unknown"
    # SECTION unexpectedly appears on a previously sectionless page
    other = tmp_path / "plain"
    other.mkdir()
    plain = _source(other)
    plain[2].write_text('{"sections":[]}')
    assert _run(plain, witness=plain[3]).tier == "unknown"


def test_malformed_cache_and_unreadable_pdic_are_unknown(tmp_path):
    source = _source(tmp_path)
    source[1].write_bytes(b"not-json")
    witness = replace(source[3], cache_sha256=sha256(source[1].read_bytes()).hexdigest())
    assert _run(source, witness=witness).tier == "unknown"
    source[0].write_bytes(b"\xff\xfe\xfa")
    witness = replace(witness, pdic_sha256=sha256(source[0].read_bytes()).hexdigest())
    assert _run(source, witness=witness).tier == "unknown"


def test_queue_default_off_and_no_mutation_or_identity_loss():
    targets = [
        {"page_index": 0, "section_key": "whole-page", "id": "normal"},
        {"page_index": 0, "section_key": "whole-page", "id": "priority"},
        {"page_index": 0, "section_key": "whole-page", "id": "unknown"},
    ]
    risks = [ReviewRisk("normal", ("CURRENT_DUAL_AGREEMENT",)),
             ReviewRisk("priority", ("OCR_REPAIR",)),
             ReviewRisk("unknown", ("STALE_OR_UNVERIFIED_SOURCE",))]
    before = [dict(x) for x in targets]
    assert order_review_targets(targets, risks=risks) == targets
    result = order_review_targets(targets, risks=risks, enabled=True)
    assert [x["id"] for x in result] == ["priority", "normal", "unknown"]
    assert targets == before
    assert all(any(row is original for original in targets) for row in result)


def test_queue_preserves_page_section_groups_and_stability():
    targets = [
        {"page_index": 1, "section_key": "A", "id": "n1"},
        {"page_index": 1, "section_key": "A", "id": "p1"},
        {"page_index": 1, "section_key": "A", "id": "p2"},
        {"page_index": 1, "section_key": "B", "id": "n2"},
        {"page_index": 1, "section_key": "B", "id": "p3"},
        {"page_index": 2, "section_key": "A", "id": "n3"},
        {"page_index": 2, "section_key": "A", "id": "p4"},
    ]
    risks = [ReviewRisk("priority", ()) if row["id"].startswith("p") else ReviewRisk("unknown", ())
             for row in targets]
    result = order_review_targets(targets, risks=risks, enabled=True)
    assert [x["id"] for x in result] == ["p1", "p2", "n1", "p3", "n2", "p4", "n3"]
    assert [x["id"] for x in order_review_targets(targets, risks=risks, enabled=False)] == [x["id"] for x in targets]


@pytest.mark.parametrize("bad", [None, [], [ReviewRisk("priority", ())], [object()] * 3])
def test_missing_or_invalid_risks_never_reorder(bad):
    rows = [
        {"page_index": 0, "section_key": "A", "id": 1},
        {"page_index": 0, "section_key": "A", "id": 2},
        {"page_index": 0, "section_key": "A", "id": 3},
    ]
    assert order_review_targets(rows, risks=bad, enabled=True) == rows


def test_missing_section_key_fails_closed_no_ranking():
    rows = [{"page_index": 0, "id": "a"}, {"page_index": 0, "id": "b"}]
    risks = [ReviewRisk("normal", ()), ReviewRisk("priority", ())]
    assert order_review_targets(rows, risks=risks, enabled=True) == rows
