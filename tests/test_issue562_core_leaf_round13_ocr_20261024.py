"""Issue #562 round 13: CJK visual rescue and typography diagnostics leaves."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import paddle_headwords as public_paddle
from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import peer_typography, visual_rescue_policy

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def cfg(**kw):
    values = dict(
        profile_tail_structure_version=0,
        profile_tail_allow_visual_rescue=False,
        paddle_allow_strong_edge_visual_rescue=True,
        paddle_boldness_ratio=1.3,
        paddle_rec_score_threshold=0.6,
        paddle_strong_edge_visual_boldness_ratio=1.22,
        paddle_strong_edge_visual_height_ratio=0.9,
        paddle_strong_edge_visual_min_confidence=0.55,
        profile_tail_allow_pos=True,
        profile_tail_allow_inflection=True,
        profile_tail_allow_variant=True,
        profile_tail_allow_pronunciation=False,
        profile_tail_allow_descriptor=True,
    )
    values.update(kw)
    return SimpleNamespace(**values)


def parsed():
    return SimpleNamespace(
        normalized="bonjour", parser_trace=("pronunciation:/foo/",),
        has_pos=True, has_inflection=True, has_descriptor=True, variants=("b",),
    )


def test_leaf_inventory_signature_and_legacy_origins():
    assert len(list(PKG.glob("*.py"))) == 10
    for path in ("ocr/visual_rescue_policy.py", "ocr/peer_typography.py"):
        assert (PKG / path).is_file()
        assert not (PKG / Path(path).name).exists()
    for fn in (
        core._accepted_cjk_row_for_visual_run,
        core._selected_tail_structure_evidence,
        core._ordinary_visual_rescue_thresholds,
        core._ordinary_strong_edge_visual_rescue,
        core._median_and_mad,
        core._annotate_peer_typography_matches,
    ):
        assert fn.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(core._ordinary_strong_edge_visual_rescue).parameters) == [
        "settings", "parsed", "at_left", "below_header", "boldness_ratio",
        "height_ratio", "confidence", "looks_like_continuation", "marker_noise",
    ]


def test_accepted_cjk_matches_only_same_physical_run_and_current_script_hook(monkeypatch):
    row = {
        "accepted": True, "normalized_headword": "漢", "features": {},
        "box": [4, 20, 25, 55],
    }
    assert core._accepted_cjk_row_for_visual_run([row], 24, 48, "漢") is row
    assert core._accepted_cjk_row_for_visual_run([row], 130, 148, "漢") is None
    original = core._is_single_cjk_ideograph
    monkeypatch.setattr(public_paddle, "_is_single_cjk_ideograph", lambda word: False)
    assert core._accepted_cjk_row_for_visual_run([row], 24, 48, "漢") is None
    monkeypatch.setattr(public_paddle, "_is_single_cjk_ideograph", original)
    assert visual_rescue_policy.accepted_cjk_row_for_visual_run(
        [row], 24, 48, "漢", single_cjk_fn=original,
    ) is row


def test_profile_v0_v1_tail_evidence_and_visible_thresholds():
    legacy = cfg()
    selected, meta = core._selected_tail_structure_evidence(legacy, parsed())
    assert set(selected) == {"pos", "inflection", "descriptor"}
    assert meta["available_variant"] and not meta["selected_variant"]
    explicit = cfg(
        profile_tail_structure_version=1,
        profile_tail_allow_pos=False,
        profile_tail_allow_pronunciation=True,
        profile_tail_allow_visual_rescue=True,
    )
    selected, meta = core._selected_tail_structure_evidence(explicit, parsed())
    assert "pos" not in selected
    assert "variant" in selected and "pronunciation" in selected
    assert not meta["selected_pos"]
    t0 = core._ordinary_visual_rescue_thresholds(legacy)
    assert t0["source"] == "legacy_hidden_thresholds"
    t1 = core._ordinary_visual_rescue_thresholds(explicit)
    assert t1 == visual_rescue_policy.ordinary_visual_rescue_thresholds(explicit)
    assert t1["source"] == "visible_profile_specificity"
    assert t1["height"] == 0.0
    assert t1["boldness"] == 1.3


def test_rescue_requires_semantic_guards_and_live_threshold_patch(monkeypatch):
    settings = cfg(profile_tail_structure_version=1, profile_tail_allow_visual_rescue=True)
    kwargs = dict(
        at_left=True, below_header=True, boldness_ratio=1.1, height_ratio=0.9,
        confidence=0.9, looks_like_continuation=False, marker_noise=False,
    )
    assert not core._ordinary_strong_edge_visual_rescue(settings, parsed(), **kwargs)
    original = core._ordinary_visual_rescue_thresholds
    monkeypatch.setattr(
        public_paddle, "_ordinary_visual_rescue_thresholds",
        lambda settings: {"boldness": 1.0, "height": 0.5, "confidence": 0.7},
    )
    assert core._ordinary_strong_edge_visual_rescue(settings, parsed(), **kwargs)
    assert not core._ordinary_strong_edge_visual_rescue(
        settings, parsed(), **{**kwargs, "at_left": False},
    )
    assert not core._ordinary_strong_edge_visual_rescue(
        settings, parsed(), **{**kwargs, "marker_noise": True},
    )
    monkeypatch.setattr(public_paddle, "_ordinary_visual_rescue_thresholds", original)


def _anchor():
    return {
        "accepted": True, "confidence": .97,
        "features": dict(
            height_ratio=1.2, boldness_ratio=1.5, preceding_gap=12,
            at_left=True, below_header=True,
        ),
    }


def test_peer_typography_annotations_never_accept_and_require_anchor_quorum(monkeypatch):
    soft = {
        "accepted": False, "confidence": 0.88, "reject_reason": "score_below_threshold",
        "normalized_headword": "casa",
        "features": dict(
            at_left=True, below_header=True, image_boundary_supported=True,
            height_ratio=1.2, boldness_ratio=1.5, preceding_gap=12,
        ),
    }
    rows = [_anchor() for _ in range(3)] + [soft]
    assert core._annotate_peer_typography_matches(rows) == 0
    assert not soft["accepted"]
    rows.insert(0, _anchor())
    calls = []
    original = core._median_and_mad
    def observed(values):
        calls.append(tuple(values))
        return original(values)
    monkeypatch.setattr(public_paddle, "_median_and_mad", observed)
    assert core._annotate_peer_typography_matches(rows) == 1
    assert len(calls) == 3
    assert not soft["accepted"]
    assert soft["features"]["peer_typography_match"] is True
    assert soft["features"]["peer_typography_anchor_count"] == 4
    assert soft["parser_trace"] == ["peer_typography_match"]
    assert soft["bug_types"] == ["PEER_TYPOGRAPHY_MATCH"]
    assert core._annotate_peer_typography_matches(rows) == 1
    assert soft["parser_trace"] == ["peer_typography_match"]
    monkeypatch.setattr(public_paddle, "_median_and_mad", original)


def test_robust_typography_center_and_outlier_spread():
    assert core._median_and_mad([]) == (0.0, 0.0)
    assert core._median_and_mad([1, 3, 9]) == (3.0, 2.0)
    assert core._median_and_mad([1, 3, 9]) == peer_typography.median_and_mad([1, 3, 9])
