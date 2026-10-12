"""Oversized headword rescue from transitive multirow/phonetic regions.

Regression reproduces the documented Page009 regions (their *geometry*,
not their page coordinates). No dictionary-specific locations, words, or
saved annotations are used by the production detector.
"""
import numpy as np

from picture_capture.ordinary_large_head_evidence import (
    _candidate_boxes,
    _recover_oversized_front_lane,
)


def _strip_image():
    ink = np.zeros((510, 270), dtype=bool)
    # Four full-size independent CJK display glyph footprints.
    # With 13px gaps (<.50*30) original transitive grouping joins them.
    for top in (25, 108, 191, 356):
        ink[top:top+70, 12:88] = True
    # Normal body lines inside the same large merged envelope.
    ink[274:303, 12:88] = True
    ink[318:347, 12:88] = True
    return ink


def test_tall_chain_of_heads_recovers_separate_glyphs_not_normal_rows():
    ink = _strip_image()
    boxes = []
    detected = _candidate_boxes(ink, 30, boxes)
    expected_y = [25, 108, 191, 356]
    assert len(detected) == 4
    assert [box[1] for box in detected] == expected_y
    assert all(box[3] - box[1] == 70 for box in detected)
    assert sum(row["reason"] == "geometry_pass" for row in boxes) == 4
    assert sum(row["reason"] == "split_parent" for row in boxes) == 1


def test_wide_bracket_annotation_does_not_obscure_single_tall_head():
    ink = np.zeros((160, 270), dtype=bool)
    ink[20:91, 5:98] = True
    # A word/annotation to the right is close enough to be transitively
    # grouped, even though it is not part of the first enlarged ideograph.
    ink[34:70, 110:165] = True
    traced = []
    detected = _candidate_boxes(ink, 30, traced)
    assert len(detected) == 1
    assert detected[0] == (5, 20, 98, 91)
    assert any(row["reason"] == "split_parent" for row in traced)


def test_normal_size_text_groups_are_not_promoted_to_large_heads():
    ink = np.zeros((360, 245), dtype=bool)
    for top in (10, 57, 104, 151, 198):
        ink[top:top+29, 10:82] = True
    detected = _candidate_boxes(ink, 30)
    assert detected == []


def test_front_lane_rescue_does_not_require_existing_layout_roles():
    ink = _strip_image()
    recovered = _recover_oversized_front_lane(
        ink, (12, 25, 88, 426), 30,
    )
    assert [box[1] for box in recovered] == [25, 108, 191, 356]


def test_recovered_parent_diagnostics_keep_exact_child_count():
    """Every recoverable giant group must export its true child count."""
    observed = []
    boxes = _candidate_boxes(_strip_image(), 30, observed)
    parents = [row for row in observed if row["reason"] == "split_parent"]
    assert len(parents) == 1
    assert parents[0]["recovered_count"] == len(boxes) == 4
    children = [row for row in observed if row.get("parent") == parents[0]["box"]]
    assert len(children) == parents[0]["recovered_count"]
