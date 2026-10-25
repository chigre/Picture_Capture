from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from PIL import Image

from ..preprocess.analysis_image import normalize_page_rgb
from . import homography_ops as _homography_ops
from . import text_scale_audit as _text_scale_audit
from . import horizontal_alignment_audit as _horizontal_alignment_audit
from . import horizontal_strength as _horizontal_strength
from ..layout.detection import LayoutEstimate, infer_layout_from_boxes
from ..models import AppSettings


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
HORIZONTAL_ALIGNMENT_MAX_EDGE_PAIR_DELTA_DEG = 0.15
HORIZONTAL_ALIGNMENT_TAIL_FRACTION = 0.18
HORIZONTAL_ALIGNMENT_MAX_TAIL_DEG = 0.18
HORIZONTAL_VP_COLUMN_SPREAD_MAX_DEG = 0.35
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
    valid_column_indices: tuple[int, ...] = ()
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
    before_worst_edge_deg: float = 0.0
    after_worst_edge_deg: float = 0.0
    before_top_edge_p90_abs_deg: float = 0.0
    after_top_edge_p90_abs_deg: float = 0.0
    before_bottom_edge_p90_abs_deg: float = 0.0
    after_bottom_edge_p90_abs_deg: float = 0.0
    before_edge_pair_delta_p90_deg: float = 0.0
    after_edge_pair_delta_p90_deg: float = 0.0
    edge_pair_count: int = 0
    before_worst_region_span_deg: float = 0.0
    after_worst_region_span_deg: float = 0.0
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
    before_column_top_tail_p90_abs_deg: tuple[float, ...] = ()
    after_column_top_tail_p90_abs_deg: tuple[float, ...] = ()
    before_column_bottom_tail_p90_abs_deg: tuple[float, ...] = ()
    after_column_bottom_tail_p90_abs_deg: tuple[float, ...] = ()
    before_worst_tail_p90_abs_deg: float = 0.0
    after_worst_tail_p90_abs_deg: float = 0.0
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
    """Return the analytic 2x2 Jacobian at original source XY."""
    return _homography_ops.homography_jacobian(matrix, x, y)


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
    return _text_scale_audit.polygon_inline_cross_size(
        polygon, writing_mode=writing_mode,
    )


def _robust_spatial_gradient_ratio(
    samples: list[tuple[float, float, float]],
    size: tuple[int, int],
) -> float:
    """Historical gradient helper, physically owned by scale audit."""
    return _text_scale_audit.robust_spatial_gradient_ratio(samples, size)


def audit_text_scale_stability(
    before_polygons: Iterable[np.ndarray],
    after_polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    *,
    writing_mode: str = "horizontal-tb",
) -> TextScaleStabilityAudit:
    """Measure the transform-induced scale field using paired text polygons."""
    return _text_scale_audit.audit_text_scale_stability(
        before_polygons, after_polygons, size,
        writing_mode=writing_mode,
        audit_type=TextScaleStabilityAudit,
        polygon_measure=_polygon_inline_cross_size,
        gradient_ratio=_robust_spatial_gradient_ratio,
        limits=(
            TEXT_SCALE_INLINE_SPAN_MAX, TEXT_SCALE_CROSS_SPAN_MAX,
            TEXT_SCALE_INLINE_GRADIENT_MAX, TEXT_SCALE_CROSS_GRADIENT_MAX,
            TEXT_SCALE_ANISOTROPY_P95_MAX,
        ),
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


def _weighted_percentile_pairs(
    values: list[tuple[float, float]],
    percentile: float,
) -> float:
    if not values:
        return 0.0
    ordered = sorted(
        (float(value), max(0.0, float(weight)))
        for value, weight in values
    )
    total = sum(weight for _value, weight in ordered)
    if total <= 0.0:
        return float(np.percentile([value for value, _weight in ordered], percentile))
    target = total * max(0.0, min(100.0, float(percentile))) / 100.0
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= target:
            return value
    return ordered[-1][0]


def _horizontal_polygon_edge_angles(
    raw: np.ndarray,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Return independent top/bottom edge angles for one OCR text polygon.

    True row horizontality requires *both* long horizontal edges to be level.
    Collapsing a quadrilateral to one representative angle can hide a trapezoid
    or projective shear where the top edge and bottom edge tilt in opposite
    directions.
    """
    poly = np.asarray(raw, dtype=float)
    if poly.ndim != 2 or poly.shape[0] < 4 or poly.shape[1] < 2:
        return None
    points = poly[:, :2]
    if not np.isfinite(points).all():
        return None
    width = float(points[:, 0].max() - points[:, 0].min())
    height = float(points[:, 1].max() - points[:, 1].min())
    if width < max(12.0, height * 1.35) or height < 3.0:
        return None

    edges: list[tuple[float, float, float]] = []
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
            midpoint_y = float((p0[1] + p1[1]) / 2.0)
            edges.append((midpoint_y, angle, length))
    if len(edges) < 2:
        return None

    ordered = sorted(edges, key=lambda item: item[0])
    top = ordered[0]
    bottom = ordered[-1]
    if top is bottom:
        return None
    return (
        (float(top[1]), float(top[2])),
        (float(bottom[1]), float(bottom[2])),
    )


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

    edge_pair = _horizontal_polygon_edge_angles(poly)
    if edge_pair is None:
        return None
    (top_angle, top_length), (bottom_angle, bottom_length) = edge_pair
    total_length = max(1e-9, top_length + bottom_length)
    # Angles are constrained to ±20°, so a length-weighted mean is stable and
    # uses both boundaries instead of silently selecting only one of them.
    angle = (
        top_angle * top_length + bottom_angle * bottom_length
    ) / total_length
    center = points.mean(axis=0)
    return (
        float(center[0]),
        float(center[1]),
        float(angle),
        max(1.0, width),
        max(1.0, height),
    )


def _horizontal_polygon_edge_metrics(
    polygons: list[np.ndarray],
    groups: list[list[int]],
) -> tuple[int, float, float, float, float]:
    """Robust dual-edge audit, equalized by column.

    Returns (sample_count, top_abs_p90, bottom_abs_p90, pair_delta_p90,
    worst_edge). Each populated column is summarized first, then the worst
    column is retained so one bad column cannot disappear in a page average.
    """
    column_top: list[float] = []
    column_bottom: list[float] = []
    column_delta: list[float] = []
    sample_count = 0
    for indices in groups:
        top_values: list[tuple[float, float]] = []
        bottom_values: list[tuple[float, float]] = []
        delta_values: list[tuple[float, float]] = []
        for index in indices:
            if not (0 <= index < len(polygons)):
                continue
            edge_pair = _horizontal_polygon_edge_angles(polygons[index])
            if edge_pair is None:
                continue
            (top_angle, top_length), (bottom_angle, bottom_length) = edge_pair
            weight = max(1.0, min(float(top_length), float(bottom_length)))
            top_values.append((abs(float(top_angle)), weight))
            bottom_values.append((abs(float(bottom_angle)), weight))
            delta_values.append(
                (
                    abs(
                        _normalize_text_angle(
                            float(top_angle) - float(bottom_angle)
                        )
                    ),
                    weight,
                )
            )
        if len(top_values) < 5:
            continue
        sample_count += len(top_values)
        column_top.append(_weighted_percentile_pairs(top_values, 90.0))
        column_bottom.append(_weighted_percentile_pairs(bottom_values, 90.0))
        column_delta.append(_weighted_percentile_pairs(delta_values, 90.0))

    top_p90 = max(column_top, default=0.0)
    bottom_p90 = max(column_bottom, default=0.0)
    pair_p90 = max(column_delta, default=0.0)
    return (
        int(sample_count),
        float(top_p90),
        float(bottom_p90),
        float(pair_p90),
        float(max(top_p90, bottom_p90)),
    )


def _cluster_horizontal_samples(
    samples: list[tuple[float, float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    """Cluster text-box orientation samples into rows *within one column*."""
    if not samples:
        return []
    samples = list(samples)
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


def _horizontal_rows(
    polygons: Iterable[np.ndarray],
) -> list[tuple[float, float, float, float]]:
    """Legacy/global helper; N-column analysis uses per-column clustering."""
    samples = [
        sample
        for raw in polygons
        if (sample := _horizontal_polygon_sample(np.asarray(raw, dtype=float)))
        is not None
    ]
    return _cluster_horizontal_samples(samples)


def _horizontal_column_indices(
    polygons: list[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings | None = None,
) -> tuple[list[list[int]], tuple[int, ...]]:
    """Assign text polygons to 1..N structural columns without cross-column rows.

    Layout detection supplies column starts/rights. A polygon is assigned to one
    column by maximal horizontal overlap; page-spanning headers/rules are
    deliberately excluded from column row geometry.
    """
    width, height = size
    if not polygons:
        return [], ()
    active_settings = settings or AppSettings()
    boxes = polygon_boxes(polygons, width, height)
    try:
        estimate = infer_layout_from_boxes(
            boxes,
            size,
            display_scale=1.0,
            ink_mask=None,
            columns_policy=active_settings.layout_columns_policy,
            fixed_columns=active_settings.columns,
            column_separator_mode=active_settings.layout_column_separator_mode,
        )
        starts = tuple(int(v) for v in estimate.column_starts)
        rights = tuple(int(v) for v in estimate.column_rights)
    except Exception:
        starts = ()
        rights = ()

    if not starts:
        return [list(range(len(polygons)))], (0,)
    if len(rights) != len(starts):
        inferred_rights: list[int] = []
        for index, left in enumerate(starts):
            if index + 1 < len(starts):
                inferred_rights.append(
                    int(round((left + starts[index + 1]) / 2.0))
                )
            else:
                inferred_rights.append(width)
        rights = tuple(inferred_rights)

    bounds: list[tuple[float, float]] = []
    for index, left in enumerate(starts):
        right = rights[index] if index < len(rights) else width
        if right <= left:
            right = (
                starts[index + 1]
                if index + 1 < len(starts)
                else width
            )
        bounds.append(
            (
                max(0.0, float(left)),
                min(float(width), max(float(left) + 1.0, float(right))),
            )
        )

    typical_width = float(
        np.median([max(1.0, right - left) for left, right in bounds])
    )
    groups: list[list[int]] = [[] for _ in bounds]
    for poly_index, raw in enumerate(polygons):
        sample = _horizontal_polygon_sample(raw)
        if sample is None:
            continue
        center_x, _center_y, _angle, box_width, _box_height = sample
        x0 = center_x - box_width / 2.0
        x1 = center_x + box_width / 2.0

        # Headers and other elements spanning more than one designed column do
        # not define the baseline orientation of any individual column.
        if len(bounds) > 1 and box_width > typical_width * 1.35:
            continue

        overlaps = [
            max(0.0, min(x1, right) - max(x0, left))
            for left, right in bounds
        ]
        best_index = int(np.argmax(overlaps))
        best_overlap = overlaps[best_index]
        left, right = bounds[best_index]
        center_inside = left <= center_x <= right
        if best_overlap >= max(3.0, box_width * 0.42) or center_inside:
            groups[best_index].append(poly_index)

    # Keep all detected columns in diagnostics, even when a sparse column has
    # too few usable row boxes; sparse columns simply do not drive the fit.
    return groups, starts


def _horizontal_column_rows(
    polygons: list[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings | None = None,
    *,
    fixed_groups: list[list[int]] | None = None,
) -> tuple[list[list[tuple[float, float, float, float]]], list[list[int]]]:
    groups, _starts = (
        _horizontal_column_indices(polygons, size, settings)
        if fixed_groups is None
        else (fixed_groups, ())
    )
    result: list[list[tuple[float, float, float, float]]] = []
    for indices in groups:
        samples = [
            sample
            for index in indices
            if 0 <= index < len(polygons)
            and (
                sample := _horizontal_polygon_sample(polygons[index])
            )
            is not None
        ]
        result.append(_cluster_horizontal_samples(samples))
    return result, groups


def horizontal_column_rows(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings | None = None,
) -> list[list[tuple[float, float, float, float]]]:
    """Public read-only N-column row reconstruction for geometry diagnostics."""
    polygon_list = [np.asarray(poly, dtype=float) for poly in polygons]
    rows, _groups = _horizontal_column_rows(
        polygon_list, size, settings,
    )
    return rows


def _horizontal_row_stats(
    rows: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float, float, float]:
    return _horizontal_alignment_audit.horizontal_row_stats(rows)


def _horizontal_region_angles(
    rows: list[tuple[float, float, float, float]],
    *,
    fallback: tuple[float, float, float],
) -> tuple[float, float, float]:
    return _horizontal_alignment_audit.horizontal_region_angles(
        rows, fallback=fallback, median_pairs=_weighted_median_pairs,
    )


def _horizontal_tail_p90_abs(
    rows: list[tuple[float, float, float, float]],
    *,
    fraction: float = HORIZONTAL_ALIGNMENT_TAIL_FRACTION,
) -> tuple[float, float]:
    return _horizontal_alignment_audit.horizontal_tail_p90_abs(
        rows, fraction=fraction, percentile_pairs=_weighted_percentile_pairs,
    )


def _horizontal_metric(
    middle: float,
    top: float,
    bottom: float,
    trend: float,
    mad: float,
) -> float:
    return _horizontal_alignment_audit.horizontal_metric(
        middle, top, bottom, trend, mad,
    )


def audit_horizontal_alignment(
    before_polygons: Iterable[np.ndarray],
    after_polygons: Iterable[np.ndarray],
    size: tuple[int, int] | None = None,
    settings: AppSettings | None = None,
) -> HorizontalAlignmentAudit:
    """Audit global horizontality while preserving independent N-column rows."""
    return _horizontal_alignment_audit.audit_horizontal_alignment(
        before_polygons, after_polygons, size, settings,
        ops=_horizontal_alignment_audit.HorizontalAuditOps(
            column_rows=_horizontal_column_rows,
            row_stats=_horizontal_row_stats,
            region_angles=_horizontal_region_angles,
            tail_p90=_horizontal_tail_p90_abs,
            metric=_horizontal_metric,
            edge_metrics=_horizontal_polygon_edge_metrics,
            result_type=HorizontalAlignmentAudit,
            vp_min_rows=HORIZONTAL_VP_MIN_ROWS,
            vp_min_trend_deg=HORIZONTAL_VP_MIN_TREND_DEG,
            min_improvement=HORIZONTAL_ALIGNMENT_MIN_IMPROVEMENT,
            max_after_trend_deg=HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG,
            max_after_edge_deg=HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG,
            max_edge_pair_delta_deg=HORIZONTAL_ALIGNMENT_MAX_EDGE_PAIR_DELTA_DEG,
        ),
    )


def _fit_horizontal_vanishing_point(
    column_rows: list[list[tuple[float, float, float, float]]],
) -> tuple[float, float]:
    """Fit one common horizontal VP with equalized contribution per column."""
    usable = [
        rows for rows in column_rows if len(rows) >= 3
    ]
    total_rows = sum(len(rows) for rows in usable)
    if total_rows < HORIZONTAL_VP_MIN_ROWS:
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
        if int(keep.sum()) < HORIZONTAL_VP_MIN_ROWS:
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


def _horizontal_vp_column_spread_deg(
    column_rows: list[list[tuple[float, float, float, float]]],
    common_vp: tuple[float, float],
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
            predicted = _normalize_text_angle(
                math.degrees(
                    math.atan2(common_y - float(y), common_x - float(x))
                )
            )
            residual = abs(
                _normalize_text_angle(float(angle_deg) - predicted)
            )
            residual_pairs.append((residual, max(1.0, float(weight))))
        if residual_pairs:
            column_residuals.append(
                _weighted_median_pairs(residual_pairs)
            )
    return (
        float(np.percentile(column_residuals, 90))
        if len(column_residuals) >= 2
        else (column_residuals[0] if column_residuals else 0.0)
    )


def estimate_horizontal_perspective_from_polygons(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings | None = None,
) -> PerspectiveEstimate:
    """Build one global projective rectifier from independent 1..N column rows.

    Rows are reconstructed separately inside each detected/fixed layout column,
    so text at similar Y positions in different columns is never treated as one
    typographic line. All columns still vote for one common horizontal VP and
    therefore one global homography.
    """
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


def interpolate_perspective_estimate(
    estimate: PerspectiveEstimate,
    size: tuple[int, int],
    strength: float,
    *,
    candidate_source: str | None = None,
) -> PerspectiveEstimate:
    """Interpolate identity→estimate while retaining the live geometry hooks."""
    return _horizontal_strength.interpolate_perspective_estimate(
        estimate, size, strength,
        candidate_source=candidate_source,
        result_type=PerspectiveEstimate,
        transform_points=transform_points_homography,
    )


def optimize_horizontal_perspective_strength(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    full_estimate: PerspectiveEstimate,
    settings: AppSettings | None = None,
) -> tuple[PerspectiveEstimate, HorizontalAlignmentAudit, float]:
    """Keep public optimizer ABI and capture current collaborators at call time."""
    return _horizontal_strength.optimize_horizontal_perspective_strength(
        polygons, size, full_estimate, settings,
        ops=_horizontal_strength.HorizontalStrengthOps(
            transform_polygons=transform_polygons_homography,
            audit_alignment=audit_horizontal_alignment,
            interpolate=interpolate_perspective_estimate,
            vp_min_rows=HORIZONTAL_VP_MIN_ROWS,
            min_strength=HORIZONTAL_STRENGTH_MIN,
            coarse_step=HORIZONTAL_STRENGTH_COARSE_STEP,
            fine_step=HORIZONTAL_STRENGTH_FINE_STEP,
        ),
    )


def compose_perspective_estimates(
    first: PerspectiveEstimate,
    second: PerspectiveEstimate,
    size: tuple[int, int],
) -> PerspectiveEstimate:
    """Compose two homographies with the historical result class and geometry hook."""
    return _horizontal_strength.compose_perspective_estimates(
        first, second, size,
        result_type=PerspectiveEstimate,
        transform_points=transform_points_homography,
    )


def _homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Return a 3x3 matrix mapping src XY coordinates to dst XY coordinates."""
    return _homography_ops.solve_quad_homography(src, dst)


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
    return _homography_ops.transform_points_homography(points, matrix)


def transform_polygons_homography(
    polygons: Iterable[np.ndarray], matrix: Iterable[float],
) -> list[np.ndarray]:
    return _homography_ops.transform_polygons_homography(
        polygons, matrix, transform_points=transform_points_homography,
    )


def _paper_fill(image: Image.Image) -> tuple[int, int, int]:
    """Historical pixel-fill entrypoint with live normalization dependency."""
    return _homography_ops.corner_paper_fill(
        image, normalize_page_rgb=normalize_page_rgb,
    )


def apply_homography_image(image: Image.Image, matrix: Iterable[float]) -> Image.Image:
    return _homography_ops.apply_homography_image(
        image, matrix, normalize_page_rgb=normalize_page_rgb, paper_fill=_paper_fill,
    )


