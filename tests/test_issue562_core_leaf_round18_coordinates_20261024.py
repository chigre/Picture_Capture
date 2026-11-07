"""Round 18: source-coordinate projection and manual anchor variants."""
from __future__ import annotations

import inspect
from copy import deepcopy
from types import SimpleNamespace

from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import review_anchor_variants, source_candidate_coordinates


def test_source_coordinates_use_original_pixels_and_clean_canonical_keys():
    geom = SimpleNamespace(
        x_at=lambda column, y: 10 + int(column) + int(y),
        canonical_to_source=lambda u, v: (100 - u, 200 + v),
    )
    rows = [
        {"meta": {"_header_cutoff_axis_v": "4"}},
        {
            "_axis_v": "10", "_coarse_axis_v": "8", "_anchor_axis_v": "6",
            "canonical_u": 42, "canonical_v": 14,
            "coarse_canonical_v": 8, "anchor_canonical_v": 6,
            "canonical_coordinate_space": "transformed",
        },
    ]
    core._attach_source_candidate_coordinates(rows, geom, 2)
    assert rows[0]["meta"]["coordinate_space"] == "source_image_pixels"
    assert rows[0]["meta"]["header_cutoff_source_x"] == 84
    assert rows[0]["meta"]["header_cutoff_source_y"] == 204
    item = rows[1]
    assert (item["source_x"], item["source_y"]) == (78, 210)
    assert (item["coarse_source_x"], item["coarse_source_y"]) == (80, 208)
    assert (item["anchor_source_x"], item["anchor_source_y"]) == (82, 206)
    assert item["_axis_v"] == 10
    assert item["coordinate_space"] == "source_image_pixels"
    assert "canonical_u" not in item and "canonical_coordinate_space" not in item
    saved = core._source_only_persistence(rows)
    assert "_axis_v" not in saved[1]
    assert saved[1]["source_y"] == 210
    assert core._attach_source_candidate_coordinates.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(core._attach_source_candidate_coordinates).parameters) == [
        "diagnostics", "geometry", "column",
    ]


def test_source_coordinate_leaf_and_historical_core_give_identical_output():
    geom = SimpleNamespace(
        x_at=lambda col, y: col * 50,
        canonical_to_source=lambda x, y: (x + 10, y - 2),
    )
    original = [{"_axis_v": "30", "_coarse_axis_v": "27", "_anchor_axis_v": "25"}]
    a, b = deepcopy(original), deepcopy(original)
    core._attach_source_candidate_coordinates(a, geom, 1)
    source_candidate_coordinates.attach_source_candidate_coordinates(b, geom, 1)
    assert a == b
    assert a[0]["source_y"] == 28


def test_review_anchor_fallback_metadata_isolated_and_unchecked():
    item = {
        "candidate_id": "head-1", "column": 1, "source_x": 12,
        "source_y": 30, "coarse_source_x": 11, "coarse_source_y": 22,
        "anchor_source_x": 14, "anchor_source_y": 25,
        "_axis_v": 30, "_coarse_axis_v": 22, "_anchor_axis_v": 25,
        "position_variant": "refined", "selected": True,
        "issue_types": ["manual_review"],
    }
    candidates = [item]
    assert core._expand_original_y_fallback_candidates(candidates) == 1
    assert len(candidates) == 2
    original = next(v for v in candidates if v["position_variant"] == "original")
    refined = next(v for v in candidates if v["position_variant"] == "refined")
    assert original["candidate_id"] == "head-1-rawy"
    assert original["source_x"] == 14 and original["source_y"] == 25
    assert original["_axis_v"] == 25
    assert not original["selected"] and not original["manual_override"]
    assert original["fallback_kind"] == "image_anchor"
    assert refined["selected"] is True
    assert refined["position_group_id"] == original["position_group_id"] == "head-1"
    assert original["issue_types"] == refined["issue_types"]
    assert original["issue_types"] is not refined["issue_types"]
    assert core._expand_original_y_fallback_candidates.__module__ == "picture_capture.paddle_headwords_core"
    no_fallback = [{"candidate_id": "same", "source_x": 2, "source_y": 20, "anchor_source_y": 20}]
    assert review_anchor_variants.expand_original_y_fallback_candidates(no_fallback) == 0
    assert len(no_fallback) == 1
