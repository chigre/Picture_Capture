from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .layout_detection import LayoutEstimate, infer_layout_from_boxes
from .models import AppSettings


TEXT_SCALE_INLINE_SPAN_MAX = 0.045
TEXT_SCALE_CROSS_SPAN_MAX = 0.075
TEXT_SCALE_INLINE_GRADIENT_MAX = 0.045
TEXT_SCALE_CROSS_GRADIENT_MAX = 0.075
TEXT_SCALE_ANISOTROPY_P95_MAX = 0.040

HORIZONTAL_VP_MIN_TREND_DEG = 0.18
HORIZONTAL_VP_MIN_ROWS = 8
HORIZONTAL_ALIGNMENT_MIN_IMPROVEMENT = 0.50
HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG = 0.12
HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG = 0.18
HORIZONTAL_STRENGTH_MIN = 0.15
HORIZONTAL_STRENGTH_COARSE_STEP = 0.10
HORIZONTAL_STRENGTH_FINE_STEP = 0.025


@dataclass(frozen=True, slots=True)
class HomographyDistortionAudit:
    """Local scale distortion introduced by one projective transform.

    The audit samples the analytic Jacobian over the text-bearing region.  It
    therefore measures what the transform itself would do to character scale,
    independent of OCR language, detected separators, or page decoration.
    """

    sample_count: int = 0
    horizontal_scale_median: float = 1.0
    vertical_scale_median: float = 1.0
    area_scale_median: float = 1.0
    horizontal_scale_span_ratio: float = 0.0
    vertical_scale_span_ratio: float = 0.0
    area_scale_span_ratio: float = 0.0
    anisotropy_p95_ratio: float = 0.0
    min_determinant: float = 1.0
    valid: bool = True


@dataclass(frozen=True, slots=True)
class TextScaleStabilityAudit:
    """Paired scale field of the same detected text polygons.

    Each text polygon is measured before and after the candidate transform and
    converted to after/before inline and cross-line scale ratios. Natural font
    size, word length, headings and phonetic annotations therefore cancel from
    the primary safety signal; what remains is the scale field introduced by the
    transform itself.
    """

    sample_count: int = 0
    inline_ratio_p05: float = 1.0
    inline_ratio_median: float = 1.0
    inline_ratio_p95: float = 1.0
    cross_ratio_p05: float = 1.0
    cross_ratio_median: float = 1.0
    cross_ratio_p95: float = 1.0
    inline_ratio_span_ratio: float = 0.0
    cross_ratio_span_ratio: float = 0.0
    inline_ratio_gradient_ratio: float = 0.0
    cross_ratio_gradient_ratio: float = 0.0
    anisotropy_p95_ratio: float = 0.0
    # Retain absolute before/after gradients as secondary diagnostics only.
    before_inline_gradient_ratio: float = 0.0
    after_inline_gradient_ratio: float = 0.0
    before_cross_gradient_ratio: float = 0.0
    after_cross_gradient_ratio: float = 0.0
    before_score: float = 0.0
    after_score: float = 0.0
    verdict: str = "insufficient"


@dataclass(frozen=True, slots=True)
class HorizontalAlignmentAudit:
    """Before/after horizontal geometry with N-column-aware worst-region checks."""

    row_count: int = 0
    column_count: int = 0
    valid_column_count: int = 0
    column_row_counts: tuple[int, ...] = ()
    before_global_angle_deg: float = 0.0
    after_global_angle_deg: float = 0.0
    before_top_angle_deg: float = 0.0
    after_top_angle_deg: float = 0.0
    before_bottom_angle_deg: float = 0.0
    after_bottom_angle_deg: float = 0.0
    before_trend_deg: float = 0.0
    after_trend_deg: float = 0.0
    before_residual_mad_deg: float = 0.0
    after_residual_mad_deg: float = 0.0
    before_metric_deg: float = 0.0
    after_metric_deg: float = 0.0
    before_worst_region_deg: float = 0.0
    after_worst_region_deg: float = 0.0
    before_worst_column_metric_deg: float = 0.0
    after_worst_column_metric_deg: float = 0.0
    after_worst_column_index: int = -1
    before_column_top_angles_deg: tuple[float, ...] = ()
    after_column_top_angles_deg: tuple[float, ...] = ()
    before_column_middle_angles_deg: tuple[float, ...] = ()
    after_column_middle_angles_deg: tuple[float, ...] = ()
    before_column_bottom_angles_deg: tuple[float, ...] = ()
    after_column_bottom_angles_deg: tuple[float, ...] = ()
    before_column_trends_deg: tuple[float, ...] = ()
    after_column_trends_deg: tuple[float, ...] = ()
    before_column_metrics_deg: tuple[float, ...] = ()
    after_column_metrics_deg: tuple[float, ...] = ()
    improvement_ratio: float = 0.0
    verdict: str = "insufficient"


@dataclass(frozen=True, slots=True)
class PerspectiveEstimate:
    """Projective correction inferred from structural column trajectories.

    The diagnostics separate common lateral drift (rotation/shear-like) from
    differential edge drift (true width convergence/divergence). Automatic
    preprocessing can therefore reject a large homography even when OCR-derived
    signals agree that "something" changes over Y.
    """

    matrix: tuple[float, ...]
    source_quad: tuple[float, ...]
    target_quad: tuple[float, ...]
    strength_px: float
    left_drift_px: float = 0.0
    right_drift_px: float = 0.0
    common_drift_px: float = 0.0
    width_delta_px: float = 0.0
    width_change_ratio: float = 0.0
    scale_top: float = 1.0
    scale_bottom: float = 1.0
    scale_delta_ratio: float = 0.0
    classification: str = "unknown"
    candidate_source: str = "structural"
    horizontal_vanishing_x: float = 0.0
    horizontal_vanishing_y: float = 0.0
    horizontal_row_count: int = 0
    horizontal_column_count: int = 0
    horizontal_vp_column_spread_deg: float = 0.0


def polygon_boxes(
    polygons: Iterable[np.ndarray],
    width: int,
    height: int,
) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for raw in polygons:
        poly = np.asarray(raw, dtype=float)
        if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
            continue
        x0 = max(0, min(width - 1, math.floor(float(poly[:, 0].min()))))
        y0 = max(0, min(height - 1, math.floor(float(poly[:, 1].min()))))
        x1 = max(1, min(width, math.ceil(float(poly[:, 0].max())) + 1))
        y1 = max(1, min(height, math.ceil(float(poly[:, 1].max())) + 1))
        if x1 - x0 >= 3 and y1 - y0 >= 3:
            boxes.append((x0, y0, x1, y1))
    return boxes


def _layout(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings,
) -> tuple[list[tuple[int, int, int, int]], LayoutEstimate]:
    width, height = size
    boxes = polygon_boxes(polygons, width, height)
    if len(boxes) < 8:
        raise RuntimeError("高级几何纠正需要更多有效文本框")
    estimate = infer_layout_from_boxes(
        boxes,
        size,
        display_scale=1.0,
        ink_mask=None,
        columns_policy=settings.layout_columns_policy,
        fixed_columns=settings.columns,
        column_separator_mode=settings.layout_column_separator_mode,
    )
    if len(estimate.column_starts) < 2:
        raise RuntimeError("高级几何纠正至少需要两栏结构")
    return boxes, estimate


def _column_pitch(starts: tuple[int, ...], index: int, width: int) -> float:
    if len(starts) <= 1:
        return max(20.0, float(width) * 0.5)
    if index == 0:
        return float(starts[1] - starts[0])
    if index == len(starts) - 1:
        return float(starts[-1] - starts[-2])
    return float(min(starts[index] - starts[index - 1], starts[index + 1] - starts[index]))


def _column_left_samples(
    boxes: list[tuple[int, int, int, int]],
    estimate: LayoutEstimate,
    width: int,
) -> list[list[tuple[float, float]]]:
    starts = tuple(int(v) for v in estimate.column_starts)
    samples: list[list[tuple[float, float]]] = [[] for _ in starts]
    char_h = max(4.0, float(estimate.character_height))
    top = float(estimate.start_y) - char_h * 1.2
    bottom = float(estimate.bottom_y) + char_h * 1.2

    for box in boxes:
        x0, y0, _x1, y1 = box
        yc = (float(y0) + float(y1)) / 2.0
        if yc < top or yc > bottom:
            continue
        distances = [abs(float(x0) - float(start)) for start in starts]
        index = int(np.argmin(distances))
        pitch = max(20.0, _column_pitch(starts, index, width))
        # Only boxes that genuinely begin near a structural column edge are
        # useful trajectory anchors. Continuation/indented lines are excluded.
        tolerance = max(char_h * 2.0, min(pitch * 0.28, float(estimate.column_width) * 0.32))
        if distances[index] <= tolerance:
            samples[index].append((yc, float(x0)))
    return samples


def _robust_line(samples: list[tuple[float, float]]) -> tuple[float, float]:
    if len(samples) < 5:
        raise RuntimeError("栏左轨迹样本不足")
    ys = np.asarray([p[0] for p in samples], dtype=float)
    xs = np.asarray([p[1] for p in samples], dtype=float)
    keep = np.ones(len(samples), dtype=bool)
    for _ in range(3):
        if int(keep.sum()) < 5:
            break
        slope, intercept = np.polyfit(ys[keep], xs[keep], 1)
        residual = xs - (slope * ys + intercept)
        center = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - center)))
        threshold = max(2.5, mad * 3.5)
        new_keep = np.abs(residual - center) <= threshold
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep
    if int(keep.sum()) < 5:
        raise RuntimeError("栏左轨迹异常值过多")
    slope, intercept = np.polyfit(ys[keep], xs[keep], 1)
    return float(slope), float(intercept)


def _robust_relative_span(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size < 3:
        return 0.0
    q05, q95 = np.quantile(finite, [0.05, 0.95])
    median = float(np.median(np.abs(finite)))
    if median < 1e-9:
        return 0.0
    return max(0.0, float(q95 - q05) / median)


def homography_jacobian(
    matrix: Iterable[float], x: float, y: float,
) -> np.ndarray:
    """Return the analytic 2x2 Jacobian of a 3x3 homography at source XY."""
    mat = np.asarray(tuple(matrix), dtype=float).reshape(3, 3)
    a, b, c = mat[0]
    d, e, f = mat[1]
    g, h, i = mat[2]
    denominator = g * float(x) + h * float(y) + i
    if abs(denominator) < 1e-9:
        raise ValueError("Homography Jacobian is singular at the requested point")
    numerator_u = a * float(x) + b * float(y) + c
    numerator_v = d * float(x) + e * float(y) + f
    denom_sq = denominator * denominator
    return np.asarray(
        [
            [
                (a * denominator - g * numerator_u) / denom_sq,
                (b * denominator - h * numerator_u) / denom_sq,
            ],
            [
                (d * denominator - g * numerator_v) / denom_sq,
                (e * denominator - h * numerator_v) / denom_sq,
            ],
        ],
        dtype=float,
    )


def _audit_region_from_polygons(
    polygons: Iterable[np.ndarray] | None,
    size: tuple[int, int],
) -> tuple[float, float, float, float]:
    width, height = size
    points: list[np.ndarray] = []
    if polygons is not None:
        for raw in polygons:
            poly = np.asarray(raw, dtype=float)
            if poly.ndim == 2 and poly.shape[0] >= 3 and poly.shape[1] >= 2:
                valid = poly[:, :2]
                valid = valid[np.isfinite(valid).all(axis=1)]
                if len(valid):
                    points.append(valid)
    if points:
        merged = np.vstack(points)
        x0, x1 = np.quantile(merged[:, 0], [0.03, 0.97])
        y0, y1 = np.quantile(merged[:, 1], [0.03, 0.97])
        if x1 - x0 >= 20 and y1 - y0 >= 20:
            return (
                max(0.0, float(x0)),
                max(0.0, float(y0)),
                min(float(width - 1), float(x1)),
                min(float(height - 1), float(y1)),
            )
    return (
        float(width) * 0.08,
        float(height) * 0.08,
        float(width) * 0.92,
        float(height) * 0.92,
    )


def audit_homography_distortion(
    matrix: Iterable[float],
    size: tuple[int, int],
    *,
    polygons: Iterable[np.ndarray] | None = None,
    grid_x: int = 9,
    grid_y: int = 13,
) -> HomographyDistortionAudit:
    """Measure local scale variation introduced by a candidate homography."""
    matrix_values = tuple(float(v) for v in matrix)
    if len(matrix_values) != 9:
        raise ValueError("Homography audit requires a 3x3 matrix")
    x0, y0, x1, y1 = _audit_region_from_polygons(polygons, size)
    xs = np.linspace(x0, x1, max(3, int(grid_x)))
    ys = np.linspace(y0, y1, max(3, int(grid_y)))

    horizontal: list[float] = []
    vertical: list[float] = []
    area: list[float] = []
    anisotropy: list[float] = []
    determinants: list[float] = []

    for y in ys:
        for x in xs:
            try:
                jacobian = homography_jacobian(matrix_values, float(x), float(y))
            except (ValueError, np.linalg.LinAlgError):
                continue
            if not np.isfinite(jacobian).all():
                continue
            determinant = float(np.linalg.det(jacobian))
            singular = np.linalg.svd(jacobian, compute_uv=False)
            if (
                singular.size != 2
                or not np.isfinite(singular).all()
                or float(singular.min()) <= 1e-9
            ):
                continue
            horizontal.append(float(np.linalg.norm(jacobian[:, 0])))
            vertical.append(float(np.linalg.norm(jacobian[:, 1])))
            area.append(math.sqrt(abs(determinant)))
            anisotropy.append(float(singular.max() / singular.min() - 1.0))
            determinants.append(determinant)

    if not horizontal:
        return HomographyDistortionAudit(
            sample_count=0,
            min_determinant=0.0,
            valid=False,
        )

    h_values = np.asarray(horizontal, dtype=float)
    v_values = np.asarray(vertical, dtype=float)
    a_values = np.asarray(area, dtype=float)
    an_values = np.asarray(anisotropy, dtype=float)
    det_values = np.asarray(determinants, dtype=float)
    min_det = float(np.min(det_values))
    return HomographyDistortionAudit(
        sample_count=int(len(h_values)),
        horizontal_scale_median=float(np.median(h_values)),
        vertical_scale_median=float(np.median(v_values)),
        area_scale_median=float(np.median(a_values)),
        horizontal_scale_span_ratio=_robust_relative_span(h_values),
        vertical_scale_span_ratio=_robust_relative_span(v_values),
        area_scale_span_ratio=_robust_relative_span(a_values),
        anisotropy_p95_ratio=float(np.quantile(an_values, 0.95)),
        min_determinant=min_det,
        valid=bool(np.isfinite(min_det) and min_det > 0.0),
    )


def _polygon_inline_cross_size(
    polygon: np.ndarray,
    *,
    writing_mode: str,
) -> tuple[float, float, float, float] | None:
    poly = np.asarray(polygon, dtype=float)
    if poly.ndim != 2 or poly.shape[0] < 4 or poly.shape[1] < 2:
        return None
    points = poly[:4, :2]
    if not np.isfinite(points).all():
        return None
    edge_a1 = points[1] - points[0]
    edge_a2 = points[2] - points[3]
    edge_b1 = points[2] - points[1]
    edge_b2 = points[3] - points[0]
    length_a = (float(np.linalg.norm(edge_a1)) + float(np.linalg.norm(edge_a2))) / 2.0
    length_b = (float(np.linalg.norm(edge_b1)) + float(np.linalg.norm(edge_b2))) / 2.0
    if min(length_a, length_b) < 1.0:
        return None

    vector_a = (edge_a1 + edge_a2) / 2.0
    vector_b = (edge_b1 + edge_b2) / 2.0
    vertical = str(writing_mode or "horizontal-tb").startswith("vertical")
    if vertical:
        score_a = abs(float(vector_a[1])) / max(1e-9, float(np.linalg.norm(vector_a)))
        score_b = abs(float(vector_b[1])) / max(1e-9, float(np.linalg.norm(vector_b)))
    else:
        score_a = abs(float(vector_a[0])) / max(1e-9, float(np.linalg.norm(vector_a)))
        score_b = abs(float(vector_b[0])) / max(1e-9, float(np.linalg.norm(vector_b)))
    if score_a >= score_b:
        inline, cross = length_a, length_b
    else:
        inline, cross = length_b, length_a
    center = points.mean(axis=0)
    return float(center[0]), float(center[1]), float(inline), float(cross)


def _robust_spatial_gradient_ratio(
    samples: list[tuple[float, float, float]],
    size: tuple[int, int],
) -> float:
    """Estimate multiplicative size drift across the page with robust log-plane fit."""
    if len(samples) < 12:
        return 0.0
    width, height = size
    values = np.asarray([sample[2] for sample in samples], dtype=float)
    xs = np.asarray([sample[0] for sample in samples], dtype=float)
    ys = np.asarray([sample[1] for sample in samples], dtype=float)
    valid = np.isfinite(values) & np.isfinite(xs) & np.isfinite(ys) & (values > 0.0)
    if int(valid.sum()) < 12:
        return 0.0
    values = values[valid]
    xs = xs[valid] / max(1.0, float(width)) - 0.5
    ys = ys[valid] / max(1.0, float(height)) - 0.5
    logs = np.log(values)
    design = np.column_stack([np.ones(len(logs)), xs, ys])
    keep = np.ones(len(logs), dtype=bool)
    coeff = np.zeros(3, dtype=float)
    for _ in range(4):
        if int(keep.sum()) < 10:
            break
        coeff, *_ = np.linalg.lstsq(design[keep], logs[keep], rcond=None)
        residual = logs - design @ coeff
        center = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - center)))
        threshold = max(0.08, mad * 3.5)
        new_keep = np.abs(residual - center) <= threshold
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep
    if int(keep.sum()) < 10:
        return 0.0
    coeff, *_ = np.linalg.lstsq(design[keep], logs[keep], rcond=None)
    gradient = math.hypot(float(coeff[1]), float(coeff[2]))
    return max(0.0, math.exp(gradient) - 1.0)


def audit_text_scale_stability(
    before_polygons: Iterable[np.ndarray],
    after_polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    *,
    writing_mode: str = "horizontal-tb",
) -> TextScaleStabilityAudit:
    """Measure the transform-induced scale field using paired text polygons."""
    before_list = list(before_polygons)
    after_list = list(after_polygons)
    count = min(len(before_list), len(after_list))
    if count < 12:
        return TextScaleStabilityAudit(sample_count=count)

    before_inline: list[tuple[float, float, float]] = []
    before_cross: list[tuple[float, float, float]] = []
    after_inline: list[tuple[float, float, float]] = []
    after_cross: list[tuple[float, float, float]] = []
    inline_ratio_samples: list[tuple[float, float, float]] = []
    cross_ratio_samples: list[tuple[float, float, float]] = []
    anisotropy: list[float] = []
    inline_ratios: list[float] = []
    cross_ratios: list[float] = []

    for before, after in zip(before_list[:count], after_list[:count]):
        first = _polygon_inline_cross_size(before, writing_mode=writing_mode)
        second = _polygon_inline_cross_size(after, writing_mode=writing_mode)
        if first is None or second is None:
            continue
        bx, by, bi, bc = first
        ax, ay, ai, ac = second
        if min(bi, bc, ai, ac) <= 1e-9:
            continue
        inline_ratio = float(ai / bi)
        cross_ratio = float(ac / bc)
        if (
            not math.isfinite(inline_ratio)
            or not math.isfinite(cross_ratio)
            or inline_ratio <= 0.0
            or cross_ratio <= 0.0
        ):
            continue

        before_inline.append((bx, by, bi))
        before_cross.append((bx, by, bc))
        after_inline.append((ax, ay, ai))
        after_cross.append((ax, ay, ac))
        inline_ratio_samples.append((bx, by, inline_ratio))
        cross_ratio_samples.append((bx, by, cross_ratio))
        inline_ratios.append(inline_ratio)
        cross_ratios.append(cross_ratio)
        anisotropy.append(
            max(inline_ratio / cross_ratio, cross_ratio / inline_ratio) - 1.0
        )

    paired = len(inline_ratios)
    if paired < 12:
        return TextScaleStabilityAudit(sample_count=paired)

    inline_values = np.asarray(inline_ratios, dtype=float)
    cross_values = np.asarray(cross_ratios, dtype=float)
    anisotropy_values = np.asarray(anisotropy, dtype=float)
    inline_p05, inline_median, inline_p95 = np.quantile(
        inline_values, [0.05, 0.50, 0.95]
    )
    cross_p05, cross_median, cross_p95 = np.quantile(
        cross_values, [0.05, 0.50, 0.95]
    )
    inline_span = (
        float(inline_p95 - inline_p05) / max(1e-9, float(inline_median))
    )
    cross_span = (
        float(cross_p95 - cross_p05) / max(1e-9, float(cross_median))
    )
    inline_gradient = _robust_spatial_gradient_ratio(
        inline_ratio_samples, size
    )
    cross_gradient = _robust_spatial_gradient_ratio(
        cross_ratio_samples, size
    )
    anisotropy_p95 = float(np.quantile(anisotropy_values, 0.95))

    # Absolute size trends are useful for diagnostics but can be confounded by
    # genuine typography (headwords, phonetics, mixed font sizes). They no
    # longer decide whether the transform is safe.
    before_inline_gradient = _robust_spatial_gradient_ratio(before_inline, size)
    after_inline_gradient = _robust_spatial_gradient_ratio(after_inline, size)
    before_cross_gradient = _robust_spatial_gradient_ratio(before_cross, size)
    after_cross_gradient = _robust_spatial_gradient_ratio(after_cross, size)
    before_score = 0.30 * before_inline_gradient + 0.70 * before_cross_gradient
    after_score = 0.30 * after_inline_gradient + 0.70 * after_cross_gradient

    # Slightly looser than the analytic Jacobian budget because polygon edge
    # lengths also carry detector quantization/orientation noise.
    safe = bool(
        inline_span <= TEXT_SCALE_INLINE_SPAN_MAX
        and cross_span <= TEXT_SCALE_CROSS_SPAN_MAX
        and inline_gradient <= TEXT_SCALE_INLINE_GRADIENT_MAX
        and cross_gradient <= TEXT_SCALE_CROSS_GRADIENT_MAX
        and anisotropy_p95 <= TEXT_SCALE_ANISOTROPY_P95_MAX
    )
    verdict = "stable" if safe else "worse"
    return TextScaleStabilityAudit(
        sample_count=paired,
        inline_ratio_p05=float(inline_p05),
        inline_ratio_median=float(inline_median),
        inline_ratio_p95=float(inline_p95),
        cross_ratio_p05=float(cross_p05),
        cross_ratio_median=float(cross_median),
        cross_ratio_p95=float(cross_p95),
        inline_ratio_span_ratio=max(0.0, inline_span),
        cross_ratio_span_ratio=max(0.0, cross_span),
        inline_ratio_gradient_ratio=max(0.0, inline_gradient),
        cross_ratio_gradient_ratio=max(0.0, cross_gradient),
        anisotropy_p95_ratio=max(0.0, anisotropy_p95),
        before_inline_gradient_ratio=before_inline_gradient,
        after_inline_gradient_ratio=after_inline_gradient,
        before_cross_gradient_ratio=before_cross_gradient,
        after_cross_gradient_ratio=after_cross_gradient,
        before_score=before_score,
        after_score=after_score,
        verdict=verdict,
    )

def _normalize_text_angle(angle: float) -> float:
    value = float(angle)
    while value >= 90.0:
        value -= 180.0
    while value < -90.0:
        value += 180.0
    return value


def _weighted_median_pairs(values: list[tuple[float, float]]) -> float:
    if not values:
        return 0.0
    ordered = sorted(
        (float(value), max(0.0, float(weight)))
        for value, weight in values
    )
    total = sum(weight for _value, weight in ordered)
    if total <= 0.0:
        return float(np.median([value for value, _weight in ordered]))
    target = total / 2.0
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= target:
            return value
    return ordered[-1][0]


def _horizontal_polygon_sample(
    raw: np.ndarray,
) -> tuple[float, float, float, float, float] | None:
    poly = np.asarray(raw, dtype=float)
    if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
        return None
    points = poly[:, :2]
    if not np.isfinite(points).all():
        return None
    x0 = float(points[:, 0].min())
    x1 = float(points[:, 0].max())
    y0 = float(points[:, 1].min())
    y1 = float(points[:, 1].max())
    width = x1 - x0
    height = y1 - y0
    if width < max(12.0, height * 1.35) or height < 3.0:
        return None

    edges: list[tuple[float, float]] = []
    for index in range(len(points)):
        p0 = points[index]
        p1 = points[(index + 1) % len(points)]
        dx = float(p1[0] - p0[0])
        dy = float(p1[1] - p0[1])
        length = math.hypot(dx, dy)
        if length < max(8.0, height * 1.2):
            continue
        angle = _normalize_text_angle(math.degrees(math.atan2(dy, dx)))
        if abs(angle) <= 20.0 and abs(dx) >= abs(dy):
            edges.append((angle, length))
    if not edges:
        return None
    selected = sorted(edges, key=lambda item: item[1], reverse=True)[:2]
    angle = _weighted_median_pairs(selected)
    center = points.mean(axis=0)
    return (
        float(center[0]),
        float(center[1]),
        float(angle),
        max(1.0, width),
        max(1.0, height),
    )


def _horizontal_rows(
    polygons: Iterable[np.ndarray],
) -> list[tuple[float, float, float, float]]:
    samples = [
        sample
        for raw in polygons
        if (sample := _horizontal_polygon_sample(np.asarray(raw, dtype=float)))
        is not None
    ]
    if not samples:
        return []
    median_height = float(np.median([sample[4] for sample in samples]))
    tolerance = max(4.0, median_height * 0.72)
    samples.sort(key=lambda item: item[1])

    clusters: list[list[tuple[float, float, float, float, float]]] = []
    for sample in samples:
        if not clusters:
            clusters.append([sample])
            continue
        cluster_y = _weighted_median_pairs(
            [(item[1], item[3]) for item in clusters[-1]]
        )
        if abs(sample[1] - cluster_y) <= tolerance:
            clusters[-1].append(sample)
        else:
            clusters.append([sample])

    rows: list[tuple[float, float, float, float]] = []
    for cluster in clusters:
        x = _weighted_median_pairs([(item[0], item[3]) for item in cluster])
        y = _weighted_median_pairs([(item[1], item[3]) for item in cluster])
        angle = _weighted_median_pairs([(item[2], item[3]) for item in cluster])
        weight = sum(item[3] for item in cluster)
        rows.append((x, y, angle, max(1.0, weight)))
    return rows


def _horizontal_row_stats(
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


def audit_horizontal_alignment(
    before_polygons: Iterable[np.ndarray],
    after_polygons: Iterable[np.ndarray],
) -> HorizontalAlignmentAudit:
    before_rows = _horizontal_rows(before_polygons)
    after_rows = _horizontal_rows(after_polygons)
    if min(len(before_rows), len(after_rows)) < 5:
        return HorizontalAlignmentAudit(
            row_count=min(len(before_rows), len(after_rows)),
        )
    (
        before_global,
        before_top,
        before_bottom,
        before_trend,
        before_mad,
        _before_span,
    ) = _horizontal_row_stats(before_rows)
    (
        after_global,
        after_top,
        after_bottom,
        after_trend,
        after_mad,
        _after_span,
    ) = _horizontal_row_stats(after_rows)
    before_metric = (
        max(abs(before_top), abs(before_bottom))
        + 0.45 * abs(before_trend)
        + 0.35 * before_mad
    )
    after_metric = (
        max(abs(after_top), abs(after_bottom))
        + 0.45 * abs(after_trend)
        + 0.35 * after_mad
    )
    improvement = (
        (before_metric - after_metric) / max(1e-6, before_metric)
        if before_metric > 1e-6 else 0.0
    )
    edge_after = max(abs(after_top), abs(after_bottom))
    if len(after_rows) < HORIZONTAL_VP_MIN_ROWS:
        verdict = "insufficient"
    elif (
        abs(before_trend) >= HORIZONTAL_VP_MIN_TREND_DEG
        and improvement >= HORIZONTAL_ALIGNMENT_MIN_IMPROVEMENT
        and abs(after_trend) <= HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG
        and edge_after <= HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG
        and after_mad <= max(0.16, before_mad + 0.03)
    ):
        verdict = "improved"
    elif after_metric <= before_metric + 0.03:
        verdict = "stable"
    else:
        verdict = "worse"
    return HorizontalAlignmentAudit(
        row_count=min(len(before_rows), len(after_rows)),
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
        improvement_ratio=max(-10.0, min(1.0, improvement)),
        verdict=verdict,
    )


def _fit_horizontal_vanishing_point(
    rows: list[tuple[float, float, float, float]],
) -> tuple[float, float]:
    if len(rows) < HORIZONTAL_VP_MIN_ROWS:
        raise RuntimeError("有效文本行不足，无法估计水平消失点")
    angles = np.asarray([row[2] for row in rows], dtype=float)
    if float(np.percentile(angles, 90) - np.percentile(angles, 10)) < 0.14:
        raise RuntimeError("文本行角度变化过小，无需水平消失点校正")

    equations: list[tuple[float, float, float, float]] = []
    for x, y, angle_deg, weight in rows:
        radians = math.radians(float(angle_deg))
        a = -math.sin(radians)
        b = math.cos(radians)
        c = -(a * float(x) + b * float(y))
        equations.append((a, b, c, max(1.0, float(weight))))

    keep = np.ones(len(equations), dtype=bool)
    point = np.zeros(2, dtype=float)
    for _ in range(5):
        if int(keep.sum()) < HORIZONTAL_VP_MIN_ROWS:
            raise RuntimeError("水平消失点有效行不足")
        selected = [equations[i] for i in range(len(equations)) if keep[i]]
        a_mat = np.asarray([[item[0], item[1]] for item in selected], dtype=float)
        b_vec = np.asarray([-item[2] for item in selected], dtype=float)
        weights = np.sqrt(np.asarray([item[3] for item in selected], dtype=float))
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


def estimate_horizontal_perspective_from_polygons(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
) -> PerspectiveEstimate:
    """Build a minimal projective rectifier from the horizontal vanishing point.

    The transform sends the common vanishing point of text rows to infinity,
    then rotates that infinite direction onto the image X axis.  At the page
    center the projective component is identity, minimizing unnecessary local
    scale change; downstream Jacobian and paired-text audits remain mandatory.
    """
    width, height = size
    polygon_list = [np.asarray(poly, dtype=float) for poly in polygons]
    rows = _horizontal_rows(polygon_list)
    if len(rows) < HORIZONTAL_VP_MIN_ROWS:
        raise RuntimeError("有效文本行不足，无法估计水平消失点")
    (
        _global_angle,
        _top_angle,
        _bottom_angle,
        trend,
        _residual_mad,
        _span,
    ) = _horizontal_row_stats(rows)
    if abs(trend) < HORIZONTAL_VP_MIN_TREND_DEG:
        raise RuntimeError("文本行上下角度变化不足，无需水平消失点校正")

    vx, vy = _fit_horizontal_vanishing_point(rows)
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
    # A vanishing point at infinity is homogeneous: d and -d describe the
    # same direction.  Force the representative to point toward +X so a VP on
    # the left side of the page does not accidentally introduce a 180° flip.
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
    )


def interpolate_perspective_estimate(
    estimate: PerspectiveEstimate,
    size: tuple[int, int],
    strength: float,
    *,
    candidate_source: str | None = None,
) -> PerspectiveEstimate:
    """Interpolate identity→estimate while preserving a valid global homography.

    This is used for residual horizontal-VP correction: the full vanishing-point
    rectifier provides the *direction* of projective correction, while a bounded
    one-dimensional search chooses the smallest strength that best flattens the
    text rows without exceeding scale-distortion budgets.
    """
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
    )


def optimize_horizontal_perspective_strength(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    full_estimate: PerspectiveEstimate,
) -> tuple[PerspectiveEstimate, HorizontalAlignmentAudit, float]:
    """Find the partial horizontal-VP strength with minimum row error.

    The search is intentionally lightweight: polygon transforms and angle
    audits only, no image resampling. Safety audits are applied by the caller to
    the final composed transform.
    """
    polygon_list = [np.asarray(poly, dtype=float) for poly in polygons]
    if len(polygon_list) < HORIZONTAL_VP_MIN_ROWS:
        raise RuntimeError("有效文本框不足，无法优化水平投影强度")

    full_polygons = transform_polygons_homography(
        polygon_list, full_estimate.matrix,
    )
    full_audit = audit_horizontal_alignment(polygon_list, full_polygons)
    before_trend = float(full_audit.before_trend_deg)
    after_trend = float(full_audit.after_trend_deg)

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
        tuple[float, float, PerspectiveEstimate, HorizontalAlignmentAudit]
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
        audit = audit_horizontal_alignment(polygon_list, mapped)
        objective = (
            float(audit.after_metric_deg)
            + 0.08 * abs(float(audit.after_trend_deg))
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
        audit = audit_horizontal_alignment(polygon_list, mapped)
        objective = (
            float(audit.after_metric_deg)
            + 0.08 * abs(float(audit.after_trend_deg))
            + 0.02 * float(lam)
        )
        evaluated.append((objective, float(lam), candidate, audit))

    best = min(evaluated, key=lambda item: (item[0], item[1]))
    return best[2], best[3], best[1]


def compose_perspective_estimates(
    first: PerspectiveEstimate,
    second: PerspectiveEstimate,
    size: tuple[int, int],
) -> PerspectiveEstimate:
    """Compose source→first and first→second candidate transforms."""
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
    )


def _homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Return a 3x3 matrix mapping src XY coordinates to dst XY coordinates."""
    if src.shape != (4, 2) or dst.shape != (4, 2):
        raise ValueError("Homography requires four 2D source and destination points")
    rows: list[list[float]] = []
    values: list[float] = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        values.append(u)
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        values.append(v)
    coeff = np.linalg.solve(np.asarray(rows, dtype=float), np.asarray(values, dtype=float))
    matrix = np.asarray(
        [
            [coeff[0], coeff[1], coeff[2]],
            [coeff[3], coeff[4], coeff[5]],
            [coeff[6], coeff[7], 1.0],
        ],
        dtype=float,
    )
    return matrix


def estimate_perspective_from_polygons(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings,
) -> PerspectiveEstimate:
    width, _height = size
    polygons = list(polygons)
    boxes, estimate = _layout(polygons, size, settings)
    starts = tuple(int(v) for v in estimate.column_starts)
    samples = _column_left_samples(boxes, estimate, width)

    first_line = _robust_line(samples[0])
    last_line = _robust_line(samples[-1])
    top = float(max(0, estimate.start_y))
    bottom = float(max(estimate.start_y + 1, estimate.bottom_y))

    def at(line: tuple[float, float], y: float) -> float:
        return line[0] * y + line[1]

    left_top = at(first_line, top)
    left_bottom = at(first_line, bottom)
    right_top = at(last_line, top)
    right_bottom = at(last_line, bottom)
    if min(right_top - left_top, right_bottom - left_bottom) < max(20.0, width * 0.12):
        raise RuntimeError("栏间跨度不足，无法稳定估计透视")

    target_left = float(np.median([x for _y, x in samples[0]]))
    target_right = float(np.median([x for _y, x in samples[-1]]))
    if target_right - target_left < max(20.0, width * 0.12):
        raise RuntimeError("目标栏间跨度不足，无法稳定估计透视")

    src = np.asarray(
        [
            [left_top, top],
            [right_top, top],
            [right_bottom, bottom],
            [left_bottom, bottom],
        ],
        dtype=float,
    )
    dst = np.asarray(
        [
            [target_left, top],
            [target_right, top],
            [target_right, bottom],
            [target_left, bottom],
        ],
        dtype=float,
    )
    matrix = _homography(src, dst)
    strength = float(np.max(np.linalg.norm(src - dst, axis=1)))
    top_width = float(right_top - left_top)
    bottom_width = float(right_bottom - left_bottom)
    mean_width = max(1.0, (top_width + bottom_width) / 2.0)
    left_drift = float(left_bottom - left_top)
    right_drift = float(right_bottom - right_top)
    common_drift = float((left_drift + right_drift) / 2.0)
    width_delta = float(bottom_width - top_width)
    width_change_ratio = abs(width_delta) / mean_width
    target_width = max(1.0, float(target_right - target_left))
    scale_top = target_width / max(1.0, top_width)
    scale_bottom = target_width / max(1.0, bottom_width)
    scale_mean = max(1e-9, (abs(scale_top) + abs(scale_bottom)) / 2.0)
    scale_delta_ratio = abs(scale_bottom - scale_top) / scale_mean
    same_direction = left_drift * right_drift > 0.0
    parallel_dominant = (
        same_direction
        and abs(common_drift) >= max(4.0, abs(width_delta) * 1.5)
    )
    if parallel_dominant:
        classification = "parallel_drift"
    elif width_change_ratio >= 0.003:
        classification = "keystone"
    else:
        classification = "weak"

    return PerspectiveEstimate(
        matrix=tuple(float(v) for v in matrix.reshape(-1)),
        source_quad=tuple(float(v) for v in src.reshape(-1)),
        target_quad=tuple(float(v) for v in dst.reshape(-1)),
        strength_px=strength,
        left_drift_px=left_drift,
        right_drift_px=right_drift,
        common_drift_px=common_drift,
        width_delta_px=width_delta,
        width_change_ratio=width_change_ratio,
        scale_top=scale_top,
        scale_bottom=scale_bottom,
        scale_delta_ratio=scale_delta_ratio,
        classification=classification,
        candidate_source="structural",
    )


def perspective_from_quad(
    quad: Iterable[float],
    size: tuple[int, int],
) -> PerspectiveEstimate:
    """Build a manual four-corner rectification on the existing page canvas.

    quad is ordered TL, TR, BR, BL in source-image pixels. The selected
    quadrilateral is mapped to its axis-aligned bounding rectangle, preserving
    the surrounding canvas so downstream layout detection can run normally.
    """
    values = tuple(float(v) for v in quad)
    if len(values) != 8:
        raise ValueError("手动四角必须包含 4 个二维坐标")
    width, height = size
    src = np.asarray(values, dtype=float).reshape(4, 2)
    if not np.isfinite(src).all():
        raise ValueError("手动四角包含无效坐标")
    src[:, 0] = np.clip(src[:, 0], 0.0, max(0.0, float(width - 1)))
    src[:, 1] = np.clip(src[:, 1], 0.0, max(0.0, float(height - 1)))

    tl, tr, br, bl = src
    top_width = float(np.linalg.norm(tr - tl))
    bottom_width = float(np.linalg.norm(br - bl))
    left_height = float(np.linalg.norm(bl - tl))
    right_height = float(np.linalg.norm(br - tr))
    if min(top_width, bottom_width) < max(20.0, width * 0.08):
        raise ValueError("手动四角的页面宽度过小")
    if min(left_height, right_height) < max(20.0, height * 0.08):
        raise ValueError("手动四角的页面高度过小")

    crosses = []
    for index in range(4):
        p0 = src[index]
        p1 = src[(index + 1) % 4]
        p2 = src[(index + 2) % 4]
        first = p1 - p0
        second = p2 - p1
        crosses.append(float(first[0] * second[1] - first[1] * second[0]))
    if not (all(v > 0 for v in crosses) or all(v < 0 for v in crosses)):
        raise ValueError("四角顺序发生交叉，请保持左上→右上→右下→左下")

    left = float(min(tl[0], bl[0]))
    right = float(max(tr[0], br[0]))
    top = float(min(tl[1], tr[1]))
    bottom = float(max(bl[1], br[1]))
    if right - left < 20 or bottom - top < 20:
        raise ValueError("手动四角形成的目标矩形过小")
    dst = np.asarray(
        [[left, top], [right, top], [right, bottom], [left, bottom]],
        dtype=float,
    )
    matrix = _homography(src, dst)
    strength = float(np.max(np.linalg.norm(src - dst, axis=1)))
    top_width = max(1.0, float(np.linalg.norm(tr - tl)))
    bottom_width = max(1.0, float(np.linalg.norm(br - bl)))
    target_width = max(1.0, float(right - left))
    scale_top = target_width / top_width
    scale_bottom = target_width / bottom_width
    scale_mean = max(1e-9, (abs(scale_top) + abs(scale_bottom)) / 2.0)
    return PerspectiveEstimate(
        matrix=tuple(float(v) for v in matrix.reshape(-1)),
        source_quad=tuple(float(v) for v in src.reshape(-1)),
        target_quad=tuple(float(v) for v in dst.reshape(-1)),
        strength_px=strength,
        left_drift_px=float(bl[0] - tl[0]),
        right_drift_px=float(br[0] - tr[0]),
        common_drift_px=float(((bl[0] - tl[0]) + (br[0] - tr[0])) / 2.0),
        width_delta_px=float(bottom_width - top_width),
        width_change_ratio=abs(bottom_width - top_width) / max(1.0, (top_width + bottom_width) / 2.0),
        scale_top=scale_top,
        scale_bottom=scale_bottom,
        scale_delta_ratio=abs(scale_bottom - scale_top) / scale_mean,
        classification="manual",
    )


def transform_points_homography(points: np.ndarray, matrix: Iterable[float]) -> np.ndarray:
    mat = np.asarray(tuple(matrix), dtype=float).reshape(3, 3)
    raw = np.asarray(points, dtype=float)
    flat = raw.reshape(-1, 2)
    hom = np.column_stack([flat, np.ones(len(flat), dtype=float)])
    mapped = hom @ mat.T
    denom = mapped[:, 2:3]
    denom[np.abs(denom) < 1e-9] = 1e-9
    xy = mapped[:, :2] / denom
    return xy.reshape(raw.shape)


def transform_polygons_homography(
    polygons: Iterable[np.ndarray], matrix: Iterable[float],
) -> list[np.ndarray]:
    return [
        transform_points_homography(np.asarray(poly, dtype=float), matrix)
        for poly in polygons
    ]


def _paper_fill(image: Image.Image) -> tuple[int, int, int]:
    source = normalize_page_rgb(image)
    w, h = source.size
    pw = max(1, round(w * 0.04))
    ph = max(1, round(h * 0.04))
    samples = [
        np.asarray(source.crop((0, 0, pw, ph)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((max(0, w - pw), 0, w, ph)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((0, max(0, h - ph), pw, h)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((max(0, w - pw), max(0, h - ph), w, h)), dtype=np.uint8).reshape(-1, 3),
    ]
    median = np.median(np.concatenate(samples, axis=0), axis=0)
    return tuple(int(round(v)) for v in median[:3])


def apply_homography_image(image: Image.Image, matrix: Iterable[float]) -> Image.Image:
    source = normalize_page_rgb(image)
    mat = np.asarray(tuple(matrix), dtype=float).reshape(3, 3)
    inverse = np.linalg.inv(mat)
    inverse /= inverse[2, 2]
    coeff = (
        float(inverse[0, 0]), float(inverse[0, 1]), float(inverse[0, 2]),
        float(inverse[1, 0]), float(inverse[1, 1]), float(inverse[1, 2]),
        float(inverse[2, 0]), float(inverse[2, 1]),
    )
    return source.transform(
        source.size,
        Image.Transform.PERSPECTIVE,
        coeff,
        resample=Image.Resampling.BICUBIC,
        fillcolor=_paper_fill(source),
    )


