"""B1 synthetic golden tests: metric semantics, no actual scan accuracy claims."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from picture_capture.quality.detection_quality_metrics import (
    MATCHING_ALGORITHM,
    marker_metrics,
    pooled_counts,
)


FIXTURE = Path(__file__).parent / "fixtures" / "headword_quality_v1.json"


def test_quality_golden_fixture_identity_and_accuracy_cases():
    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert corpus["run_type"] == "synthetic_fixture"
    assert corpus["label_status"] == "synthetic_contract_only_not_human_truth"
    assert len(corpus["examples"]) >= 6
    for row in corpus["examples"]:
        actual = marker_metrics(row["predicted"], row["reference"], row["tolerance"])
        assert actual["matching_algorithm"] == MATCHING_ALGORITHM
        for key, value in row["expected"].items():
            assert actual[key] == value, (row["id"], key, actual[key], value)


def test_quality_match_is_monotonic_with_close_neighbors():
    result = marker_metrics([(0, 0), (0, 5)], [(0, 4), (0, 9)], 5)
    assert result["matched"] == 2
    assert result["median_abs_delta_v"] == 4


@pytest.mark.parametrize("bad", [-1, -100])
def test_quality_tolerance_rejects_negative_values(bad):
    with pytest.raises(ValueError, match="tolerance"):
        marker_metrics([], [], bad)


def test_quality_pooled_counts_are_micro_average_not_average_page_f1():
    counts = pooled_counts(1, 1, 2)
    assert counts == {
        "tp": 1, "fp": 1, "fn": 2,
        "precision": 0.5, "recall": 0.333333, "f1": 0.4,
    }
    with pytest.raises(ValueError):
        pooled_counts(3, -1, 2)


def test_quality_permutation_and_empty_page_contract():
    first = marker_metrics([(1, 200), (0, 100)], [(0, 100), (1, 200)], 1)
    assert first["exact"] is True
    assert first["matched"] == 2
    assert marker_metrics([], [], 1)["f1"] == 1.0
    # Without verified truth, the caller must NOT call this with reference=[].
    assert marker_metrics([(0, 100)], [], 1)["false_positive"] == 1
