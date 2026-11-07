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
from . import horizontal_rows as _horizontal_rows_owner
from . import horizontal_vanishing as _horizontal_vanishing
from . import structural_perspective as _structural_perspective
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
    return _structural_perspective.layout(
        polygons, size, settings,
        polygon_boxes=polygon_boxes, infer_layout=infer_layout_from_boxes,
    )


def _column_pitch(starts: tuple[int, ...], index: int, width: int) -> float:
    return _structural_perspective.column_pitch(starts, index, width)


def _column_left_samples(
    boxes: list[tuple[int, int, int, int]],
    estimate: LayoutEstimate,
    width: int,
) -> list[list[tuple[float, float]]]:
    return _structural_perspective.column_left_samples(
        boxes, estimate, width, column_pitch=_column_pitch,
    )


def _robust_line(samples: list[tuple[float, float]]) -> tuple[float, float]:
    return _structural_perspective.robust_line(samples)


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
    return _horizontal_rows_owner.normalize_text_angle(angle)


def _weighted_median_pairs(values: list[tuple[float, float]]) -> float:
    return _horizontal_rows_owner.weighted_median_pairs(values)


def _weighted_percentile_pairs(
    values: list[tuple[float, float]], percentile: float,
) -> float:
    return _horizontal_rows_owner.weighted_percentile_pairs(values, percentile)


def _horizontal_polygon_edge_angles(raw: np.ndarray) -> tuple[tuple[float, float], tuple[float, float]] | None:
    return _horizontal_rows_owner.horizontal_polygon_edge_angles(raw, normalize_angle=_normalize_text_angle)


def _horizontal_polygon_sample(raw: np.ndarray) -> tuple[float, float, float, float, float] | None:
    return _horizontal_rows_owner.horizontal_polygon_sample(raw, edge_angles=_horizontal_polygon_edge_angles)


def _horizontal_polygon_edge_metrics(
    polygons: list[np.ndarray], groups: list[list[int]],
) -> tuple[int, float, float, float, float]:
    return _horizontal_rows_owner.horizontal_polygon_edge_metrics(
        polygons, groups,
        edge_angles=_horizontal_polygon_edge_angles,
        normalize_angle=_normalize_text_angle,
        percentile_pairs=_weighted_percentile_pairs,
    )


def _cluster_horizontal_samples(
    samples: list[tuple[float, float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    return _horizontal_rows_owner.cluster_horizontal_samples(samples, median_pairs=_weighted_median_pairs)


def _horizontal_rows(polygons: Iterable[np.ndarray]) -> list[tuple[float, float, float, float]]:
    return _horizontal_rows_owner.horizontal_rows(
        polygons, sample_polygon=_horizontal_polygon_sample,
        cluster_samples=_cluster_horizontal_samples,
    )


def _horizontal_column_indices(
    polygons: list[np.ndarray], size: tuple[int, int],
    settings: AppSettings | None = None,
) -> tuple[list[list[int]], tuple[int, ...]]:
    return _horizontal_rows_owner.horizontal_column_indices(
        polygons, size, settings,
        settings_type=AppSettings, polygon_boxes=polygon_boxes,
        infer_layout=infer_layout_from_boxes, sample_polygon=_horizontal_polygon_sample,
    )


def _horizontal_column_rows(
    polygons: list[np.ndarray], size: tuple[int, int],
    settings: AppSettings | None = None, *,
    fixed_groups: list[list[int]] | None = None,
) -> tuple[list[list[tuple[float, float, float, float]]], list[list[int]]]:
    return _horizontal_rows_owner.horizontal_column_rows(
        polygons, size, settings, fixed_groups=fixed_groups,
        column_indices=_horizontal_column_indices,
        sample_polygon=_horizontal_polygon_sample,
        cluster_samples=_cluster_horizontal_samples,
    )


def horizontal_column_rows(
    polygons: Iterable[np.ndarray], size: tuple[int, int],
    settings: AppSettings | None = None,
) -> list[list[tuple[float, float, float, float]]]:
    """Public read-only N-column row reconstruction for geometry diagnostics."""
    return _horizontal_rows_owner.public_horizontal_column_rows(
        polygons, size, settings, column_rows=_horizontal_column_rows,
    )


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
    return _horizontal_vanishing.fit_horizontal_vanishing_point(
        column_rows, vp_min_rows=HORIZONTAL_VP_MIN_ROWS,
    )


def _horizontal_vp_column_spread_deg(
    column_rows: list[list[tuple[float, float, float, float]]],
    common_vp: tuple[float, float],
) -> float:
    return _horizontal_vanishing.horizontal_vp_column_spread_deg(
        column_rows, common_vp,
        normalize_angle=_normalize_text_angle,
        median_pairs=_weighted_median_pairs,
    )


def estimate_horizontal_perspective_from_polygons(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings | None = None,
) -> PerspectiveEstimate:
    """Build one global projective rectifier from independent 1..N column rows."""
    return _horizontal_vanishing.estimate_horizontal_perspective_from_polygons(
        polygons, size, settings,
        ops=_horizontal_vanishing.HorizontalVanishingOps(
            column_rows=_horizontal_column_rows,
            row_stats=_horizontal_row_stats,
            region_angles=_horizontal_region_angles,
            fit_vp=_fit_horizontal_vanishing_point,
            column_spread=_horizontal_vp_column_spread_deg,
            transform_points=transform_points_homography,
            result_type=PerspectiveEstimate,
            vp_min_rows=HORIZONTAL_VP_MIN_ROWS,
            vp_min_trend_deg=HORIZONTAL_VP_MIN_TREND_DEG,
        ),
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
    return _structural_perspective.estimate_perspective_from_polygons(
        polygons, size, settings,
        ops=_structural_perspective.StructuralPerspectiveOps(
            layout=_layout,
            column_left_samples=_column_left_samples,
            robust_line=_robust_line,
            homography=_homography,
            result_type=PerspectiveEstimate,
        ),
    )


def perspective_from_quad(
    quad: Iterable[float],
    size: tuple[int, int],
) -> PerspectiveEstimate:
    """Manual four-corner correction in original source-image coordinates."""
    return _structural_perspective.perspective_from_quad(
        quad, size, homography=_homography, result_type=PerspectiveEstimate,
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


