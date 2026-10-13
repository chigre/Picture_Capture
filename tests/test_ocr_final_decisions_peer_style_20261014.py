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
    assert not selected  # Never guess between two colliding candidate identities.
    assert report["summary"]["unmatched_final"] == 1


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

    # A regenerated OCR cache invalidates the old proposal provenance even
    # if PDIC text and coordinates have not yet changed.
    cache.write_text('{"signature":"sig2","review_candidates":[]}', encoding="utf-8")
    assert load_current_final_decisions(cache, pdic) is None
    cache.write_text(
        '{"signature":"sig1","review_candidates":['
        '{"candidate_id":"c1-y80","selected":true,"source_x":10,"source_y":80,"word":"abandonar"}'
        ']}', encoding="utf-8",
    )
    assert load_current_final_decisions(cache, pdic) is not None

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


def test_production_filter_hook_freezes_peer_anchors_before_existing_rescues(monkeypatch):
    from PIL import Image
    import picture_capture.evidence_fusion as fusion

    candidate = _continuation()
    initial_peers = [_peer(25), _peer(115)]  # Inadequate on its own.
    later_peer = _peer(55)
    diagnostics = initial_peers + [candidate]
    seen = {}

    def fake_filter(*args, **kwargs):
        return [], diagnostics

    def fake_existing_rescue(*args, **kwargs):
        # A prior (possibly mistaken) rescue must not count as an independent
        # trusted anchor for the new peer-style algorithm.
        diagnostics.append(later_peer)
        return 1

    monkeypatch.setattr(fusion, "_original_filter_headword_records", fake_filter)
    monkeypatch.setattr(fusion, "_rescue_cjk_parser_failed_rows", lambda *a, **k: 0)
    monkeypatch.setattr(fusion, "_rescue_false_continuation_rows", fake_existing_rescue)
    monkeypatch.setattr(fusion._core, "_is_chinese_ocr", lambda _s: False)
    monkeypatch.setattr(fusion._core, "_is_japanese_ocr", lambda _s: False)
    entries, output = fusion.filter_headword_records(
        [], Image.new("RGB", (120, 220), "white"), 0, 10, AppSettings(),
    )
    assert entries == []
    assert not candidate["accepted"]
    assert len(output) == 4


def test_peer_style_is_explicitly_opt_in_and_can_be_rolled_back(tmp_path, monkeypatch):
    from PIL import Image
    import picture_capture.evidence_fusion as fusion
    from picture_capture.ui.settings import schema

    default = AppSettings()
    assert default.paddle_peer_style_rescue is False
    assert ("实验：同栏词头样式救回续行（默认关）", "paddle_peer_style_rescue") in schema.OCR_ADVANCED_CHECKS
    assert "默认关闭" in schema.CHECK_HELP["paddle_peer_style_rescue"]
    settings_path = tmp_path / "settings.json"
    default.paddle_peer_style_rescue = True
    default.to_json(settings_path)
    assert AppSettings.from_json(settings_path).paddle_peer_style_rescue is True

    called = []
    monkeypatch.setattr(fusion, "_original_filter_headword_records", lambda *a, **k: ([], []))
    monkeypatch.setattr(fusion, "_rescue_cjk_parser_failed_rows", lambda *a, **k: 0)
    monkeypatch.setattr(fusion, "_rescue_false_continuation_rows", lambda *a, **k: 0)
    monkeypatch.setattr(
        fusion, "_rescue_local_peer_style_continuations",
        lambda *a, **k: called.append(True) or 0,
    )
    band = Image.new("RGB", (50, 50), "white")
    default.paddle_peer_style_rescue = False
    fusion.filter_headword_records([], band, 0, 0, default)
    assert called == []
    default.paddle_peer_style_rescue = True
    fusion.filter_headword_records([], band, 0, 0, default)
    assert called == [True]
    default.paddle_peer_style_rescue = False
    fusion.filter_headword_records([], band, 0, 0, default)
    assert called == [True]


def test_default_disabled_state_does_not_mutate_preexisting_ocr_diagnostics(monkeypatch):
    from PIL import Image
    import picture_capture.evidence_fusion as fusion

    diagnostic = {"accepted": False, "reject_reason": "continuation_fragment",
                  "text": "ordinary example", "features": {}}
    monkeypatch.setattr(
        fusion, "_original_filter_headword_records",
        lambda *a, **k: ([], [diagnostic]),
    )
    monkeypatch.setattr(fusion, "_rescue_cjk_parser_failed_rows", lambda *a, **k: 0)
    monkeypatch.setattr(fusion, "_rescue_false_continuation_rows", lambda *a, **k: 0)
    result, rows = fusion.filter_headword_records(
        [], Image.new("RGB", (50, 50), "white"), 0, 0, AppSettings(),
    )
    assert result == [] and rows[0] is diagnostic
    assert "peer_style_evidence" not in rows[0]["features"]


def test_ocr_prewrite_backups_are_lossless_deduplicated_and_preserve_edits(tmp_path):
    from picture_capture.ocr_pdic_preservation import preserve_prior_pdic
    project = tmp_path / "Dictionary"
    project.mkdir()
    page = project / "p001.tif"
    pdic = project / "p001.pdic"
    original = b"Original#11#42#1#3#p001#@#@\r\n"
    pdic.write_bytes(original)
    first = preserve_prior_pdic(project, page, pdic)
    assert first is not None and first.read_bytes() == original
    second = preserve_prior_pdic(project, page, pdic)
    assert second == first
    assert len(list(first.parent.glob("*.pdic"))) == 1

    pdic.write_bytes(b"Human-edit#15#44#1#3#p001#@#@\n")
    third = preserve_prior_pdic(project, page, pdic)
    assert third != first
    assert first.read_bytes() == original
    assert third.read_bytes() == pdic.read_bytes()
    assert len(list(first.parent.glob("*.pdic"))) == 2

    pdic.unlink()
    assert preserve_prior_pdic(project, page, pdic) is None


def test_ocr_prewrite_snapshot_failure_must_not_overwrite_existing_pdic(tmp_path, monkeypatch):
    import picture_capture.ocr_pdic_preservation as backup
    page = tmp_path / "p001.tif"
    pdic = tmp_path / "p001.pdic"
    pdic.write_bytes(b"confirmed original annotations")
    monkeypatch.setattr(backup, "data_root", lambda _root: tmp_path / "inaccessible")
    # A directory replaced by a regular file is not writable. The original
    # must survive the error, so the batch worker can stop safely.
    (tmp_path / "inaccessible").write_text("occupied", encoding="utf-8")
    with pytest.raises(OSError):
        backup.preserve_prior_pdic(tmp_path, page, pdic)
    assert pdic.read_bytes() == b"confirmed original annotations"
