"""Regression for false positive/false negative scoring and production pairing."""
import pytest

from picture_capture.quality.ordered_marker_matching import match_ordered_markers


def edges(left, right, tolerance):
    return [
        (abs(a-b), i, j)
        for i, a in enumerate(left)
        for j, b in enumerate(right)
        if abs(a-b) <= tolerance
    ]


def test_nearest_first_greedy_loses_valid_second_word():
    # Greedy takes (5,4) (distance=1), stranding both 0 and 9.
    # Correct lexicographic objective is 2 matches: (0,4), (5,9).
    assert match_ordered_markers(2, 2, edges([0, 5], [4, 9], 5)) == [
        (0, 0), (1, 1),
    ]


def test_minimize_delta_given_equal_match_cardinality():
    assert match_ordered_markers(
        3, 2, edges([10, 13, 31], [11, 30], 5),
    ) == [(0, 0), (2, 1)]


def test_sorted_order_keeps_dense_neighboring_real_entries_distinct():
    assert match_ordered_markers(
        4, 4, edges([10, 15, 25, 30], [14, 19, 27, 34], 6),
    ) == [(0, 0), (1, 1), (2, 2), (3, 3)]


def test_no_cross_column_matches_when_caller_only_emits_same_column_edges():
    # Caller must only produce same-column edges. The matcher does not invent
    # new matches simply because two entries share the same source-space Y.
    assert match_ordered_markers(2, 2, [(0, 0, 0), (0, 1, 1)]) == [
        (0, 0), (1, 1),
    ]
    assert match_ordered_markers(1, 1, []) == []


def test_empty_negative_and_invalid_edges():
    assert match_ordered_markers(0, 3, []) == []
    assert match_ordered_markers(2, 0, []) == []
    with pytest.raises(ValueError):
        match_ordered_markers(-1, 2, [])
    with pytest.raises(ValueError):
        match_ordered_markers(1, 1, [(0, 1, 0)])
    with pytest.raises(ValueError):
        match_ordered_markers(1, 1, [(float("nan"), 0, 0)])


def test_real_benchmark_uses_identical_production_matching_primitive():
    from pathlib import Path
    import picture_capture.processing_core as core

    processing = Path(core.__file__).read_text(encoding="utf-8")
    benchmark = (
        Path(core.__file__).resolve().parents[2] / "scripts" /
        "detection_benchmark.py"
    ).read_text(encoding="utf-8")
    # The benchmark now delegates to a pure metric helper, which must use
    # the same primitive as production processing. Check the complete chain,
    # not only a function-name occurrence in one particular source file.
    import picture_capture.quality.detection_quality_metrics as quality

    metric_source = Path(quality.__file__).read_text(encoding="utf-8")
    assert "marker_metrics(" in benchmark
    assert "match_ordered_markers(" in metric_source
    assert "match_ordered_markers(" in processing
    assert quality.marker_metrics(
        [(0, 0), (0, 5)], [(0, 4), (0, 9)], 5,
    )["matched"] == 2
