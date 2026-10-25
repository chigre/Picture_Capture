"""Physical owner for N-column horizontal alignment safety statistics and verdicts.

No reverse import of geometry.py or GUI. The original geometry module owns
the result dataclass, public safety thresholds and callback patchpoints, which
are captured at call time in the frozen dependency structure below.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Iterable

import numpy as np


@dataclass(frozen=True)
class HorizontalAuditOps:
    """Legacy-compatible per-call functions and policy captured by geometry."""
    column_rows: Callable[..., Any]
    row_stats: Callable[..., Any]
    region_angles: Callable[..., Any]
    tail_p90: Callable[..., Any]
    metric: Callable[..., Any]
    edge_metrics: Callable[..., Any]
    result_type: Callable[..., Any]
    vp_min_rows: int
    vp_min_trend_deg: float
    min_improvement: float
    max_after_trend_deg: float
    max_after_edge_deg: float
    max_edge_pair_delta_deg: float


def horizontal_row_stats(
    rows: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float, float, float]:
    if len(rows) < 5:
        raise RuntimeError("有效文本行不足")
    ys = np.asarray([row[1] for row in rows], dtype=float)
    angles = np.asarray([row[2] for row in rows], dtype=float)
    weights = np.sqrt(np.asarray([row[3] for row in rows], dtype=float))
    y_min = float(ys.min())
    y_max = float(ys.max())
    span = max(1.0, y_max - y_min)
    norm_y = (ys - y_min) / span - 0.5
    keep = np.ones(len(rows), dtype=bool)

    slope = 0.0
    intercept = float(np.median(angles))
    for _ in range(4):
        if int(keep.sum()) < 5:
            break
        slope, intercept = np.polyfit(
            norm_y[keep], angles[keep], 1, w=weights[keep],
        )
        residual = angles - (slope * norm_y + intercept)
        center = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - center)))
        threshold = max(0.12, mad * 3.5)
        new_keep = np.abs(residual - center) <= threshold
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep

    if int(keep.sum()) >= 5:
        slope, intercept = np.polyfit(
            norm_y[keep], angles[keep], 1, w=weights[keep],
        )
    predicted = slope * norm_y + intercept
    residual = angles - predicted
    valid = residual[keep] if int(keep.sum()) else residual
    center = float(np.median(valid))
    residual_mad = float(np.median(np.abs(valid - center)))
    top = float(intercept - slope * 0.5)
    bottom = float(intercept + slope * 0.5)
    return (
        float(intercept),
        top,
        bottom,
        float(slope),
        max(0.0, residual_mad),
        span,
    )


def horizontal_region_angles(
    rows: list[tuple[float, float, float, float]],
    *,
    fallback: tuple[float, float, float],
    median_pairs: Callable[[list[tuple[float, float]]], float],
) -> tuple[float, float, float]:
    """Direct robust top/middle/bottom row angles for one populated column.

    Trend fitting remains useful for the VP direction, but a small local defect
    (for example only the lower-right part of a page) can be diluted by one
    global linear fit. Region medians therefore provide an independent
    worst-region gate.
    """
    _weighted_median_pairs = median_pairs
    if not rows:
        return fallback
    ys = np.asarray([row[1] for row in rows], dtype=float)
    y_min = float(ys.min())
    y_max = float(ys.max())
    span = max(1.0, y_max - y_min)
    norm = (ys - y_min) / span
    bands = (
        norm < (1.0 / 3.0),
        (norm >= (1.0 / 3.0)) & (norm < (2.0 / 3.0)),
        norm >= (2.0 / 3.0),
    )
    values: list[float] = []
    for band_index, mask in enumerate(bands):
        indices = np.flatnonzero(mask)
        if indices.size < 2:
            values.append(float(fallback[band_index]))
            continue
        values.append(
            _weighted_median_pairs(
                [
                    (rows[int(index)][2], rows[int(index)][3])
                    for index in indices
                ]
            )
        )
    return float(values[0]), float(values[1]), float(values[2])


def horizontal_tail_p90_abs(
    rows: list[tuple[float, float, float, float]],
    *,
    fraction: float,
    percentile_pairs: Callable[[list[tuple[float, float]], float], float],
) -> tuple[float, float]:
    """Return robust top/bottom tail P90 absolute row angles.

    Third-based region medians can hide a defect confined to the final few
    lines. Tail windows deliberately isolate the outer ~18% of each populated
    column so a lower-right residual cannot disappear into the bottom-third
    median.
    """
    _weighted_percentile_pairs = percentile_pairs
    if len(rows) < 5:
        return 0.0, 0.0
    ys = np.asarray([row[1] for row in rows], dtype=float)
    y_min = float(ys.min())
    y_max = float(ys.max())
    span = max(1.0, y_max - y_min)
    top_limit = y_min + span * max(0.05, min(0.35, float(fraction)))
    bottom_limit = y_max - span * max(0.05, min(0.35, float(fraction)))

    def p90(mask: np.ndarray) -> float:
        indices = np.flatnonzero(mask)
        if indices.size < 3:
            return 0.0
        return _weighted_percentile_pairs(
            [
                (
                    abs(float(rows[int(index)][2])),
                    max(1.0, float(rows[int(index)][3])),
                )
                for index in indices
            ],
            90.0,
        )

    return float(p90(ys <= top_limit)), float(p90(ys >= bottom_limit))


def horizontal_metric(
    middle: float,
    top: float,
    bottom: float,
    trend: float,
    mad: float,
) -> float:
    return (
        max(abs(top), abs(middle), abs(bottom))
        + 0.45 * abs(trend)
        + 0.35 * max(0.0, mad)
    )


def audit_horizontal_alignment(
    before_polygons: Iterable[np.ndarray],
    after_polygons: Iterable[np.ndarray],
    size: tuple[int, int] | None = None,
    settings: Any = None,
    *,
    ops: HorizontalAuditOps,
) -> Any:
    """Audit global horizontality while preserving independent N-column rows."""
    _horizontal_column_rows = ops.column_rows
    _horizontal_row_stats = ops.row_stats
    _horizontal_region_angles = ops.region_angles
    _horizontal_tail_p90_abs = ops.tail_p90
    _horizontal_metric = ops.metric
    _horizontal_polygon_edge_metrics = ops.edge_metrics
    HorizontalAlignmentAudit = ops.result_type
    HORIZONTAL_VP_MIN_ROWS = ops.vp_min_rows
    HORIZONTAL_VP_MIN_TREND_DEG = ops.vp_min_trend_deg
    HORIZONTAL_ALIGNMENT_MIN_IMPROVEMENT = ops.min_improvement
    HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG = ops.max_after_trend_deg
    HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG = ops.max_after_edge_deg
    HORIZONTAL_ALIGNMENT_MAX_EDGE_PAIR_DELTA_DEG = ops.max_edge_pair_delta_deg
    before_list = [np.asarray(poly, dtype=float) for poly in before_polygons]
    after_list = [np.asarray(poly, dtype=float) for poly in after_polygons]
    count = min(len(before_list), len(after_list))
    before_list = before_list[:count]
    after_list = after_list[:count]
    if count < 5:
        return HorizontalAlignmentAudit(row_count=count)

    if size is None:
        all_points = [
            poly[:, :2]
            for poly in before_list
            if poly.ndim == 2 and poly.shape[0] >= 3
        ]
        if all_points:
            stacked = np.vstack(all_points)
            width = max(2, int(math.ceil(float(stacked[:, 0].max()))) + 2)
            height = max(2, int(math.ceil(float(stacked[:, 1].max()))) + 2)
            size = (width, height)
        else:
            size = (1000, 1000)

    before_columns, groups = _horizontal_column_rows(
        before_list, size, settings,
    )
    after_columns, _ = _horizontal_column_rows(
        after_list, size, settings, fixed_groups=groups,
    )
    column_count = len(before_columns)
    column_row_counts = tuple(len(rows) for rows in before_columns)

    valid_pairs: list[
        tuple[
            tuple[float, float, float, float, float, float],
            tuple[float, float, float, float, float, float],
            int,
        ]
    ] = []
    for index, (before_rows, after_rows) in enumerate(
        zip(before_columns, after_columns)
    ):
        if min(len(before_rows), len(after_rows)) < 5:
            continue
        try:
            before_stats = _horizontal_row_stats(before_rows)
            after_stats = _horizontal_row_stats(after_rows)
        except RuntimeError:
            continue
        valid_pairs.append((before_stats, after_stats, index))

    before_rows = [row for column in before_columns for row in column]
    after_rows = [row for column in after_columns for row in column]
    if min(len(before_rows), len(after_rows)) < 5 or not valid_pairs:
        return HorizontalAlignmentAudit(
            row_count=min(len(before_rows), len(after_rows)),
            column_count=column_count,
            valid_column_count=len(valid_pairs),
            valid_column_indices=tuple(pair[2] for pair in valid_pairs),
            column_row_counts=column_row_counts,
        )

    before_global, before_top, before_bottom, before_trend, before_mad, _ = (
        _horizontal_row_stats(before_rows)
    )
    after_global, after_top, after_bottom, after_trend, after_mad, _ = (
        _horizontal_row_stats(after_rows)
    )
    global_before_metric = _horizontal_metric(
        before_global, before_top, before_bottom, before_trend, before_mad,
    )
    global_after_metric = _horizontal_metric(
        after_global, after_top, after_bottom, after_trend, after_mad,
    )

    before_tops: list[float] = []
    after_tops: list[float] = []
    before_middles: list[float] = []
    after_middles: list[float] = []
    before_bottoms: list[float] = []
    after_bottoms: list[float] = []
    before_trends: list[float] = []
    after_trends: list[float] = []
    before_metrics: list[float] = []
    after_metrics: list[float] = []
    before_top_tails: list[float] = []
    after_top_tails: list[float] = []
    before_bottom_tails: list[float] = []
    after_bottom_tails: list[float] = []
    valid_indices: list[int] = []

    for before_stats, after_stats, index in valid_pairs:
        bm, bt, bb, btrend, bmad, _bspan = before_stats
        am, at, ab, atrend, amad, _aspan = after_stats
        before_rows_for_column = before_columns[index]
        after_rows_for_column = after_columns[index]
        btop_region, bmiddle_region, bbottom_region = _horizontal_region_angles(
            before_rows_for_column,
            fallback=(bt, bm, bb),
        )
        atop_region, amiddle_region, abottom_region = _horizontal_region_angles(
            after_rows_for_column,
            fallback=(at, am, ab),
        )
        before_tops.append(btop_region)
        after_tops.append(atop_region)
        before_middles.append(bmiddle_region)
        after_middles.append(amiddle_region)
        before_bottoms.append(bbottom_region)
        after_bottoms.append(abottom_region)
        before_trends.append(btrend)
        after_trends.append(atrend)
        btop_tail, bbottom_tail = _horizontal_tail_p90_abs(
            before_rows_for_column
        )
        atop_tail, abottom_tail = _horizontal_tail_p90_abs(
            after_rows_for_column
        )
        before_top_tails.append(btop_tail)
        after_top_tails.append(atop_tail)
        before_bottom_tails.append(bbottom_tail)
        after_bottom_tails.append(abottom_tail)
        before_metrics.append(
            _horizontal_metric(
                bmiddle_region,
                btop_region,
                bbottom_region,
                btrend,
                bmad,
            )
        )
        after_metrics.append(
            _horizontal_metric(
                amiddle_region,
                atop_region,
                abottom_region,
                atrend,
                amad,
            )
        )
        valid_indices.append(index)

    before_worst_region = max(
        abs(value)
        for values in (before_tops, before_middles, before_bottoms)
        for value in values
    )
    after_worst_region = max(
        abs(value)
        for values in (after_tops, after_middles, after_bottoms)
        for value in values
    )
    before_worst_tail = max(
        before_top_tails + before_bottom_tails,
        default=0.0,
    )
    after_worst_tail = max(
        after_top_tails + after_bottom_tails,
        default=0.0,
    )
    (
        before_edge_count,
        before_top_edge_p90,
        before_bottom_edge_p90,
        before_edge_pair_delta_p90,
        before_worst_edge,
    ) = _horizontal_polygon_edge_metrics(before_list, groups)
    (
        after_edge_count,
        after_top_edge_p90,
        after_bottom_edge_p90,
        after_edge_pair_delta_p90,
        after_worst_edge,
    ) = _horizontal_polygon_edge_metrics(after_list, groups)
    edge_pair_count = min(before_edge_count, after_edge_count)
    before_region_spans = [
        max(top, middle, bottom) - min(top, middle, bottom)
        for top, middle, bottom in zip(
            before_tops, before_middles, before_bottoms
        )
    ]
    after_region_spans = [
        max(top, middle, bottom) - min(top, middle, bottom)
        for top, middle, bottom in zip(
            after_tops, after_middles, after_bottoms
        )
    ]
    before_worst_region_span = max(before_region_spans, default=0.0)
    after_worst_region_span = max(after_region_spans, default=0.0)
    before_worst_column_metric = max(before_metrics)
    after_worst_column_metric = max(after_metrics)
    worst_position = int(np.argmax(after_metrics))
    worst_column_index = valid_indices[worst_position]

    # A page-wide average must not hide one bad lower/right column. The global
    # component rewards coherent whole-page correction; the worst-column
    # component keeps the optimizer accountable to every populated column.
    before_metric = (
        0.40 * global_before_metric
        + 0.60 * before_worst_column_metric
    )
    after_metric = (
        0.40 * global_after_metric
        + 0.60 * after_worst_column_metric
    )
    improvement = (
        (before_metric - after_metric) / max(1e-6, before_metric)
        if before_metric > 1e-6 else 0.0
    )
    before_driver_trend = max(
        [abs(before_trend), before_worst_region_span]
        + [abs(value) for value in before_trends]
    )
    after_worst_trend = max(
        [abs(after_trend)] + [abs(value) for value in after_trends]
    )

    dual_edge_safe = bool(
        edge_pair_count < HORIZONTAL_VP_MIN_ROWS
        or (
            after_worst_edge <= HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG
            and (
                after_edge_pair_delta_p90
                <= HORIZONTAL_ALIGNMENT_MAX_EDGE_PAIR_DELTA_DEG
            )
        )
    )

    if len(after_rows) < HORIZONTAL_VP_MIN_ROWS:
        verdict = "insufficient"
    elif (
        before_driver_trend >= HORIZONTAL_VP_MIN_TREND_DEG
        and improvement >= HORIZONTAL_ALIGNMENT_MIN_IMPROVEMENT
        and after_worst_trend <= HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG
        and after_worst_region <= HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG
        and dual_edge_safe
        and after_mad <= max(0.16, before_mad + 0.03)
    ):
        verdict = "improved"
    elif after_metric <= before_metric + 0.03:
        verdict = "stable"
    else:
        verdict = "worse"

    return HorizontalAlignmentAudit(
        row_count=min(len(before_rows), len(after_rows)),
        column_count=column_count,
        valid_column_count=len(valid_pairs),
        valid_column_indices=tuple(valid_indices),
        column_row_counts=column_row_counts,
        before_global_angle_deg=before_global,
        after_global_angle_deg=after_global,
        before_top_angle_deg=before_top,
        after_top_angle_deg=after_top,
        before_bottom_angle_deg=before_bottom,
        after_bottom_angle_deg=after_bottom,
        before_trend_deg=before_trend,
        after_trend_deg=after_trend,
        before_residual_mad_deg=before_mad,
        after_residual_mad_deg=after_mad,
        before_metric_deg=before_metric,
        after_metric_deg=after_metric,
        before_worst_region_deg=before_worst_region,
        after_worst_region_deg=after_worst_region,
        before_worst_edge_deg=before_worst_edge,
        after_worst_edge_deg=after_worst_edge,
        before_top_edge_p90_abs_deg=before_top_edge_p90,
        after_top_edge_p90_abs_deg=after_top_edge_p90,
        before_bottom_edge_p90_abs_deg=before_bottom_edge_p90,
        after_bottom_edge_p90_abs_deg=after_bottom_edge_p90,
        before_edge_pair_delta_p90_deg=before_edge_pair_delta_p90,
        after_edge_pair_delta_p90_deg=after_edge_pair_delta_p90,
        edge_pair_count=edge_pair_count,
        before_worst_region_span_deg=before_worst_region_span,
        after_worst_region_span_deg=after_worst_region_span,
        before_worst_column_metric_deg=before_worst_column_metric,
        after_worst_column_metric_deg=after_worst_column_metric,
        after_worst_column_index=worst_column_index,
        before_column_top_angles_deg=tuple(before_tops),
        after_column_top_angles_deg=tuple(after_tops),
        before_column_middle_angles_deg=tuple(before_middles),
        after_column_middle_angles_deg=tuple(after_middles),
        before_column_bottom_angles_deg=tuple(before_bottoms),
        after_column_bottom_angles_deg=tuple(after_bottoms),
        before_column_trends_deg=tuple(before_trends),
        after_column_trends_deg=tuple(after_trends),
        before_column_metrics_deg=tuple(before_metrics),
        after_column_metrics_deg=tuple(after_metrics),
        before_column_top_tail_p90_abs_deg=tuple(before_top_tails),
        after_column_top_tail_p90_abs_deg=tuple(after_top_tails),
        before_column_bottom_tail_p90_abs_deg=tuple(before_bottom_tails),
        after_column_bottom_tail_p90_abs_deg=tuple(after_bottom_tails),
        before_worst_tail_p90_abs_deg=float(before_worst_tail),
        after_worst_tail_p90_abs_deg=float(after_worst_tail),
        improvement_ratio=max(-10.0, min(1.0, improvement)),
        verdict=verdict,
    )
