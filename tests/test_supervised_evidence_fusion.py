from __future__ import annotations

import picture_capture.paddle_headwords as ph
from picture_capture.models import AppSettings


def _accepted_anchor(boldness: float, height: float = 1.0, gap: float = 18.0):
    return {
        "accepted": True,
        "confidence": 0.96,
        "normalized_headword": "anchor",
        "features": {
            "at_left": True,
            "below_header": True,
            "boldness_ratio": boldness,
            "height_ratio": height,
            "preceding_gap": gap,
            "forced_accept": False,
            "marker_noise": False,
            "looks_like_continuation": False,
        },
        "parser_trace": [],
        "bug_types": [],
    }


def test_latin_peer_typography_requires_boldness_not_only_height_and_gap():
    diagnostics = [
        _accepted_anchor(1.00),
        _accepted_anchor(1.02, gap=19),
        _accepted_anchor(1.04, gap=20),
        _accepted_anchor(1.01, gap=21),
    ]
    body_like = {
        "accepted": False,
        "confidence": 0.94,
        "normalized_headword": "parecia",
        "reject_reason": "missing_selected_tail_structure",
        "features": {
            "at_left": True,
            "below_header": True,
            "image_boundary_supported": True,
            "boldness_ratio": 0.74,
            "height_ratio": 1.01,
            "preceding_gap": 19,
        },
        "parser_trace": [],
        "bug_types": [],
    }
    diagnostics.append(body_like)

    matched = ph._annotate_peer_typography_matches(diagnostics)

    assert matched == 0
    assert not body_like["features"].get("peer_typography_match")
    assert "peer_typography_match" not in body_like["parser_trace"]


def test_peer_typography_still_accepts_true_bold_match():
    diagnostics = [
        _accepted_anchor(1.00),
        _accepted_anchor(1.02, gap=19),
        _accepted_anchor(1.04, gap=20),
        _accepted_anchor(1.01, gap=21),
    ]
    head_like = {
        "accepted": False,
        "confidence": 0.91,
        "normalized_headword": "abastecimiento",
        "reject_reason": "missing_selected_tail_structure",
        "features": {
            "at_left": True,
            "below_header": True,
            "image_boundary_supported": True,
            "boldness_ratio": 1.01,
            "height_ratio": 1.02,
            "preceding_gap": 19,
        },
        "parser_trace": [],
        "bug_types": [],
    }
    diagnostics.append(head_like)

    matched = ph._annotate_peer_typography_matches(diagnostics)

    assert matched == 1
    assert head_like["features"]["peer_typography_match"] is True
    assert head_like["features"]["peer_typography_boldness_required"] is True


def test_cjk_parser_failure_can_be_rescued_by_large_head_geometry():
    settings = AppSettings(
        ocr_language="chi_sim",
        paddle_language="ch",
        profile_parser_controls_version=1,
        profile_cjk_allow_single_headword=True,
        character_height=30,
    )
    row = {
        "accepted": False,
        "reject_reason": "lemma_parse_failed",
        "text": "阿 ā 释义文本",
        "confidence": 0.96,
        "source_y": 58,
        "image_boundary_match": {"y": 50, "strength": 0.9},
        "user_rule": {"rejected": False},
        "features": {
            "at_left": True,
            "below_header": True,
            "image_boundary_supported": True,
            "height_ratio": 2.20,
            "leading_record_height_ratio": 2.10,
            "forced_reject": False,
            "marker_noise": False,
            "internal_article_symbol": False,
            "internal_relation_label": False,
            "internal_locution": False,
        },
        "parser_trace": ["lemma:failed"],
        "bug_types": ["LEMMA_PARSE_FAILED"],
    }
    entries = []

    count = ph._rescue_cjk_parser_failed_rows(
        entries,
        [row],
        source_top=10,
        source_column_x=20,
        settings=settings,
        engine_name="paddle",
        profile=None,
    )

    assert count == 1
    assert len(entries) == 1
    assert entries[0].word == "阿"
    assert entries[0].y == 60
    assert row["accepted"] is True
    assert row["reject_reason"] == ""
    assert row["parser_stage"] == "cjk_parser_failed_visual_rescue"
    assert row["features"]["cjk_parser_failed_visual_rescue"] is True


def test_cjk_parser_failure_requires_independent_image_boundary():
    settings = AppSettings(
        ocr_language="chi_sim",
        paddle_language="ch",
        profile_parser_controls_version=1,
        profile_cjk_allow_single_headword=True,
        character_height=30,
    )
    row = {
        "accepted": False,
        "reject_reason": "lemma_parse_failed",
        "text": "阿 ā 释义文本",
        "confidence": 0.99,
        "source_y": 58,
        "user_rule": {"rejected": False},
        "features": {
            "at_left": True,
            "below_header": True,
            "image_boundary_supported": False,
            "height_ratio": 2.50,
            "leading_record_height_ratio": 2.40,
        },
        "parser_trace": [],
        "bug_types": [],
    }
    entries = []

    count = ph._rescue_cjk_parser_failed_rows(
        entries,
        [row],
        source_top=10,
        source_column_x=20,
        settings=settings,
        engine_name="paddle",
        profile=None,
    )

    assert count == 0
    assert entries == []
    assert row["accepted"] is False


def _latin_diagnostics(candidate_boldness: float):
    anchors = [
        _accepted_anchor(1.00),
        _accepted_anchor(1.02),
        _accepted_anchor(1.04),
        _accepted_anchor(1.01),
    ]
    candidate = {
        "accepted": False,
        "reject_reason": "continuation_fragment",
        "normalized_headword": "ababadar",
        "text": "ababadar v.t. golpear",
        "pos_cue": "v.t.",
        "confidence": 0.95,
        "source_y": 105,
        "image_boundary_match": {"y": 100, "strength": 0.9},
        "user_rule": {"rejected": False},
        "looks_like_continuation": True,
        "continuation_reason": "punctuated_fragment",
        "parser_stage": "latin_regular",
        "features": {
            "at_left": True,
            "below_header": True,
            "image_boundary_supported": True,
            "boldness_ratio": candidate_boldness,
            "height_ratio": 1.0,
            "structural_cue": True,
            "looks_like_continuation": True,
            "forced_reject": False,
            "marker_noise": False,
            "internal_article_symbol": False,
            "internal_relation_label": False,
            "internal_locution": False,
        },
        "parser_trace": ["continuation_fragment"],
        "bug_types": ["CONTINUATION_FRAGMENT"],
    }
    return anchors + [candidate], candidate


def test_dense_latin_headword_can_override_false_continuation():
    settings = AppSettings(
        ocr_language="por",
        character_height=22,
        paddle_boldness_ratio=1.0,
    )
    diagnostics, candidate = _latin_diagnostics(1.03)
    entries = []

    count = ph._rescue_false_continuation_rows(
        entries,
        diagnostics,
        source_top=10,
        source_column_x=20,
        settings=settings,
        engine_name="paddle",
        profile=None,
    )

    assert count == 1
    assert len(entries) == 1
    assert entries[0].word == "ababadar"
    assert entries[0].y == 110
    assert candidate["accepted"] is True
    assert candidate["features"]["continuation_visual_headword_override"] is True
    assert candidate["looks_like_continuation"] is False


def test_body_like_latin_continuation_is_not_rescued_when_not_bold():
    settings = AppSettings(
        ocr_language="spa",
        character_height=22,
        paddle_boldness_ratio=1.0,
    )
    diagnostics, candidate = _latin_diagnostics(0.74)
    candidate["normalized_headword"] = "parecia"
    candidate["text"] = "parecía alta v. ejemplo"
    entries = []

    count = ph._rescue_false_continuation_rows(
        entries,
        diagnostics,
        source_top=10,
        source_column_x=20,
        settings=settings,
        engine_name="paddle",
        profile=None,
    )

    assert count == 0
    assert entries == []
    assert candidate["accepted"] is False


def test_phase6b_import_keeps_core_supervised_symbols_unmutated():
    import picture_capture.evidence_fusion as fusion

    assert fusion._core.filter_headword_records is fusion._original_filter_headword_records
    assert (
        fusion._core._annotate_peer_typography_matches
        is fusion._original_annotate_peer_typography_matches
    )
    assert ph.filter_headword_records is fusion.filter_headword_records
    assert (
        ph._annotate_peer_typography_matches
        is fusion._annotate_peer_typography_matches
    )
    assert callable(ph.detect_paddle_headwords)


def test_phase6b_filter_injects_supervised_peer_annotator(monkeypatch):
    import picture_capture.evidence_fusion as fusion

    seen = {}

    def fake_original(*_args, **kwargs):
        seen.update(kwargs)
        return [], []

    monkeypatch.setattr(fusion, "_original_filter_headword_records", fake_original)
    entries, diagnostics = fusion.filter_headword_records(
        [],
        object(),
        0,
        0,
        AppSettings(ocr_language="eng"),
    )

    assert entries == []
    assert diagnostics == []
    assert (
        seen["peer_typography_annotator"]
        is fusion._annotate_peer_typography_matches
    )


def test_phase6b_detector_injects_supervised_filter(monkeypatch):
    import picture_capture.evidence_fusion as fusion

    seen = {}

    def fake_detect(*_args, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(fusion, "_original_detect_paddle_headwords", fake_detect)
    result = fusion.detect_paddle_headwords(object(), object(), AppSettings())

    assert result == []
    assert seen["record_filter"] is fusion.filter_headword_records


def test_phase6a_assignment_mirroring_is_public_facade_only(monkeypatch):
    import picture_capture.evidence_fusion as fusion

    core = ph._core
    original_core_runner = core.run_paddle_band

    fusion_runner = object()
    monkeypatch.setattr(fusion, "run_paddle_band", fusion_runner)
    assert fusion.run_paddle_band is fusion_runner
    assert core.run_paddle_band is original_core_runner

    public_runner = object()
    monkeypatch.setattr(ph, "run_paddle_band", public_runner)
    assert ph.run_paddle_band is public_runner
    assert core.run_paddle_band is public_runner


def test_phase6b_custom_core_filter_remains_authoritative(monkeypatch):
    import picture_capture.evidence_fusion as fusion

    custom_filter = lambda *_args, **_kwargs: ([], [])
    seen = {}

    def fake_detect(*_args, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(fusion._core, "filter_headword_records", custom_filter)
    monkeypatch.setattr(fusion, "_original_detect_paddle_headwords", fake_detect)

    fusion.detect_paddle_headwords(object(), object(), AppSettings())

    assert seen["record_filter"] is custom_filter
