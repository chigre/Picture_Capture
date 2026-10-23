"""Manual and selected automatic projective stages for page preprocessing.

Working-only diagnostics are explicitly scoped to one analysis invocation.
No public model is cloned; all changeable policies and operations are supplied
by the existing public preprocessing facade at call time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PIL import Image


@dataclass
class PerspectiveState:
    """Working diagnostic fields; defaults mirror the historical facade."""
    perspective_matrix: object = None
    perspective_source_quad: object = None
    perspective_target_quad: object = None
    perspective_classification: object = "none"
    perspective_candidate_source: object = "none"
    perspective_horizontal_vanishing_x: object = 0.0
    perspective_horizontal_vanishing_y: object = 0.0
    perspective_horizontal_row_count: object = 0
    perspective_horizontal_column_count: object = 0
    perspective_horizontal_vp_column_spread_deg: object = 0.0
    perspective_horizontal_strength: object = 0.0
    perspective_structural_applied: object = False
    perspective_structural_safe: object = False
    perspective_row_valid_column_count: object = 0
    perspective_row_valid_column_indices: object = ()
    perspective_row_column_row_counts: object = ()
    perspective_row_after_worst_region_deg: object = 0.0
    perspective_row_after_worst_column_metric_deg: object = 0.0
    perspective_row_after_worst_column_index: object = -1
    perspective_row_before_column_top_angles_deg: object = ()
    perspective_row_after_column_top_angles_deg: object = ()
    perspective_row_before_column_middle_angles_deg: object = ()
    perspective_row_after_column_middle_angles_deg: object = ()
    perspective_row_before_column_bottom_angles_deg: object = ()
    perspective_row_after_column_bottom_angles_deg: object = ()
    perspective_row_before_column_trends_deg: object = ()
    perspective_row_after_column_trends_deg: object = ()
    perspective_row_before_top_angle_deg: object = 0.0
    perspective_row_after_top_angle_deg: object = 0.0
    perspective_row_before_bottom_angle_deg: object = 0.0
    perspective_row_after_bottom_angle_deg: object = 0.0
    perspective_row_before_trend_deg: object = 0.0
    perspective_row_after_trend_deg: object = 0.0
    perspective_row_before_metric_deg: object = 0.0
    perspective_row_after_metric_deg: object = 0.0
    perspective_row_improvement_ratio: object = 0.0
    perspective_row_alignment_verdict: object = "insufficient"
    perspective_candidate_strength_px: object = 0.0
    perspective_left_drift_px: object = 0.0
    perspective_right_drift_px: object = 0.0
    perspective_common_drift_px: object = 0.0
    perspective_width_delta_px: object = 0.0
    perspective_width_change_ratio: object = 0.0
    perspective_scale_top: object = 1.0
    perspective_scale_bottom: object = 1.0
    perspective_scale_delta_ratio: object = 0.0
    perspective_jacobian_samples: object = 0
    perspective_jacobian_horizontal_scale_span_ratio: object = 0.0
    perspective_jacobian_vertical_scale_span_ratio: object = 0.0
    perspective_jacobian_area_scale_span_ratio: object = 0.0
    perspective_jacobian_anisotropy_p95_ratio: object = 0.0
    perspective_jacobian_min_determinant: object = 1.0
    perspective_text_scale_samples: object = 0
    perspective_text_scale_inline_ratio_p05: object = 1.0
    perspective_text_scale_inline_ratio_median: object = 1.0
    perspective_text_scale_inline_ratio_p95: object = 1.0
    perspective_text_scale_cross_ratio_p05: object = 1.0
    perspective_text_scale_cross_ratio_median: object = 1.0
    perspective_text_scale_cross_ratio_p95: object = 1.0
    perspective_text_scale_inline_ratio_span_ratio: object = 0.0
    perspective_text_scale_cross_ratio_span_ratio: object = 0.0
    perspective_text_scale_inline_ratio_gradient_ratio: object = 0.0
    perspective_text_scale_cross_ratio_gradient_ratio: object = 0.0
    perspective_text_scale_anisotropy_p95_ratio: object = 0.0
    perspective_text_scale_before_inline_gradient_ratio: object = 0.0
    perspective_text_scale_after_inline_gradient_ratio: object = 0.0
    perspective_text_scale_before_cross_gradient_ratio: object = 0.0
    perspective_text_scale_after_cross_gradient_ratio: object = 0.0
    perspective_text_scale_before_score: object = 0.0
    perspective_text_scale_after_score: object = 0.0
    perspective_text_scale_verdict: object = "insufficient"
    perspective_auto_safe: object = False


@dataclass(frozen=True)
class ProjectiveStageResult:
    image: Image.Image
    polygons: list
    geometry_mode: str
    geometry_strength: float


def apply_manual_perspective(
    working: Image.Image,
    working_polygons: list,
    manual_quad: tuple[float, ...] | None,
    width: int, height: int, applied: float,
    settings: object,
    state: PerspectiveState,
    geometry_strength: float,
    method_parts: list[str],
    warnings: list[str],
    *,
    point_rotator: Callable,
    manual_estimator: Callable,
    polygon_transformer: Callable,
    distortion_auditor: Callable,
    text_scale_auditor: Callable,
    row_auditor: Callable,
    homography_warper: Callable,
) -> ProjectiveStageResult:
    actual_geometry_mode = "deskew"
    # A saved manual quadrilateral is expressed in original-source pixels.
    # Rotate those four handles through the same small-angle correction first,
    # then rectify before any automatic perspective/dewarp stage.
    if manual_quad is not None:
        try:
            rotated_quad: list[float] = []
            for index in range(0, 8, 2):
                x, y = point_rotator(
                    manual_quad[index], manual_quad[index + 1],
                    width, height, applied,
                )
                rotated_quad.extend((x, y))
            manual_estimate = manual_estimator(
                rotated_quad, working.size,
            )
            state.perspective_matrix = manual_estimate.matrix
            state.perspective_source_quad = tuple(manual_estimate.source_quad)
            state.perspective_target_quad = tuple(manual_estimate.target_quad)
            state.perspective_classification = str(manual_estimate.classification)
            state.perspective_candidate_source = "manual"
            state.perspective_candidate_strength_px = float(manual_estimate.strength_px)
            state.perspective_left_drift_px = float(manual_estimate.left_drift_px)
            state.perspective_right_drift_px = float(manual_estimate.right_drift_px)
            state.perspective_common_drift_px = float(manual_estimate.common_drift_px)
            state.perspective_width_delta_px = float(manual_estimate.width_delta_px)
            state.perspective_width_change_ratio = float(manual_estimate.width_change_ratio)
            state.perspective_scale_top = float(manual_estimate.scale_top)
            state.perspective_scale_bottom = float(manual_estimate.scale_bottom)
            state.perspective_scale_delta_ratio = float(manual_estimate.scale_delta_ratio)
            geometry_strength = max(
                geometry_strength, float(manual_estimate.strength_px)
            )
            if working_polygons:
                manual_candidate_polygons = polygon_transformer(
                    working_polygons, state.perspective_matrix,
                )
                jacobian_audit = distortion_auditor(
                    state.perspective_matrix,
                    working.size,
                    polygons=working_polygons,
                )
                text_scale_audit = text_scale_auditor(
                    working_polygons,
                    manual_candidate_polygons,
                    working.size,
                    writing_mode=settings.layout_writing_mode,
                )
                row_audit = row_auditor(
                    working_polygons,
                    manual_candidate_polygons,
                    size=working.size,
                    settings=settings,
                )
                state.perspective_row_before_top_angle_deg = row_audit.before_top_angle_deg
                state.perspective_row_after_top_angle_deg = row_audit.after_top_angle_deg
                state.perspective_row_before_bottom_angle_deg = row_audit.before_bottom_angle_deg
                state.perspective_row_after_bottom_angle_deg = row_audit.after_bottom_angle_deg
                state.perspective_row_before_trend_deg = row_audit.before_trend_deg
                state.perspective_row_after_trend_deg = row_audit.after_trend_deg
                state.perspective_row_before_metric_deg = row_audit.before_metric_deg
                state.perspective_row_after_metric_deg = row_audit.after_metric_deg
                state.perspective_row_improvement_ratio = row_audit.improvement_ratio
                state.perspective_row_alignment_verdict = row_audit.verdict
                state.perspective_jacobian_samples = jacobian_audit.sample_count
                state.perspective_jacobian_horizontal_scale_span_ratio = (
                    jacobian_audit.horizontal_scale_span_ratio
                )
                state.perspective_jacobian_vertical_scale_span_ratio = (
                    jacobian_audit.vertical_scale_span_ratio
                )
                state.perspective_jacobian_area_scale_span_ratio = (
                    jacobian_audit.area_scale_span_ratio
                )
                state.perspective_jacobian_anisotropy_p95_ratio = (
                    jacobian_audit.anisotropy_p95_ratio
                )
                state.perspective_jacobian_min_determinant = (
                    jacobian_audit.min_determinant
                )
                state.perspective_text_scale_samples = text_scale_audit.sample_count
                state.perspective_text_scale_inline_ratio_p05 = (
                    text_scale_audit.inline_ratio_p05
                )
                state.perspective_text_scale_inline_ratio_median = (
                    text_scale_audit.inline_ratio_median
                )
                state.perspective_text_scale_inline_ratio_p95 = (
                    text_scale_audit.inline_ratio_p95
                )
                state.perspective_text_scale_cross_ratio_p05 = (
                    text_scale_audit.cross_ratio_p05
                )
                state.perspective_text_scale_cross_ratio_median = (
                    text_scale_audit.cross_ratio_median
                )
                state.perspective_text_scale_cross_ratio_p95 = (
                    text_scale_audit.cross_ratio_p95
                )
                state.perspective_text_scale_inline_ratio_span_ratio = (
                    text_scale_audit.inline_ratio_span_ratio
                )
                state.perspective_text_scale_cross_ratio_span_ratio = (
                    text_scale_audit.cross_ratio_span_ratio
                )
                state.perspective_text_scale_inline_ratio_gradient_ratio = (
                    text_scale_audit.inline_ratio_gradient_ratio
                )
                state.perspective_text_scale_cross_ratio_gradient_ratio = (
                    text_scale_audit.cross_ratio_gradient_ratio
                )
                state.perspective_text_scale_anisotropy_p95_ratio = (
                    text_scale_audit.anisotropy_p95_ratio
                )
                state.perspective_text_scale_before_inline_gradient_ratio = (
                    text_scale_audit.before_inline_gradient_ratio
                )
                state.perspective_text_scale_after_inline_gradient_ratio = (
                    text_scale_audit.after_inline_gradient_ratio
                )
                state.perspective_text_scale_before_cross_gradient_ratio = (
                    text_scale_audit.before_cross_gradient_ratio
                )
                state.perspective_text_scale_after_cross_gradient_ratio = (
                    text_scale_audit.after_cross_gradient_ratio
                )
                state.perspective_text_scale_before_score = text_scale_audit.before_score
                state.perspective_text_scale_after_score = text_scale_audit.after_score
                state.perspective_text_scale_verdict = text_scale_audit.verdict
            else:
                manual_candidate_polygons = []
            working = homography_warper(
                working, state.perspective_matrix,
            )
            if manual_candidate_polygons:
                working_polygons = manual_candidate_polygons
            actual_geometry_mode = "manual_perspective"
            method_parts.append("manual_perspective")
        except Exception as exc:
            warnings.append(f"手动四角透视纠正不可用：{exc}")


    return ProjectiveStageResult(
        working, working_polygons, actual_geometry_mode, geometry_strength,
    )


def apply_selected_perspective(
    selection: object,
    working: Image.Image,
    working_polygons: list,
    actual_geometry_mode: str,
    geometry_strength: float,
    state: PerspectiveState,
    *,
    requested_geometry_mode: str,
    line_geometry: object,
    method_parts: list[str],
    warnings: list[str],
    homography_warper: Callable,
    horizontal_scale_span_max: float,
    vertical_scale_span_max: float,
    area_scale_span_max: float,
    anisotropy_p95_max: float,
) -> ProjectiveStageResult:
    selected_entry = selection.selected_entry
    selected_candidate = selection.selected_candidate
    selected_horizontal_strength = selection.selected_horizontal_strength
    diagnostic_entry = selection.diagnostic_entry
    diagnostic_candidate = selection.diagnostic_candidate
    diagnostic_horizontal_strength = selection.diagnostic_horizontal_strength
    state.perspective_structural_applied = selection.state.perspective_structural_applied
    state.perspective_structural_safe = selection.state.perspective_structural_safe
    structural_auto_safe = selection.structural_auto_safe
    horizontal_auto_safe = selection.horizontal_auto_safe
    structural_candidate = selection.structural_candidate
    structural_entry = selection.structural_entry
    line_supports_perspective = selection.line_supports_perspective
    horizontal_total_candidate = selection.horizontal_total_candidate
    horizontal_full = selection.horizontal_full
    horizontal_row_audit = selection.horizontal_row_audit
    horizontal_strength = selection.horizontal_strength

    if diagnostic_entry is not None and diagnostic_candidate is not None:
        perspective = diagnostic_candidate
        jacobian_audit = diagnostic_entry["jacobian"]
        text_scale_audit = diagnostic_entry["text_scale"]
        row_audit = diagnostic_entry["row"]

        source_quad_value = getattr(perspective, "source_quad", None)
        target_quad_value = getattr(perspective, "target_quad", None)
        state.perspective_source_quad = (
            tuple(float(v) for v in source_quad_value)
            if source_quad_value is not None else None
        )
        state.perspective_target_quad = (
            tuple(float(v) for v in target_quad_value)
            if target_quad_value is not None else None
        )
        state.perspective_candidate_source = str(
            getattr(perspective, "candidate_source", "structural")
        )
        state.perspective_classification = str(
            getattr(perspective, "classification", "unknown")
        )
        state.perspective_horizontal_vanishing_x = float(
            getattr(perspective, "horizontal_vanishing_x", 0.0)
        )
        state.perspective_horizontal_vanishing_y = float(
            getattr(perspective, "horizontal_vanishing_y", 0.0)
        )
        state.perspective_horizontal_row_count = int(
            getattr(perspective, "horizontal_row_count", 0)
        )
        state.perspective_horizontal_column_count = int(
            getattr(perspective, "horizontal_column_count", 0)
        )
        state.perspective_horizontal_vp_column_spread_deg = float(
            getattr(
                perspective,
                "horizontal_vp_column_spread_deg",
                0.0,
            )
        )
        state.perspective_horizontal_strength = float(
            diagnostic_horizontal_strength
        )
        state.perspective_candidate_strength_px = float(
            getattr(perspective, "strength_px", 0.0)
        )
        state.perspective_left_drift_px = float(
            getattr(perspective, "left_drift_px", 0.0)
        )
        state.perspective_right_drift_px = float(
            getattr(perspective, "right_drift_px", 0.0)
        )
        state.perspective_common_drift_px = float(
            getattr(perspective, "common_drift_px", 0.0)
        )
        state.perspective_width_delta_px = float(
            getattr(perspective, "width_delta_px", 0.0)
        )
        state.perspective_width_change_ratio = max(
            0.0, float(getattr(perspective, "width_change_ratio", 0.0))
        )
        state.perspective_scale_top = max(
            0.0, float(getattr(perspective, "scale_top", 1.0))
        )
        state.perspective_scale_bottom = max(
            0.0, float(getattr(perspective, "scale_bottom", 1.0))
        )
        state.perspective_scale_delta_ratio = max(
            0.0, float(getattr(perspective, "scale_delta_ratio", 0.0))
        )

        state.perspective_row_valid_column_count = int(
            getattr(row_audit, "valid_column_count", 0)
        )
        state.perspective_row_valid_column_indices = tuple(
            int(value)
            for value in getattr(row_audit, "valid_column_indices", ())
        )
        state.perspective_row_column_row_counts = tuple(
            getattr(row_audit, "column_row_counts", ())
        )
        state.perspective_row_after_worst_region_deg = float(
            getattr(row_audit, "after_worst_region_deg", 0.0)
        )
        state.perspective_row_after_worst_column_metric_deg = float(
            getattr(
                row_audit,
                "after_worst_column_metric_deg",
                0.0,
            )
        )
        state.perspective_row_after_worst_column_index = int(
            getattr(row_audit, "after_worst_column_index", -1)
        )
        state.perspective_row_before_column_top_angles_deg = tuple(
            getattr(row_audit, "before_column_top_angles_deg", ())
        )
        state.perspective_row_after_column_top_angles_deg = tuple(
            getattr(row_audit, "after_column_top_angles_deg", ())
        )
        state.perspective_row_before_column_middle_angles_deg = tuple(
            getattr(row_audit, "before_column_middle_angles_deg", ())
        )
        state.perspective_row_after_column_middle_angles_deg = tuple(
            getattr(row_audit, "after_column_middle_angles_deg", ())
        )
        state.perspective_row_before_column_bottom_angles_deg = tuple(
            getattr(row_audit, "before_column_bottom_angles_deg", ())
        )
        state.perspective_row_after_column_bottom_angles_deg = tuple(
            getattr(row_audit, "after_column_bottom_angles_deg", ())
        )
        state.perspective_row_before_column_trends_deg = tuple(
            getattr(row_audit, "before_column_trends_deg", ())
        )
        state.perspective_row_after_column_trends_deg = tuple(
            getattr(row_audit, "after_column_trends_deg", ())
        )
        state.perspective_row_before_top_angle_deg = row_audit.before_top_angle_deg
        state.perspective_row_after_top_angle_deg = row_audit.after_top_angle_deg
        state.perspective_row_before_bottom_angle_deg = row_audit.before_bottom_angle_deg
        state.perspective_row_after_bottom_angle_deg = row_audit.after_bottom_angle_deg
        state.perspective_row_before_trend_deg = row_audit.before_trend_deg
        state.perspective_row_after_trend_deg = row_audit.after_trend_deg
        state.perspective_row_before_metric_deg = row_audit.before_metric_deg
        state.perspective_row_after_metric_deg = row_audit.after_metric_deg
        state.perspective_row_improvement_ratio = row_audit.improvement_ratio
        state.perspective_row_alignment_verdict = row_audit.verdict

        state.perspective_jacobian_samples = jacobian_audit.sample_count
        state.perspective_jacobian_horizontal_scale_span_ratio = (
            jacobian_audit.horizontal_scale_span_ratio
        )
        state.perspective_jacobian_vertical_scale_span_ratio = (
            jacobian_audit.vertical_scale_span_ratio
        )
        state.perspective_jacobian_area_scale_span_ratio = (
            jacobian_audit.area_scale_span_ratio
        )
        state.perspective_jacobian_anisotropy_p95_ratio = (
            jacobian_audit.anisotropy_p95_ratio
        )
        state.perspective_jacobian_min_determinant = (
            jacobian_audit.min_determinant
        )
        state.perspective_text_scale_samples = text_scale_audit.sample_count
        state.perspective_text_scale_inline_ratio_p05 = text_scale_audit.inline_ratio_p05
        state.perspective_text_scale_inline_ratio_median = (
            text_scale_audit.inline_ratio_median
        )
        state.perspective_text_scale_inline_ratio_p95 = text_scale_audit.inline_ratio_p95
        state.perspective_text_scale_cross_ratio_p05 = text_scale_audit.cross_ratio_p05
        state.perspective_text_scale_cross_ratio_median = (
            text_scale_audit.cross_ratio_median
        )
        state.perspective_text_scale_cross_ratio_p95 = text_scale_audit.cross_ratio_p95
        state.perspective_text_scale_inline_ratio_span_ratio = (
            text_scale_audit.inline_ratio_span_ratio
        )
        state.perspective_text_scale_cross_ratio_span_ratio = (
            text_scale_audit.cross_ratio_span_ratio
        )
        state.perspective_text_scale_inline_ratio_gradient_ratio = (
            text_scale_audit.inline_ratio_gradient_ratio
        )
        state.perspective_text_scale_cross_ratio_gradient_ratio = (
            text_scale_audit.cross_ratio_gradient_ratio
        )
        state.perspective_text_scale_anisotropy_p95_ratio = (
            text_scale_audit.anisotropy_p95_ratio
        )
        state.perspective_text_scale_before_inline_gradient_ratio = (
            text_scale_audit.before_inline_gradient_ratio
        )
        state.perspective_text_scale_after_inline_gradient_ratio = (
            text_scale_audit.after_inline_gradient_ratio
        )
        state.perspective_text_scale_before_cross_gradient_ratio = (
            text_scale_audit.before_cross_gradient_ratio
        )
        state.perspective_text_scale_after_cross_gradient_ratio = (
            text_scale_audit.after_cross_gradient_ratio
        )
        state.perspective_text_scale_before_score = text_scale_audit.before_score
        state.perspective_text_scale_after_score = text_scale_audit.after_score
        state.perspective_text_scale_verdict = text_scale_audit.verdict

    state.perspective_auto_safe = bool(
        requested_geometry_mode == "auto"
        and selected_entry is not None
        and (
            selected_candidate is structural_candidate
            and structural_auto_safe
            or selected_candidate is horizontal_total_candidate
            and horizontal_auto_safe
        )
    )

    if (
        requested_geometry_mode == "auto"
        and selected_candidate is horizontal_total_candidate
        and structural_candidate is not None
        and not structural_auto_safe
    ):
        warnings.append(
            "栏结构候选未通过自动 keystone/尺度安全门；"
            f"已改用安全的优化水平投影（λ={selected_horizontal_strength:.3f}），"
            "不叠加危险的 structural 变换。"
        )
    if (
        requested_geometry_mode == "auto"
        and structural_auto_safe
        and selected_candidate is structural_candidate
        and horizontal_full is not None
        and not horizontal_auto_safe
    ):
        if horizontal_row_audit is not None:
            worst_index = (
                horizontal_row_audit.after_worst_column_index + 1
                if horizontal_row_audit.after_worst_column_index >= 0
                else 0
            )
            warnings.append(
                "已执行安全的栏结构透视，但残余水平投影未通过自动门："
                f"最优强度 {horizontal_strength:.3f}，"
                f"全页行趋势 {horizontal_row_audit.before_trend_deg:+.2f}°→"
                f"{horizontal_row_audit.after_trend_deg:+.2f}°，"
                f"最差区域残余 {horizontal_row_audit.after_worst_region_deg:.2f}°"
                + (
                    f"（第 {worst_index} 栏）"
                    if worst_index else ""
                )
                + "。已保留 structural 结果，未强行继续拉伸文字。"
            )
        else:
            warnings.append(
                "已执行安全的栏结构透视，但残余水平投影证据不足；"
                "已保留 structural 结果。"
            )

    if selected_entry is not None and selected_candidate is not None:
        apply_perspective = bool(
            float(getattr(selected_candidate, "strength_px", 0.0)) >= 0.75
        )
        if apply_perspective:
            state.perspective_matrix = selected_candidate.matrix
            geometry_strength = max(
                geometry_strength,
                float(getattr(selected_candidate, "strength_px", 0.0)),
            )
            working = homography_warper(
                working, state.perspective_matrix,
            )
            working_polygons = selected_entry["polygons"]
            actual_geometry_mode = "perspective"
            method_parts.append("perspective")
            if state.perspective_structural_applied:
                method_parts.append("structural")
            if selected_horizontal_strength > 0.0:
                method_parts.append("horizontal_vp")
                method_parts.append("horizontal_vp_optimized")
    elif requested_geometry_mode == "auto":
        review_reasons: list[str] = []
        if (
            structural_candidate is not None
            and not structural_auto_safe
            and not line_geometry.separator_curve_reliable
        ):
            classification = str(
                getattr(structural_candidate, "classification", "unknown")
            )
            if classification == "parallel_drift":
                review_reasons.append(
                    "栏结构主要呈同向平行漂移，不作为 keystone 自动执行"
                )
            elif not line_supports_perspective:
                review_reasons.append("文本行几何证据不足或与栏结构透视不一致")
            if structural_entry is not None:
                structural_j = structural_entry["jacobian"]
                structural_t = structural_entry["text_scale"]
                if (
                    structural_j.horizontal_scale_span_ratio
                    > horizontal_scale_span_max
                ):
                    review_reasons.append(
                        "栏结构候选横向局部尺度漂移 "
                        f"{structural_j.horizontal_scale_span_ratio * 100:.2f}% 超限"
                    )
                if (
                    structural_j.vertical_scale_span_ratio
                    > vertical_scale_span_max
                ):
                    review_reasons.append(
                        "栏结构候选纵向局部尺度漂移 "
                        f"{structural_j.vertical_scale_span_ratio * 100:.2f}% 超限"
                    )
                if (
                    structural_j.area_scale_span_ratio
                    > area_scale_span_max
                ):
                    review_reasons.append(
                        "栏结构候选局部面积尺度漂移 "
                        f"{structural_j.area_scale_span_ratio * 100:.2f}% 超限"
                    )
                if (
                    structural_j.anisotropy_p95_ratio
                    > anisotropy_p95_max
                ):
                    review_reasons.append(
                        "栏结构候选局部横纵不等比例拉伸 "
                        f"{structural_j.anisotropy_p95_ratio * 100:.2f}% 超限"
                    )
                if structural_t.verdict == "worse":
                    review_reasons.append(
                        "栏结构候选配对文本框尺度场超限："
                        f"行向 {structural_t.inline_ratio_span_ratio * 100:.2f}% / "
                        f"跨行 {structural_t.cross_ratio_span_ratio * 100:.2f}%"
                    )
        if (
            horizontal_full is not None
            and not horizontal_auto_safe
            and not line_geometry.separator_curve_reliable
        ):
            if horizontal_row_audit is not None:
                worst_index = (
                    horizontal_row_audit.after_worst_column_index + 1
                    if horizontal_row_audit.after_worst_column_index >= 0
                    else 0
                )
                spread = float(
                    getattr(
                        horizontal_full,
                        "horizontal_vp_column_spread_deg",
                        0.0,
                    )
                )
                edge_note = ""
                if int(getattr(horizontal_row_audit, "edge_pair_count", 0)) >= 8:
                    edge_note = (
                        "，字框上/下边缘P90 "
                        f"{horizontal_row_audit.after_top_edge_p90_abs_deg:.2f}°/"
                        f"{horizontal_row_audit.after_bottom_edge_p90_abs_deg:.2f}°"
                        "，上下边缘分歧P90 "
                        f"{horizontal_row_audit.after_edge_pair_delta_p90_deg:.2f}°"
                    )
                review_reasons.append(
                    "残余水平投影优化未同时满足分栏水平改善、"
                    "单行上下边缘水平性与尺度安全："
                    f"强度 {horizontal_strength:.3f}，"
                    f"全页Δ角 {horizontal_row_audit.before_trend_deg:+.2f}°→"
                    f"{horizontal_row_audit.after_trend_deg:+.2f}°，"
                    f"最差区域 {horizontal_row_audit.after_worst_region_deg:.2f}°"
                    + (
                        f"（第 {worst_index} 栏）"
                        if worst_index else ""
                    )
                    + edge_note
                    + (
                        f"，栏间VP分歧 {spread:.2f}°"
                        if spread > 0.0 else ""
                    )
                )
            else:
                review_reasons.append("残余水平投影证据不足")
        if review_reasons:
            warnings.append(
                "自动投影候选已拦截：" + "；".join(review_reasons)
                + "。可人工选择“自动透视”复核。"
            )
            method_parts.append("perspective_review")

    if (
        requested_geometry_mode == "perspective"
        and selected_entry is not None
        and not (
            structural_auto_safe
            or horizontal_auto_safe
        )
    ):
        warnings.append(
            "已按用户显式选择执行投影矫正；该候选未通过自动安全门。"
            f"来源={state.perspective_candidate_source}，"
            f"水平强度={state.perspective_horizontal_strength:.3f}，"
            f"行趋势 {state.perspective_row_before_trend_deg:+.2f}°→"
            f"{state.perspective_row_after_trend_deg:+.2f}°。"
        )


    return ProjectiveStageResult(
        working, working_polygons, actual_geometry_mode, geometry_strength,
    )
