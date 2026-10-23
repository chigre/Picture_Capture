"""Orthogonal mesh estimation, pixel validation and retained-page convergence.

Owns the complete closed loop: estimate → candidate → warped-pixel verification
→ accept/rollback → retry/stop → retained pixel diagnostics and warnings.
All changeable operations/policies arrive at call time through OrthogonalRuntime.
The returned 59 historical per-page measurements are working-only; no persisted
model, GUI, root facade or native engine is imported by this module.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import pixel_row_policy as _pixel_row_policy


@dataclass(frozen=True)
class OrthogonalRuntime:
    """Current facade callbacks and numeric gates; no global installer."""
    estimate_orthogonal_warp: object
    _orthogonal_safe_gain_cap: object
    transform_polygons_orthogonal: object
    audit_text_scale_stability: object
    audit_horizontal_alignment: object
    _absolute_horizontal_quality: object
    _choose_orthogonal_candidate: object
    apply_orthogonal_warp_image: object
    detect_text_polygons: object
    audit_pixel_row_profiles: object
    separator_track_points: object
    _separator_vertical_span: object
    horizontal_rule_metrics: object
    _orthogonal_step_payload: object
    ORTHOGONAL_MAX_AUTO_PASSES: object
    ORTHOGONAL_AUTO_MIN_CONFIDENCE: object
    ORTHOGONAL_MIN_SAFE_GAIN: object
    ORTHOGONAL_AUTO_MIN_SCORE_IMPROVEMENT: object
    HORIZONTAL_ALIGNMENT_MAX_TAIL_DEG: object
    PIXEL_ROW_PROFILE_P90_MAX_PX: object
    PIXEL_ROW_PROFILE_WORST_MAX_PX: object
    PIXEL_ROW_BOTTOM_TAIL_P90_MAX_PX: object
    PIXEL_ROW_BOTTOM_TAIL_WORST_MAX_PX: object
    ORTHOGONAL_TAIL_PROGRESS_RATIO: object
    ORTHOGONAL_TAIL_MAX_REGRESSION_PX: object
    ORTHOGONAL_VERTICAL_MAX_SPAN_MIN_PX: object
    ORTHOGONAL_VERTICAL_MAX_SPAN_WIDTH_RATIO: object
    HORIZONTAL_RULE_MAX_RESIDUAL_MIN_PX: object
    HORIZONTAL_RULE_MAX_RESIDUAL_WIDTH_RATIO: object
    HORIZONTAL_RULE_MAX_ANGLE_DEG: object


@dataclass(frozen=True)
class OrthogonalRunResult:
    """One analysis invocation's pixels, diagnostics, and pre-save metadata."""
    orthogonal_applied: object
    orthogonal_passes: object
    orthogonal_steps: object
    orthogonal_row_count: object
    orthogonal_valid_column_count: object
    orthogonal_separator_point_count: object
    orthogonal_row_gain: object
    orthogonal_reference_x: object
    orthogonal_y_knots: object
    orthogonal_angle_knots_deg: object
    orthogonal_x_knots: object
    orthogonal_row_grid_rows: object
    orthogonal_row_grid_cols: object
    orthogonal_row_angle_grid_deg: object
    orthogonal_row_displacement_grid_px: object
    orthogonal_separator_y_knots: object
    orthogonal_separator_shift_knots_px: object
    orthogonal_horizontal_rule_point_count: object
    orthogonal_horizontal_rule_y: object
    orthogonal_before_horizontal_rule_angle_deg: object
    orthogonal_after_horizontal_rule_angle_deg: object
    orthogonal_before_horizontal_rule_residual_px: object
    orthogonal_after_horizontal_rule_residual_px: object
    orthogonal_horizontal_rule_verdict: object
    orthogonal_pixel_angle_sample_count: object
    orthogonal_pixel_angle_used_count: object
    orthogonal_pixel_angle_confidence: object
    orthogonal_pixel_row_sample_count: object
    orthogonal_before_pixel_row_p90_px: object
    orthogonal_after_pixel_row_p90_px: object
    orthogonal_before_pixel_row_worst_px: object
    orthogonal_after_pixel_row_worst_px: object
    orthogonal_pixel_row_verdict: object
    orthogonal_bottom_tail_sample_count: object
    orthogonal_before_bottom_tail_p90_px: object
    orthogonal_after_bottom_tail_p90_px: object
    orthogonal_before_bottom_tail_worst_px: object
    orthogonal_after_bottom_tail_worst_px: object
    orthogonal_bottom_tail_verdict: object
    orthogonal_safe_gain_cap: object
    orthogonal_initial_pixel_row_p90_px: object
    orthogonal_initial_pixel_row_worst_px: object
    orthogonal_initial_pixel_row_available: object
    orthogonal_initial_bottom_tail_p90_px: object
    orthogonal_initial_bottom_tail_worst_px: object
    orthogonal_initial_bottom_tail_available: object
    orthogonal_confidence: object
    orthogonal_column_spread_deg: object
    orthogonal_max_row_angle_deg: object
    orthogonal_row_angle_span_deg: object
    orthogonal_max_horizontal_shift_px: object
    orthogonal_max_vertical_shift_px: object
    orthogonal_max_scale_deviation: object
    orthogonal_before_quality_score: object
    orthogonal_after_quality_score: object
    orthogonal_before_separator_span_px: object
    orthogonal_after_separator_span_px: object
    orthogonal_vertical_verdict: object
    orthogonal_alignment_verdict: object
    working: object
    working_polygons: object
    geometry_strength: object
    actual_geometry_mode: object
    advanced_redetected: object
    retained_pixels: object


def run_orthogonal_pipeline(
    working: object,
    working_polygons: list,
    settings: object,
    *,
    requested_geometry_mode: str,
    actual_geometry_mode: str,
    geometry_strength: float,
    advanced_redetected: bool,
    line_geometry: object,
    method_parts: list[str],
    warnings: list[str],
    runtime: OrthogonalRuntime,
) -> OrthogonalRunResult:
    # Resolve current operations and policies once for this invocation.
    estimate_orthogonal_warp = runtime.estimate_orthogonal_warp
    _orthogonal_safe_gain_cap = runtime._orthogonal_safe_gain_cap
    transform_polygons_orthogonal = runtime.transform_polygons_orthogonal
    audit_text_scale_stability = runtime.audit_text_scale_stability
    audit_horizontal_alignment = runtime.audit_horizontal_alignment
    _absolute_horizontal_quality = runtime._absolute_horizontal_quality
    _choose_orthogonal_candidate = runtime._choose_orthogonal_candidate
    apply_orthogonal_warp_image = runtime.apply_orthogonal_warp_image
    detect_text_polygons = runtime.detect_text_polygons
    audit_pixel_row_profiles = runtime.audit_pixel_row_profiles
    separator_track_points = runtime.separator_track_points
    _separator_vertical_span = runtime._separator_vertical_span
    horizontal_rule_metrics = runtime.horizontal_rule_metrics
    _orthogonal_step_payload = runtime._orthogonal_step_payload
    ORTHOGONAL_MAX_AUTO_PASSES = runtime.ORTHOGONAL_MAX_AUTO_PASSES
    ORTHOGONAL_AUTO_MIN_CONFIDENCE = runtime.ORTHOGONAL_AUTO_MIN_CONFIDENCE
    ORTHOGONAL_MIN_SAFE_GAIN = runtime.ORTHOGONAL_MIN_SAFE_GAIN
    ORTHOGONAL_AUTO_MIN_SCORE_IMPROVEMENT = runtime.ORTHOGONAL_AUTO_MIN_SCORE_IMPROVEMENT
    HORIZONTAL_ALIGNMENT_MAX_TAIL_DEG = runtime.HORIZONTAL_ALIGNMENT_MAX_TAIL_DEG
    PIXEL_ROW_PROFILE_P90_MAX_PX = runtime.PIXEL_ROW_PROFILE_P90_MAX_PX
    PIXEL_ROW_PROFILE_WORST_MAX_PX = runtime.PIXEL_ROW_PROFILE_WORST_MAX_PX
    PIXEL_ROW_BOTTOM_TAIL_P90_MAX_PX = runtime.PIXEL_ROW_BOTTOM_TAIL_P90_MAX_PX
    PIXEL_ROW_BOTTOM_TAIL_WORST_MAX_PX = runtime.PIXEL_ROW_BOTTOM_TAIL_WORST_MAX_PX
    ORTHOGONAL_TAIL_PROGRESS_RATIO = runtime.ORTHOGONAL_TAIL_PROGRESS_RATIO
    ORTHOGONAL_TAIL_MAX_REGRESSION_PX = runtime.ORTHOGONAL_TAIL_MAX_REGRESSION_PX
    ORTHOGONAL_VERTICAL_MAX_SPAN_MIN_PX = runtime.ORTHOGONAL_VERTICAL_MAX_SPAN_MIN_PX
    ORTHOGONAL_VERTICAL_MAX_SPAN_WIDTH_RATIO = runtime.ORTHOGONAL_VERTICAL_MAX_SPAN_WIDTH_RATIO
    HORIZONTAL_RULE_MAX_RESIDUAL_MIN_PX = runtime.HORIZONTAL_RULE_MAX_RESIDUAL_MIN_PX
    HORIZONTAL_RULE_MAX_RESIDUAL_WIDTH_RATIO = runtime.HORIZONTAL_RULE_MAX_RESIDUAL_WIDTH_RATIO
    HORIZONTAL_RULE_MAX_ANGLE_DEG = runtime.HORIZONTAL_RULE_MAX_ANGLE_DEG

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

    return OrthogonalRunResult(
        orthogonal_applied=orthogonal_applied,
        orthogonal_passes=orthogonal_passes,
        orthogonal_steps=orthogonal_steps,
        orthogonal_row_count=orthogonal_row_count,
        orthogonal_valid_column_count=orthogonal_valid_column_count,
        orthogonal_separator_point_count=orthogonal_separator_point_count,
        orthogonal_row_gain=orthogonal_row_gain,
        orthogonal_reference_x=orthogonal_reference_x,
        orthogonal_y_knots=orthogonal_y_knots,
        orthogonal_angle_knots_deg=orthogonal_angle_knots_deg,
        orthogonal_x_knots=orthogonal_x_knots,
        orthogonal_row_grid_rows=orthogonal_row_grid_rows,
        orthogonal_row_grid_cols=orthogonal_row_grid_cols,
        orthogonal_row_angle_grid_deg=orthogonal_row_angle_grid_deg,
        orthogonal_row_displacement_grid_px=orthogonal_row_displacement_grid_px,
        orthogonal_separator_y_knots=orthogonal_separator_y_knots,
        orthogonal_separator_shift_knots_px=orthogonal_separator_shift_knots_px,
        orthogonal_horizontal_rule_point_count=orthogonal_horizontal_rule_point_count,
        orthogonal_horizontal_rule_y=orthogonal_horizontal_rule_y,
        orthogonal_before_horizontal_rule_angle_deg=orthogonal_before_horizontal_rule_angle_deg,
        orthogonal_after_horizontal_rule_angle_deg=orthogonal_after_horizontal_rule_angle_deg,
        orthogonal_before_horizontal_rule_residual_px=orthogonal_before_horizontal_rule_residual_px,
        orthogonal_after_horizontal_rule_residual_px=orthogonal_after_horizontal_rule_residual_px,
        orthogonal_horizontal_rule_verdict=orthogonal_horizontal_rule_verdict,
        orthogonal_pixel_angle_sample_count=orthogonal_pixel_angle_sample_count,
        orthogonal_pixel_angle_used_count=orthogonal_pixel_angle_used_count,
        orthogonal_pixel_angle_confidence=orthogonal_pixel_angle_confidence,
        orthogonal_pixel_row_sample_count=orthogonal_pixel_row_sample_count,
        orthogonal_before_pixel_row_p90_px=orthogonal_before_pixel_row_p90_px,
        orthogonal_after_pixel_row_p90_px=orthogonal_after_pixel_row_p90_px,
        orthogonal_before_pixel_row_worst_px=orthogonal_before_pixel_row_worst_px,
        orthogonal_after_pixel_row_worst_px=orthogonal_after_pixel_row_worst_px,
        orthogonal_pixel_row_verdict=orthogonal_pixel_row_verdict,
        orthogonal_bottom_tail_sample_count=orthogonal_bottom_tail_sample_count,
        orthogonal_before_bottom_tail_p90_px=orthogonal_before_bottom_tail_p90_px,
        orthogonal_after_bottom_tail_p90_px=orthogonal_after_bottom_tail_p90_px,
        orthogonal_before_bottom_tail_worst_px=orthogonal_before_bottom_tail_worst_px,
        orthogonal_after_bottom_tail_worst_px=orthogonal_after_bottom_tail_worst_px,
        orthogonal_bottom_tail_verdict=orthogonal_bottom_tail_verdict,
        orthogonal_safe_gain_cap=orthogonal_safe_gain_cap,
        orthogonal_initial_pixel_row_p90_px=orthogonal_initial_pixel_row_p90_px,
        orthogonal_initial_pixel_row_worst_px=orthogonal_initial_pixel_row_worst_px,
        orthogonal_initial_pixel_row_available=orthogonal_initial_pixel_row_available,
        orthogonal_initial_bottom_tail_p90_px=orthogonal_initial_bottom_tail_p90_px,
        orthogonal_initial_bottom_tail_worst_px=orthogonal_initial_bottom_tail_worst_px,
        orthogonal_initial_bottom_tail_available=orthogonal_initial_bottom_tail_available,
        orthogonal_confidence=orthogonal_confidence,
        orthogonal_column_spread_deg=orthogonal_column_spread_deg,
        orthogonal_max_row_angle_deg=orthogonal_max_row_angle_deg,
        orthogonal_row_angle_span_deg=orthogonal_row_angle_span_deg,
        orthogonal_max_horizontal_shift_px=orthogonal_max_horizontal_shift_px,
        orthogonal_max_vertical_shift_px=orthogonal_max_vertical_shift_px,
        orthogonal_max_scale_deviation=orthogonal_max_scale_deviation,
        orthogonal_before_quality_score=orthogonal_before_quality_score,
        orthogonal_after_quality_score=orthogonal_after_quality_score,
        orthogonal_before_separator_span_px=orthogonal_before_separator_span_px,
        orthogonal_after_separator_span_px=orthogonal_after_separator_span_px,
        orthogonal_vertical_verdict=orthogonal_vertical_verdict,
        orthogonal_alignment_verdict=orthogonal_alignment_verdict,
        working=working,
        working_polygons=working_polygons,
        geometry_strength=geometry_strength,
        actual_geometry_mode=actual_geometry_mode,
        advanced_redetected=advanced_redetected,
        retained_pixels=retained_pixels,
    )
