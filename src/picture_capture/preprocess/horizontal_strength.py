"""Horizontal perspective strength and homography composition policy.

Canonical per-branch linear interpolation, coarse/fine safety objective search,
and composition. No import of geometry.py, UI or OCR. Caller retains dataclass
identity, safety constants and patchable projective/assessment functions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

import numpy as np


@dataclass(frozen=True)
class HorizontalStrengthOps:
    transform_polygons: Callable[..., Any]
    audit_alignment: Callable[..., Any]
    interpolate: Callable[..., Any]
    vp_min_rows: int
    min_strength: float
    coarse_step: float
    fine_step: float


def interpolate_perspective_estimate(
    estimate: PerspectiveEstimate,
    size: tuple[int, int],
    strength: float,
    *,
    candidate_source: str | None = None,
    result_type: Callable[..., Any],
    transform_points: Callable[..., np.ndarray],
) -> Any:
    """Interpolate identity→estimate while preserving a valid global homography.

    This is used for residual horizontal-VP correction: the full vanishing-point
    rectifier provides the *direction* of projective correction, while a bounded
    one-dimensional search chooses the smallest strength that best flattens the
    text rows without exceeding scale-distortion budgets.
    """
    PerspectiveEstimate = result_type
    transform_points_homography = transform_points
    width, height = size
    lam = max(0.0, min(1.0, float(strength)))
    full = np.asarray(estimate.matrix, dtype=float).reshape(3, 3)
    identity = np.eye(3, dtype=float)
    matrix = identity + lam * (full - identity)
    if abs(float(matrix[2, 2])) < 1e-9:
        raise RuntimeError("插值投影矩阵退化")
    matrix /= matrix[2, 2]
    if not np.isfinite(matrix).all() or abs(float(np.linalg.det(matrix))) < 1e-9:
        raise RuntimeError("插值投影矩阵无效")

    src = np.asarray(
        [
            [0.0, 0.0],
            [float(width - 1), 0.0],
            [float(width - 1), float(height - 1)],
            [0.0, float(height - 1)],
        ],
        dtype=float,
    )
    dst = transform_points_homography(src, matrix.reshape(-1))
    if not np.isfinite(dst).all():
        raise RuntimeError("插值投影映射无效")
    strength_px = float(np.max(np.linalg.norm(src - dst, axis=1)))
    top_width = float(np.linalg.norm(dst[1] - dst[0]))
    bottom_width = float(np.linalg.norm(dst[2] - dst[3]))
    mean_width = max(1.0, (top_width + bottom_width) / 2.0)
    scale_top = top_width / max(1.0, float(width - 1))
    scale_bottom = bottom_width / max(1.0, float(width - 1))
    scale_mean = max(1e-9, (abs(scale_top) + abs(scale_bottom)) / 2.0)
    source = (
        str(candidate_source)
        if candidate_source is not None
        else str(estimate.candidate_source)
    )
    return PerspectiveEstimate(
        matrix=tuple(float(v) for v in matrix.reshape(-1)),
        source_quad=tuple(float(v) for v in src.reshape(-1)),
        target_quad=tuple(float(v) for v in dst.reshape(-1)),
        strength_px=strength_px,
        left_drift_px=float(estimate.left_drift_px) * lam,
        right_drift_px=float(estimate.right_drift_px) * lam,
        common_drift_px=float(estimate.common_drift_px) * lam,
        width_delta_px=float(bottom_width - top_width),
        width_change_ratio=abs(bottom_width - top_width) / mean_width,
        scale_top=scale_top,
        scale_bottom=scale_bottom,
        scale_delta_ratio=abs(scale_bottom - scale_top) / scale_mean,
        classification=str(estimate.classification),
        candidate_source=source,
        horizontal_vanishing_x=float(estimate.horizontal_vanishing_x),
        horizontal_vanishing_y=float(estimate.horizontal_vanishing_y),
        horizontal_row_count=int(estimate.horizontal_row_count),
        horizontal_column_count=int(estimate.horizontal_column_count),
        horizontal_vp_column_spread_deg=float(
            estimate.horizontal_vp_column_spread_deg
        ),
    )


def optimize_horizontal_perspective_strength(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    full_estimate: Any,
    settings: Any = None,
    *,
    ops: HorizontalStrengthOps,
) -> tuple[Any, Any, float]:
    """Find the partial horizontal-VP strength with minimum row error.

    The search is intentionally lightweight: polygon transforms and angle
    audits only, no image resampling. Safety audits are applied by the caller to
    the final composed transform.
    """
    transform_polygons_homography = ops.transform_polygons
    audit_horizontal_alignment = ops.audit_alignment
    interpolate_perspective_estimate = ops.interpolate
    HORIZONTAL_VP_MIN_ROWS = ops.vp_min_rows
    HORIZONTAL_STRENGTH_MIN = ops.min_strength
    HORIZONTAL_STRENGTH_COARSE_STEP = ops.coarse_step
    HORIZONTAL_STRENGTH_FINE_STEP = ops.fine_step
    polygon_list = [np.asarray(poly, dtype=float) for poly in polygons]
    if len(polygon_list) < HORIZONTAL_VP_MIN_ROWS:
        raise RuntimeError("有效文本框不足，无法优化水平投影强度")

    full_polygons = transform_polygons_homography(
        polygon_list, full_estimate.matrix,
    )
    full_audit = audit_horizontal_alignment(
        polygon_list, full_polygons, size=size, settings=settings,
    )
    before_candidates = [abs(float(full_audit.before_trend_deg))]
    before_candidates.extend(
        abs(float(value)) for value in full_audit.before_column_trends_deg
    )
    after_candidates = [abs(float(full_audit.after_trend_deg))]
    after_candidates.extend(
        abs(float(value)) for value in full_audit.after_column_trends_deg
    )
    before_trend = (
        float(full_audit.before_trend_deg)
        if abs(float(full_audit.before_trend_deg))
        >= max(before_candidates, default=0.0) - 1e-9
        else (
            float(full_audit.before_column_trends_deg[
                int(np.argmax(np.abs(full_audit.before_column_trends_deg)))
            ])
            if full_audit.before_column_trends_deg else 0.0
        )
    )
    after_trend = (
        float(full_audit.after_trend_deg)
        if abs(float(full_audit.after_trend_deg))
        >= max(after_candidates, default=0.0) - 1e-9
        else (
            float(full_audit.after_column_trends_deg[
                int(np.argmax(np.abs(full_audit.after_column_trends_deg)))
            ])
            if full_audit.after_column_trends_deg else 0.0
        )
    )

    guesses: set[float] = set()
    coarse_count = int(
        round((1.0 - HORIZONTAL_STRENGTH_MIN) / HORIZONTAL_STRENGTH_COARSE_STEP)
    )
    for index in range(coarse_count + 1):
        guesses.add(
            round(
                HORIZONTAL_STRENGTH_MIN
                + index * HORIZONTAL_STRENGTH_COARSE_STEP,
                6,
            )
        )
    guesses.add(1.0)
    denominator = before_trend - after_trend
    if abs(denominator) > 1e-6:
        zero_crossing = before_trend / denominator
        if 0.0 < zero_crossing <= 1.2:
            zero_crossing = max(
                HORIZONTAL_STRENGTH_MIN,
                min(1.0, float(zero_crossing)),
            )
            for offset in (-0.10, -0.05, 0.0, 0.05, 0.10):
                guesses.add(
                    round(
                        max(
                            HORIZONTAL_STRENGTH_MIN,
                            min(1.0, zero_crossing + offset),
                        ),
                        6,
                    )
                )

    evaluated: list[
        tuple[float, float, Any, Any]
    ] = []
    for lam in sorted(guesses):
        candidate = interpolate_perspective_estimate(
            full_estimate,
            size,
            lam,
            candidate_source=str(full_estimate.candidate_source),
        )
        mapped = transform_polygons_homography(
            polygon_list, candidate.matrix,
        )
        audit = audit_horizontal_alignment(
            polygon_list, mapped, size=size, settings=settings,
        )
        edge_penalty = (
            float(audit.after_worst_edge_deg)
            + 0.75 * float(audit.after_edge_pair_delta_p90_deg)
            if audit.edge_pair_count >= HORIZONTAL_VP_MIN_ROWS
            else 0.0
        )
        objective = (
            0.45 * float(audit.after_metric_deg)
            + 0.25 * float(audit.after_worst_region_deg)
            + 0.10 * float(audit.after_worst_column_metric_deg)
            + 0.20 * edge_penalty
            + 0.02 * float(lam)
        )
        evaluated.append((objective, float(lam), candidate, audit))

    if not evaluated:
        raise RuntimeError("水平投影强度优化失败")
    coarse_best = min(evaluated, key=lambda item: (item[0], item[1]))
    best_lam = coarse_best[1]

    fine_values: set[float] = set()
    for offset_index in range(-4, 5):
        value = best_lam + offset_index * HORIZONTAL_STRENGTH_FINE_STEP
        if HORIZONTAL_STRENGTH_MIN <= value <= 1.0:
            fine_values.add(round(value, 6))
    for lam in sorted(fine_values):
        if any(abs(existing[1] - lam) < 1e-9 for existing in evaluated):
            continue
        candidate = interpolate_perspective_estimate(
            full_estimate,
            size,
            lam,
            candidate_source=str(full_estimate.candidate_source),
        )
        mapped = transform_polygons_homography(
            polygon_list, candidate.matrix,
        )
        audit = audit_horizontal_alignment(
            polygon_list, mapped, size=size, settings=settings,
        )
        edge_penalty = (
            float(audit.after_worst_edge_deg)
            + 0.75 * float(audit.after_edge_pair_delta_p90_deg)
            if audit.edge_pair_count >= HORIZONTAL_VP_MIN_ROWS
            else 0.0
        )
        objective = (
            0.45 * float(audit.after_metric_deg)
            + 0.25 * float(audit.after_worst_region_deg)
            + 0.10 * float(audit.after_worst_column_metric_deg)
            + 0.20 * edge_penalty
            + 0.02 * float(lam)
        )
        evaluated.append((objective, float(lam), candidate, audit))

    best = min(evaluated, key=lambda item: (item[0], item[1]))
    return best[2], best[3], best[1]


def compose_perspective_estimates(
    first: Any,
    second: Any,
    size: tuple[int, int],
    *,
    result_type: Callable[..., Any],
    transform_points: Callable[..., np.ndarray],
) -> Any:
    """Compose source→first and first→second candidate transforms."""
    PerspectiveEstimate = result_type
    transform_points_homography = transform_points
    width, height = size
    first_matrix = np.asarray(first.matrix, dtype=float).reshape(3, 3)
    second_matrix = np.asarray(second.matrix, dtype=float).reshape(3, 3)
    matrix = second_matrix @ first_matrix
    matrix /= matrix[2, 2]
    src = np.asarray(
        [
            [0.0, 0.0],
            [float(width - 1), 0.0],
            [float(width - 1), float(height - 1)],
            [0.0, float(height - 1)],
        ],
        dtype=float,
    )
    dst = transform_points_homography(src, matrix.reshape(-1))
    strength = float(np.max(np.linalg.norm(src - dst, axis=1)))
    top_width = float(np.linalg.norm(dst[1] - dst[0]))
    bottom_width = float(np.linalg.norm(dst[2] - dst[3]))
    mean_width = max(1.0, (top_width + bottom_width) / 2.0)
    scale_top = top_width / max(1.0, float(width - 1))
    scale_bottom = bottom_width / max(1.0, float(width - 1))
    scale_mean = max(1e-9, (abs(scale_top) + abs(scale_bottom)) / 2.0)
    return PerspectiveEstimate(
        matrix=tuple(float(v) for v in matrix.reshape(-1)),
        source_quad=tuple(float(v) for v in src.reshape(-1)),
        target_quad=tuple(float(v) for v in dst.reshape(-1)),
        strength_px=strength,
        left_drift_px=first.left_drift_px,
        right_drift_px=first.right_drift_px,
        common_drift_px=first.common_drift_px,
        width_delta_px=float(bottom_width - top_width),
        width_change_ratio=abs(bottom_width - top_width) / mean_width,
        scale_top=scale_top,
        scale_bottom=scale_bottom,
        scale_delta_ratio=abs(scale_bottom - scale_top) / scale_mean,
        classification="combined",
        candidate_source="structural+horizontal_vp",
        horizontal_vanishing_x=second.horizontal_vanishing_x,
        horizontal_vanishing_y=second.horizontal_vanishing_y,
        horizontal_row_count=second.horizontal_row_count,
        horizontal_column_count=second.horizontal_column_count,
        horizontal_vp_column_spread_deg=second.horizontal_vp_column_spread_deg,
    )
