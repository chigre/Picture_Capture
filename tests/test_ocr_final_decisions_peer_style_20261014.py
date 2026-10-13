"""Real PDIC finalization and conservative peer-style boundary decisions."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.evidence_fusion import _rescue_local_peer_style_continuations
from picture_capture.formats import read_pdic, write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.ocr_final_decisions import (
    apply_final_review_annotations,
    build_final_decisions,
    final_decisions_path,
    load_current_final_decisions,
    record_final_decisions,
)
from picture_capture.ocr_peer_style import peer_style_continuation_evidence


def _entry(word, x, y, *, cid="", source="paddle"):
    return Entry(word=word, x=x, y=y, candidate_id=cid, ocr_source=source)


def test_saved_pdic_is_authoritative_even_after_layout_moves_and_rescues():
    detected = [
        _entry("alpha", 12, 120, cid="c1-y120"),
        _entry("layout", 12, 270, source="page_understanding:ocr_layout_rescue"),
        _entry("beta", 12, 340, cid="c1-y335"),
    ]
    saved = [_entry(e.word, e.x, e.y) for e in detected]
    candidates = [
        {"candidate_id": "c1-y120", "selected": True, "source_x": 12, "source_y": 120,
         "word": "alpha", "decision_reason": "paddle_only"},
        {"candidate_id": "c1-y335", "selected": True, "source_x": 12, "source_y": 335,
         "word": "beta"},
        {"candidate_id": "c1-y400", "selected": False, "source_x": 12, "source_y": 400,
         "word": "continuation"},
    ]
    report = build_final_decisions(detected, saved, candidates, tolerance=12)
    assert report["pdic_rows"] == [["alpha", 12, 120], ["layout", 12, 270], ["beta", 12, 340]]
    assert [r["final_status"] for r in report["candidate_decisions"]] == [
        "retained", "moved_by_post_ocr", "rejected",
    ]
    assert report["candidate_decisions"][1]["final_source_y"] == 340
    assert report["summary"]["linked"] == 2
    assert report["summary"]["unmatched_final"] == 1
    assert report["final_only"][0]["reason"] == "post_ocr_layout_or_symbol"


def test_ambiguous_quantized_candidate_id_is_not_silently_inherited():
    detected = [_entry("one", 10, 100, cid="c1-y100")]
    candidates = [
        {"candidate_id": "c1-y100", "selected": True, "source_x": 10, "source_y": 100},
        {"candidate_id": "c1-y100", "selected": True, "source_x": 11, "source_y": 101},
    ]
    report = build_final_decisions(detected, detected, candidates, tolerance=12)
    selected = [r for r in report["candidate_decisions"] if r["final_selected"]]
    assert len(selected) <= 1  # Never link both checkboxes to one PDIC marker.


def test_final_manifest_uses_readback_and_refuses_stale_after_manual_edit(tmp_path):
    cache = tmp_path / "OCRCache" / "p001.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        '{"signature":"sig1","review_candidates":['
        '{"candidate_id":"c1-y80","selected":true,"source_x":10,"source_y":80,"word":"abandonar"}'
        ']}', encoding="utf-8",
    )
    pdic = tmp_path / "p001.pdic"
    markers = [_entry("abandonar", 10, 80, cid="c1-y80")]
    write_pdic(pdic, markers, 1200, ("p001", "@", "@"))
    summary = record_final_decisions(cache, pdic, markers)
    assert summary["linked"] == 1
    audit = load_current_final_decisions(cache, pdic)
    assert audit is not None
    assert audit["ocr_cache_signature"] == "sig1"
    augmented = apply_final_review_annotations(
        [{"candidate_id": "c1-y80", "source_y": 80}], audit,
    )
    assert augmented[0]["final_decision"]["final_selected"] is True
    assert final_decisions_path(cache).name == "p001_final_decisions.json"

    # Manual edits (including text-only corrections) invalidate old automatic
    # position/status claims; never overwrite the manually changed PDIC.
    write_pdic(pdic, [_entry("abandonar cor.", 10, 80)], 1200, ("p001", "@", "@"))
    assert load_current_final_decisions(cache, pdic) is None
    assert read_pdic(pdic)[0].word == "abandonar cor."


def test_final_annotator_refuses_reordered_or_regenerated_ocr_cache():
    audit = {"candidate_decisions": [
        {"candidate_id": "old", "final_selected": True},
    ]}
    source = [{"candidate_id": "new", "selected": False}]
    assert apply_final_review_annotations(source, audit) is source


def _peer(y, *, bold=1.14, x=5, accepted=True):
    return {
        "source_y": y, "box": [x, 0, 65, 22],
        "confidence": 0.96, "accepted": accepted,
        "pos_cue": "v.", "features": {
            "at_left": True, "structural_cue": True,
            "boldness_ratio": bold, "height_ratio": 1.05,
        },
    }


def _continuation():
    return {
        "source_y": 85, "source_x": 5, "box": [5, 0, 77, 22],
        "text": "abandonar v. tr.",
        "normalized_headword": "abandonar",
        "confidence": 0.95, "accepted": False,
        "reject_reason": "continuation_fragment",
        "continuation_reason": "visual_continuation",
        "looks_like_continuation": True, "pos_cue": "v. tr.",
        "image_boundary_match": {"y": 85, "strength": 0.78},
        "user_rule": {"rejected": False},
        "features": {
            "at_left": True, "below_header": True,
            "image_boundary_supported": True,
            "boldness_ratio": 1.11, "height_ratio": 1.02,
            "structural_cue": True, "looks_like_continuation": True,
        },
    }


def test_peer_style_rescue_requires_local_bracketing_and_real_image_gap():
    cand = _continuation()
    peers = [_peer(25), _peer(55), _peer(115), _peer(148)]
    result = peer_style_continuation_evidence(cand, peers)
    assert result["supported"] is True
    assert result["peer_count"] == 4
    assert result["gap_strength"] == 0.78
    assert peer_style_continuation_evidence(cand, peers[:2])["supported"] is False
    assert peer_style_continuation_evidence(cand, peers[:2] + [_peer(75)])["supported"] is False
    no_gap = deepcopy(cand)
    no_gap["image_boundary_match"] = None
    assert peer_style_continuation_evidence(no_gap, peers)["reason"] == "no_strong_image_gap"


@pytest.mark.parametrize("change,expected", [
    ({"user_rule": {"rejected": True}}, "explicit_reject"),
    ({"features": {"forced_reject": True}}, "explicit_reject"),
    ({"features": {"at_left": False}}, "not_left_edge"),
    ({"confidence": 0.55}, "weak_candidate"),
    ({"pos_cue": "", "inflection_cue": ""}, "no_explicit_grammar"),
])
def test_peer_style_respects_explicit_negatives_and_ocr_uncertainty(change, expected):
    cand = _continuation()
    for key, value in change.items():
        if key == "features":
            cand[key].update(value)
        else:
            cand[key] = value
    if "pos_cue" in change:
        cand["features"]["structural_cue"] = False
    assert peer_style_continuation_evidence(
        cand, [_peer(25), _peer(55), _peer(115), _peer(148)]
    )["reason"] == expected


def test_peer_style_never_rescues_body_typography_or_cjk():
    cand = _continuation()
    cand["features"]["boldness_ratio"] = 0.75
    peers = [_peer(25), _peer(55), _peer(115), _peer(148)]
    assert peer_style_continuation_evidence(cand, peers)["reason"] == "weak_candidate"

    entries = []
    settings = AppSettings()
    settings.ocr_language = "chi_sim"
    assert _rescue_local_peer_style_continuations(
        entries, [cand], source_top=0, source_column_x=10,
        settings=settings, engine_name="paddle", trusted_anchors=peers,
    ) == 0
    assert entries == []


def test_peer_style_promotes_real_lexical_candidate_once_and_records_provenance():
    cand = _continuation()
    peers = [_peer(25), _peer(55), _peer(115), _peer(148)]
    entries = []
    settings = AppSettings()
    settings.ocr_language = "spa+eng"
    count = _rescue_local_peer_style_continuations(
        entries, [cand], source_top=0, source_column_x=10,
        settings=settings, engine_name="paddle", trusted_anchors=peers,
    )
    assert count == 1
    assert [(e.word, e.x, e.y) for e in entries] == [("abandonar", 10, 85)]
    assert cand["accepted"] is True
    assert "PEER_STYLE_CONTINUATION_RESCUE" in cand["bug_types"]
    assert cand["features"]["peer_style_evidence"]["peer_count"] == 4
    # Already accepted candidate must not be inserted a second time.
    assert _rescue_local_peer_style_continuations(
        entries, [cand], source_top=0, source_column_x=10,
        settings=settings, engine_name="paddle", trusted_anchors=peers,
    ) == 0
