"""Issue #562: OCR-to-saved-PDIC training links have one package owner."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from picture_capture import training_export
from picture_capture.training import ground_truth_matching as matching


def _layout(transform):
    return SimpleNamespace(source_to_canonical=transform)


def test_physical_owner_with_unchanged_legacy_training_export_symbol() -> None:
    package = Path(training_export.__file__).resolve().parent
    assert Path(matching.__file__).resolve() == package / "training" / "ground_truth_matching.py"
    assert training_export._candidate_ground_truth_link is matching._candidate_ground_truth_link
    assert matching._candidate_ground_truth_link.__module__ == (
        "picture_capture.training.ground_truth_matching"
    )
    assert "def _candidate_ground_truth_link(" not in (
        package / "training_export.py"
    ).read_text(encoding="utf-8")


def test_rotated_page_matches_on_canonical_reading_axis_but_exports_source_xy() -> None:
    # Vertical/canonical reading progress is -source X here, not source Y.
    transform = _layout(lambda x, y: (y, 1000 - x))
    candidate = {"column": 1, "source_x": 100, "source_y": 700}
    truth = [
        {"column": 1, "x": 105, "y": 501},
        {"column": 1, "x": 160, "y": 698},
        {"column": 0, "x": 100, "y": 700},
    ]
    result = matching._candidate_ground_truth_link(candidate, truth, transform, 20)
    assert result == {
        "ground_truth_selected": True,
        "nearest_ground_truth_source": [105, 501],
        "nearest_ground_truth_source_x": 105,
        "nearest_ground_truth_source_y": 501,
        "ground_truth_source_x_delta": 5,
        "ground_truth_source_y_delta": 199,
    }


def test_rejected_distant_match_retains_real_nearest_ground_truth_and_source_deltas() -> None:
    layout = _layout(lambda x, y: (x, y))
    result = matching._candidate_ground_truth_link(
        {"column": 0, "source_x": 80, "source_y": 100},
        [{"column": 0, "x": 78, "y": 150}],
        layout,
        20,
    )
    assert result["ground_truth_selected"] is False
    assert result["nearest_ground_truth_source"] == [78, 150]
    assert result["ground_truth_source_x_delta"] == 2
    assert result["ground_truth_source_y_delta"] == 50


def test_missing_or_wrong_column_candidate_returns_original_empty_contract() -> None:
    layout = _layout(lambda x, y: (x, y))
    missing = {
        "ground_truth_selected": False,
        "nearest_ground_truth_source": None,
        "ground_truth_source_y_delta": None,
    }
    assert matching._candidate_ground_truth_link(
        {"column": 0, "source_x": None, "source_y": 9}, [],
        layout, 20,
    ) == missing
    assert matching._candidate_ground_truth_link(
        {"column": 2, "source_x": 1, "source_y": 9},
        [{"column": 1, "x": 1, "y": 9}], layout, 20,
    ) == missing


def test_refined_source_y_fallback_and_minimum_four_pixel_tolerance() -> None:
    layout = _layout(lambda x, y: (x, y))
    match = matching._candidate_ground_truth_link(
        {"column": 0, "source_x": 25, "refined_source_y": 100},
        [{"column": 0, "x": 27, "y": 104}],
        layout, 1,
    )
    assert match["ground_truth_selected"] is True
    assert match["ground_truth_source_y_delta"] == 4


def test_leaf_first_import_does_not_import_gui_or_training_export() -> None:
    script = """
import importlib
import sys
leaf = importlib.import_module('picture_capture.training.ground_truth_matching')
assert 'picture_capture.training_export' not in sys.modules
assert 'picture_capture.app' not in sys.modules
root = importlib.import_module('picture_capture.training_export')
assert root._candidate_ground_truth_link is leaf._candidate_ground_truth_link
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
