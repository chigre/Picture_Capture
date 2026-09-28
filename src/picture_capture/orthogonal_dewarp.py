from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .models import AppSettings
from .preprocess_geometry import horizontal_column_rows
from .text_line_geometry import separator_track_points


ORTHOGONAL_WARP_MIN_ROWS = 12
ORTHOGONAL_WARP_MIN_DRIVER_DEG = 0.14
ORTHOGONAL_WARP_MIN_SEPARATOR_SHIFT_PX = 2.0
ORTHOGONAL_WARP_MAX_ANGLE_DEG = 2.0
ORTHOGONAL_WARP_MAX_COLUMN_SPREAD_DEG = 0.35
ORTHOGONAL_WARP_MAX_SCALE_DEVIATION = 0.035
ORTHOGONAL_WARP_MAX_SEPARATOR_SHIFT_RATIO = 0.02
ORTHOGONAL_WARP_MESH_STEP_PX = 32


@dataclass(frozen=True, slots=True)
class OrthogonalWarpEstimate:
    """Small, page-preserving nonlinear warp for horizontal dictionary pages.

    The mapping intentionally separates the two orthogonal constraints:
    - row_angle(y) changes only Y as a function of X, flattening text rows;
    - separator_shift(y) changes only X for a complete scanline, straightening
      a physical vertical separator without bending horizontal rows.

    This is deliberately not a generic document-unwarping model. It is a
    deterministic final geometry normalizer for pages whose desired output is
    explicitly horizontal text rows and vertical column separators.
    """

    y_knots: tuple[float, ...] = ()
    angle_knots_deg: tuple[float, ...] = ()
    separator_y_knots: tuple[float, ...] = ()
    separator_shift_knots_px: tuple[float, ...] = ()
    reference_x: float = 0.0
    row_count: int = 0
    valid_column_count: int = 0
    column_spread_deg: float = 0.0
    separator_point_count: int = 0
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
    if values.size < 3:
        return values.astype(float, copy=True)
    median = values.astype(float, copy=True)
    for index in range(values.size):
        lo = max(0, index - 1)
        hi = min(values.size, index + 2)
        median[index] = float(np.median(values[lo:hi]))
    if values.size < 4:
        return median
    smooth = median.copy()
    for index in range(1, values.size - 1):
        smooth[index] = (
            0.25 * median[index - 1]
            + 0.50 * median[index]
            + 0.25 * median[index + 1]
        )
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
    """Estimate the row angle *at* y with a robust local linear fit.

    A local median is biased toward the page centre when the row direction
    changes steadily from top to bottom: the endpoint windows are asymmetric
    and therefore under-correct the very rows that need the largest adjustment.
    Fitting angle against centred Y preserves an exact linear trend while still
    following smooth nonlinear changes locally.
    """
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


def estimate_orthogonal_warp(
    image: Image.Image,
    polygons: Iterable[np.ndarray],
    settings: AppSettings,
) -> OrthogonalWarpEstimate:
    """Estimate a deterministic row/column straightening field.

    The estimator uses already-detected text polygons after global deskew (and
    after any accepted projective correction). It therefore targets only the
    residual geometry that remains visible in the current working image.
    """
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

    ys = np.asarray([row[1] for row in all_rows], dtype=float)
    y_lo = float(np.percentile(ys, 2.0))
    y_hi = float(np.percentile(ys, 98.0))
    span = max(1.0, y_hi - y_lo)
    knot_count = int(max(7, min(13, round(span / 260.0) + 1)))
    knot_ys = np.linspace(y_lo, y_hi, knot_count)
    radius = max(90.0, span / max(4.0, float(knot_count - 2)) * 1.35)

    angle_values: list[float] = []
    spreads: list[float] = []
    for knot_y in knot_ys:
        per_column: list[tuple[float, float]] = []
        raw_column_angles: list[float] = []
        for rows in valid_columns:
            local = _local_column_angle(rows, float(knot_y), radius)
            if local is None:
                continue
            # Every populated column gets approximately equal influence. This
            # prevents one dense column from dictating the page warp.
            per_column.append((float(local), 1.0))
            raw_column_angles.append(float(local))
        if per_column:
            angle_values.append(_weighted_median(per_column))
            spreads.append(
                max(raw_column_angles) - min(raw_column_angles)
                if len(raw_column_angles) >= 2 else 0.0
            )
        else:
            angle_values.append(0.0)
            spreads.append(0.0)

    angles = _smooth_knots(np.asarray(angle_values, dtype=float))
    angles = np.clip(
        angles,
        -ORTHOGONAL_WARP_MAX_ANGLE_DEG,
        ORTHOGONAL_WARP_MAX_ANGLE_DEG,
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
        sep_x = np.asarray([item[1] for item in ordered], dtype=float)
        sep_x = _smooth_knots(sep_x)
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

    angle_abs = np.abs(angles)
    max_angle = float(angle_abs.max()) if angle_abs.size else 0.0
    angle_span = (
        float(angles.max() - angles.min()) if angles.size else 0.0
    )
    max_horizontal_shift = (
        max((abs(v) for v in separator_shift), default=0.0)
    )
    max_x_distance = max(reference_x, (width - 1.0) - reference_x)
    max_vertical_shift = (
        abs(math.tan(math.radians(max_angle))) * max_x_distance
    )

    # A changing shear angle changes local vertical scale at the far page
    # edges. Estimate that Jacobian term directly and keep the budget small.
    tan_values = np.tan(np.radians(angles))
    if len(knot_ys) >= 2:
        dm_dy = np.diff(tan_values) / np.maximum(
            1.0, np.diff(knot_ys)
        )
        max_dm_dy = float(np.max(np.abs(dm_dy)))
    else:
        max_dm_dy = 0.0
    if len(separator_y) >= 2:
        dx_dy = np.diff(np.asarray(separator_shift)) / np.maximum(
            1.0, np.diff(np.asarray(separator_y))
        )
        max_dx_dy = float(np.max(np.abs(dx_dy)))
    else:
        max_dx_dy = 0.0
    max_scale_deviation = (
        max_dm_dy * max_x_distance
        + abs(math.tan(math.radians(max_angle))) * max_dx_dy
    )

    column_spread = max(spreads, default=0.0)
    row_factor = min(1.0, len(all_rows) / 36.0)
    column_factor = min(1.0, len(valid_columns) / 2.0)
    agreement_factor = max(
        0.0,
        1.0 - column_spread / max(
            0.01, ORTHOGONAL_WARP_MAX_COLUMN_SPREAD_DEG
        ),
    )
    confidence = row_factor * (0.65 + 0.35 * column_factor)
    confidence *= 0.55 + 0.45 * agreement_factor
    active = bool(
        len(all_rows) >= ORTHOGONAL_WARP_MIN_ROWS
        and len(valid_columns) >= 1
        and column_spread <= ORTHOGONAL_WARP_MAX_COLUMN_SPREAD_DEG
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
        angle_knots_deg=tuple(float(v) for v in angles),
        separator_y_knots=separator_y,
        separator_shift_knots_px=separator_shift,
        reference_x=float(reference_x),
        row_count=len(all_rows),
        valid_column_count=len(valid_columns),
        column_spread_deg=float(column_spread),
        separator_point_count=len(separator_points),
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
    angles = np.asarray(
        _interp(ys, estimate.y_knots, estimate.angle_knots_deg),
        dtype=float,
    ) * float(row_gain)
    shifts = np.asarray(
        _interp(
            ys,
            estimate.separator_y_knots,
            estimate.separator_shift_knots_px,
        ),
        dtype=float,
    ) * float(separator_gain)

    x_out = flat[:, 0] - shifts
    slopes = np.tan(np.radians(angles))
    y_out = flat[:, 1] - slopes * (x_out - estimate.reference_x)
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
    # Fixed-point inversion is stable because these residual warps are small
    # (normally < 1 degree and only a few pixels of separator drift).
    y_source = float(y_out)
    x_source = float(x_out)
    for _ in range(4):
        shift = float(
            _interp(
                y_source,
                estimate.separator_y_knots,
                estimate.separator_shift_knots_px,
            )
        ) * float(separator_gain)
        x_source = float(x_out) + shift
        angle = float(
            _interp(
                y_source,
                estimate.y_knots,
                estimate.angle_knots_deg,
            )
        ) * float(row_gain)
        slope = math.tan(math.radians(angle))
        y_source = (
            float(y_out)
            + slope * (float(x_out) - estimate.reference_x)
        )
    return x_source, y_source


def apply_orthogonal_warp_image(
    image: Image.Image,
    estimate: OrthogonalWarpEstimate,
    *,
    row_gain: float = 1.0,
    separator_gain: float = 1.0,
    mesh_step_px: int = ORTHOGONAL_WARP_MESH_STEP_PX,
) -> Image.Image:
    source = normalize_page_rgb(image)
    width, height = source.size
    step = max(12, int(mesh_step_px))
    mesh: list[
        tuple[tuple[int, int, int, int], tuple[float, ...]]
    ] = []
    for y0 in range(0, height, step):
        y1 = min(height, y0 + step)
        ul = _inverse_corner(
            0.0, float(y0), estimate, row_gain, separator_gain,
        )
        ll = _inverse_corner(
            0.0, float(y1), estimate, row_gain, separator_gain,
        )
        lr = _inverse_corner(
            float(width), float(y1), estimate, row_gain, separator_gain,
        )
        ur = _inverse_corner(
            float(width), float(y0), estimate, row_gain, separator_gain,
        )
        mesh.append(
            (
                (0, y0, width, y1),
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
