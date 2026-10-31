"""G3 R5.1 synthetic parity: immutable primitive score input, no OCR engine labels."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields
from itertools import product
import json
import subprocess
import sys

import pytest

from picture_capture.ocr.candidate_scoring import CandidateScoreFeatures, score_candidate


WEIGHTS = (
    ("parsed", 2.0),
    ("left_evidence", 2.0),
    ("selected_pos", 3.0),
    ("selected_inflection", 2.0),
    ("selected_variant", 1.5),
    ("selected_pronunciation", 1.5),
    ("selected_descriptor", 3.0),
    ("front_structure_cue", 1.0),
    ("large", 0.75),
    ("bold", 1.0),
    ("separated", 0.5),
    ("cjk_candidate_right_sparse", 0.75),
)


def test_score_snapshot_has_exact_twelve_primitive_bool_terms():
    assert tuple(field.name for field in fields(CandidateScoreFeatures)) == tuple(
        name for name, _ in WEIGHTS
    )
    snapshot = CandidateScoreFeatures(**{name: False for name, _ in WEIGHTS})
    assert all(type(v) is bool for v in asdict(snapshot).values())
    assert json.loads(json.dumps(asdict(snapshot))) == asdict(snapshot)
    with pytest.raises(FrozenInstanceError):
        snapshot.parsed = True


def test_exact_legacy_candidate_score_for_all_4096_boolean_feature_vectors():
    # Old expression at candidate_filter.py: the weights/ordering are a frozen
    # pre-extraction baseline; never infer a new threshold from these fixtures.
    names = [name for name, _ in WEIGHTS]
    for bits in product((False, True), repeat=len(names)):
        snapshot = CandidateScoreFeatures(**dict(zip(names, bits)))
        legacy_score = (
            (2.0 if snapshot.parsed else 0.0)
            + (2.0 if snapshot.left_evidence else 0.0)
            + (3.0 if snapshot.selected_pos else 0.0)
            + (2.0 if snapshot.selected_inflection else 0.0)
            + (1.5 if snapshot.selected_variant else 0.0)
            + (1.5 if snapshot.selected_pronunciation else 0.0)
            + (3.0 if snapshot.selected_descriptor else 0.0)
            + (1.0 if snapshot.front_structure_cue else 0.0)
            + (0.75 if snapshot.large else 0.0)
            + (1.0 if snapshot.bold else 0.0)
            + (0.5 if snapshot.separated else 0.0)
            + (0.75 if snapshot.cjk_candidate_right_sparse else 0.0)
        )
        assert score_candidate(snapshot) == legacy_score, (bits, legacy_score)
        assert score_candidate(CandidateScoreFeatures(**json.loads(json.dumps(asdict(snapshot))))) == legacy_score


@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        ({"parsed": True, "left_evidence": True, "selected_pos": True}, 7.0),
        ({"parsed": True, "left_evidence": True, "selected_descriptor": True}, 7.0),
        ({"parsed": True, "left_evidence": True, "selected_variant": True,
          "selected_pronunciation": True}, 7.0),
        ({"parsed": True, "left_evidence": True, "large": True, "bold": True,
          "separated": True}, 6.25),
        ({"parsed": True, "left_evidence": False, "cjk_candidate_right_sparse": True}, 2.75),
        ({}, 0.0),
    ],
)
def test_synthetic_pos_descriptor_cjk_visual_and_no_parse(signals, expected):
    values = {name: signals.get(name, False) for name, _ in WEIGHTS}
    assert score_candidate(CandidateScoreFeatures(**values)) == expected


def test_pure_score_module_imports_without_gui_ocr_or_heavy_runtime():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ocr.candidate_scoring import CandidateScoreFeatures, score_candidate
assert 'picture_capture.app' not in sys.modules
assert 'picture_capture.paddle_headwords_core' not in sys.modules
assert 'paddle' not in sys.modules
assert 'tkinter' not in sys.modules
"""], check=True)


def test_real_filter_records_use_pure_score_without_changing_diagnostic_contract(monkeypatch):
    from PIL import Image
    from picture_capture import paddle_headwords_core as core
    from picture_capture.models import AppSettings
    from picture_capture.ocr import candidate_filter
    from picture_capture.ocr.headword_models import OCRRecord

    observed = []
    real_score = candidate_filter.score_candidate

    def track_score(snapshot):
        observed.append(snapshot)
        return real_score(snapshot)

    monkeypatch.setattr(candidate_filter, "score_candidate", track_score)
    image = Image.new("RGB", (160, 120), "white")
    try:
        entries, diagnostics = core.filter_headword_records(
            [OCRRecord("árbol m. tree", 0.99, (2, 20, 135, 35))],
            image, source_top=45, source_column_x=12, settings=AppSettings(),
        )
        candidates = [row for row in diagnostics if "score" in row]
        assert len(observed) == len(candidates) == 1
        assert diagnostics[0].get("meta", {}).get("line_count") == 1
        row = candidates[0]
        assert row["score"] == round(real_score(observed[0]), 3)
        assert row["features"]["at_left"] is True
        assert row["source_y"] >= 45 and row["coarse_source_y"] >= 45
        assert row["accepted"] is False or row["reject_reason"] == ""
        assert all(entry.x == 12 and entry.y >= 45 for entry in entries)
    finally:
        image.close()


@pytest.mark.parametrize("engine", ["paddle", "tesseract", "lens"])
@pytest.mark.parametrize(
    ("text", "language", "min_score", "force_reject"),
    [
        ("árbol m. tree", "spa", 0.0, False),
        ("árbol m. tree", "spa", 100.0, False),
        ("árbol m. tree", "spa", 0.0, True),
        ("中", "chi_tra", 0.0, False),
        ("【中文】", "chi_tra", 0.0, False),
        ("incomplete continuation", "spa", 0.0, False),
    ],
)
def test_legacy_math_and_extracted_math_yield_identical_full_filter_outputs(
    monkeypatch, engine, text, language, min_score, force_reject,
):
    # Differential E2 test: every downstream acceptance/reject decision,
    # diagnostics feature, repaired source coordinate and Entry is compared.
    # This is NOT a human ground-truth OCR accuracy test.
    from PIL import Image
    from picture_capture import paddle_headwords_core as core
    from picture_capture.models import AppSettings
    from picture_capture.ocr import candidate_filter
    from picture_capture.ocr.headword_models import OCRRecord

    def old_score(f):
        return (
            (2.0 if f.parsed else 0.0)
            + (2.0 if f.left_evidence else 0.0)
            + (3.0 if f.selected_pos else 0.0)
            + (2.0 if f.selected_inflection else 0.0)
            + (1.5 if f.selected_variant else 0.0)
            + (1.5 if f.selected_pronunciation else 0.0)
            + (3.0 if f.selected_descriptor else 0.0)
            + (1.0 if f.front_structure_cue else 0.0)
            + (0.75 if f.large else 0.0)
            + (1.0 if f.bold else 0.0)
            + (0.5 if f.separated else 0.0)
            + (0.75 if f.cjk_candidate_right_sparse else 0.0)
        )

    settings = AppSettings(ocr_language=language)
    settings.paddle_min_candidate_score = min_score
    rules = (
        core.parse_headword_filter_rules("reject_lemma_exact: árbol")
        if force_reject else []
    )
    image = Image.new("RGB", (160, 130), "white")
    try:
        original = candidate_filter.score_candidate
        monkeypatch.setattr(candidate_filter, "score_candidate", old_score)
        reference = core.filter_headword_records(
            [OCRRecord(text, .99, (2, 18, 140, 35))],
            image, source_top=50, source_column_x=11,
            settings=settings, user_rules=rules, engine_name=engine,
        )
        monkeypatch.setattr(candidate_filter, "score_candidate", original)
        after = core.filter_headword_records(
            [OCRRecord(text, .99, (2, 18, 140, 35))],
            image, source_top=50, source_column_x=11,
            settings=settings, user_rules=rules, engine_name=engine,
        )
        assert after == reference
        assert all(row["source_y"] >= 50 and row["coarse_source_y"] >= 50
                   for row in after[1] if "score" in row)
        assert all(entry.x == 11 and entry.ocr_source == engine for entry in after[0])
    finally:
        image.close()
