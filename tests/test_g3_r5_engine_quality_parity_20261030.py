"""R5.2 synthetic arbitration q parity; NOT verified OCR truth or a learned score."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, fields
from itertools import product
import json
import subprocess
import sys

import pytest

from picture_capture.ocr.engine_quality_scoring import (
    EngineQualityFeatures, score_engine_quality,
)


def old_quality(pair, prefix):
    """Frozen historical pairing_arbitration._engine_quality arithmetic."""
    accepted = pair.get(f"{prefix}_accepted") is True
    score = float(pair.get(f"{prefix}_score") or 0.0)
    conf = float(pair.get(f"{prefix}_conf") or 0.0)
    features = pair.get(f"{prefix}_features", {}) or {}
    repairs = pair.get(f"{prefix}_repairs", []) or []
    q = score + 2.0 * conf + (1.0 if accepted else 0.0)
    if features.get("structural_cue"):
        q += 1.0
    if features.get("strong_visual_fallback"):
        q += 0.35
    if features.get("peer_typography_match"):
        q += 0.30
    boundary = pair.get(f"{prefix}_image_boundary_match", {}) or {}
    if isinstance(boundary, dict) and boundary:
        try:
            boundary_strength = max(0.0, min(1.0, float(boundary.get("strength") or 0.0)))
        except (TypeError, ValueError):
            boundary_strength = 0.0
        q += 0.20 + 0.35 * boundary_strength
    if features.get("forced_accept"):
        q += 1.2
    if features.get("forced_reject"):
        q -= 5.0
    q -= min(0.9, 0.08 * len(repairs))
    return q


def _pair_features(*, bits=(), score=7.0, conf=.92, repairs=0, boundary_strength=0.5):
    names = (
        "accepted", "structural_cue", "strong_visual_fallback",
        "peer_typography_match", "boundary_present", "forced_accept",
        "forced_reject",
    )
    toggles = dict(zip(names, bits))
    values = dict(
        score=score, confidence=conf, repair_count=repairs,
        boundary_strength=boundary_strength,
    )
    values.update(toggles)
    return EngineQualityFeatures(**values)


def test_immutable_snapshot_has_only_primitive_serializable_fields():
    assert tuple(x.name for x in fields(EngineQualityFeatures)) == (
        "accepted", "score", "confidence", "structural_cue",
        "strong_visual_fallback", "peer_typography_match",
        "boundary_present", "boundary_strength", "forced_accept",
        "forced_reject", "repair_count",
    )
    v = _pair_features(bits=(False,) * 7)
    encoded = asdict(v)
    assert json.loads(json.dumps(encoded)) == encoded
    assert all(type(item) in (bool, int, float) for item in encoded.values())
    with pytest.raises(FrozenInstanceError):
        v.score = 123


@pytest.mark.parametrize("score,conf,repairs,boundary_strength", [
    (0.0, 0.0, 0, 0.0),
    (2.75, 0.69, 1, 0.33),
    (7.0, 0.92, 4, 0.8),
    (15.25, 1.0, 100, 1.0),
])
def test_all_128_flag_vectors_preserve_exact_historical_float_order(
    score, conf, repairs, boundary_strength,
):
    for bits in product((False, True), repeat=7):
        v = _pair_features(
            bits=bits, score=score, conf=conf, repairs=repairs,
            boundary_strength=boundary_strength,
        )
        pair = {
            "lens_accepted": v.accepted,
            "lens_score": v.score,
            "lens_conf": v.confidence,
            "lens_repairs": ["REPAIR"] * v.repair_count,
            "lens_image_boundary_match": (
                {"strength": v.boundary_strength} if v.boundary_present else {}
            ),
            "lens_features": {
                "structural_cue": v.structural_cue,
                "strong_visual_fallback": v.strong_visual_fallback,
                "peer_typography_match": v.peer_typography_match,
                "forced_accept": v.forced_accept,
                "forced_reject": v.forced_reject,
            },
        }
        assert score_engine_quality(v) == old_quality(pair, "lens")
        assert score_engine_quality(EngineQualityFeatures(**json.loads(json.dumps(asdict(v))))) == old_quality(pair, "lens")


@pytest.mark.parametrize("prefix", ("paddle", "tesseract", "lens"))
@pytest.mark.parametrize("boundary", (
    {}, {"strength": "not-a-number"}, {"strength": None},
    {"strength": -100.0}, {"strength": 9.0}, {"strength": 0.67},
    {"strength": float("nan")}, {"strength": object()}, ["nondict"],
    {"unrelated": "still a matched boundary"},
))
def test_old_q_and_new_owner_match_boundary_missing_invalid_and_clamped(
    prefix, boundary,
):
    from picture_capture import paddle_headwords_core as core
    pair = {
        f"{prefix}_score": "5.25",
        f"{prefix}_conf": "0.9",
        f"{prefix}_accepted": True,
        f"{prefix}_features": {"structural_cue": True, "forced_reject": True},
        f"{prefix}_repairs": ["RIGHT_FRAGMENT_ABSORBED", "MULTILINE_POS"],
        f"{prefix}_image_boundary_match": boundary,
    }
    original = deepcopy(pair)
    assert core._engine_quality(pair, prefix) == old_quality(pair, prefix)
    # Nan values compare unequally to themselves; check the source reference
    # was not replaced with a new mapping or stripped by the pure function.
    assert pair[f"{prefix}_image_boundary_match"] is boundary


@pytest.mark.parametrize("value", ("unparseable", object()))
def test_bad_score_and_confidence_retain_existing_failures(value):
    from picture_capture import paddle_headwords_core as core
    for key in ("score", "conf"):
        pair = {"paddle_score": 4.0, "paddle_conf": 0.95}
        pair[f"paddle_{key}"] = value
        with pytest.raises((ValueError, TypeError)) as expected:
            old_quality(pair, "paddle")
        with pytest.raises(type(expected.value)):
            core._engine_quality(pair, "paddle")


def _candidate(word, y, *, score=7.0, accepted=True, conf=.92, features=None):
    return {
        "normalized_headword": word, "raw_headword": word,
        "corrected_headword": word, "text": word,
        "box": (13, y - 4, 86, y + 15),
        "accepted": accepted, "confidence": conf, "score": score,
        "_axis_v": y, "source_x": 13, "source_y": y,
        "features": {"at_left": True, "structural_cue": True, **(features or {})},
    }


@pytest.mark.parametrize("case", (
    "dual_tie", "dual_tess_higher", "similar_close", "different_acceptance",
    "different_both_accepted", "paddle_only", "tesseract_only",
    "lens_only", "lens_only_diagnostic", "lens_agrees_paddle",
    "three_way_agree", "lens_disagrees_with_local_consensus",
    "forced_reject", "repairs_boundary", "soft_reject",
))
def test_legacy_and_pure_q_produce_identical_entire_arbitration_record(
    monkeypatch, case,
):
    from picture_capture import paddle_headwords_core as core
    from picture_capture.models import AppSettings

    p = _candidate("atlas", 60)
    t = _candidate("atlas", 61)
    lens = None
    settings = AppSettings()
    if case == "dual_tess_higher":
        t["score"] = 10.0
    elif case == "similar_close":
        t["normalized_headword"] = "atlasé"
    elif case == "different_acceptance":
        t["normalized_headword"] = "banco"
        t["accepted"] = False
    elif case == "different_both_accepted":
        t["normalized_headword"] = "banco"
    elif case == "paddle_only":
        t = None
    elif case == "tesseract_only":
        p = None
    elif case in ("lens_only", "lens_only_diagnostic"):
        p = t = None
        lens = _candidate("only", 62)
        settings.paddle_lens_mode = "diagnostic" if case.endswith("diagnostic") else "on"
    elif case in ("lens_agrees_paddle", "three_way_agree", "lens_disagrees_with_local_consensus"):
        lens = _candidate("atlas" if case != "lens_disagrees_with_local_consensus" else "other", 62, score=9.0)
        settings.paddle_lens_mode = "on"
        if case == "lens_agrees_paddle":
            t["normalized_headword"] = "banco"
    elif case == "forced_reject":
        p["features"]["forced_reject"] = True
    elif case == "repairs_boundary":
        p["ocr_repairs"] = ["RIGHT_FRAGMENT_ABSORBED"] * 15
        p["image_boundary_match"] = {"strength": "invalid"}
    elif case == "soft_reject":
        p["accepted"] = False
        t["accepted"] = False
        p["reject_reason"] = "missing_pos_inflection_descriptor_or_symbol"
        t["reject_reason"] = "missing_pos_inflection_descriptor_or_symbol"
        p["features"]["strong_visual_fallback"] = True
    if case == "dual_tie":
        t["score"] = p["score"]
        t["confidence"] = p["confidence"]

    pair = core._make_ocr_pair(p, t, "synthetic_parity")
    if lens:
        core._copy_candidate_to_pair(pair, "lens", lens)
    pair_original = deepcopy(pair)
    historical_quality = core._engine_quality
    monkeypatch.setattr(core, "_engine_quality", lambda pair, prefix: old_quality(pair, prefix))
    historical_result = core._arbitrate_pair(pair, 1, 17, settings)
    monkeypatch.setattr(core, "_engine_quality", historical_quality)
    extracted_result = core._arbitrate_pair(pair, 1, 17, settings)
    assert extracted_result == historical_result, case
    assert pair == pair_original
    assert extracted_result["coordinate_space"] == "source_image_pixels"
    assert extracted_result["source_y"] >= 0


def test_existing_quality_facade_passes_snapshot_and_monkeypatch_remains_live(monkeypatch):
    from picture_capture import paddle_headwords_core as core
    from picture_capture.ocr import pairing_arbitration as owner

    original = owner.score_engine_quality
    captured = []
    def score_spy(features):
        assert isinstance(features, EngineQualityFeatures)
        captured.append(features)
        return original(features)
    monkeypatch.setattr(owner, "score_engine_quality", score_spy)
    pair = {"paddle_score": 7.0, "paddle_conf": 0.95,
            "paddle_accepted": True, "paddle_features": {"structural_cue": True}}
    assert core._engine_quality(pair, "paddle") == old_quality(pair, "paddle")
    assert len(captured) == 1


def test_pure_engine_score_does_not_import_ocr_runtime_gui_or_engines():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ocr.engine_quality_scoring import EngineQualityFeatures, score_engine_quality
assert "picture_capture.paddle_headwords_core" not in sys.modules
assert "picture_capture.app" not in sys.modules
assert "paddle" not in sys.modules
assert "tkinter" not in sys.modules
"""], check=True)
