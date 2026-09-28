from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .models import AppSettings
from .preprocess_geometry import horizontal_column_rows
from .text_line_geometry import (
    horizontal_rule_track_points,
    separator_track_points,
)


ORTHOGONAL_WARP_MIN_ROWS = 12
ORTHOGONAL_WARP_MIN_DRIVER_DEG = 0.14
ORTHOGONAL_WARP_MIN_SEPARATOR_SHIFT_PX = 2.0
ORTHOGONAL_WARP_MAX_ANGLE_DEG = 2.0
ORTHOGONAL_WARP_MAX_SCALE_DEVIATION = 0.035
ORTHOGONAL_WARP_MAX_SEPARATOR_SHIFT_RATIO = 0.02
ORTHOGONAL_WARP_MESH_STEP_PX = 40

HORIZONTAL_RULE_MAX_ANGLE_DEG = 0.10
HORIZONTAL_RULE_MAX_RESIDUAL_MIN_PX = 2.5
HORIZONTAL_RULE_MAX_RESIDUAL_WIDTH_RATIO = 0.0015


@dataclass(frozen=True, slots=True)
class OrthogonalWarpEstimate:
    """Small, structure-anchored 2-D warp for horizontal dictionary pages.

    Two orthogonal constraints are estimated independently:

    * X correction is a scanline translation derived from a persistent vertical
      separator x(y). It straightens the column separator without bending rows.
    * Y correction is a 2-D displacement field obtained by integrating the
      measured text-row slope m(x, y) across X. Each populated column therefore
      gets its own local row-angle trajectory; disagreement between columns is
      modeled instead of treated as a veto.

    A persistent page-header horizontal rule is inserted as a structural anchor
    row when available. This prevents the common failure where OCR-based global
    deskew makes the middle body level but visibly tilts an originally straight
    running-header rule.
    """

    y_knots: tuple[float, ...] = ()
    angle_knots_deg: tuple[float, ...] = ()
    x_knots: tuple[float, ...] = ()
    row_grid_rows: int = 0
    row_grid_cols: int = 0
    row_displacement_grid_px: tuple[float, ...] = ()
    separator_y_knots: tuple[float, ...] = ()
    separator_shift_knots_px: tuple[float, ...] = ()
    reference_x: float = 0.0
    row_count: int = 0
    valid_column_count: int = 0
    column_spread_deg: float = 0.0
    separator_point_count: int = 0
    horizontal_rule_point_count: int = 0
    horizontal_rule_y: float = 0.0
    horizontal_rule_angle_deg: float = 0.0
    horizontal_rule_residual_span_px: float = 0.0
    max_row_angle_deg: float = 0.0
    row_angle_span_deg: float = 0.0
    max_horizontal_shift_px: float = 0.0
    max_vertical_shift_px: float = 0.0
    max_scale_deviation: float = 0.0
    confidence: float = 0.0
    active: bool = False


def _weighted_median(values: list[tuple[float, float]]) -> float:
    if not values:
        return 0.0
    ordered = sorted(
        (float(value), max(0.0, float(weight)))
        for value, weight in values
    )
    total = sum(weight for _value, weight in ordered)
    if total <= 1e-12:
        return float(np.median([value for value, _weight in ordered]))
    target = total / 2.0
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= target:
            return value
    return ordered[-1][0]


def _smooth_knots(values: np.ndarray) -> np.ndarray:
    """Suppress local noise while preserving the first/last measured values."""
    raw = values.astype(float, copy=True)
    if raw.size < 3:
        return raw
    median = raw.copy()
    for index in range(1, raw.size - 1):
        median[index] = float(np.median(raw[index - 1:index + 2]))
    if raw.size < 4:
        return median
    smooth = median.copy()
    for index in range(1, raw.size - 1):
        smooth[index] = (
            0.25 * median[index - 1]
            + 0.50 * median[index]
            + 0.25 * median[index + 1]
        )
    smooth[0] = raw[0]
    smooth[-1] = raw[-1]
    return smooth


def _interp(
    y: float | np.ndarray,
    knots_y: tuple[float, ...],
    knots_v: tuple[float, ...],
) -> float | np.ndarray:
    if not knots_y or not knots_v:
        if isinstance(y, np.ndarray):
            return np.zeros_like(y, dtype=float)
        return 0.0
    return np.interp(
        y,
        np.asarray(knots_y, dtype=float),
        np.asarray(knots_v, dtype=float),
        left=float(knots_v[0]),
        right=float(knots_v[-1]),
    )


def _local_column_angle(
    rows: list[tuple[float, float, float, float]],
    y: float,
    radius: float,
) -> float | None:
    """Estimate row angle at Y using a robust local linear fit."""
    samples: list[tuple[float, float, float]] = []
    for _x, row_y, angle, weight in rows:
        distance = abs(float(row_y) - float(y))
        if distance > radius:
            continue
        locality = max(0.05, 1.0 - distance / max(1e-6, radius))
        samples.append(
            (
                float(row_y) - float(y),
                float(angle),
                math.sqrt(max(1.0, float(weight))) * locality,
            )
        )
    if len(samples) < 2:
        return None
    if len(samples) == 2:
        dy0, angle0, _weight0 = samples[0]
        dy1, angle1, _weight1 = samples[1]
        denominator = dy1 - dy0
        if abs(denominator) < 1e-9:
            return float((angle0 + angle1) / 2.0)
        slope = (angle1 - angle0) / denominator
        return float(angle0 - slope * dy0)

    dy = np.asarray([item[0] for item in samples], dtype=float)
    angles = np.asarray([item[1] for item in samples], dtype=float)
    weights = np.asarray([item[2] for item in samples], dtype=float)
    keep = np.ones(len(samples), dtype=bool)
    intercept = float(np.median(angles))
    for _ in range(3):
        if int(keep.sum()) < 3:
            break
        slope, intercept = np.polyfit(
            dy[keep],
            angles[keep],
            1,
            w=weights[keep],
        )
        residual = angles - (slope * dy + intercept)
        centre = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - centre)))
        threshold = max(0.08, mad * 3.5)
        new_keep = np.abs(residual - centre) <= threshold
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep
    if int(keep.sum()) >= 3:
        _slope, intercept = np.polyfit(
            dy[keep],
            angles[keep],
            1,
            w=weights[keep],
        )
    return float(intercept)


def _robust_track_fit(
    points: Iterable[tuple[float, float]],
) -> tuple[int, float, float, float]:
    """Fit y(x); return count, angle degrees, residual span, median Y."""
    raw = [
        (float(x), float(y))
        for x, y in points
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    if len(raw) < 7:
        return 0, 0.0, 0.0, 0.0
    x = np.asarray([item[0] for item in raw], dtype=float)
    y = np.asarray([item[1] for item in raw], dtype=float)
    keep = np.ones(len(raw), dtype=bool)
    for _ in range(4):
        if int(keep.sum()) < 7:
            break
        slope, intercept = np.polyfit(x[keep], y[keep], 1)
        residual = y - (slope * x + intercept)
        centre = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - centre)))
        new_keep = np.abs(residual - centre) <= max(1.2, mad * 3.5)
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep
    if int(keep.sum()) < 7:
        return 0, 0.0, 0.0, 0.0
    slope, intercept = np.polyfit(x[keep], y[keep], 1)
    residual = y[keep] - (slope * x[keep] + intercept)
    residual_span = float(
        np.percentile(residual, 90) - np.percentile(residual, 10)
    )
    return (
        int(keep.sum()),
        float(math.degrees(math.atan(float(slope)))),
        max(0.0, residual_span),
        float(np.median(y[keep])),
    )


def horizontal_rule_metrics(
    image: Image.Image,
    polygons: Iterable[np.ndarray],
    settings: AppSettings,
) -> tuple[int, float, float, float]:
    """Return count, signed angle, residual span and median Y of header rule."""
    points = horizontal_rule_track_points(image, polygons, settings)
    return _robust_track_fit(points)


def horizontal_rule_is_level(
    image: Image.Image,
    polygons: Iterable[np.ndarray],
    settings: AppSettings,
) -> tuple[bool, int, float, float]:
    count, angle, residual, _y = horizontal_rule_metrics(
        image, polygons, settings,
    )
    if count < 7:
        return False, count, angle, residual
    limit = max(
        HORIZONTAL_RULE_MAX_RESIDUAL_MIN_PX,
        image.width * HORIZONTAL_RULE_MAX_RESIDUAL_WIDTH_RATIO,
    )
    return (
        abs(float(angle)) <= HORIZONTAL_RULE_MAX_ANGLE_DEG
        and float(residual) <= limit,
        count,
        angle,
        residual,
    )


def _local_track_angle(
    points: list[tuple[float, float]],
    x: float,
    radius: float,
    fallback: float,
) -> float:
    samples = [
        (px - float(x), py)
        for px, py in points
        if abs(px - float(x)) <= radius
    ]
    if len(samples) < 4:
        return float(fallback)
    dx = np.asarray([item[0] for item in samples], dtype=float)
    ys = np.asarray([item[1] for item in samples], dtype=float)
    keep = np.ones(len(samples), dtype=bool)
    slope = math.tan(math.radians(float(fallback)))
    intercept = float(np.median(ys))
    for _ in range(3):
        if int(keep.sum()) < 4:
            break
        slope, intercept = np.polyfit(dx[keep], ys[keep], 1)
        residual = ys - (slope * dx + intercept)
        centre = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - centre)))
        new_keep = np.abs(residual - centre) <= max(1.0, mad * 3.5)
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep
    return float(math.degrees(math.atan(float(slope))))


def _column_center(
    rows: list[tuple[float, float, float, float]],
) -> float:
    return _weighted_median(
        [(float(row[0]), max(1.0, float(row[3]))) for row in rows]
    )


def _unique_sorted(values: Iterable[float], tolerance: float = 1.0) -> np.ndarray:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return np.asarray([], dtype=float)
    result = [ordered[0]]
    for value in ordered[1:]:
        if abs(value - result[-1]) <= tolerance:
            result[-1] = (result[-1] + value) / 2.0
        else:
            result.append(value)
    return np.asarray(result, dtype=float)


def _integrated_row_displacement(
    x_knots: np.ndarray,
    angle_deg: np.ndarray,
    reference_x: float,
) -> np.ndarray:
    slopes = np.tan(np.radians(angle_deg))
    displacement = np.zeros(len(x_knots), dtype=float)
    for index in range(1, len(x_knots)):
        dx = float(x_knots[index] - x_knots[index - 1])
        displacement[index] = (
            displacement[index - 1]
            + 0.5 * float(slopes[index - 1] + slopes[index]) * dx
        )
    reference = float(np.interp(reference_x, x_knots, displacement))
    return displacement - reference


def _row_grid_matrix(estimate: OrthogonalWarpEstimate) -> np.ndarray | None:
    rows = int(estimate.row_grid_rows)
    cols = int(estimate.row_grid_cols)
    if (
        rows < 2
        or cols < 2
        or len(estimate.y_knots) != rows
        or len(estimate.x_knots) != cols
        or len(estimate.row_displacement_grid_px) != rows * cols
    ):
        return None
    return np.asarray(
        estimate.row_displacement_grid_px,
        dtype=float,
    ).reshape(rows, cols)


def _row_displacement(
    x: float | np.ndarray,
    y: float | np.ndarray,
    estimate: OrthogonalWarpEstimate,
) -> float | np.ndarray:
    grid = _row_grid_matrix(estimate)
    if grid is None:
        # Backward-compatible shared-angle field.
        angles = np.asarray(
            _interp(y, estimate.y_knots, estimate.angle_knots_deg),
            dtype=float,
        )
        return np.tan(np.radians(angles)) * (
            np.asarray(x, dtype=float) - float(estimate.reference_x)
        )

    xs = np.asarray(estimate.x_knots, dtype=float)
    ys = np.asarray(estimate.y_knots, dtype=float)
    x_array, y_array = np.broadcast_arrays(
        np.asarray(x, dtype=float),
        np.asarray(y, dtype=float),
    )
    flat_x = x_array.ravel()
    flat_y = y_array.ravel()
    result = np.empty_like(flat_x, dtype=float)

    # Interpolate across X on the two neighbouring Y knot rows, then interpolate
    # those two values in Y. The grid is intentionally small (normally <=5x14),
    # so this explicit loop is cheap and keeps dependencies minimal.
    y_indices = np.searchsorted(ys, flat_y, side="right") - 1
    y_indices = np.clip(y_indices, 0, len(ys) - 2)
    for index, (px, py, iy) in enumerate(zip(flat_x, flat_y, y_indices)):
        iy = int(iy)
        y0 = float(ys[iy])
        y1 = float(ys[iy + 1])
        v0 = float(np.interp(px, xs, grid[iy]))
        v1 = float(np.interp(px, xs, grid[iy + 1]))
        if py <= ys[0]:
            result[index] = float(np.interp(px, xs, grid[0]))
        elif py >= ys[-1]:
            result[index] = float(np.interp(px, xs, grid[-1]))
        elif y1 - y0 <= 1e-9:
            result[index] = v0
        else:
            t = (float(py) - y0) / (y1 - y0)
            result[index] = v0 * (1.0 - t) + v1 * t

    shaped = result.reshape(x_array.shape)
    if np.isscalar(x) and np.isscalar(y):
        return float(shaped)
    return shaped


def estimate_orthogonal_warp(
    image: Image.Image,
    polygons: Iterable[np.ndarray],
    settings: AppSettings,
) -> OrthogonalWarpEstimate:
    """Estimate a structure-anchored 2-D residual straightening field."""
    source = normalize_page_rgb(image)
    width, height = source.size
    polygon_list = [np.asarray(poly, dtype=float) for poly in polygons]
    columns = horizontal_column_rows(polygon_list, source.size, settings)
    valid_columns = [rows for rows in columns if len(rows) >= 5]
    all_rows = [row for column in valid_columns for row in column]
    if len(all_rows) < ORTHOGONAL_WARP_MIN_ROWS:
        return OrthogonalWarpEstimate(
            row_count=len(all_rows),
            valid_column_count=len(valid_columns),
        )

    separator_points = separator_track_points(
        source, polygon_list, settings,
    )
    separator_y: tuple[float, ...] = ()
    separator_shift: tuple[float, ...] = ()
    reference_x = (width - 1.0) / 2.0
    if len(separator_points) >= 7:
        ordered = sorted(
            (float(y), float(x))
            for y, x in separator_points
        )
        sep_y = np.asarray([item[0] for item in ordered], dtype=float)
        sep_x = _smooth_knots(
            np.asarray([item[1] for item in ordered], dtype=float)
        )
        target_x = float(np.median(sep_x))
        shifts = sep_x - target_x
        max_allowed = max(
            3.0,
            width * ORTHOGONAL_WARP_MAX_SEPARATOR_SHIFT_RATIO,
        )
        shifts = np.clip(shifts, -max_allowed, max_allowed)
        separator_y = tuple(float(v) for v in sep_y)
        separator_shift = tuple(float(v) for v in shifts)
        reference_x = target_x

    column_centres = np.asarray(
        [_column_center(rows) for rows in valid_columns],
        dtype=float,
    )
    order = np.argsort(column_centres)
    column_centres = column_centres[order]
    valid_columns = [valid_columns[int(index)] for index in order]

    ys = np.asarray([row[1] for row in all_rows], dtype=float)
    y_lo = float(np.percentile(ys, 2.0))
    y_hi = float(np.percentile(ys, 98.0))
    span = max(1.0, y_hi - y_lo)
    knot_count = int(max(7, min(13, round(span / 260.0) + 1)))
    body_y_knots = np.linspace(y_lo, y_hi, knot_count)
    radius = max(
        90.0,
        span / max(4.0, float(knot_count - 2)) * 1.35,
    )

    rule_points_raw = horizontal_rule_track_points(
        source, polygon_list, settings,
    )
    rule_points = [
        (float(x), float(y))
        for x, y in rule_points_raw
    ]
    (
        rule_count,
        rule_angle,
        rule_residual,
        rule_y,
    ) = _robust_track_fit(rule_points)

    y_values: list[float] = list(float(v) for v in body_y_knots)
    if rule_count >= 7 and rule_y < y_hi:
        y_values.append(float(rule_y))
    knot_ys = _unique_sorted(y_values, tolerance=3.0)
    if knot_ys.size < 2:
        return OrthogonalWarpEstimate(
            row_count=len(all_rows),
            valid_column_count=len(valid_columns),
        )

    x_values: list[float] = [0.0, float(width - 1), float(reference_x)]
    x_values.extend(float(v) for v in column_centres)
    x_knots = _unique_sorted(x_values, tolerance=3.0)
    if x_knots.size < 2:
        return OrthogonalWarpEstimate(
            row_count=len(all_rows),
            valid_column_count=len(valid_columns),
        )

    angle_grid = np.zeros((len(knot_ys), len(x_knots)), dtype=float)
    spreads: list[float] = []
    median_angles: list[float] = []
    rule_radius = max(160.0, width * 0.18)

    for yi, knot_y in enumerate(knot_ys):
        is_rule_row = (
            rule_count >= 7
            and abs(float(knot_y) - float(rule_y)) <= 3.0
        )
        if is_rule_row:
            row_angles = np.asarray(
                [
                    _local_track_angle(
                        rule_points,
                        float(x),
                        rule_radius,
                        rule_angle,
                    )
                    for x in x_knots
                ],
                dtype=float,
            )
            spread = float(row_angles.max() - row_angles.min())
        else:
            local_samples: list[tuple[float, float]] = []
            for centre, rows in zip(column_centres, valid_columns):
                local = _local_column_angle(
                    rows,
                    float(knot_y),
                    radius,
                )
                if local is not None:
                    local_samples.append((float(centre), float(local)))
            if not local_samples:
                row_angles = np.zeros(len(x_knots), dtype=float)
                spread = 0.0
            else:
                sample_x = np.asarray(
                    [item[0] for item in local_samples],
                    dtype=float,
                )
                sample_a = np.asarray(
                    [item[1] for item in local_samples],
                    dtype=float,
                )
                if len(sample_x) == 1:
                    row_angles = np.full(
                        len(x_knots),
                        float(sample_a[0]),
                        dtype=float,
                    )
                    spread = 0.0
                else:
                    row_angles = np.interp(
                        x_knots,
                        sample_x,
                        sample_a,
                        left=float(sample_a[0]),
                        right=float(sample_a[-1]),
                    )
                    spread = float(sample_a.max() - sample_a.min())

        angle_grid[yi] = np.clip(
            row_angles,
            -ORTHOGONAL_WARP_MAX_ANGLE_DEG,
            ORTHOGONAL_WARP_MAX_ANGLE_DEG,
        )
        spreads.append(max(0.0, spread))
        median_angles.append(float(np.median(angle_grid[yi])))

    # Smooth only through Y at each X knot; preserve the explicit header-rule
    # anchor row exactly so OCR rows cannot pull it away from level.
    for xi in range(angle_grid.shape[1]):
        smoothed = _smooth_knots(angle_grid[:, xi])
        if rule_count >= 7:
            rule_index = int(np.argmin(np.abs(knot_ys - rule_y)))
            smoothed[rule_index] = angle_grid[rule_index, xi]
        angle_grid[:, xi] = smoothed

    displacement_grid = np.vstack(
        [
            _integrated_row_displacement(
                x_knots,
                angle_grid[yi],
                reference_x,
            )
            for yi in range(len(knot_ys))
        ]
    )

    max_angle = float(np.max(np.abs(angle_grid)))
    angle_span = float(angle_grid.max() - angle_grid.min())
    max_horizontal_shift = max(
        (abs(v) for v in separator_shift),
        default=0.0,
    )
    max_vertical_shift = float(np.max(np.abs(displacement_grid)))

    if len(knot_ys) >= 2:
        drow_dy = np.diff(displacement_grid, axis=0) / np.maximum(
            1.0,
            np.diff(knot_ys)[:, None],
        )
        max_drow_dy = float(np.max(np.abs(drow_dy)))
    else:
        max_drow_dy = 0.0
    if len(separator_y) >= 2:
        dx_dy = np.diff(
            np.asarray(separator_shift, dtype=float)
        ) / np.maximum(
            1.0,
            np.diff(np.asarray(separator_y, dtype=float)),
        )
        max_dx_dy = float(np.max(np.abs(dx_dy)))
    else:
        max_dx_dy = 0.0
    max_local_slope = float(
        np.max(np.abs(np.tan(np.radians(angle_grid))))
    )
    max_scale_deviation = (
        max_drow_dy + max_local_slope * max_dx_dy
    )

    column_spread = max(spreads, default=0.0)
    row_factor = min(1.0, len(all_rows) / 36.0)
    column_factor = min(1.0, len(valid_columns) / 2.0)
    rule_factor = 1.0 if rule_count >= 7 else 0.0
    confidence = (
        row_factor
        * (0.75 + 0.25 * column_factor)
        * (0.92 + 0.08 * rule_factor)
    )
    active = bool(
        len(all_rows) >= ORTHOGONAL_WARP_MIN_ROWS
        and len(valid_columns) >= 1
        and max_scale_deviation <= ORTHOGONAL_WARP_MAX_SCALE_DEVIATION
        and (
            max_angle >= ORTHOGONAL_WARP_MIN_DRIVER_DEG
            or angle_span >= ORTHOGONAL_WARP_MIN_DRIVER_DEG * 1.5
            or max_horizontal_shift
            >= ORTHOGONAL_WARP_MIN_SEPARATOR_SHIFT_PX
        )
    )

    return OrthogonalWarpEstimate(
        y_knots=tuple(float(v) for v in knot_ys),
        angle_knots_deg=tuple(float(v) for v in median_angles),
        x_knots=tuple(float(v) for v in x_knots),
        row_grid_rows=int(displacement_grid.shape[0]),
        row_grid_cols=int(displacement_grid.shape[1]),
        row_displacement_grid_px=tuple(
            float(v) for v in displacement_grid.ravel()
        ),
        separator_y_knots=separator_y,
        separator_shift_knots_px=separator_shift,
        reference_x=float(reference_x),
        row_count=len(all_rows),
        valid_column_count=len(valid_columns),
        column_spread_deg=float(column_spread),
        separator_point_count=len(separator_points),
        horizontal_rule_point_count=int(rule_count),
        horizontal_rule_y=float(rule_y),
        horizontal_rule_angle_deg=float(rule_angle),
        horizontal_rule_residual_span_px=float(rule_residual),
        max_row_angle_deg=float(max_angle),
        row_angle_span_deg=float(angle_span),
        max_horizontal_shift_px=float(max_horizontal_shift),
        max_vertical_shift_px=float(max_vertical_shift),
        max_scale_deviation=float(max_scale_deviation),
        confidence=max(0.0, min(1.0, float(confidence))),
        active=active,
    )


def transform_points_orthogonal(
    points: np.ndarray,
    estimate: OrthogonalWarpEstimate,
    *,
    row_gain: float = 1.0,
    separator_gain: float = 1.0,
) -> np.ndarray:
    raw = np.asarray(points, dtype=float)
    shape = raw.shape
    flat = raw.reshape(-1, 2).copy()
    if flat.size == 0:
        return flat.reshape(shape)

    ys = flat[:, 1]
    shifts = np.asarray(
        _interp(
            ys,
            estimate.separator_y_knots,
            estimate.separator_shift_knots_px,
        ),
        dtype=float,
    ) * float(separator_gain)
    x_out = flat[:, 0] - shifts
    displacement = np.asarray(
        _row_displacement(x_out, ys, estimate),
        dtype=float,
    ) * float(row_gain)
    y_out = flat[:, 1] - displacement
    flat[:, 0] = x_out
    flat[:, 1] = y_out
    return flat.reshape(shape)


def transform_polygons_orthogonal(
    polygons: Iterable[np.ndarray],
    estimate: OrthogonalWarpEstimate,
    *,
    row_gain: float = 1.0,
    separator_gain: float = 1.0,
) -> list[np.ndarray]:
    return [
        transform_points_orthogonal(
            np.asarray(poly, dtype=float),
            estimate,
            row_gain=row_gain,
            separator_gain=separator_gain,
        )
        for poly in polygons
    ]


def _paper_fill(image: Image.Image) -> tuple[int, int, int]:
    source = normalize_page_rgb(image)
    width, height = source.size
    pw = max(1, round(width * 0.04))
    ph = max(1, round(height * 0.04))
    samples = [
        np.asarray(source.crop((0, 0, pw, ph)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(
            source.crop((max(0, width - pw), 0, width, ph)),
            dtype=np.uint8,
        ).reshape(-1, 3),
        np.asarray(
            source.crop((0, max(0, height - ph), pw, height)),
            dtype=np.uint8,
        ).reshape(-1, 3),
        np.asarray(
            source.crop((
                max(0, width - pw),
                max(0, height - ph),
                width,
                height,
            )),
            dtype=np.uint8,
        ).reshape(-1, 3),
    ]
    median = np.median(np.concatenate(samples, axis=0), axis=0)
    return tuple(int(round(v)) for v in median[:3])


def _inverse_corner(
    x_out: float,
    y_out: float,
    estimate: OrthogonalWarpEstimate,
    row_gain: float,
    separator_gain: float,
) -> tuple[float, float]:
    """Invert the small residual warp by fixed-point iteration."""
    y_source = float(y_out)
    x_source = float(x_out)
    for _ in range(5):
        shift = float(
            _interp(
                y_source,
                estimate.separator_y_knots,
                estimate.separator_shift_knots_px,
            )
        ) * float(separator_gain)
        x_source = float(x_out) + shift
        displacement = float(
            _row_displacement(
                float(x_out),
                y_source,
                estimate,
            )
        ) * float(row_gain)
        y_source = float(y_out) + displacement
    return x_source, y_source


def apply_orthogonal_warp_image(
    image: Image.Image,
    estimate: OrthogonalWarpEstimate,
    *,
    row_gain: float = 1.0,
    separator_gain: float = 1.0,
    mesh_step_px: int = ORTHOGONAL_WARP_MESH_STEP_PX,
) -> Image.Image:
    """Apply the saved 2-D warp as a true X/Y mesh, not full-width strips."""
    source = normalize_page_rgb(image)
    width, height = source.size
    step = max(16, int(mesh_step_px))
    mesh: list[
        tuple[tuple[int, int, int, int], tuple[float, ...]]
    ] = []
    for y0 in range(0, height, step):
        y1 = min(height, y0 + step)
        for x0 in range(0, width, step):
            x1 = min(width, x0 + step)
            ul = _inverse_corner(
                float(x0), float(y0), estimate, row_gain, separator_gain,
            )
            ll = _inverse_corner(
                float(x0), float(y1), estimate, row_gain, separator_gain,
            )
            lr = _inverse_corner(
                float(x1), float(y1), estimate, row_gain, separator_gain,
            )
            ur = _inverse_corner(
                float(x1), float(y0), estimate, row_gain, separator_gain,
            )
            mesh.append(
                (
                    (x0, y0, x1, y1),
                    (
                        ul[0], ul[1],
                        ll[0], ll[1],
                        lr[0], lr[1],
                        ur[0], ur[1],
                    ),
                )
            )
    return source.transform(
        source.size,
        Image.Transform.MESH,
        mesh,
        resample=Image.Resampling.BICUBIC,
        fillcolor=_paper_fill(source),
    )
