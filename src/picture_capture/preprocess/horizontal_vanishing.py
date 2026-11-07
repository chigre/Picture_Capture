"""N-column robust common horizontal VP fitting and perspective estimation.

Retains equal-column robust weighted line fit, outlier rejection, common-VP
spread diagnostics and one global rectifier. All legacy runtime callbacks and
thresholds are injected by geometry.py at call time, no backwards import.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Iterable
import numpy as np


@dataclass(frozen=True)
class HorizontalVanishingOps:
    column_rows: Callable[..., Any]
    row_stats: Callable[..., Any]
    region_angles: Callable[..., Any]
    fit_vp: Callable[..., Any]
    column_spread: Callable[..., Any]
    transform_points: Callable[..., Any]
    result_type: Callable[..., Any]
    vp_min_rows: int
    vp_min_trend_deg: float


def fit_horizontal_vanishing_point(
    column_rows: list[list[tuple[float, float, float, float]]],
    *,
    vp_min_rows: int,
) -> tuple[float, float]:
    """Fit one common horizontal VP with equalized contribution per column."""
    usable = [
        rows for rows in column_rows if len(rows) >= 3
    ]
    total_rows = sum(len(rows) for rows in usable)
    if total_rows < vp_min_rows:
        raise RuntimeError("有效文本行不足，无法估计水平消失点")
    all_angles = np.asarray(
        [row[2] for rows in usable for row in rows],
        dtype=float,
    )
    if float(np.percentile(all_angles, 90) - np.percentile(all_angles, 10)) < 0.14:
        raise RuntimeError("文本行角度变化过小，无需水平消失点校正")

    equations: list[tuple[float, float, float, float]] = []
    for rows in usable:
        total_weight = sum(max(1.0, float(row[3])) for row in rows)
        for x, y, angle_deg, weight in rows:
            radians = math.radians(float(angle_deg))
            a = -math.sin(radians)
            b = math.cos(radians)
            cc = -(a * float(x) + b * float(y))
            # Equal total influence for every populated column, then preserve
            # within-column confidence using each row's relative line length.
            balanced_weight = max(
                1e-6,
                max(1.0, float(weight)) / max(1.0, total_weight),
            )
            equations.append((a, b, cc, balanced_weight))

    keep = np.ones(len(equations), dtype=bool)
    point = np.zeros(2, dtype=float)
    for _ in range(5):
        if int(keep.sum()) < vp_min_rows:
            raise RuntimeError("水平消失点有效行不足")
        selected = [equations[i] for i in range(len(equations)) if keep[i]]
        a_mat = np.asarray([[item[0], item[1]] for item in selected], dtype=float)
        b_vec = np.asarray([-item[2] for item in selected], dtype=float)
        weights = np.sqrt(
            np.asarray([item[3] for item in selected], dtype=float)
        )
        weighted_a = a_mat * weights[:, None]
        weighted_b = b_vec * weights
        point, _residuals, rank, _singular = np.linalg.lstsq(
            weighted_a, weighted_b, rcond=None,
        )
        if int(rank) < 2 or not np.isfinite(point).all():
            raise RuntimeError("水平消失点估计退化")
        residuals = np.asarray(
            [
                abs(a * point[0] + b * point[1] + cc)
                for a, b, cc, _weight in equations
            ],
            dtype=float,
        )
        center = float(np.median(residuals[keep]))
        mad = float(np.median(np.abs(residuals[keep] - center)))
        threshold = max(2.0, center + mad * 4.0)
        new_keep = residuals <= threshold
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep
    return float(point[0]), float(point[1])


def horizontal_vp_column_spread_deg(
    column_rows: list[list[tuple[float, float, float, float]]],
    common_vp: tuple[float, float],
    *,
    normalize_angle: Callable[[float], float],
    median_pairs: Callable[..., float],
) -> float:
    """Return P90 column disagreement with one common horizontal VP.

    Fitting a separate VP for each column is numerically unstable when the true
    VP is very far away. Instead, compare every observed row direction directly
    with the direction from that row center to the common VP, summarize each
    populated column robustly, then take P90 across columns.
    """
    common_x, common_y = common_vp
    column_residuals: list[float] = []
    for rows in column_rows:
        if len(rows) < 5:
            continue
        residual_pairs: list[tuple[float, float]] = []
        for x, y, angle_deg, weight in rows:
            predicted = normalize_angle(
                math.degrees(
                    math.atan2(common_y - float(y), common_x - float(x))
                )
            )
            residual = abs(
                normalize_angle(float(angle_deg) - predicted)
            )
            residual_pairs.append((residual, max(1.0, float(weight))))
        if residual_pairs:
            column_residuals.append(
                median_pairs(residual_pairs)
            )
    return (
        float(np.percentile(column_residuals, 90))
        if len(column_residuals) >= 2
        else (column_residuals[0] if column_residuals else 0.0)
    )


def estimate_horizontal_perspective_from_polygons(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    settings: Any = None,
    *,
    ops: HorizontalVanishingOps,
) -> Any:
    """Build one global projective rectifier from independent 1..N column rows.

    Rows are reconstructed separately inside each detected/fixed layout column,
    so text at similar Y positions in different columns is never treated as one
    typographic line. All columns still vote for one common horizontal VP and
    therefore one global homography.
    """
    _horizontal_column_rows = ops.column_rows
    _horizontal_row_stats = ops.row_stats
    _horizontal_region_angles = ops.region_angles
    _fit_horizontal_vanishing_point = ops.fit_vp
    _horizontal_vp_column_spread_deg = ops.column_spread
    transform_points_homography = ops.transform_points
    PerspectiveEstimate = ops.result_type
    HORIZONTAL_VP_MIN_ROWS = ops.vp_min_rows
    HORIZONTAL_VP_MIN_TREND_DEG = ops.vp_min_trend_deg
    width, height = size
    polygon_list = [np.asarray(poly, dtype=float) for poly in polygons]
    column_rows, _groups = _horizontal_column_rows(
        polygon_list, size, settings,
    )
    usable_columns = [rows for rows in column_rows if len(rows) >= 5]
    rows = [row for column in usable_columns for row in column]
    if len(rows) < HORIZONTAL_VP_MIN_ROWS:
        raise RuntimeError("有效文本行不足，无法估计水平消失点")

    driver_changes: list[float] = []
    for column in usable_columns:
        try:
            middle, top, bottom, trend, _mad, _span = (
                _horizontal_row_stats(column)
            )
            region_top, region_middle, region_bottom = _horizontal_region_angles(
                column,
                fallback=(top, middle, bottom),
            )
            region_span = (
                max(region_top, region_middle, region_bottom)
                - min(region_top, region_middle, region_bottom)
            )
            driver_changes.append(
                max(abs(float(trend)), abs(float(region_span)))
            )
        except RuntimeError:
            continue
    if not driver_changes or max(driver_changes) < HORIZONTAL_VP_MIN_TREND_DEG:
        raise RuntimeError("各栏文本行上下角度变化不足，无需水平消失点校正")

    vx, vy = _fit_horizontal_vanishing_point(usable_columns)
    vp_spread = _horizontal_vp_column_spread_deg(
        usable_columns, (vx, vy),
    )
    cx = (float(width) - 1.0) / 2.0
    cy = (float(height) - 1.0) / 2.0
    vx_rel = vx - cx
    vy_rel = vy - cy
    if abs(vx_rel) < max(float(width) * 3.0, 500.0):
        raise RuntimeError("水平消失点过近，候选投影变换过强")
    if not (math.isfinite(vx_rel) and math.isfinite(vy_rel)):
        raise RuntimeError("水平消失点无效")

    to_center = np.asarray(
        [[1.0, 0.0, -cx], [0.0, 1.0, -cy], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    from_center = np.asarray(
        [[1.0, 0.0, cx], [0.0, 1.0, cy], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    projective = np.asarray(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-1.0 / vx_rel, 0.0, 1.0]],
        dtype=float,
    )
    direction_x = vx_rel
    direction_y = vy_rel
    if direction_x < 0.0:
        direction_x = -direction_x
        direction_y = -direction_y
    norm = math.hypot(direction_x, direction_y)
    ux = direction_x / max(1e-12, norm)
    uy = direction_y / max(1e-12, norm)
    align = np.asarray(
        [[ux, uy, 0.0], [-uy, ux, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    matrix = from_center @ align @ projective @ to_center
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
    if not np.isfinite(dst).all():
        raise RuntimeError("水平消失点候选映射无效")
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
        width_delta_px=float(bottom_width - top_width),
        width_change_ratio=abs(bottom_width - top_width) / mean_width,
        scale_top=scale_top,
        scale_bottom=scale_bottom,
        scale_delta_ratio=abs(scale_bottom - scale_top) / scale_mean,
        classification="horizontal_vp",
        candidate_source="horizontal_vp",
        horizontal_vanishing_x=vx,
        horizontal_vanishing_y=vy,
        horizontal_row_count=len(rows),
        horizontal_column_count=len(usable_columns),
        horizontal_vp_column_spread_deg=vp_spread,
    )
