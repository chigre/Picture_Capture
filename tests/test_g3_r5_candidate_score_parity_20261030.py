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
