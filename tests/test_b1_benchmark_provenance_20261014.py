"""B1/R1.3: prevent historical cache F1 from becoming current-detector F1."""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.benchmark_provenance import (
    build_quality_report,
    markdown_quality_report,
    quality_rows,
)


def _current():
    return {
        "format": "picture-capture-detection-benchmark-v1",
        "run_type": "current_detector",
        "ground_truth_status": "saved_pdic_unless_independently_verified",
        "summary": {"paddleocr": {
            "true_positive": 9, "false_positive": 1,
            "false_negative": 2, "precision": 0.9,
            "recall": 0.818182, "f1": 0.857143,
            "ground_truth_pages": 3,
        }},
    }


def _historic():
    return {
        "format": "picture-capture-archive-audit-v1",
        "run_type": "historic_cache",
        "datasets": [
            {
                "kind": "historic_training_cache",
                "archive": "example.zip", "project": "mock-dictionary",
                "pages": 3, "TP": 1, "FP": 2, "FN": 3,
                "precision": 0.333333, "recall": 0.25, "F1": 0.285714,
            },
            {"kind": "image_only_no_ground_truth", "archive": "no-gt.zip", "images": 3},
        ],
    }


def test_quality_report_keeps_historical_and_current_scores_in_separate_rows():
    result = build_quality_report([("historical.json", _historic()), ("current.json", _current())])
    assert [row["run_type"] for row in result["rows"]] == [
        "historic_cache", "current_detector",
    ]
    assert result["rows"][0]["f1"] == 0.285714
    assert result["rows"][1]["f1"] == 0.857143
    assert result["rows"][0]["dictionary"] == "mock-dictionary"
    assert "warning" in result
    markdown = markdown_quality_report(result)
    assert "historic_cache" in markdown and "current_detector" in markdown
    assert markdown.count(chr(10)) >= 7


@pytest.mark.parametrize("invalid", [
    {"format": "picture-capture-detection-benchmark-v1", "run_type": "historic_cache"},
    {"format": "picture-capture-archive-audit-v1", "run_type": "current_detector"},
    {"format": "picture-capture-random-unknown"},
])
def test_quality_provenance_never_guesses_or_relabels(invalid):
    with pytest.raises(ValueError):
        quality_rows(invalid, label="invalid.json")


def test_no_labeled_archives_cannot_synthesize_accuracy():
    report = {
        "format": "picture-capture-archive-audit-v1",
        "datasets": [{"kind": "image_only_no_ground_truth", "images": 24}],
    }
    assert quality_rows(report, label="unlabelled.json") == []


def test_existing_benchmark_runners_declare_separate_sources():
    root = Path(__file__).resolve().parents[1] / "scripts"
    current = (root / "detection_benchmark.py").read_text(encoding="utf-8")
    historic = (root / "benchmark_training_archives.py").read_text(encoding="utf-8")
    regenerated = (root / "run_training_archive_full_benchmark.py").read_text(encoding="utf-8")
    assert '"run_type": "current_detector"' in current
    assert '"run_type": "historic_cache"' in historic
    assert 'result["test_kind"] = "actual_detection_regenerated"' in regenerated
    assert "marker_metrics(" in current
