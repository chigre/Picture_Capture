from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

from .preprocess.document_unwarping import unwarp_document_image
from .image_utils import normalize_page_rgb
from .layout.detection import (
    LayoutEstimate,
    analysis_ink_mask,
    detect_text_polygons,
    infer_layout_from_boxes,
)
from .models import AppSettings
from .preprocess.orthogonal_dewarp import (
    HORIZONTAL_RULE_MAX_ANGLE_DEG,
    HORIZONTAL_RULE_MAX_RESIDUAL_MIN_PX,
    HORIZONTAL_RULE_MAX_RESIDUAL_WIDTH_RATIO,
    ORTHOGONAL_WARP_MAX_SCALE_DEVIATION,
    PIXEL_ROW_BOTTOM_TAIL_P90_MAX_PX,
    PIXEL_ROW_BOTTOM_TAIL_WORST_MAX_PX,
    PIXEL_ROW_PROFILE_P90_MAX_PX,
    PIXEL_ROW_PROFILE_WORST_MAX_PX,
    OrthogonalWarpEstimate,
    apply_orthogonal_warp_image,
    audit_pixel_row_profiles,
    estimate_orthogonal_warp,
    horizontal_rule_metrics,
    transform_polygons_orthogonal,
)
from .preprocess.geometry import (
    HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG,
    HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG,
    HORIZONTAL_ALIGNMENT_MAX_EDGE_PAIR_DELTA_DEG,
    HORIZONTAL_ALIGNMENT_MAX_TAIL_DEG,
    HORIZONTAL_ALIGNMENT_MIN_IMPROVEMENT,
    HORIZONTAL_VP_COLUMN_SPREAD_MAX_DEG,
    HORIZONTAL_STRENGTH_COARSE_STEP,
    HORIZONTAL_STRENGTH_FINE_STEP,
    HORIZONTAL_STRENGTH_MIN,
    HORIZONTAL_VP_MIN_ROWS,
    HORIZONTAL_VP_MIN_TREND_DEG,
    TEXT_SCALE_ANISOTROPY_P95_MAX,
    TEXT_SCALE_CROSS_GRADIENT_MAX,
    TEXT_SCALE_CROSS_SPAN_MAX,
    TEXT_SCALE_INLINE_GRADIENT_MAX,
    TEXT_SCALE_INLINE_SPAN_MAX,
    apply_homography_image,
    audit_horizontal_alignment,
    audit_homography_distortion,
    audit_text_scale_stability,
    compose_perspective_estimates,
    estimate_horizontal_perspective_from_polygons,
    estimate_perspective_from_polygons,
    optimize_horizontal_perspective_strength,
    perspective_from_quad,
    transform_polygons_homography,
)
from .preprocess.text_line_geometry import (
    SEPARATOR_CURVATURE_SCORE_MIN,
    SEPARATOR_CURVE_SPAN_MIN,
    SEPARATOR_CURVE_WIDTH_RATIO_THRESHOLD,
    SEPARATOR_JUMP_MIN_PX,
    SEPARATOR_JUMP_WIDTH_RATIO_MAX,
    SEPARATOR_TRACK_QUALITY_MIN,
    TextLineGeometryAnalysis,
    analyze_text_line_geometry,
    separator_track_points,
)
from .persistence.project_storage import image_preprocess_output_root
from .preprocess.models import (
    DEFAULT_SAFETY_MARGIN_PX,
    PREPROCESS_FORMAT,
    PREPROCESS_FORMAT_VERSION,
    OutputCanvasInfo,
    PreprocessAnalysis,
)
from .preprocess.constants import (
    AUTO_HOMOGRAPHY_ANISOTROPY_P95_MAX,
    AUTO_HOMOGRAPHY_AREA_SCALE_SPAN_MAX,
    AUTO_HOMOGRAPHY_HORIZONTAL_SCALE_SPAN_MAX,
    AUTO_HOMOGRAPHY_VERTICAL_SCALE_SPAN_MAX,
    DEFAULT_DESKEW_DEAD_ZONE_DEG,
    DEFAULT_MAX_AUTO_DESKEW_DEG,
    ORTHOGONAL_AUTO_GAINS,
    ORTHOGONAL_AUTO_MIN_CONFIDENCE,
    ORTHOGONAL_AUTO_MIN_SCORE_IMPROVEMENT,
    ORTHOGONAL_MAX_AUTO_PASSES,
    ORTHOGONAL_MIN_SAFE_GAIN,
    ORTHOGONAL_SCALE_SAFETY_FRACTION,
    ORTHOGONAL_TAIL_MAX_REGRESSION_PX,
    ORTHOGONAL_TAIL_PROGRESS_RATIO,
    ORTHOGONAL_VERTICAL_MAX_SPAN_MIN_PX,
    ORTHOGONAL_VERTICAL_MAX_SPAN_WIDTH_RATIO,
    POST_PERSPECTIVE_REDETECT_MIN_BOXES,
)
from .preprocess.canvas import (
    _normalize_canvas_alignment,
    output_canvas_info,
)
from .preprocess.persistence import (
    MANUAL_GEOMETRY_FORMAT,
    MANUAL_GEOMETRY_VERSION,
    clear_manual_perspective_quad,
    load_analysis,
    load_manual_perspective_quad,
    manual_geometry_path,
    result_path,
    save_analysis,
    save_manual_perspective_quad,
)
from .preprocess.storage import (
    preview_output_root,
    processed_output_root,
    promote_processed_pages,
)
from .preprocess.reporting import (
    _export_diagnostic_json_impl,
    export_summary_csv,
    result_summary,
)

from .preprocess import content_bounds as _content_bounds
from .preprocess.content_bounds import _smooth_1d
from .preprocess.deskew import (
    _normalize_half_turn,
    _weighted_median,
    estimate_skew_from_polygons,
    _paper_fill,
    deskew_image,
    _rotate_point_same_canvas,
    _rotate_polygons_same_canvas,
    _rotated_text_box,
    _polygon_boxes,
    _expand_box_px,
    _rotate_box_same_canvas,
)


from .preprocess import orthogonal_policy as _orthogonal_policy
from .preprocess import replay as _geometry_replay
from .preprocess.orthogonal_policy import (
    _absolute_horizontal_quality,
    _separator_vertical_span,
    _orthogonal_safe_gain_cap,
    _orthogonal_step_payload,
    _orthogonal_estimate_from_step,
)



from .preprocess import geometry_stages as _geometry_stages
from .preprocess import perspective_stages as _perspective_stages
from .preprocess import pixel_row_policy as _pixel_row_policy
from .preprocess import projective_selection as _projective_selection
from .preprocess import finalization as _finalization
from .preprocess import source_evidence as _source_evidence
from .preprocess import rendering as _rendering
from .preprocess.rendering import PREVIEW_YELLOW, PREVIEW_OUTLINE


def _projection_content_box(image: Image.Image, settings: AppSettings) -> tuple[int, int, int, int]:
    return _content_bounds._projection_content_box(
        image, settings, ink_mask_builder=analysis_ink_mask,
    )


def _layout_content_box_from_polygons(
    polygons: Iterable[np.ndarray], width: int, height: int, settings: AppSettings,
) -> tuple[tuple[int, int, int, int], LayoutEstimate]:
    return _content_bounds._layout_content_box_from_polygons(
        polygons, width, height, settings, layout_estimator=infer_layout_from_boxes,
    )


def _projection_skew_fallback(
    image: Image.Image, settings: AppSettings, *, writing_mode: str,
) -> float:
    return _content_bounds._projection_skew_fallback(
        image, settings, writing_mode=writing_mode, ink_mask_builder=analysis_ink_mask,
    )


def _choose_orthogonal_candidate(
    polygons: Iterable[np.ndarray], estimate: OrthogonalWarpEstimate,
    size: tuple[int, int], settings: AppSettings, *, max_gain: float | None = None,
) -> tuple[float, list[np.ndarray], str, float, float]:
    return _orthogonal_policy._choose_orthogonal_candidate(
        polygons, estimate, size, settings, max_gain=max_gain,
        horizontal_auditor=audit_horizontal_alignment,
        scale_auditor=audit_text_scale_stability,
        polygon_transformer=transform_polygons_orthogonal,
        quality_evaluator=_absolute_horizontal_quality,
    )


def _normalize_geometry_mode(value: str | None) -> str:
    mode = str(value or "auto").strip().lower()
    aliases = {
        "auto": "auto",
        "deskew": "deskew",
        "light": "deskew",
        "perspective": "perspective",
        "dewarp": "uvdoc",
        "mesh": "uvdoc",
        "uvdoc": "uvdoc",
        "paddle_unwarp": "uvdoc",
    }
    return aliases.get(mode, "auto")


def geometry_corrected_image(
    image: Image.Image, analysis: PreprocessAnalysis,
) -> Image.Image:
    """Apply the saved geometric correction without cropping.

    Export/preview reuse the exact analysis transform; they do not run Paddle
    again, so a reviewed result remains deterministic.
    """
    return _geometry_replay.geometry_corrected_image(
        image, analysis, deskewer=deskew_image,
        homography_warper=apply_homography_image,
        document_unwarper=unwarp_document_image,
        orthogonal_warper=apply_orthogonal_warp_image,
        step_decoder=_orthogonal_estimate_from_step,
    )


def analyze_preprocess_page(
    image: Image.Image,
    settings: AppSettings,
    *,
    safety_margin_px: int = DEFAULT_SAFETY_MARGIN_PX,
    auto_deskew: bool = True,
    geometry_mode: str = "auto",
    manual_perspective_quad: tuple[float, ...] | None = None,
) -> PreprocessAnalysis:
    source = normalize_page_rgb(image)
    width, height = source.size
    requested_geometry_mode = _normalize_geometry_mode(geometry_mode)
    manual_quad = (
        tuple(float(v) for v in manual_perspective_quad)
        if manual_perspective_quad is not None and len(manual_perspective_quad) == 8
        else None
    )
    evidence = _source_evidence.collect_source_geometry_evidence(
        source, settings,
        requested_geometry_mode=requested_geometry_mode,
        auto_deskew=auto_deskew,
        text_detector=detect_text_polygons,
        line_analyzer=analyze_text_line_geometry,
        line_geometry_factory=TextLineGeometryAnalysis,
        skew_estimator=estimate_skew_from_polygons,
        projection_estimator=_projection_skew_fallback,
        rule_metrics=horizontal_rule_metrics,
        separator_curve_width_ratio=SEPARATOR_CURVE_WIDTH_RATIO_THRESHOLD,
        header_residual_min_px=HORIZONTAL_RULE_MAX_RESIDUAL_MIN_PX,
        header_residual_width_ratio=HORIZONTAL_RULE_MAX_RESIDUAL_WIDTH_RATIO,
        max_auto_deskew_deg=DEFAULT_MAX_AUTO_DESKEW_DEG,
        deskew_dead_zone_deg=DEFAULT_DESKEW_DEAD_ZONE_DEG,
    )
    warnings = evidence.warnings
    polygons = evidence.polygons
    method_parts = evidence.method_parts
    line_geometry = evidence.line_geometry
    ocr_correction = evidence.ocr_correction
    angle_samples = evidence.angle_samples
    angle_mad = evidence.angle_mad
    correction = evidence.correction
    deskew_anchor_source = evidence.deskew_anchor_source
    source_header_rule_point_count = evidence.source_header_rule_point_count
    source_header_rule_angle_deg = evidence.source_header_rule_angle_deg
    source_header_rule_residual_px = evidence.source_header_rule_residual_px
    applied = evidence.applied

    working = deskew_image(source, applied)
    working_polygons = (
        _rotate_polygons_same_canvas(polygons, width, height, applied)
        if polygons else []
    )
    actual_geometry_mode = "deskew"
    geometry_strength = 0.0
    perspective_state = _perspective_stages.PerspectiveState()

    manual_stage = _perspective_stages.apply_manual_perspective(
        working, working_polygons, manual_quad,
        width, height, applied, settings, perspective_state,
        geometry_strength, method_parts, warnings,
        point_rotator=_rotate_point_same_canvas,
        manual_estimator=perspective_from_quad,
        polygon_transformer=transform_polygons_homography,
        distortion_auditor=audit_homography_distortion,
        text_scale_auditor=audit_text_scale_stability,
        row_auditor=audit_horizontal_alignment,
        homography_warper=apply_homography_image,
    )
    working = manual_stage.image
    working_polygons = manual_stage.polygons
    actual_geometry_mode = manual_stage.geometry_mode
    geometry_strength = manual_stage.geometry_strength

    # Keep explicit neural unwarp separate from the automatic geometry path.
    uvdoc_stage = _geometry_stages.apply_explicit_uvdoc(
        working, working_polygons, actual_geometry_mode,
        requested_geometry_mode=requested_geometry_mode,
        document_unwarper=unwarp_document_image,
        warnings=warnings, method_parts=method_parts,
    )
    working = uvdoc_stage.image
    working_polygons = uvdoc_stage.polygons
    actual_geometry_mode = uvdoc_stage.geometry_mode
    advanced_redetected = False

    # Advanced projective geometry is staged after the global small-angle
    # correction:
    #   A) structural keystone correction is decided on its own evidence and
    #      distortion safety; it is NOT required to improve row horizontality.
    #   B) any residual top-to-bottom row-angle trend is then corrected by a
    #      horizontal-VP homography whose strength is optimized in [0, 1].
    # This avoids the v12 failure mode where a useful 0004-style structural
    # correction was rejected by the horizontal gate, while a full-strength VP
    # correction over-shot the near-zero row trend on 0002/0004/0011.
    if (
        manual_quad is None
        and working_polygons
        and requested_geometry_mode in {"auto", "perspective"}
    ):
        selection = _projective_selection.select_projective_candidate(
            working_polygons, working.size, settings,
            source_width=width, line_geometry=line_geometry,
            requested_geometry_mode=requested_geometry_mode,
            polygon_transformer=transform_polygons_homography,
            jacobian_auditor=audit_homography_distortion,
            scale_auditor=audit_text_scale_stability,
            row_auditor=audit_horizontal_alignment,
            structural_estimator=estimate_perspective_from_polygons,
            horizontal_estimator=estimate_horizontal_perspective_from_polygons,
            strength_optimizer=optimize_horizontal_perspective_strength,
            perspective_composer=compose_perspective_estimates,
            horizontal_scale_span_max=AUTO_HOMOGRAPHY_HORIZONTAL_SCALE_SPAN_MAX,
            vertical_scale_span_max=AUTO_HOMOGRAPHY_VERTICAL_SCALE_SPAN_MAX,
            area_scale_span_max=AUTO_HOMOGRAPHY_AREA_SCALE_SPAN_MAX,
            anisotropy_p95_max=AUTO_HOMOGRAPHY_ANISOTROPY_P95_MAX,
            horizontal_min_rows=HORIZONTAL_VP_MIN_ROWS,
            horizontal_min_trend_deg=HORIZONTAL_VP_MIN_TREND_DEG,
            horizontal_column_spread_max_deg=HORIZONTAL_VP_COLUMN_SPREAD_MAX_DEG,
        )
        projective_stage = _perspective_stages.apply_selected_perspective(
            selection, working, working_polygons,
            actual_geometry_mode, geometry_strength, perspective_state,
            requested_geometry_mode=requested_geometry_mode,
            line_geometry=line_geometry,
            method_parts=method_parts, warnings=warnings,
            homography_warper=apply_homography_image,
            horizontal_scale_span_max=AUTO_HOMOGRAPHY_HORIZONTAL_SCALE_SPAN_MAX,
            vertical_scale_span_max=AUTO_HOMOGRAPHY_VERTICAL_SCALE_SPAN_MAX,
            area_scale_span_max=AUTO_HOMOGRAPHY_AREA_SCALE_SPAN_MAX,
            anisotropy_p95_max=AUTO_HOMOGRAPHY_ANISOTROPY_P95_MAX,
        )
        working = projective_stage.image
        working_polygons = projective_stage.polygons
        actual_geometry_mode = projective_stage.geometry_mode
        geometry_strength = projective_stage.geometry_strength

    perspective_matrix = perspective_state.perspective_matrix
    perspective_source_quad = perspective_state.perspective_source_quad
    perspective_target_quad = perspective_state.perspective_target_quad
    perspective_classification = perspective_state.perspective_classification
    perspective_candidate_source = perspective_state.perspective_candidate_source
    perspective_horizontal_vanishing_x = perspective_state.perspective_horizontal_vanishing_x
    perspective_horizontal_vanishing_y = perspective_state.perspective_horizontal_vanishing_y
    perspective_horizontal_row_count = perspective_state.perspective_horizontal_row_count
    perspective_horizontal_column_count = perspective_state.perspective_horizontal_column_count
    perspective_horizontal_vp_column_spread_deg = perspective_state.perspective_horizontal_vp_column_spread_deg
    perspective_horizontal_strength = perspective_state.perspective_horizontal_strength
    perspective_structural_applied = perspective_state.perspective_structural_applied
    perspective_structural_safe = perspective_state.perspective_structural_safe
    perspective_row_valid_column_count = perspective_state.perspective_row_valid_column_count
    perspective_row_valid_column_indices = perspective_state.perspective_row_valid_column_indices
    perspective_row_column_row_counts = perspective_state.perspective_row_column_row_counts
    perspective_row_after_worst_region_deg = perspective_state.perspective_row_after_worst_region_deg
    perspective_row_after_worst_column_metric_deg = perspective_state.perspective_row_after_worst_column_metric_deg
    perspective_row_after_worst_column_index = perspective_state.perspective_row_after_worst_column_index
    perspective_row_before_column_top_angles_deg = perspective_state.perspective_row_before_column_top_angles_deg
    perspective_row_after_column_top_angles_deg = perspective_state.perspective_row_after_column_top_angles_deg
    perspective_row_before_column_middle_angles_deg = perspective_state.perspective_row_before_column_middle_angles_deg
    perspective_row_after_column_middle_angles_deg = perspective_state.perspective_row_after_column_middle_angles_deg
    perspective_row_before_column_bottom_angles_deg = perspective_state.perspective_row_before_column_bottom_angles_deg
    perspective_row_after_column_bottom_angles_deg = perspective_state.perspective_row_after_column_bottom_angles_deg
    perspective_row_before_column_trends_deg = perspective_state.perspective_row_before_column_trends_deg
    perspective_row_after_column_trends_deg = perspective_state.perspective_row_after_column_trends_deg
    perspective_row_before_top_angle_deg = perspective_state.perspective_row_before_top_angle_deg
    perspective_row_after_top_angle_deg = perspective_state.perspective_row_after_top_angle_deg
    perspective_row_before_bottom_angle_deg = perspective_state.perspective_row_before_bottom_angle_deg
    perspective_row_after_bottom_angle_deg = perspective_state.perspective_row_after_bottom_angle_deg
    perspective_row_before_trend_deg = perspective_state.perspective_row_before_trend_deg
    perspective_row_after_trend_deg = perspective_state.perspective_row_after_trend_deg
    perspective_row_before_metric_deg = perspective_state.perspective_row_before_metric_deg
    perspective_row_after_metric_deg = perspective_state.perspective_row_after_metric_deg
    perspective_row_improvement_ratio = perspective_state.perspective_row_improvement_ratio
    perspective_row_alignment_verdict = perspective_state.perspective_row_alignment_verdict
    perspective_candidate_strength_px = perspective_state.perspective_candidate_strength_px
    perspective_left_drift_px = perspective_state.perspective_left_drift_px
    perspective_right_drift_px = perspective_state.perspective_right_drift_px
    perspective_common_drift_px = perspective_state.perspective_common_drift_px
    perspective_width_delta_px = perspective_state.perspective_width_delta_px
    perspective_width_change_ratio = perspective_state.perspective_width_change_ratio
    perspective_scale_top = perspective_state.perspective_scale_top
    perspective_scale_bottom = perspective_state.perspective_scale_bottom
    perspective_scale_delta_ratio = perspective_state.perspective_scale_delta_ratio
    perspective_jacobian_samples = perspective_state.perspective_jacobian_samples
    perspective_jacobian_horizontal_scale_span_ratio = perspective_state.perspective_jacobian_horizontal_scale_span_ratio
    perspective_jacobian_vertical_scale_span_ratio = perspective_state.perspective_jacobian_vertical_scale_span_ratio
    perspective_jacobian_area_scale_span_ratio = perspective_state.perspective_jacobian_area_scale_span_ratio
    perspective_jacobian_anisotropy_p95_ratio = perspective_state.perspective_jacobian_anisotropy_p95_ratio
    perspective_jacobian_min_determinant = perspective_state.perspective_jacobian_min_determinant
    perspective_text_scale_samples = perspective_state.perspective_text_scale_samples
    perspective_text_scale_inline_ratio_p05 = perspective_state.perspective_text_scale_inline_ratio_p05
    perspective_text_scale_inline_ratio_median = perspective_state.perspective_text_scale_inline_ratio_median
    perspective_text_scale_inline_ratio_p95 = perspective_state.perspective_text_scale_inline_ratio_p95
    perspective_text_scale_cross_ratio_p05 = perspective_state.perspective_text_scale_cross_ratio_p05
    perspective_text_scale_cross_ratio_median = perspective_state.perspective_text_scale_cross_ratio_median
    perspective_text_scale_cross_ratio_p95 = perspective_state.perspective_text_scale_cross_ratio_p95
    perspective_text_scale_inline_ratio_span_ratio = perspective_state.perspective_text_scale_inline_ratio_span_ratio
    perspective_text_scale_cross_ratio_span_ratio = perspective_state.perspective_text_scale_cross_ratio_span_ratio
    perspective_text_scale_inline_ratio_gradient_ratio = perspective_state.perspective_text_scale_inline_ratio_gradient_ratio
    perspective_text_scale_cross_ratio_gradient_ratio = perspective_state.perspective_text_scale_cross_ratio_gradient_ratio
    perspective_text_scale_anisotropy_p95_ratio = perspective_state.perspective_text_scale_anisotropy_p95_ratio
    perspective_text_scale_before_inline_gradient_ratio = perspective_state.perspective_text_scale_before_inline_gradient_ratio
    perspective_text_scale_after_inline_gradient_ratio = perspective_state.perspective_text_scale_after_inline_gradient_ratio
    perspective_text_scale_before_cross_gradient_ratio = perspective_state.perspective_text_scale_before_cross_gradient_ratio
    perspective_text_scale_after_cross_gradient_ratio = perspective_state.perspective_text_scale_after_cross_gradient_ratio
    perspective_text_scale_before_score = perspective_state.perspective_text_scale_before_score
    perspective_text_scale_after_score = perspective_state.perspective_text_scale_after_score
    perspective_text_scale_verdict = perspective_state.perspective_text_scale_verdict
    perspective_auto_safe = perspective_state.perspective_auto_safe

    # Re-detect on the actual perspective-corrected pixels before the
    # orthogonal normalizer; retain transformed boxes on failure.
    post_perspective = _geometry_stages.redetect_after_perspective(
        working, working_polygons, settings,
        requested_geometry_mode=requested_geometry_mode,
        actual_geometry_mode=actual_geometry_mode,
        text_detector=detect_text_polygons,
        min_boxes=POST_PERSPECTIVE_REDETECT_MIN_BOXES,
        warnings=warnings, method_parts=method_parts,
    )
    working_polygons = post_perspective.polygons
    advanced_redetected = post_perspective.redetected

    # Final deterministic orthogonal normalizer.
    #
    # Rotation/homography solve global geometry; UVDoc is a generic neural
    # fallback. Neither guarantees that every dictionary row is horizontal and
    # every physical column separator is vertical. Use the current post-transform
    # OCR geometry itself to build a small row-wise mesh, then validate the
    # actually transformed pixels by a fresh detection pass. This makes the
    # acceptance criterion part of the correction loop instead of a warning only.
    orthogonal_applied = False
    orthogonal_passes = 0
    orthogonal_steps: list[dict[str, object]] = []
    orthogonal_row_count = 0
    orthogonal_valid_column_count = 0
    orthogonal_separator_point_count = 0
    orthogonal_row_gain = 0.0
    orthogonal_reference_x = 0.0
    orthogonal_y_knots: tuple[float, ...] = ()
    orthogonal_angle_knots_deg: tuple[float, ...] = ()
    orthogonal_x_knots: tuple[float, ...] = ()
    orthogonal_row_grid_rows = 0
    orthogonal_row_grid_cols = 0
    orthogonal_row_angle_grid_deg: tuple[float, ...] = ()
    orthogonal_row_displacement_grid_px: tuple[float, ...] = ()
    orthogonal_separator_y_knots: tuple[float, ...] = ()
    orthogonal_separator_shift_knots_px: tuple[float, ...] = ()
    orthogonal_horizontal_rule_point_count = 0
    orthogonal_horizontal_rule_y = 0.0
    orthogonal_before_horizontal_rule_angle_deg = 0.0
    orthogonal_after_horizontal_rule_angle_deg = 0.0
    orthogonal_before_horizontal_rule_residual_px = 0.0
    orthogonal_after_horizontal_rule_residual_px = 0.0
    orthogonal_horizontal_rule_verdict = "insufficient"
    orthogonal_pixel_angle_sample_count = 0
    orthogonal_pixel_angle_used_count = 0
    orthogonal_pixel_angle_confidence = 0.0
    orthogonal_pixel_row_sample_count = 0
    orthogonal_before_pixel_row_p90_px = 0.0
    orthogonal_after_pixel_row_p90_px = 0.0
    orthogonal_before_pixel_row_worst_px = 0.0
    orthogonal_after_pixel_row_worst_px = 0.0
    orthogonal_pixel_row_verdict = "insufficient"
    orthogonal_bottom_tail_sample_count = 0
    orthogonal_before_bottom_tail_p90_px = 0.0
    orthogonal_after_bottom_tail_p90_px = 0.0
    orthogonal_before_bottom_tail_worst_px = 0.0
    orthogonal_after_bottom_tail_worst_px = 0.0
    orthogonal_bottom_tail_verdict = "insufficient"
    orthogonal_safe_gain_cap = 0.0
    orthogonal_initial_pixel_row_p90_px = 0.0
    orthogonal_initial_pixel_row_worst_px = 0.0
    orthogonal_initial_pixel_row_available = False
    orthogonal_initial_bottom_tail_p90_px = 0.0
    orthogonal_initial_bottom_tail_worst_px = 0.0
    orthogonal_initial_bottom_tail_available = False
    orthogonal_confidence = 0.0
    orthogonal_column_spread_deg = 0.0
    orthogonal_max_row_angle_deg = 0.0
    orthogonal_row_angle_span_deg = 0.0
    orthogonal_max_horizontal_shift_px = 0.0
    orthogonal_max_vertical_shift_px = 0.0
    orthogonal_max_scale_deviation = 0.0
    orthogonal_before_quality_score = 0.0
    orthogonal_after_quality_score = 0.0
    orthogonal_before_separator_span_px = 0.0
    orthogonal_after_separator_span_px = 0.0
    orthogonal_vertical_verdict = "insufficient"
    orthogonal_alignment_verdict = "insufficient"

    if (
        requested_geometry_mode == "auto"
        and working_polygons
        and not str(settings.layout_writing_mode or "horizontal-tb").startswith(
            "vertical"
        )
    ):
        for pass_index in range(ORTHOGONAL_MAX_AUTO_PASSES):
            try:
                estimate = estimate_orthogonal_warp(
                    working,
                    working_polygons,
                    settings,
                )
            except Exception as exc:
                warnings.append(f"正交网格几何估计不可用：{exc}")
                break

            orthogonal_row_count = int(estimate.row_count)
            orthogonal_valid_column_count = int(
                estimate.valid_column_count
            )
            orthogonal_separator_point_count = int(
                estimate.separator_point_count
            )
            orthogonal_horizontal_rule_point_count = int(
                estimate.horizontal_rule_point_count
            )
            orthogonal_horizontal_rule_y = float(
                estimate.horizontal_rule_y
            )
            orthogonal_before_horizontal_rule_angle_deg = float(
                estimate.horizontal_rule_angle_deg
            )
            orthogonal_before_horizontal_rule_residual_px = float(
                estimate.horizontal_rule_residual_span_px
            )
            orthogonal_pixel_angle_sample_count = int(
                estimate.pixel_angle_sample_count
            )
            orthogonal_pixel_angle_used_count = int(
                estimate.pixel_angle_used_count
            )
            orthogonal_pixel_angle_confidence = float(
                estimate.pixel_angle_confidence
            )
            orthogonal_confidence = float(estimate.confidence)
            orthogonal_column_spread_deg = float(
                estimate.column_spread_deg
            )
            orthogonal_max_row_angle_deg = float(
                estimate.max_row_angle_deg
            )
            orthogonal_row_angle_span_deg = float(
                estimate.row_angle_span_deg
            )
            orthogonal_max_horizontal_shift_px = float(
                estimate.max_horizontal_shift_px
            )
            orthogonal_max_vertical_shift_px = float(
                estimate.max_vertical_shift_px
            )
            orthogonal_max_scale_deviation = float(
                estimate.max_scale_deviation
            )

            safe_gain_cap = _orthogonal_safe_gain_cap(estimate)
            orthogonal_safe_gain_cap = float(safe_gain_cap)
            if (
                not estimate.active
                or estimate.confidence < ORTHOGONAL_AUTO_MIN_CONFIDENCE
                or safe_gain_cap < ORTHOGONAL_MIN_SAFE_GAIN
            ):
                if (
                    pass_index == 0
                    and estimate.active
                    and estimate.confidence >= ORTHOGONAL_AUTO_MIN_CONFIDENCE
                    and safe_gain_cap < ORTHOGONAL_MIN_SAFE_GAIN
                ):
                    warnings.append(
                        "残余几何需要的网格强度超过安全尺度预算，"
                        "即使降强度也不足以安全执行，已保留前一步结果。"
                    )
                break
            if safe_gain_cap < 0.999:
                method_parts.append("orthogonal_gain_limited")

            pixel_driven = bool(
                estimate.pixel_angle_used_count
                >= max(4, estimate.valid_column_count * 3)
                and estimate.pixel_angle_confidence >= 0.06
            )
            if pixel_driven:
                # Pixel projection estimates a physical correction angle, so
                # unit gain has a direct meaning. OCR polygons remain a safety
                # audit, not the optimizer for this branch.
                row_gain = min(1.0, float(safe_gain_cap))
                predicted_polygons = transform_polygons_orthogonal(
                    working_polygons,
                    estimate,
                    row_gain=row_gain,
                    separator_gain=1.0,
                )
                predicted_scale = audit_text_scale_stability(
                    working_polygons,
                    predicted_polygons,
                    working.size,
                    writing_mode=settings.layout_writing_mode,
                )
                predicted_audit = audit_horizontal_alignment(
                    working_polygons,
                    predicted_polygons,
                    size=working.size,
                    settings=settings,
                )
                baseline_predicted_audit = audit_horizontal_alignment(
                    working_polygons,
                    working_polygons,
                    size=working.size,
                    settings=settings,
                )
                _before_predicted_verdict, before_score = (
                    _absolute_horizontal_quality(baseline_predicted_audit)
                )
                predicted_verdict, predicted_score = (
                    _absolute_horizontal_quality(predicted_audit)
                )
                predicted_improved = predicted_scale.verdict != "worse"
                method_parts.append("pixel_angle_field")
            else:
                (
                    row_gain,
                    predicted_polygons,
                    predicted_verdict,
                    before_score,
                    predicted_score,
                ) = _choose_orthogonal_candidate(
                    working_polygons,
                    estimate,
                    working.size,
                    settings,
                    max_gain=float(safe_gain_cap),
                )
                predicted_improved = bool(
                    predicted_verdict == "passed"
                    or (
                        predicted_verdict != "insufficient"
                        and before_score > 1e-6
                        and predicted_score
                        <= before_score
                        * (1.0 - ORTHOGONAL_AUTO_MIN_SCORE_IMPROVEMENT)
                    )
                )
            orthogonal_before_quality_score = float(before_score)

            if not predicted_improved or row_gain <= 0.0:
                if pass_index == 0:
                    warnings.append(
                        "检测到残余行/列几何，但正交网格候选未达到"
                        "自动改善阈值，已保留前一步结果。"
                    )
                break

            try:
                candidate_image = apply_orthogonal_warp_image(
                    working,
                    estimate,
                    row_gain=row_gain,
                    separator_gain=1.0,
                )
                candidate_polygons = detect_text_polygons(
                    candidate_image,
                    settings,
                )
            except Exception as exc:
                warnings.append(
                    f"正交网格展平后复检失败，已保留前一步结果：{exc}"
                )
                break
            if len(candidate_polygons) < 8:
                warnings.append(
                    "正交网格展平后有效文本框不足，已保留前一步结果。"
                )
                break

            baseline_audit = audit_horizontal_alignment(
                working_polygons,
                working_polygons,
                size=working.size,
                settings=settings,
            )
            candidate_audit = audit_horizontal_alignment(
                candidate_polygons,
                candidate_polygons,
                size=candidate_image.size,
                settings=settings,
            )
            baseline_pixel_rows = audit_pixel_row_profiles(
                working,
                working_polygons,
                settings,
            )
            if (
                not orthogonal_initial_pixel_row_available
                and baseline_pixel_rows.sample_count >= 8
                and baseline_pixel_rows.valid_column_count >= 1
            ):
                orthogonal_initial_pixel_row_p90_px = float(
                    baseline_pixel_rows.p90_shift_px
                )
                orthogonal_initial_pixel_row_worst_px = float(
                    baseline_pixel_rows.worst_shift_px
                )
                orthogonal_initial_pixel_row_available = True
            if (
                not orthogonal_initial_bottom_tail_available
                and baseline_pixel_rows.bottom_tail_sample_count >= 2
                and baseline_pixel_rows.bottom_tail_valid_column_count >= 1
            ):
                orthogonal_initial_bottom_tail_p90_px = float(
                    baseline_pixel_rows.bottom_tail_p90_shift_px
                )
                orthogonal_initial_bottom_tail_worst_px = float(
                    baseline_pixel_rows.bottom_tail_worst_shift_px
                )
                orthogonal_initial_bottom_tail_available = True
            candidate_pixel_rows = audit_pixel_row_profiles(
                candidate_image,
                candidate_polygons,
                settings,
            )
            orthogonal_pixel_row_sample_count = int(
                candidate_pixel_rows.sample_count
            )
            orthogonal_before_pixel_row_p90_px = float(
                baseline_pixel_rows.p90_shift_px
            )
            orthogonal_after_pixel_row_p90_px = float(
                candidate_pixel_rows.p90_shift_px
            )
            orthogonal_before_pixel_row_worst_px = float(
                baseline_pixel_rows.worst_shift_px
            )
            orthogonal_after_pixel_row_worst_px = float(
                candidate_pixel_rows.worst_shift_px
            )
            orthogonal_bottom_tail_sample_count = int(
                candidate_pixel_rows.bottom_tail_sample_count
            )
            orthogonal_before_bottom_tail_p90_px = float(
                baseline_pixel_rows.bottom_tail_p90_shift_px
            )
            orthogonal_after_bottom_tail_p90_px = float(
                candidate_pixel_rows.bottom_tail_p90_shift_px
            )
            orthogonal_before_bottom_tail_worst_px = float(
                baseline_pixel_rows.bottom_tail_worst_shift_px
            )
            orthogonal_after_bottom_tail_worst_px = float(
                candidate_pixel_rows.bottom_tail_worst_shift_px
            )
            baseline_verdict, baseline_score = _absolute_horizontal_quality(
                baseline_audit
            )
            actual_verdict, actual_score = _absolute_horizontal_quality(
                candidate_audit
            )
            horizontal_improved = bool(
                actual_verdict == "passed"
                or (
                    actual_verdict != "insufficient"
                    and baseline_verdict != "insufficient"
                    and baseline_score > 1e-6
                    and actual_score
                    <= baseline_score
                    * (1.0 - ORTHOGONAL_AUTO_MIN_SCORE_IMPROVEMENT)
                )
            )
            tail_safe = bool(
                float(
                    getattr(
                        candidate_audit,
                        "after_worst_tail_p90_abs_deg",
                        0.0,
                    )
                )
                <= HORIZONTAL_ALIGNMENT_MAX_TAIL_DEG
            )
            pixel_assessment = _pixel_row_policy.assess_candidate_pixels(
                candidate_pixel_rows, baseline_pixel_rows,
                row_p90_max_px=PIXEL_ROW_PROFILE_P90_MAX_PX,
                row_worst_max_px=PIXEL_ROW_PROFILE_WORST_MAX_PX,
                tail_p90_max_px=PIXEL_ROW_BOTTOM_TAIL_P90_MAX_PX,
                tail_worst_max_px=PIXEL_ROW_BOTTOM_TAIL_WORST_MAX_PX,
                tail_progress_ratio=ORTHOGONAL_TAIL_PROGRESS_RATIO,
                tail_max_regression_px=ORTHOGONAL_TAIL_MAX_REGRESSION_PX,
            )
            pixel_row_available = pixel_assessment.row_available
            pixel_row_safe = pixel_assessment.row_safe
            pixel_row_improved = pixel_assessment.row_improved
            pixel_tail_available = pixel_assessment.tail_available
            pixel_tail_retainable = pixel_assessment.tail_retainable
            orthogonal_pixel_row_verdict = pixel_assessment.row_verdict
            orthogonal_bottom_tail_verdict = pixel_assessment.tail_verdict

            vertical_required = bool(estimate.separator_point_count >= 7)
            vertical_safe = True
            if vertical_required:
                before_separator = separator_track_points(
                    working,
                    working_polygons,
                    settings,
                )
                after_separator = separator_track_points(
                    candidate_image,
                    candidate_polygons,
                    settings,
                )
                (
                    before_separator_count,
                    before_separator_span,
                ) = _separator_vertical_span(before_separator)
                (
                    after_separator_count,
                    after_separator_span,
                ) = _separator_vertical_span(after_separator)
                orthogonal_before_separator_span_px = float(
                    before_separator_span
                )
                orthogonal_after_separator_span_px = float(
                    after_separator_span
                )
                vertical_limit = max(
                    ORTHOGONAL_VERTICAL_MAX_SPAN_MIN_PX,
                    working.width
                    * ORTHOGONAL_VERTICAL_MAX_SPAN_WIDTH_RATIO,
                )
                vertical_safe = bool(
                    before_separator_count >= 7
                    and after_separator_count >= 7
                    and after_separator_span <= vertical_limit
                )
                orthogonal_vertical_verdict = (
                    "passed" if vertical_safe else "failed"
                )
            else:
                orthogonal_vertical_verdict = "not_required"

            header_rule_required = bool(
                estimate.horizontal_rule_point_count >= 7
            )
            header_rule_safe = True
            if header_rule_required:
                (
                    after_rule_count,
                    after_rule_angle,
                    after_rule_residual,
                    _after_rule_y,
                ) = horizontal_rule_metrics(
                    candidate_image,
                    candidate_polygons,
                    settings,
                )
                orthogonal_after_horizontal_rule_angle_deg = float(
                    after_rule_angle
                )
                orthogonal_after_horizontal_rule_residual_px = float(
                    after_rule_residual
                )
                header_residual_limit = max(
                    HORIZONTAL_RULE_MAX_RESIDUAL_MIN_PX,
                    candidate_image.width
                    * HORIZONTAL_RULE_MAX_RESIDUAL_WIDTH_RATIO,
                )
                header_rule_safe = bool(
                    after_rule_count >= 7
                    and abs(float(after_rule_angle))
                    <= HORIZONTAL_RULE_MAX_ANGLE_DEG
                    and float(after_rule_residual)
                    <= header_residual_limit
                )
                orthogonal_horizontal_rule_verdict = (
                    "passed" if header_rule_safe else "failed"
                )
            else:
                orthogonal_horizontal_rule_verdict = "not_required"

            body_geometry_safe = bool(
                (
                    pixel_driven
                    and pixel_row_available
                    and (pixel_row_safe or pixel_row_improved)
                    and pixel_tail_retainable
                )
                or (
                    (not pixel_driven or not pixel_row_available)
                    and horizontal_improved
                    and tail_safe
                )
            )
            actual_improved = bool(
                body_geometry_safe
                and vertical_safe
                and header_rule_safe
            )
            if not actual_improved:
                if (
                    pixel_driven
                    and pixel_tail_available
                    and not pixel_tail_retainable
                ):
                    reason = (
                        "正文页尾像素行验收未通过"
                        f"（P90 {candidate_pixel_rows.bottom_tail_p90_shift_px:.1f}px，"
                        f"最差 {candidate_pixel_rows.bottom_tail_worst_shift_px:.1f}px）"
                    )
                elif (
                    pixel_driven
                    and pixel_row_available
                    and not (pixel_row_safe or pixel_row_improved)
                ):
                    reason = (
                        "正文像素行曲率验收未通过"
                        f"（P90 {candidate_pixel_rows.p90_shift_px:.1f}px，"
                        f"最差 {candidate_pixel_rows.worst_shift_px:.1f}px）"
                    )
                elif not tail_safe:
                    reason = (
                        "正文页首/页尾局部验收未通过"
                        f"（最差尾部P90 "
                        f"{float(getattr(candidate_audit, 'after_worst_tail_p90_abs_deg', 0.0)):.2f}°）"
                    )
                elif not horizontal_improved:
                    reason = "正文水平验收未通过"
                elif not header_rule_safe:
                    reason = "页眉横线验收未通过"
                else:
                    reason = "实体竖线验收未通过"
                warnings.append(
                    f"正交网格候选{reason}，"
                    f"正文水平质量分 {baseline_score:.2f}→{actual_score:.2f}"
                    + (
                        "，像素行位移P90 "
                        f"{baseline_pixel_rows.p90_shift_px:.1f}px→"
                        f"{candidate_pixel_rows.p90_shift_px:.1f}px"
                        if pixel_row_available else ""
                    )
                    + (
                        "，页尾像素行P90 "
                        f"{baseline_pixel_rows.bottom_tail_p90_shift_px:.1f}px→"
                        f"{candidate_pixel_rows.bottom_tail_p90_shift_px:.1f}px"
                        if pixel_tail_available else ""
                    )
                    + (
                        "，页眉横线 "
                        f"{orthogonal_before_horizontal_rule_angle_deg:+.2f}°→"
                        f"{orthogonal_after_horizontal_rule_angle_deg:+.2f}°"
                        if header_rule_required else ""
                    )
                    + (
                        "，竖线X跨度 "
                        f"{orthogonal_before_separator_span_px:.1f}px→"
                        f"{orthogonal_after_separator_span_px:.1f}px"
                        if vertical_required else ""
                    )
                    + "，已回退。"
                )
                break

            working = candidate_image
            working_polygons = [
                np.asarray(poly, dtype=float)
                for poly in candidate_polygons
            ]
            orthogonal_applied = True
            orthogonal_passes += 1
            orthogonal_steps.append(
                _orthogonal_step_payload(estimate, float(row_gain))
            )
            orthogonal_row_gain = float(row_gain)
            orthogonal_reference_x = float(estimate.reference_x)
            orthogonal_y_knots = tuple(estimate.y_knots)
            orthogonal_angle_knots_deg = tuple(estimate.angle_knots_deg)
            orthogonal_x_knots = tuple(estimate.x_knots)
            orthogonal_row_grid_rows = int(estimate.row_grid_rows)
            orthogonal_row_grid_cols = int(estimate.row_grid_cols)
            orthogonal_row_angle_grid_deg = tuple(
                estimate.row_angle_grid_deg
            )
            orthogonal_row_displacement_grid_px = tuple(
                estimate.row_displacement_grid_px
            )
            orthogonal_separator_y_knots = tuple(
                estimate.separator_y_knots
            )
            orthogonal_separator_shift_knots_px = tuple(
                estimate.separator_shift_knots_px
            )
            orthogonal_after_quality_score = float(actual_score)
            if pixel_driven and pixel_row_available:
                if (
                    orthogonal_pixel_row_verdict == "passed"
                    and (
                        not pixel_tail_available
                        or orthogonal_bottom_tail_verdict == "passed"
                    )
                ):
                    orthogonal_alignment_verdict = "passed"
                elif (
                    orthogonal_pixel_row_verdict
                    in {"passed", "improved_review"}
                    and (
                        not pixel_tail_available
                        or orthogonal_bottom_tail_verdict
                        in {"passed", "improved_review"}
                    )
                ):
                    orthogonal_alignment_verdict = "improved_review"
                else:
                    orthogonal_alignment_verdict = "failed"
            else:
                orthogonal_alignment_verdict = str(actual_verdict)
            geometry_strength = max(
                geometry_strength,
                estimate.max_vertical_shift_px * float(row_gain),
                estimate.max_horizontal_shift_px,
            )
            actual_geometry_mode = "orthogonal"
            advanced_redetected = True
            method_parts.append("orthogonal_dewarp")
            if orthogonal_passes > 1:
                method_parts.append("orthogonal_residual_pass")

            # Stop as soon as the physical row geometry is truly straight.
            # Otherwise an accepted improved_review result becomes the input
            # to another fresh measurement pass (0012-type pages). Because
            # working/working_polygons were already updated above, a later
            # rejected pass leaves the previous accepted result intact.
            if (
                pixel_driven
                and pixel_row_available
                and orthogonal_pixel_row_verdict == "passed"
                and (
                    not pixel_tail_available
                    or orthogonal_bottom_tail_verdict == "passed"
                )
            ):
                break
            if (
                not pixel_driven
                and actual_verdict == "passed"
            ):
                break

    retained_pixels = _pixel_row_policy.reaudit_retained_pixels(
        working, working_polygons, settings,
        applied=orthogonal_applied, warnings=warnings,
        current=_pixel_row_policy.RetainedPixelDiagnostics(
            row_sample_count=orthogonal_pixel_row_sample_count,
            before_row_p90_px=orthogonal_before_pixel_row_p90_px,
            after_row_p90_px=orthogonal_after_pixel_row_p90_px,
            before_row_worst_px=orthogonal_before_pixel_row_worst_px,
            after_row_worst_px=orthogonal_after_pixel_row_worst_px,
            row_verdict=orthogonal_pixel_row_verdict,
            tail_sample_count=orthogonal_bottom_tail_sample_count,
            before_tail_p90_px=orthogonal_before_bottom_tail_p90_px,
            after_tail_p90_px=orthogonal_after_bottom_tail_p90_px,
            before_tail_worst_px=orthogonal_before_bottom_tail_worst_px,
            after_tail_worst_px=orthogonal_after_bottom_tail_worst_px,
            tail_verdict=orthogonal_bottom_tail_verdict,
            alignment_verdict=orthogonal_alignment_verdict,
        ),
        pixel_auditor=audit_pixel_row_profiles,
        initial_row_available=orthogonal_initial_pixel_row_available,
        initial_row_p90_px=orthogonal_initial_pixel_row_p90_px,
        initial_row_worst_px=orthogonal_initial_pixel_row_worst_px,
        initial_tail_available=orthogonal_initial_bottom_tail_available,
        initial_tail_p90_px=orthogonal_initial_bottom_tail_p90_px,
        initial_tail_worst_px=orthogonal_initial_bottom_tail_worst_px,
        row_p90_max_px=PIXEL_ROW_PROFILE_P90_MAX_PX,
        row_worst_max_px=PIXEL_ROW_PROFILE_WORST_MAX_PX,
        tail_p90_max_px=PIXEL_ROW_BOTTOM_TAIL_P90_MAX_PX,
        tail_worst_max_px=PIXEL_ROW_BOTTOM_TAIL_WORST_MAX_PX,
        tail_progress_ratio=ORTHOGONAL_TAIL_PROGRESS_RATIO,
        tail_max_regression_px=ORTHOGONAL_TAIL_MAX_REGRESSION_PX,
    )

    if (
        requested_geometry_mode == "auto"
        and line_geometry.separator_curve_reliable
        and not orthogonal_applied
    ):
        warnings.append(
            "检测到可靠非线性弯曲，但正交网格未能通过闭环验收；"
            "已保留前一步结果，可手动选择UVDoc复核。"
        )

    finalization = _finalization.finalize_preprocess_page(
        working, settings,
        source_size=(width, height),
        polygons=polygons, working_polygons=working_polygons,
        actual_geometry_mode=actual_geometry_mode,
        advanced_redetected=advanced_redetected,
        safety_margin_px=safety_margin_px,
        angle_samples=angle_samples, angle_mad=angle_mad, correction=correction,
        warnings=warnings, method_parts=method_parts,
        text_detector=detect_text_polygons,
        horizontal_auditor=audit_horizontal_alignment,
        quality_evaluator=_absolute_horizontal_quality,
        layout_bounds=_layout_content_box_from_polygons,
        projection_bounds=_projection_content_box,
        box_expander=_expand_box_px,
        text_bounds=_rotated_text_box,
    )

    return PreprocessAnalysis(
        source_width=width,
        source_height=height,
        correction_angle_deg=round(float(correction), 4),
        applied_angle_deg=round(float(applied), 4),
        ocr_correction_angle_deg=round(float(ocr_correction), 4),
        deskew_anchor_source=str(deskew_anchor_source),
        source_header_rule_point_count=int(source_header_rule_point_count),
        source_header_rule_angle_deg=round(
            float(source_header_rule_angle_deg), 4
        ),
        source_header_rule_residual_px=round(
            float(source_header_rule_residual_px), 3
        ),
        crop_box=finalization.crop_box,
        raw_content_box=finalization.raw_content_box,
        text_box=finalization.text_box,
        source_boxes=finalization.evidence_boxes,
        angle_samples=angle_samples,
        angle_mad_deg=round(float(angle_mad), 4),
        retained_ratio=finalization.retained_ratio,
        confidence=finalization.confidence,
        status=finalization.status,
        method="+".join(dict.fromkeys(method_parts)),
        warnings=tuple(warnings),
        safety_margin_px=max(0, int(safety_margin_px)),
        auto_deskew=bool(auto_deskew),
        requested_geometry_mode=requested_geometry_mode,
        geometry_mode=actual_geometry_mode,
        geometry_strength_px=round(float(geometry_strength), 3),
        perspective_matrix=perspective_matrix,
        perspective_source_quad=perspective_source_quad,
        perspective_target_quad=perspective_target_quad,
        perspective_classification=perspective_classification,
        perspective_candidate_source=perspective_candidate_source,
        perspective_horizontal_vanishing_x=round(
            float(perspective_horizontal_vanishing_x), 3
        ),
        perspective_horizontal_vanishing_y=round(
            float(perspective_horizontal_vanishing_y), 3
        ),
        perspective_horizontal_row_count=int(perspective_horizontal_row_count),
        perspective_horizontal_column_count=int(
            perspective_horizontal_column_count
        ),
        perspective_horizontal_vp_column_spread_deg=round(
            float(perspective_horizontal_vp_column_spread_deg), 4
        ),
        perspective_horizontal_strength=round(
            float(perspective_horizontal_strength), 6
        ),
        perspective_structural_applied=bool(perspective_structural_applied),
        perspective_structural_safe=bool(perspective_structural_safe),
        perspective_row_valid_column_count=int(
            perspective_row_valid_column_count
        ),
        perspective_row_valid_column_indices=tuple(
            int(v) for v in perspective_row_valid_column_indices
        ),
        perspective_row_column_row_counts=tuple(
            int(v) for v in perspective_row_column_row_counts
        ),
        perspective_row_after_worst_region_deg=round(
            float(perspective_row_after_worst_region_deg), 4
        ),
        perspective_row_after_worst_column_metric_deg=round(
            float(perspective_row_after_worst_column_metric_deg), 4
        ),
        perspective_row_after_worst_column_index=int(
            perspective_row_after_worst_column_index
        ),
        perspective_row_before_column_top_angles_deg=tuple(
            round(float(v), 4)
            for v in perspective_row_before_column_top_angles_deg
        ),
        perspective_row_after_column_top_angles_deg=tuple(
            round(float(v), 4)
            for v in perspective_row_after_column_top_angles_deg
        ),
        perspective_row_before_column_middle_angles_deg=tuple(
            round(float(v), 4)
            for v in perspective_row_before_column_middle_angles_deg
        ),
        perspective_row_after_column_middle_angles_deg=tuple(
            round(float(v), 4)
            for v in perspective_row_after_column_middle_angles_deg
        ),
        perspective_row_before_column_bottom_angles_deg=tuple(
            round(float(v), 4)
            for v in perspective_row_before_column_bottom_angles_deg
        ),
        perspective_row_after_column_bottom_angles_deg=tuple(
            round(float(v), 4)
            for v in perspective_row_after_column_bottom_angles_deg
        ),
        perspective_row_before_column_trends_deg=tuple(
            round(float(v), 4)
            for v in perspective_row_before_column_trends_deg
        ),
        perspective_row_after_column_trends_deg=tuple(
            round(float(v), 4)
            for v in perspective_row_after_column_trends_deg
        ),
        perspective_row_before_top_angle_deg=round(
            float(perspective_row_before_top_angle_deg), 4
        ),
        perspective_row_after_top_angle_deg=round(
            float(perspective_row_after_top_angle_deg), 4
        ),
        perspective_row_before_bottom_angle_deg=round(
            float(perspective_row_before_bottom_angle_deg), 4
        ),
        perspective_row_after_bottom_angle_deg=round(
            float(perspective_row_after_bottom_angle_deg), 4
        ),
        perspective_row_before_trend_deg=round(
            float(perspective_row_before_trend_deg), 4
        ),
        perspective_row_after_trend_deg=round(
            float(perspective_row_after_trend_deg), 4
        ),
        perspective_row_before_metric_deg=round(
            float(perspective_row_before_metric_deg), 4
        ),
        perspective_row_after_metric_deg=round(
            float(perspective_row_after_metric_deg), 4
        ),
        perspective_row_improvement_ratio=round(
            float(perspective_row_improvement_ratio), 6
        ),
        perspective_row_alignment_verdict=str(
            perspective_row_alignment_verdict
        ),
        perspective_candidate_strength_px=round(float(perspective_candidate_strength_px), 3),
        perspective_left_drift_px=round(float(perspective_left_drift_px), 3),
        perspective_right_drift_px=round(float(perspective_right_drift_px), 3),
        perspective_common_drift_px=round(float(perspective_common_drift_px), 3),
        perspective_width_delta_px=round(float(perspective_width_delta_px), 3),
        perspective_width_change_ratio=round(float(perspective_width_change_ratio), 6),
        perspective_scale_top=round(float(perspective_scale_top), 6),
        perspective_scale_bottom=round(float(perspective_scale_bottom), 6),
        perspective_scale_delta_ratio=round(float(perspective_scale_delta_ratio), 6),
        perspective_jacobian_samples=int(perspective_jacobian_samples),
        perspective_jacobian_horizontal_scale_span_ratio=round(
            float(perspective_jacobian_horizontal_scale_span_ratio), 6
        ),
        perspective_jacobian_vertical_scale_span_ratio=round(
            float(perspective_jacobian_vertical_scale_span_ratio), 6
        ),
        perspective_jacobian_area_scale_span_ratio=round(
            float(perspective_jacobian_area_scale_span_ratio), 6
        ),
        perspective_jacobian_anisotropy_p95_ratio=round(
            float(perspective_jacobian_anisotropy_p95_ratio), 6
        ),
        perspective_jacobian_min_determinant=round(
            float(perspective_jacobian_min_determinant), 8
        ),
        perspective_text_scale_samples=int(perspective_text_scale_samples),
        perspective_text_scale_inline_ratio_p05=round(
            float(perspective_text_scale_inline_ratio_p05), 6
        ),
        perspective_text_scale_inline_ratio_median=round(
            float(perspective_text_scale_inline_ratio_median), 6
        ),
        perspective_text_scale_inline_ratio_p95=round(
            float(perspective_text_scale_inline_ratio_p95), 6
        ),
        perspective_text_scale_cross_ratio_p05=round(
            float(perspective_text_scale_cross_ratio_p05), 6
        ),
        perspective_text_scale_cross_ratio_median=round(
            float(perspective_text_scale_cross_ratio_median), 6
        ),
        perspective_text_scale_cross_ratio_p95=round(
            float(perspective_text_scale_cross_ratio_p95), 6
        ),
        perspective_text_scale_inline_ratio_span_ratio=round(
            float(perspective_text_scale_inline_ratio_span_ratio), 6
        ),
        perspective_text_scale_cross_ratio_span_ratio=round(
            float(perspective_text_scale_cross_ratio_span_ratio), 6
        ),
        perspective_text_scale_inline_ratio_gradient_ratio=round(
            float(perspective_text_scale_inline_ratio_gradient_ratio), 6
        ),
        perspective_text_scale_cross_ratio_gradient_ratio=round(
            float(perspective_text_scale_cross_ratio_gradient_ratio), 6
        ),
        perspective_text_scale_anisotropy_p95_ratio=round(
            float(perspective_text_scale_anisotropy_p95_ratio), 6
        ),
        perspective_text_scale_before_inline_gradient_ratio=round(
            float(perspective_text_scale_before_inline_gradient_ratio), 6
        ),
        perspective_text_scale_after_inline_gradient_ratio=round(
            float(perspective_text_scale_after_inline_gradient_ratio), 6
        ),
        perspective_text_scale_before_cross_gradient_ratio=round(
            float(perspective_text_scale_before_cross_gradient_ratio), 6
        ),
        perspective_text_scale_after_cross_gradient_ratio=round(
            float(perspective_text_scale_after_cross_gradient_ratio), 6
        ),
        perspective_text_scale_before_score=round(
            float(perspective_text_scale_before_score), 6
        ),
        perspective_text_scale_after_score=round(
            float(perspective_text_scale_after_score), 6
        ),
        perspective_text_scale_verdict=str(perspective_text_scale_verdict),
        perspective_auto_safe=bool(perspective_auto_safe),
        manual_perspective_quad=manual_quad,
        orthogonal_applied=bool(orthogonal_applied),
        orthogonal_passes=int(orthogonal_passes),
        orthogonal_steps=tuple(dict(step) for step in orthogonal_steps),
        orthogonal_row_count=int(orthogonal_row_count),
        orthogonal_valid_column_count=int(orthogonal_valid_column_count),
        orthogonal_separator_point_count=int(
            orthogonal_separator_point_count
        ),
        orthogonal_row_gain=round(float(orthogonal_row_gain), 6),
        orthogonal_reference_x=round(float(orthogonal_reference_x), 4),
        orthogonal_y_knots=tuple(
            round(float(v), 4) for v in orthogonal_y_knots
        ),
        orthogonal_angle_knots_deg=tuple(
            round(float(v), 6) for v in orthogonal_angle_knots_deg
        ),
        orthogonal_x_knots=tuple(
            round(float(v), 4) for v in orthogonal_x_knots
        ),
        orthogonal_row_grid_rows=int(orthogonal_row_grid_rows),
        orthogonal_row_grid_cols=int(orthogonal_row_grid_cols),
        orthogonal_row_angle_grid_deg=tuple(
            round(float(v), 6)
            for v in orthogonal_row_angle_grid_deg
        ),
        orthogonal_row_displacement_grid_px=tuple(
            round(float(v), 6)
            for v in orthogonal_row_displacement_grid_px
        ),
        orthogonal_separator_y_knots=tuple(
            round(float(v), 4) for v in orthogonal_separator_y_knots
        ),
        orthogonal_separator_shift_knots_px=tuple(
            round(float(v), 6)
            for v in orthogonal_separator_shift_knots_px
        ),
        orthogonal_horizontal_rule_point_count=int(
            orthogonal_horizontal_rule_point_count
        ),
        orthogonal_horizontal_rule_y=round(
            float(orthogonal_horizontal_rule_y), 3
        ),
        orthogonal_before_horizontal_rule_angle_deg=round(
            float(orthogonal_before_horizontal_rule_angle_deg), 4
        ),
        orthogonal_after_horizontal_rule_angle_deg=round(
            float(orthogonal_after_horizontal_rule_angle_deg), 4
        ),
        orthogonal_before_horizontal_rule_residual_px=round(
            float(orthogonal_before_horizontal_rule_residual_px), 3
        ),
        orthogonal_after_horizontal_rule_residual_px=round(
            float(orthogonal_after_horizontal_rule_residual_px), 3
        ),
        orthogonal_horizontal_rule_verdict=str(
            orthogonal_horizontal_rule_verdict
        ),
        orthogonal_pixel_angle_sample_count=int(
            orthogonal_pixel_angle_sample_count
        ),
        orthogonal_pixel_angle_used_count=int(
            orthogonal_pixel_angle_used_count
        ),
        orthogonal_pixel_angle_confidence=round(
            float(orthogonal_pixel_angle_confidence), 6
        ),
        orthogonal_pixel_row_sample_count=int(
            retained_pixels.row_sample_count
        ),
        orthogonal_before_pixel_row_p90_px=round(
            float(retained_pixels.before_row_p90_px), 3
        ),
        orthogonal_after_pixel_row_p90_px=round(
            float(retained_pixels.after_row_p90_px), 3
        ),
        orthogonal_before_pixel_row_worst_px=round(
            float(retained_pixels.before_row_worst_px), 3
        ),
        orthogonal_after_pixel_row_worst_px=round(
            float(retained_pixels.after_row_worst_px), 3
        ),
        orthogonal_pixel_row_verdict=str(
            retained_pixels.row_verdict
        ),
        orthogonal_bottom_tail_sample_count=int(
            retained_pixels.tail_sample_count
        ),
        orthogonal_before_bottom_tail_p90_px=round(
            float(retained_pixels.before_tail_p90_px), 3
        ),
        orthogonal_after_bottom_tail_p90_px=round(
            float(retained_pixels.after_tail_p90_px), 3
        ),
        orthogonal_before_bottom_tail_worst_px=round(
            float(retained_pixels.before_tail_worst_px), 3
        ),
        orthogonal_after_bottom_tail_worst_px=round(
            float(retained_pixels.after_tail_worst_px), 3
        ),
        orthogonal_bottom_tail_verdict=str(
            retained_pixels.tail_verdict
        ),
        orthogonal_safe_gain_cap=round(
            float(orthogonal_safe_gain_cap), 6
        ),
        orthogonal_confidence=round(float(orthogonal_confidence), 6),
        orthogonal_column_spread_deg=round(
            float(orthogonal_column_spread_deg), 4
        ),
        orthogonal_max_row_angle_deg=round(
            float(orthogonal_max_row_angle_deg), 4
        ),
        orthogonal_row_angle_span_deg=round(
            float(orthogonal_row_angle_span_deg), 4
        ),
        orthogonal_max_horizontal_shift_px=round(
            float(orthogonal_max_horizontal_shift_px), 3
        ),
        orthogonal_max_vertical_shift_px=round(
            float(orthogonal_max_vertical_shift_px), 3
        ),
        orthogonal_max_scale_deviation=round(
            float(orthogonal_max_scale_deviation), 6
        ),
        orthogonal_before_quality_score=round(
            float(orthogonal_before_quality_score), 4
        ),
        orthogonal_after_quality_score=round(
            float(orthogonal_after_quality_score), 4
        ),
        orthogonal_before_separator_span_px=round(
            float(orthogonal_before_separator_span_px), 3
        ),
        orthogonal_after_separator_span_px=round(
            float(orthogonal_after_separator_span_px), 3
        ),
        orthogonal_vertical_verdict=str(orthogonal_vertical_verdict),
        orthogonal_alignment_verdict=str(
            retained_pixels.alignment_verdict
        ),
        final_alignment_row_count=int(finalization.final_alignment_row_count),
        final_alignment_valid_column_count=int(
            finalization.final_alignment_valid_column_count
        ),
        final_alignment_edge_pair_count=int(finalization.final_alignment_edge_pair_count),
        final_alignment_top_edge_p90_abs_deg=round(
            float(finalization.final_alignment_top_edge_p90_abs_deg), 4
        ),
        final_alignment_bottom_edge_p90_abs_deg=round(
            float(finalization.final_alignment_bottom_edge_p90_abs_deg), 4
        ),
        final_alignment_edge_pair_delta_p90_deg=round(
            float(finalization.final_alignment_edge_pair_delta_p90_deg), 4
        ),
        final_alignment_worst_edge_deg=round(
            float(finalization.final_alignment_worst_edge_deg), 4
        ),
        final_alignment_worst_region_deg=round(
            float(finalization.final_alignment_worst_region_deg), 4
        ),
        final_alignment_worst_tail_p90_abs_deg=round(
            float(finalization.final_alignment_worst_tail_p90_abs_deg), 4
        ),
        final_alignment_column_top_tail_p90_abs_deg=tuple(
            round(float(v), 4)
            for v in finalization.final_alignment_column_top_tail_p90_abs_deg
        ),
        final_alignment_column_bottom_tail_p90_abs_deg=tuple(
            round(float(v), 4)
            for v in finalization.final_alignment_column_bottom_tail_p90_abs_deg
        ),
        final_alignment_trend_deg=round(float(finalization.final_alignment_trend_deg), 4),
        final_alignment_worst_column_trend_deg=round(
            float(finalization.final_alignment_worst_column_trend_deg), 4
        ),
        final_alignment_quality_score=round(
            float(finalization.final_alignment_quality_score), 4
        ),
        final_alignment_verdict=str(finalization.final_alignment_verdict),
        line_geometry_rows=int(line_geometry.row_count),
        line_geometry_global_angle_deg=float(line_geometry.global_angle_deg),
        line_geometry_top_angle_deg=float(line_geometry.top_angle_deg),
        line_geometry_middle_angle_deg=float(line_geometry.middle_angle_deg),
        line_geometry_bottom_angle_deg=float(line_geometry.bottom_angle_deg),
        line_geometry_trend_deg=float(line_geometry.angle_trend_deg),
        line_geometry_residual_mad_deg=float(line_geometry.residual_mad_deg),
        line_geometry_residual_span_deg=float(line_geometry.residual_span_deg),
        line_geometry_columns=int(getattr(line_geometry, "column_count", 0)),
        line_geometry_valid_columns=int(
            getattr(line_geometry, "valid_column_count", 0)
        ),
        line_geometry_valid_column_indices=tuple(
            int(v)
            for v in getattr(line_geometry, "valid_column_indices", ())
        ),
        line_geometry_column_row_counts=tuple(
            int(v) for v in getattr(line_geometry, "column_row_counts", ())
        ),
        line_geometry_column_trends_deg=tuple(
            float(v) for v in getattr(line_geometry, "column_trends_deg", ())
        ),
        line_geometry_worst_column_index=int(
            getattr(line_geometry, "worst_column_index", -1)
        ),
        line_geometry_worst_column_trend_deg=float(
            getattr(line_geometry, "worst_column_trend_deg", 0.0)
        ),
        line_geometry_worst_region_angle_deg=float(
            getattr(line_geometry, "worst_region_angle_deg", 0.0)
        ),
        line_geometry_separator_found=bool(line_geometry.separator_found),
        line_geometry_separator_residual_px=float(
            line_geometry.separator_residual_px
        ),
        line_geometry_separator_span_ratio=float(
            line_geometry.separator_span_ratio
        ),
        line_geometry_separator_slope_px_per_1000y=float(
            line_geometry.separator_slope_px_per_1000y
        ),
        line_geometry_separator_drift_px=float(
            line_geometry.separator_drift_px
        ),
        line_geometry_separator_track_quality=float(
            line_geometry.separator_track_quality
        ),
        line_geometry_separator_track_jump_p95_px=float(
            line_geometry.separator_track_jump_p95_px
        ),
        line_geometry_separator_curvature_score=float(
            line_geometry.separator_curvature_score
        ),
        line_geometry_separator_curve_reliable=bool(
            line_geometry.separator_curve_reliable
        ),
        line_geometry_recommendation=str(line_geometry.recommendation),
        line_geometry_confidence=float(line_geometry.confidence),
    )

def analyze_preprocess_path(
    path: Path,
    settings: AppSettings,
    *,
    safety_margin_px: int = DEFAULT_SAFETY_MARGIN_PX,
    auto_deskew: bool = True,
    geometry_mode: str = "auto",
    manual_perspective_quad: tuple[float, ...] | None = None,
) -> PreprocessAnalysis:
    path = Path(path)
    with Image.open(path) as opened:
        analysis = analyze_preprocess_page(
            opened,
            settings,
            safety_margin_px=safety_margin_px,
            auto_deskew=auto_deskew,
            geometry_mode=geometry_mode,
            manual_perspective_quad=manual_perspective_quad,
        )
    try:
        stat = path.stat()
        analysis.source_size_bytes = int(stat.st_size)
        analysis.source_mtime_ns = int(stat.st_mtime_ns)
    except OSError:
        pass
    return analysis


def analysis_is_current(
    analysis: PreprocessAnalysis,
    page: Path,
    *,
    safety_margin_px: int,
    auto_deskew: bool,
    geometry_mode: str = "auto",
    manual_perspective_quad: tuple[float, ...] | None = None,
) -> bool:
    page = Path(page)
    if int(analysis.safety_margin_px) != int(safety_margin_px):
        return False
    if bool(analysis.auto_deskew) != bool(auto_deskew):
        return False
    if _normalize_geometry_mode(analysis.requested_geometry_mode) != _normalize_geometry_mode(geometry_mode):
        return False
    expected_quad = (
        tuple(round(float(v), 4) for v in manual_perspective_quad)
        if manual_perspective_quad is not None else None
    )
    actual_quad = (
        tuple(round(float(v), 4) for v in analysis.manual_perspective_quad)
        if analysis.manual_perspective_quad is not None else None
    )
    if actual_quad != expected_quad:
        return False
    try:
        stat = page.stat()
    except OSError:
        return False
    if analysis.source_size_bytes and int(stat.st_size) != int(analysis.source_size_bytes):
        return False
    if analysis.source_mtime_ns and int(stat.st_mtime_ns) != int(analysis.source_mtime_ns):
        return False
    return True


def overlay_excluded_regions(
    image: Image.Image,
    crop_box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int, int] = PREVIEW_YELLOW,
    outline: tuple[int, int, int, int] = PREVIEW_OUTLINE,
) -> Image.Image:
    return _rendering.overlay_excluded_regions(
        image, crop_box, fill=fill, outline=outline,
        normalizer=normalize_page_rgb,
    )


def review_image(image: Image.Image, analysis: PreprocessAnalysis) -> Image.Image:
    return _rendering.review_image(
        image, analysis,
        geometry_renderer=geometry_corrected_image, overlay_renderer=overlay_excluded_regions,
    )


def processed_image(image: Image.Image, analysis: PreprocessAnalysis) -> Image.Image:
    return _rendering.processed_image(
        image, analysis,
        geometry_renderer=geometry_corrected_image,
    )


def processed_image_with_canvas(
    image: Image.Image,
    analysis: PreprocessAnalysis,
    canvas: OutputCanvasInfo | None = None,
) -> Image.Image:
    return _rendering.processed_image_with_canvas(
        image, analysis, canvas,
        content_renderer=processed_image, canvas_info_factory=output_canvas_info,
    )


def preprocess_metadata_output_root(project_root: Path) -> Path:
    path = image_preprocess_output_root(project_root) / "meta"
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_diagnostic_json(
    page: Path,
    analysis: PreprocessAnalysis,
    destination: Path,
    *,
    output_path: Path | None = None,
    canvas: OutputCanvasInfo | None = None,
    settings: AppSettings | None = None,
) -> Path:
    """Write diagnostic JSON through the reporting owner.

    The wrapper remains here so the historical callable path and the current
    `output_canvas_info` module-global hook stay observable to existing callers.
    """
    return _export_diagnostic_json_impl(
        page,
        analysis,
        destination,
        output_path=output_path,
        canvas=canvas,
        settings=settings,
        canvas_info_factory=output_canvas_info,
    )

def save_review_preview(
    page: Path,
    analysis: PreprocessAnalysis,
    destination: Path,
    *,
    max_long_side: int = 1400,
) -> Path:
    return _rendering.save_review_preview(
        page, analysis, destination, max_long_side=max_long_side,
        review_renderer=review_image,
    )


def save_processed_page(
    page: Path,
    analysis: PreprocessAnalysis,
    destination: Path,
    *,
    canvas: OutputCanvasInfo | None = None,
) -> Path:
    return _rendering.save_processed_page(
        page, analysis, destination, canvas=canvas,
        canvas_renderer=processed_image_with_canvas,
    )


