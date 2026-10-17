"""Pure, source-neutral headword marker matching and accuracy metrics.

A fixture-level regression is NOT evidence of end-to-end scan accuracy.
All rows are (canonical_column, canonical_reading_axis_y) tuples.
"""
from __future__ import annotations

from collections.abc import Sequence

from .ordered_marker_matching import match_ordered_markers

MATCHING_ALGORITHM = "ordered_max_cardinality_min_delta_v1"
METRIC_CONTRACT = "picture-capture-headword-quality-v1"


def marker_metrics(
    predicted: Sequence[tuple[int, int]],
    reference: Sequence[tuple[int, int]],
    tolerance: int,
) -> dict[str, object]:
    """Maximize TP under same-column and monotone reading order, then minimize Y error.

    Empty/empty yields P=R=F1=1 and exact=True for compatibility with the
    established benchmark; absence of *verified ground truth* must be handled
    by the caller rather than pretending an empty reference is verified.
    """
    if tolerance < 0:
        raise ValueError("matching tolerance must be nonnegative")
    pred = sorted((int(col), int(y)) for col, y in predicted)
    ref = sorted((int(col), int(y)) for col, y in reference)
    edges = [
        (abs(y - ry), pi, ri)
        for pi, (col, y) in enumerate(pred)
        for ri, (rcol, ry) in enumerate(ref)
        if col == rcol and abs(y - ry) <= tolerance
    ]
    pairs = match_ordered_markers(len(pred), len(ref), edges)
    matched_pred = {pi for pi, _ in pairs}
    matched_ref = {ri for _, ri in pairs}
    offsets = sorted(abs(pred[pi][1] - ref[ri][1]) for pi, ri in pairs)
    tp = len(pairs)
    fp, fn = len(pred) - tp, len(ref) - tp
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "predicted": len(pred),
        "reference": len(ref),
        "matched": tp,
        "matching_algorithm": MATCHING_ALGORITHM,
        "unmatched_predicted": [row for i, row in enumerate(pred) if i not in matched_pred],
        "unmatched_reference": [row for i, row in enumerate(ref) if i not in matched_ref],
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "exact": fp == 0 and fn == 0,
        # Preserve legacy upper-median and nearest-rank P95 output semantics.
        "median_abs_delta_v": offsets[len(offsets) // 2] if offsets else None,
        "p95_abs_delta_v": (
            offsets[min(len(offsets) - 1, round((len(offsets) - 1) * 0.95))]
            if offsets else None
        ),
    }


def pooled_counts(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    """Compute MICRO-average accuracy from counts; never macro-average page F1."""
    if min(tp, fp, fn) < 0:
        raise ValueError("TP, FP and FN must not be negative")
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }
