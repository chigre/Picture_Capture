"""Orthogonal-warp acceptance, safety budgets and replay payloads."""
from __future__ import annotations

import math
from typing import Callable, Iterable

import numpy as np

from ..models import AppSettings
from .constants import (
    ORTHOGONAL_AUTO_GAINS, ORTHOGONAL_MIN_SAFE_GAIN, ORTHOGONAL_SCALE_SAFETY_FRACTION,
)
from .geometry import (
    HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG,
    HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG,
    HORIZONTAL_ALIGNMENT_MAX_TAIL_DEG,
    HORIZONTAL_ALIGNMENT_MAX_EDGE_PAIR_DELTA_DEG,
    HORIZONTAL_VP_MIN_ROWS,
)
from .orthogonal_dewarp import OrthogonalWarpEstimate, ORTHOGONAL_WARP_MAX_SCALE_DEVIATION


def _absolute_horizontal_quality(audit) -> tuple[str, float]:
    """Return an absolute final-output horizontality verdict and score.

    A line is accepted only when both polygon boundaries are level and mutually
    parallel, while page and per-column row directions are also level. This
    deliberately does not use the before/after improvement verdict because a
    final self-audit has no transform delta.
    """
    worst_column_trend = max(
        [abs(float(getattr(audit, "after_trend_deg", 0.0)))]
        + [
            abs(float(value))
            for value in getattr(audit, "after_column_trends_deg", ())
        ]
    )
    score = max(
        abs(float(getattr(audit, "after_trend_deg", 0.0)))
        / max(1e-6, HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG),
        worst_column_trend
        / max(1e-6, HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG),
        float(getattr(audit, "after_worst_region_deg", 0.0))
        / max(1e-6, HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG),
        float(getattr(audit, "after_worst_edge_deg", 0.0))
        / max(1e-6, HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG),
        float(getattr(audit, "after_worst_tail_p90_abs_deg", 0.0))
        / max(1e-6, HORIZONTAL_ALIGNMENT_MAX_TAIL_DEG),
        float(getattr(audit, "after_edge_pair_delta_p90_deg", 0.0))
        / max(1e-6, HORIZONTAL_ALIGNMENT_MAX_EDGE_PAIR_DELTA_DEG),
    )
    if (
        int(getattr(audit, "row_count", 0)) < HORIZONTAL_VP_MIN_ROWS
        or int(getattr(audit, "valid_column_count", 0)) < 1
        or int(getattr(audit, "edge_pair_count", 0)) < HORIZONTAL_VP_MIN_ROWS
    ):
        return "insufficient", float(score)

    passed = bool(
        abs(float(getattr(audit, "after_trend_deg", 0.0)))
        <= HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG
        and worst_column_trend <= HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG
        and float(getattr(audit, "after_worst_region_deg", 0.0))
        <= HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG
        and float(getattr(audit, "after_top_edge_p90_abs_deg", 0.0))
        <= HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG
        and float(getattr(audit, "after_bottom_edge_p90_abs_deg", 0.0))
        <= HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG
        and float(getattr(audit, "after_worst_tail_p90_abs_deg", 0.0))
        <= HORIZONTAL_ALIGNMENT_MAX_TAIL_DEG
        and float(getattr(audit, "after_edge_pair_delta_p90_deg", 0.0))
        <= HORIZONTAL_ALIGNMENT_MAX_EDGE_PAIR_DELTA_DEG
    )
    return ("passed" if passed else "failed"), float(score)



def _separator_vertical_span(
    points: Iterable[tuple[float, float]],
) -> tuple[int, float]:
    """Return robust X spread of a physical vertical separator track."""
    values = np.asarray(
        [float(x) for _y, x in points],
        dtype=float,
    )
    if values.size < 7:
        return int(values.size), 0.0
    return (
        int(values.size),
        float(np.percentile(values, 90) - np.percentile(values, 10)),
    )



def _orthogonal_safe_gain_cap(
    estimate: OrthogonalWarpEstimate,
) -> float:
    """Return the largest row gain allowed by the local scale safety budget."""
    deviation = max(0.0, float(estimate.max_scale_deviation))
    if deviation <= 1e-9:
        return float(max(ORTHOGONAL_AUTO_GAINS))
    return max(
        0.0,
        min(
            float(max(ORTHOGONAL_AUTO_GAINS)),
            ORTHOGONAL_WARP_MAX_SCALE_DEVIATION
            * ORTHOGONAL_SCALE_SAFETY_FRACTION
            / deviation,
        ),
    )



def _choose_orthogonal_candidate(
    polygons: Iterable[np.ndarray],
    estimate: OrthogonalWarpEstimate,
    size: tuple[int, int],
    settings: AppSettings,
    *,
    max_gain: float | None = None,
    horizontal_auditor: Callable,
    scale_auditor: Callable,
    polygon_transformer: Callable,
    quality_evaluator: Callable,
) -> tuple[
    float,
    list[np.ndarray],
    str,
    float,
    float,
]:
    """Select the mildest row-warp gain that best straightens current rows."""
    source_polygons = [np.asarray(poly, dtype=float) for poly in polygons]
    before_audit = horizontal_auditor(
        source_polygons,
        source_polygons,
        size=size,
        settings=settings,
    )
    _before_verdict, before_score = quality_evaluator(before_audit)

    best_gain = 0.0
    best_polygons = source_polygons
    best_verdict = "insufficient"
    best_score = float("inf")
    best_objective = float("inf")
    gain_cap = (
        float(max_gain)
        if max_gain is not None
        else float(max(ORTHOGONAL_AUTO_GAINS))
    )
    gain_values = [
        float(gain)
        for gain in ORTHOGONAL_AUTO_GAINS
        if float(gain) <= gain_cap + 1e-9
    ]
    if (
        gain_cap >= ORTHOGONAL_MIN_SAFE_GAIN
        and all(abs(gain - gain_cap) > 1e-6 for gain in gain_values)
    ):
        gain_values.append(float(gain_cap))
    gain_values = sorted(set(gain_values))
    for gain in gain_values:
        mapped = polygon_transformer(
            source_polygons,
            estimate,
            row_gain=float(gain),
            separator_gain=1.0,
        )
        scale_audit = scale_auditor(
            source_polygons,
            mapped,
            size,
            writing_mode=settings.layout_writing_mode,
        )
        if scale_audit.verdict == "worse":
            continue
        audit = horizontal_auditor(
            source_polygons,
            mapped,
            size=size,
            settings=settings,
        )
        verdict, score = quality_evaluator(audit)
        # Prefer a true pass. Otherwise minimize the normalized absolute
        # residual, with a tiny regularizer that avoids over-correction.
        objective = float(score) + 0.025 * abs(float(gain) - 1.0)
        if verdict == "passed":
            objective -= 0.20
        if objective < best_objective:
            best_objective = objective
            best_gain = float(gain)
            best_polygons = mapped
            best_verdict = str(verdict)
            best_score = float(score)

    if not math.isfinite(best_score):
        return 0.0, source_polygons, "insufficient", before_score, before_score
    return (
        best_gain,
        best_polygons,
        best_verdict,
        float(before_score),
        float(best_score),
    )



def _orthogonal_step_payload(
    estimate: OrthogonalWarpEstimate,
    row_gain: float,
) -> dict[str, object]:
    """Serialize only the geometry needed to replay one accepted warp pass."""
    return {
        "row_gain": float(row_gain),
        "reference_x": float(estimate.reference_x),
        "y_knots": [float(v) for v in estimate.y_knots],
        "angle_knots_deg": [float(v) for v in estimate.angle_knots_deg],
        "x_knots": [float(v) for v in estimate.x_knots],
        "row_grid_rows": int(estimate.row_grid_rows),
        "row_grid_cols": int(estimate.row_grid_cols),
        "row_angle_grid_deg": [
            float(v) for v in estimate.row_angle_grid_deg
        ],
        "row_displacement_grid_px": [
            float(v) for v in estimate.row_displacement_grid_px
        ],
        "separator_y_knots": [
            float(v) for v in estimate.separator_y_knots
        ],
        "separator_shift_knots_px": [
            float(v) for v in estimate.separator_shift_knots_px
        ],
    }



def _orthogonal_estimate_from_step(
    payload: dict[str, object],
) -> tuple[OrthogonalWarpEstimate, float]:
    estimate = OrthogonalWarpEstimate(
        y_knots=tuple(float(v) for v in payload.get("y_knots", ())),
        angle_knots_deg=tuple(
            float(v) for v in payload.get("angle_knots_deg", ())
        ),
        x_knots=tuple(float(v) for v in payload.get("x_knots", ())),
        row_grid_rows=max(0, int(payload.get("row_grid_rows", 0) or 0)),
        row_grid_cols=max(0, int(payload.get("row_grid_cols", 0) or 0)),
        row_angle_grid_deg=tuple(
            float(v) for v in payload.get("row_angle_grid_deg", ())
        ),
        row_displacement_grid_px=tuple(
            float(v)
            for v in payload.get("row_displacement_grid_px", ())
        ),
        separator_y_knots=tuple(
            float(v) for v in payload.get("separator_y_knots", ())
        ),
        separator_shift_knots_px=tuple(
            float(v)
            for v in payload.get("separator_shift_knots_px", ())
        ),
        reference_x=float(payload.get("reference_x", 0.0) or 0.0),
        active=True,
    )
    return estimate, max(0.0, float(payload.get("row_gain", 1.0) or 1.0))



# Preserve the historical callable pickle paths, as with preprocess.canvas.
_absolute_horizontal_quality.__module__ = "picture_capture.image_preprocessing"
_separator_vertical_span.__module__ = "picture_capture.image_preprocessing"
_orthogonal_safe_gain_cap.__module__ = "picture_capture.image_preprocessing"
_orthogonal_step_payload.__module__ = "picture_capture.image_preprocessing"
_orthogonal_estimate_from_step.__module__ = "picture_capture.image_preprocessing"
