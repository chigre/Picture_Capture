"""#562 full Paddle/Tesseract/Lens sequence pairing and voting boundary."""
from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace
import subprocess
import sys

import pytest

from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import pairing_arbitration as owner
from picture_capture.models import AppSettings


def candidate(word, y, *, accepted=True, conf=.92, score=7.0):
    return {
        "normalized_headword": word, "raw_headword": word, "corrected_headword": word,
        "text": word, "box": (12, y - 4, 85, y + 15),
        "accepted": accepted, "confidence": conf, "score": score,
        "_axis_v": y, "source_x": 12, "source_y": y,
        "features": {"at_left": True, "structural_cue": True},
    }


def test_leaf_import_never_initializes_heavy_core_gui_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ocr.pairing_arbitration import OcrPairingDeps
assert 'picture_capture.paddle_headwords_core' not in sys.modules
assert 'picture_capture.paddle_headwords' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_dependency_snapshot_includes_original_matching_patch_seams():
    actual = {f.name for f in fields(owner.OcrPairingDeps)}
    assert len(actual) == 18
    assert {"_candidate_axis_v", "_candidate_rows", "_pair_ocr_candidates",
            "_arbitrate_pair", "_agreement_summary", "_lemma_similarity"} <= actual
    snap = core._ocr_pairing_deps()
    assert snap._arbitrate_pair is core._arbitrate_pair
    assert snap._candidate_axis_v is core._candidate_axis_v


def test_unicode_lemma_key_preserves_han_and_strips_diacritic():
    assert core._alignment_key("Ár-bol 汉字") == "arbol汉字"
    assert core._lemma_similarity("书", "书") == 1.0
    assert core._lemma_similarity("书", "字") < .82
    assert core._orthographic_similarity("niño", "nino") < 1.0


def test_pairing_missing_middle_record_does_not_shift_next_match():
    paddle = [candidate("atlas", 40), candidate("bonjour", 80),
              candidate("casa", 120)]
    tess = [candidate("atlas", 41), candidate("casa", 121)]
    pairs = core._pair_ocr_candidates(paddle, tess, tolerance=10)
    assert len(pairs) == 3
    assert sum(x.get("paddle_y") is not None and x.get("tesseract_y") is not None
               for x in pairs) == 2
    middle = next(x for x in pairs if x.get("paddle_lemma") == "bonjour")
    assert middle["tesseract_y"] is None
    trailing = next(x for x in pairs if x.get("paddle_lemma") == "casa")
    assert trailing["tesseract_lemma"] == "casa"
    assert trailing["alignment_method"] == "sequence_exact"


def test_pair_alignment_captures_live_similarity_override(monkeypatch):
    p, t = candidate("alpha", 60), candidate("beta", 60)
    monkeypatch.setattr(core, "_lemma_similarity", lambda left, right: .75)
    assert core._candidate_pair_score(p, t, tolerance=10) == pytest.approx(.82)
    pair = core._make_ocr_pair(p, t, "manual")
    assert pair["lemma_similarity"] == .75
    assert pair["alignment_method"] == "manual"


def test_lens_enrichment_attaches_matching_third_vote_and_retains_unmatched():
    pairs = core._pair_ocr_candidates(
        [candidate("atlas", 40)], [candidate("atlas", 41)], tolerance=12)
    result = core._pair_with_lens_candidates(
        pairs, [candidate("atlas", 42), candidate("other", 200)],
        tolerance=12, min_similarity=.55)
    assert len(result) == 2
    matched = next(p for p in result if p.get("paddle_lemma") == "atlas")
    unmatched = next(p for p in result if p.get("lens_lemma") == "other")
    assert matched["lens_y"] == 42
    assert matched["lens_alignment_method"] == "sequence_y_similar"
    assert unmatched["reason"] == "lens_only"
    assert unmatched["lens_y"] == 200


def test_explicit_diagnostic_lens_mode_does_not_silently_select_lens_only():
    pair = core._make_ocr_pair(None, None, "sequence_lens_only")
    core._copy_candidate_to_pair(pair, "lens", candidate("only", 64))
    settings = AppSettings()
    settings.paddle_lens_mode = "diagnostic"
    item = core._arbitrate_pair(pair, 0, 12, settings)
    assert item["selected"] is False
    assert item["final_engine"] == ""
    assert item["source_y"] == 64
    assert item["coordinate_space"] == "source_image_pixels"


def test_agreeing_dual_engine_keeps_acceptance_and_source_coordinates():
    p, t = candidate("alpha", 61), candidate("alpha", 62)
    pair = core._make_ocr_pair(p, t, "sequence_exact")
    result = core._arbitrate_pair(pair, 1, 15, AppSettings())
    assert result["selected"] is True
    assert result["decision_reason"] == "dual_agree_higher_quality"
    assert result["final_engine"] in {"paddle", "tesseract"}
    assert result["candidate_id"].startswith("c2-y")
    assert result["coordinate_space"] == "source_image_pixels"
    assert result["paddle"]["y"] == 61


def test_source_coordinate_reassignment_carries_coarse_and_anchor_as_one_engine():
    pair = core._make_ocr_pair(candidate("alpha", 60), None)
    pair["paddle_coarse_y"] = 58
    pair["paddle_anchor_y"] = 55

    class Geometry:
        def x_at(self, col, y):
            return col * 100 + y
        def canonical_to_source(self, x, y):
            return x + 1000, y + 2000

    item = {}
    core._apply_pair_engine_position(item, pair, "paddle", 2, 10, Geometry())
    assert item["source_x"] == 1260 and item["source_y"] == 2060
    assert item["coarse_source_y"] == 2058
    assert item["anchor_source_y"] == 2055
    assert item["_axis_v"] == 60 and item["_coarse_axis_v"] == 58


def test_agreement_excludes_original_y_fallback_and_non_headword_body_rows():
    pair = core._arbitrate_pair(
        core._make_ocr_pair(candidate("atlas", 31), candidate("atlas", 32)),
        0, 12, AppSettings())
    fallback = dict(pair)
    fallback["position_variant"] = "original"
    rejected = {
        "selected": False, "needs_review": False,
        "paddle": {"y": 90, "lemma": "noise", "accepted": False},
        "tesseract": {}, "lens": {},
    }
    summary = core._agreement_summary([pair, fallback, rejected])
    assert summary["candidate_union"] == 1
    assert summary["paired"] == 1 and summary["exact"] == 1
    assert summary["agreement"] == 1.0
