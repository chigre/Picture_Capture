from __future__ import annotations

"""Reporting helpers for image preprocessing.

These functions format existing preprocessing analysis into CSV/UI text.
They intentionally do not participate in page analysis or geometry mutation.
"""

import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable

from .image_preprocessing_constants import (
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
from .orthogonal_dewarp import (
    ORTHOGONAL_WARP_MAX_SCALE_DEVIATION,
    PIXEL_ROW_BOTTOM_TAIL_P90_MAX_PX,
    PIXEL_ROW_BOTTOM_TAIL_WORST_MAX_PX,
)
from .preprocess_geometry import (
    HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG,
    HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG,
    HORIZONTAL_ALIGNMENT_MAX_EDGE_PAIR_DELTA_DEG,
    HORIZONTAL_ALIGNMENT_MIN_IMPROVEMENT,
    HORIZONTAL_STRENGTH_COARSE_STEP,
    HORIZONTAL_STRENGTH_FINE_STEP,
    HORIZONTAL_STRENGTH_MIN,
    HORIZONTAL_VP_COLUMN_SPREAD_MAX_DEG,
    HORIZONTAL_VP_MIN_ROWS,
    HORIZONTAL_VP_MIN_TREND_DEG,
    TEXT_SCALE_ANISOTROPY_P95_MAX,
    TEXT_SCALE_CROSS_GRADIENT_MAX,
    TEXT_SCALE_CROSS_SPAN_MAX,
    TEXT_SCALE_INLINE_GRADIENT_MAX,
    TEXT_SCALE_INLINE_SPAN_MAX,
)
from .text_line_geometry import (
    SEPARATOR_CURVATURE_SCORE_MIN,
    SEPARATOR_CURVE_SPAN_MIN,
    SEPARATOR_CURVE_WIDTH_RATIO_THRESHOLD,
    SEPARATOR_JUMP_MIN_PX,
    SEPARATOR_JUMP_WIDTH_RATIO_MAX,
    SEPARATOR_TRACK_QUALITY_MIN,
)

if TYPE_CHECKING:
    from .image_preprocessing_models import OutputCanvasInfo, PreprocessAnalysis
    from .models import AppSettings


def export_summary_csv(
    records: Iterable[tuple[Path, PreprocessAnalysis, Path, OutputCanvasInfo]],
    destination: Path,
) -> Path:
    rows = []
    for page, analysis, output_path, canvas in records:
        rows.append({
            "page": Path(page).name,
            "status": analysis.status,
            "confidence": round(float(analysis.confidence), 4),
            "method": analysis.method,
            "warnings": " | ".join(analysis.warnings),
            "source_width": analysis.source_width,
            "source_height": analysis.source_height,
            "applied_angle_deg": analysis.applied_angle_deg,
            "correction_angle_deg": analysis.correction_angle_deg,
            "ocr_correction_angle_deg": analysis.ocr_correction_angle_deg,
            "deskew_anchor_source": analysis.deskew_anchor_source,
            "source_header_rule_point_count": analysis.source_header_rule_point_count,
            "source_header_rule_angle_deg": analysis.source_header_rule_angle_deg,
            "source_header_rule_residual_px": analysis.source_header_rule_residual_px,
            "angle_samples": analysis.angle_samples,
            "angle_mad_deg": analysis.angle_mad_deg,
            "requested_geometry_mode": analysis.requested_geometry_mode,
            "geometry_mode": analysis.geometry_mode,
            "geometry_strength_px": analysis.geometry_strength_px,
            "perspective_candidate_strength_px": analysis.perspective_candidate_strength_px,
            "perspective_classification": analysis.perspective_classification,
            "perspective_candidate_source": analysis.perspective_candidate_source,
            "perspective_horizontal_vanishing_x": (
                analysis.perspective_horizontal_vanishing_x
            ),
            "perspective_horizontal_vanishing_y": (
                analysis.perspective_horizontal_vanishing_y
            ),
            "perspective_horizontal_row_count": (
                analysis.perspective_horizontal_row_count
            ),
            "perspective_horizontal_column_count": (
                analysis.perspective_horizontal_column_count
            ),
            "perspective_horizontal_vp_column_spread_deg": (
                analysis.perspective_horizontal_vp_column_spread_deg
            ),
            "perspective_horizontal_strength": (
                analysis.perspective_horizontal_strength
            ),
            "perspective_structural_applied": (
                analysis.perspective_structural_applied
            ),
            "perspective_structural_safe": (
                analysis.perspective_structural_safe
            ),
            "perspective_row_valid_column_count": (
                analysis.perspective_row_valid_column_count
            ),
            "perspective_row_valid_column_indices": json.dumps(
                analysis.perspective_row_valid_column_indices,
                ensure_ascii=False,
            ),
            "perspective_row_column_row_counts": json.dumps(
                analysis.perspective_row_column_row_counts,
                ensure_ascii=False,
            ),
            "perspective_row_after_worst_region_deg": (
                analysis.perspective_row_after_worst_region_deg
            ),
            "perspective_row_after_worst_column_metric_deg": (
                analysis.perspective_row_after_worst_column_metric_deg
            ),
            "perspective_row_after_worst_column_index": (
                analysis.perspective_row_after_worst_column_index
            ),
            "perspective_row_before_column_top_angles_deg": json.dumps(
                analysis.perspective_row_before_column_top_angles_deg,
                ensure_ascii=False,
            ),
            "perspective_row_after_column_top_angles_deg": json.dumps(
                analysis.perspective_row_after_column_top_angles_deg,
                ensure_ascii=False,
            ),
            "perspective_row_before_column_middle_angles_deg": json.dumps(
                analysis.perspective_row_before_column_middle_angles_deg,
                ensure_ascii=False,
            ),
            "perspective_row_after_column_middle_angles_deg": json.dumps(
                analysis.perspective_row_after_column_middle_angles_deg,
                ensure_ascii=False,
            ),
            "perspective_row_before_column_bottom_angles_deg": json.dumps(
                analysis.perspective_row_before_column_bottom_angles_deg,
                ensure_ascii=False,
            ),
            "perspective_row_after_column_bottom_angles_deg": json.dumps(
                analysis.perspective_row_after_column_bottom_angles_deg,
                ensure_ascii=False,
            ),
            "perspective_row_before_column_trends_deg": json.dumps(
                analysis.perspective_row_before_column_trends_deg,
                ensure_ascii=False,
            ),
            "perspective_row_after_column_trends_deg": json.dumps(
                analysis.perspective_row_after_column_trends_deg,
                ensure_ascii=False,
            ),
            "perspective_row_before_top_angle_deg": (
                analysis.perspective_row_before_top_angle_deg
            ),
            "perspective_row_after_top_angle_deg": (
                analysis.perspective_row_after_top_angle_deg
            ),
            "perspective_row_before_bottom_angle_deg": (
                analysis.perspective_row_before_bottom_angle_deg
            ),
            "perspective_row_after_bottom_angle_deg": (
                analysis.perspective_row_after_bottom_angle_deg
            ),
            "perspective_row_before_trend_deg": (
                analysis.perspective_row_before_trend_deg
            ),
            "perspective_row_after_trend_deg": (
                analysis.perspective_row_after_trend_deg
            ),
            "perspective_row_before_metric_deg": (
                analysis.perspective_row_before_metric_deg
            ),
            "perspective_row_after_metric_deg": (
                analysis.perspective_row_after_metric_deg
            ),
            "perspective_row_improvement_ratio": (
                analysis.perspective_row_improvement_ratio
            ),
            "perspective_row_alignment_verdict": (
                analysis.perspective_row_alignment_verdict
            ),
            "perspective_left_drift_px": analysis.perspective_left_drift_px,
            "perspective_right_drift_px": analysis.perspective_right_drift_px,
            "perspective_common_drift_px": analysis.perspective_common_drift_px,
            "perspective_width_delta_px": analysis.perspective_width_delta_px,
            "perspective_width_change_ratio": analysis.perspective_width_change_ratio,
            "perspective_scale_top": analysis.perspective_scale_top,
            "perspective_scale_bottom": analysis.perspective_scale_bottom,
            "perspective_scale_delta_ratio": analysis.perspective_scale_delta_ratio,
            "perspective_jacobian_samples": analysis.perspective_jacobian_samples,
            "perspective_jacobian_horizontal_scale_span_ratio": (
                analysis.perspective_jacobian_horizontal_scale_span_ratio
            ),
            "perspective_jacobian_vertical_scale_span_ratio": (
                analysis.perspective_jacobian_vertical_scale_span_ratio
            ),
            "perspective_jacobian_area_scale_span_ratio": (
                analysis.perspective_jacobian_area_scale_span_ratio
            ),
            "perspective_jacobian_anisotropy_p95_ratio": (
                analysis.perspective_jacobian_anisotropy_p95_ratio
            ),
            "perspective_jacobian_min_determinant": (
                analysis.perspective_jacobian_min_determinant
            ),
            "perspective_text_scale_samples": analysis.perspective_text_scale_samples,
            "perspective_text_scale_inline_ratio_p05": (
                analysis.perspective_text_scale_inline_ratio_p05
            ),
            "perspective_text_scale_inline_ratio_median": (
                analysis.perspective_text_scale_inline_ratio_median
            ),
            "perspective_text_scale_inline_ratio_p95": (
                analysis.perspective_text_scale_inline_ratio_p95
            ),
            "perspective_text_scale_cross_ratio_p05": (
                analysis.perspective_text_scale_cross_ratio_p05
            ),
            "perspective_text_scale_cross_ratio_median": (
                analysis.perspective_text_scale_cross_ratio_median
            ),
            "perspective_text_scale_cross_ratio_p95": (
                analysis.perspective_text_scale_cross_ratio_p95
            ),
            "perspective_text_scale_inline_ratio_span_ratio": (
                analysis.perspective_text_scale_inline_ratio_span_ratio
            ),
            "perspective_text_scale_cross_ratio_span_ratio": (
                analysis.perspective_text_scale_cross_ratio_span_ratio
            ),
            "perspective_text_scale_inline_ratio_gradient_ratio": (
                analysis.perspective_text_scale_inline_ratio_gradient_ratio
            ),
            "perspective_text_scale_cross_ratio_gradient_ratio": (
                analysis.perspective_text_scale_cross_ratio_gradient_ratio
            ),
            "perspective_text_scale_anisotropy_p95_ratio": (
                analysis.perspective_text_scale_anisotropy_p95_ratio
            ),
            "perspective_text_scale_before_inline_gradient_ratio": (
                analysis.perspective_text_scale_before_inline_gradient_ratio
            ),
            "perspective_text_scale_after_inline_gradient_ratio": (
                analysis.perspective_text_scale_after_inline_gradient_ratio
            ),
            "perspective_text_scale_before_cross_gradient_ratio": (
                analysis.perspective_text_scale_before_cross_gradient_ratio
            ),
            "perspective_text_scale_after_cross_gradient_ratio": (
                analysis.perspective_text_scale_after_cross_gradient_ratio
            ),
            "perspective_text_scale_before_score": (
                analysis.perspective_text_scale_before_score
            ),
            "perspective_text_scale_after_score": (
                analysis.perspective_text_scale_after_score
            ),
            "perspective_text_scale_verdict": (
                analysis.perspective_text_scale_verdict
            ),
            "perspective_auto_safe": analysis.perspective_auto_safe,
            "crop_x0": analysis.crop_box[0],
            "crop_y0": analysis.crop_box[1],
            "crop_x1": analysis.crop_box[2],
            "crop_y1": analysis.crop_box[3],
            "content_width": analysis.crop_box[2] - analysis.crop_box[0],
            "content_height": analysis.crop_box[3] - analysis.crop_box[1],
            "retained_ratio": round(float(analysis.retained_ratio), 6),
            "safety_margin_px": analysis.safety_margin_px,
            "line_geometry_rows": analysis.line_geometry_rows,
            "line_geometry_global_angle_deg": analysis.line_geometry_global_angle_deg,
            "line_geometry_top_angle_deg": analysis.line_geometry_top_angle_deg,
            "line_geometry_middle_angle_deg": analysis.line_geometry_middle_angle_deg,
            "line_geometry_bottom_angle_deg": analysis.line_geometry_bottom_angle_deg,
            "line_geometry_trend_deg": analysis.line_geometry_trend_deg,
            "line_geometry_residual_mad_deg": analysis.line_geometry_residual_mad_deg,
            "line_geometry_residual_span_deg": analysis.line_geometry_residual_span_deg,
            "line_geometry_columns": analysis.line_geometry_columns,
            "line_geometry_valid_columns": analysis.line_geometry_valid_columns,
            "line_geometry_valid_column_indices": json.dumps(
                analysis.line_geometry_valid_column_indices,
                ensure_ascii=False,
            ),
            "line_geometry_column_row_counts": json.dumps(
                analysis.line_geometry_column_row_counts,
                ensure_ascii=False,
            ),
            "line_geometry_column_trends_deg": json.dumps(
                analysis.line_geometry_column_trends_deg,
                ensure_ascii=False,
            ),
            "line_geometry_worst_column_index": (
                analysis.line_geometry_worst_column_index
            ),
            "line_geometry_worst_column_trend_deg": (
                analysis.line_geometry_worst_column_trend_deg
            ),
            "line_geometry_worst_region_angle_deg": (
                analysis.line_geometry_worst_region_angle_deg
            ),
            "separator_found": analysis.line_geometry_separator_found,
            "separator_residual_px": analysis.line_geometry_separator_residual_px,
            "separator_span_ratio": analysis.line_geometry_separator_span_ratio,
            "separator_slope_px_per_1000y": analysis.line_geometry_separator_slope_px_per_1000y,
            "separator_drift_px": analysis.line_geometry_separator_drift_px,
            "separator_track_quality": analysis.line_geometry_separator_track_quality,
            "separator_track_jump_p95_px": (
                analysis.line_geometry_separator_track_jump_p95_px
            ),
            "separator_curvature_score": (
                analysis.line_geometry_separator_curvature_score
            ),
            "separator_curve_reliable": (
                analysis.line_geometry_separator_curve_reliable
            ),
            "line_geometry_recommendation": analysis.line_geometry_recommendation,
            "line_geometry_confidence": analysis.line_geometry_confidence,
            "orthogonal_applied": analysis.orthogonal_applied,
            "orthogonal_passes": analysis.orthogonal_passes,
            "orthogonal_step_count": len(analysis.orthogonal_steps),
            "orthogonal_row_count": analysis.orthogonal_row_count,
            "orthogonal_valid_column_count": (
                analysis.orthogonal_valid_column_count
            ),
            "orthogonal_separator_point_count": (
                analysis.orthogonal_separator_point_count
            ),
            "orthogonal_row_gain": analysis.orthogonal_row_gain,
            "orthogonal_row_grid_rows": analysis.orthogonal_row_grid_rows,
            "orthogonal_row_grid_cols": analysis.orthogonal_row_grid_cols,
            "orthogonal_horizontal_rule_point_count": (
                analysis.orthogonal_horizontal_rule_point_count
            ),
            "orthogonal_horizontal_rule_y": (
                analysis.orthogonal_horizontal_rule_y
            ),
            "orthogonal_before_horizontal_rule_angle_deg": (
                analysis.orthogonal_before_horizontal_rule_angle_deg
            ),
            "orthogonal_after_horizontal_rule_angle_deg": (
                analysis.orthogonal_after_horizontal_rule_angle_deg
            ),
            "orthogonal_before_horizontal_rule_residual_px": (
                analysis.orthogonal_before_horizontal_rule_residual_px
            ),
            "orthogonal_after_horizontal_rule_residual_px": (
                analysis.orthogonal_after_horizontal_rule_residual_px
            ),
            "orthogonal_horizontal_rule_verdict": (
                analysis.orthogonal_horizontal_rule_verdict
            ),
            "orthogonal_pixel_angle_sample_count": (
                analysis.orthogonal_pixel_angle_sample_count
            ),
            "orthogonal_pixel_angle_used_count": (
                analysis.orthogonal_pixel_angle_used_count
            ),
            "orthogonal_pixel_angle_confidence": (
                analysis.orthogonal_pixel_angle_confidence
            ),
            "orthogonal_pixel_row_sample_count": (
                analysis.orthogonal_pixel_row_sample_count
            ),
            "orthogonal_before_pixel_row_p90_px": (
                analysis.orthogonal_before_pixel_row_p90_px
            ),
            "orthogonal_after_pixel_row_p90_px": (
                analysis.orthogonal_after_pixel_row_p90_px
            ),
            "orthogonal_before_pixel_row_worst_px": (
                analysis.orthogonal_before_pixel_row_worst_px
            ),
            "orthogonal_after_pixel_row_worst_px": (
                analysis.orthogonal_after_pixel_row_worst_px
            ),
            "orthogonal_pixel_row_verdict": (
                analysis.orthogonal_pixel_row_verdict
            ),
            "orthogonal_bottom_tail_sample_count": (
                analysis.orthogonal_bottom_tail_sample_count
            ),
            "orthogonal_before_bottom_tail_p90_px": (
                analysis.orthogonal_before_bottom_tail_p90_px
            ),
            "orthogonal_after_bottom_tail_p90_px": (
                analysis.orthogonal_after_bottom_tail_p90_px
            ),
            "orthogonal_before_bottom_tail_worst_px": (
                analysis.orthogonal_before_bottom_tail_worst_px
            ),
            "orthogonal_after_bottom_tail_worst_px": (
                analysis.orthogonal_after_bottom_tail_worst_px
            ),
            "orthogonal_bottom_tail_verdict": (
                analysis.orthogonal_bottom_tail_verdict
            ),
            "orthogonal_safe_gain_cap": analysis.orthogonal_safe_gain_cap,
            "orthogonal_confidence": analysis.orthogonal_confidence,
            "orthogonal_column_spread_deg": (
                analysis.orthogonal_column_spread_deg
            ),
            "orthogonal_max_row_angle_deg": (
                analysis.orthogonal_max_row_angle_deg
            ),
            "orthogonal_row_angle_span_deg": (
                analysis.orthogonal_row_angle_span_deg
            ),
            "orthogonal_max_horizontal_shift_px": (
                analysis.orthogonal_max_horizontal_shift_px
            ),
            "orthogonal_max_vertical_shift_px": (
                analysis.orthogonal_max_vertical_shift_px
            ),
            "orthogonal_max_scale_deviation": (
                analysis.orthogonal_max_scale_deviation
            ),
            "orthogonal_before_quality_score": (
                analysis.orthogonal_before_quality_score
            ),
            "orthogonal_after_quality_score": (
                analysis.orthogonal_after_quality_score
            ),
            "orthogonal_before_separator_span_px": (
                analysis.orthogonal_before_separator_span_px
            ),
            "orthogonal_after_separator_span_px": (
                analysis.orthogonal_after_separator_span_px
            ),
            "orthogonal_vertical_verdict": (
                analysis.orthogonal_vertical_verdict
            ),
            "orthogonal_alignment_verdict": (
                analysis.orthogonal_alignment_verdict
            ),
            "final_alignment_row_count": analysis.final_alignment_row_count,
            "final_alignment_valid_column_count": (
                analysis.final_alignment_valid_column_count
            ),
            "final_alignment_edge_pair_count": (
                analysis.final_alignment_edge_pair_count
            ),
            "final_alignment_top_edge_p90_abs_deg": (
                analysis.final_alignment_top_edge_p90_abs_deg
            ),
            "final_alignment_bottom_edge_p90_abs_deg": (
                analysis.final_alignment_bottom_edge_p90_abs_deg
            ),
            "final_alignment_edge_pair_delta_p90_deg": (
                analysis.final_alignment_edge_pair_delta_p90_deg
            ),
            "final_alignment_worst_edge_deg": (
                analysis.final_alignment_worst_edge_deg
            ),
            "final_alignment_worst_region_deg": (
                analysis.final_alignment_worst_region_deg
            ),
            "final_alignment_trend_deg": analysis.final_alignment_trend_deg,
            "final_alignment_worst_column_trend_deg": (
                analysis.final_alignment_worst_column_trend_deg
            ),
            "final_alignment_quality_score": (
                analysis.final_alignment_quality_score
            ),
            "final_alignment_verdict": analysis.final_alignment_verdict,
            "canvas_enabled": canvas.enabled,
            "canvas_mode": canvas.mode,
            "canvas_requested_width": canvas.requested_width,
            "canvas_requested_height": canvas.requested_height,
            "canvas_width": canvas.width,
            "canvas_height": canvas.height,
            "canvas_margin_top": canvas.margin_top,
            "canvas_margin_bottom": canvas.margin_bottom,
            "canvas_margin_left": canvas.margin_left,
            "canvas_margin_right": canvas.margin_right,
            "canvas_body_x0": canvas.body_box[0],
            "canvas_body_y0": canvas.body_box[1],
            "canvas_body_x1": canvas.body_box[2],
            "canvas_body_y1": canvas.body_box[3],
            "canvas_align_x": canvas.align_x,
            "canvas_align_y": canvas.align_y,
            "canvas_content_x0": canvas.content_box[0],
            "canvas_content_y0": canvas.content_box[1],
            "canvas_content_x1": canvas.content_box[2],
            "canvas_content_y1": canvas.content_box[3],
            "canvas_expanded_width": canvas.expanded_width,
            "canvas_expanded_height": canvas.expanded_height,
            "output_filename": Path(output_path).name,
        })
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "page", "status", "confidence", "warnings", "output_filename"
    ]
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)
    return destination


def result_summary(analysis: PreprocessAnalysis) -> str:
    x0, y0, x1, y1 = analysis.crop_box
    label = "需检查" if analysis.status == "review" else "正常"
    geometry_labels = {
        "deskew": "轻量纠偏",
        "perspective": "透视纠正",
        "manual_perspective": "手动四角",
        "uvdoc": "UVDoc 展平",
        "orthogonal": "正交网格展平",
    }
    geometry = geometry_labels.get(analysis.geometry_mode, analysis.geometry_mode)
    if (
        analysis.manual_perspective_quad is not None
        and analysis.geometry_mode == "uvdoc"
    ):
        geometry = "手动四角+UVDoc"
    strength = (
        f" {analysis.geometry_strength_px:.1f}px"
        if analysis.geometry_mode in {
            "manual_perspective", "perspective", "orthogonal"
        }
        and analysis.geometry_strength_px > 0
        else ""
    )
    line_labels = {
        "none": "无需额外",
        "deskew": "旋转",
        "perspective": "透视",
        "uvdoc_review": "非线性弯曲",
        "manual_review": "人工复核",
        "insufficient": "证据不足",
    }
    perspective_part = ""
    if analysis.perspective_candidate_strength_px > 0:
        audit_part = ""
        if analysis.perspective_jacobian_samples:
            audit_part = (
                " / J尺度漂移 "
                f"X{analysis.perspective_jacobian_horizontal_scale_span_ratio * 100:.1f}%"
                f" Y{analysis.perspective_jacobian_vertical_scale_span_ratio * 100:.1f}%"
            )
        text_scale_part = ""
        if analysis.perspective_text_scale_samples:
            text_scale_label = {
                "stable": "稳定",
                "worse": "超限",
                "insufficient": "证据不足",
            }.get(
                analysis.perspective_text_scale_verdict,
                analysis.perspective_text_scale_verdict,
            )
            text_scale_part = (
                f" / 配对尺度 {text_scale_label}"
                f" I{analysis.perspective_text_scale_inline_ratio_span_ratio * 100:.1f}%"
                f" C{analysis.perspective_text_scale_cross_ratio_span_ratio * 100:.1f}%"
            )
        row_part = ""
        if analysis.perspective_row_alignment_verdict != "insufficient":
            strength_part = (
                f" λ={analysis.perspective_horizontal_strength:.3f}"
                if analysis.perspective_horizontal_strength > 0
                else ""
            )
            column_part = ""
            if analysis.perspective_row_valid_column_count:
                total_columns = max(
                    analysis.perspective_horizontal_column_count,
                    analysis.perspective_row_valid_column_count,
                )
                worst_column = (
                    analysis.perspective_row_after_worst_column_index + 1
                    if analysis.perspective_row_after_worst_column_index >= 0
                    else 0
                )
                column_part = (
                    f" / 分栏 {analysis.perspective_row_valid_column_count}"
                    f"/{total_columns}"
                    f" 最差区域 {analysis.perspective_row_after_worst_region_deg:.2f}°"
                    + (
                        f"(第{worst_column}栏)"
                        if worst_column else ""
                    )
                )
                if analysis.perspective_horizontal_vp_column_spread_deg > 0:
                    column_part += (
                        " VP分歧 "
                        f"{analysis.perspective_horizontal_vp_column_spread_deg:.2f}°"
                    )
            row_part = (
                f" / 行趋势 {analysis.perspective_row_before_trend_deg:+.2f}°"
                f"→{analysis.perspective_row_after_trend_deg:+.2f}°"
                f"{strength_part}{column_part}"
            )
        perspective_part = (
            f"｜投影候选 {analysis.perspective_candidate_strength_px:.1f}px"
            f" / {analysis.perspective_candidate_source}"
            f" / 旧尺度差 {analysis.perspective_scale_delta_ratio * 100:.2f}%"
            f"{row_part}{audit_part}{text_scale_part}"
            f" / {analysis.perspective_classification}"
        )
    line_part = ""
    if analysis.line_geometry_rows:
        separator = ""
        if analysis.line_geometry_separator_found:
            curve_flag = (
                " 曲率可靠"
                if analysis.line_geometry_separator_curve_reliable
                else ""
            )
            separator = (
                f"｜实体线残差 {analysis.line_geometry_separator_residual_px:.1f}px"
                f" 跳变P95 {analysis.line_geometry_separator_track_jump_p95_px:.1f}px"
                f"{curve_flag}"
            )
        column_geometry = ""
        if analysis.line_geometry_valid_columns:
            worst_column = (
                analysis.line_geometry_worst_column_index + 1
                if analysis.line_geometry_worst_column_index >= 0
                else 0
            )
            column_geometry = (
                f" {analysis.line_geometry_valid_columns}/"
                f"{max(analysis.line_geometry_columns, analysis.line_geometry_valid_columns)}栏"
                + (
                    f" 最差第{worst_column}栏"
                    f" Δ{analysis.line_geometry_worst_column_trend_deg:+.2f}°"
                    if worst_column else ""
                )
            )
        line_part = (
            f"｜行几何 {analysis.line_geometry_rows}行{column_geometry}"
            f" 全页Δ角 {analysis.line_geometry_trend_deg:+.2f}°"
            f"{separator}"
            f" → {line_labels.get(analysis.line_geometry_recommendation, analysis.line_geometry_recommendation)}"
        )
    orthogonal_part = ""
    if analysis.orthogonal_applied:
        orthogonal_part = (
            f"｜正交闭环 {analysis.orthogonal_alignment_verdict}"
            f" gain={analysis.orthogonal_row_gain:.2f}"
            f" 角场±{analysis.orthogonal_max_row_angle_deg:.2f}°"
            f" 纵移≤{analysis.orthogonal_max_vertical_shift_px:.1f}px"
            f" 横移≤{analysis.orthogonal_max_horizontal_shift_px:.1f}px"
            f" 质量 {analysis.orthogonal_before_quality_score:.2f}"
            f"→{analysis.orthogonal_after_quality_score:.2f}"
            + (
                f" 竖线{analysis.orthogonal_vertical_verdict}"
                f" {analysis.orthogonal_before_separator_span_px:.1f}"
                f"→{analysis.orthogonal_after_separator_span_px:.1f}px"
                if analysis.orthogonal_vertical_verdict != "insufficient"
                else ""
            )
        )
    final_alignment_part = ""
    if analysis.final_alignment_verdict != "insufficient":
        final_label = (
            "通过" if analysis.final_alignment_verdict == "passed" else "未通过"
        )
        final_alignment_part = (
            f"｜成品水平{final_label}"
            f" 上缘P90 {analysis.final_alignment_top_edge_p90_abs_deg:.2f}°"
            f" 下缘P90 {analysis.final_alignment_bottom_edge_p90_abs_deg:.2f}°"
            f" 上下缘差P90 {analysis.final_alignment_edge_pair_delta_p90_deg:.2f}°"
            f" 最差栏趋势 {analysis.final_alignment_worst_column_trend_deg:.2f}°"
        )
    return (
        f"{label}｜{geometry}{strength}｜"
        f"旋转 {analysis.applied_angle_deg:+.2f}°"
        f"（检测 {analysis.correction_angle_deg:+.2f}°）"
        f"{perspective_part}{line_part}{orthogonal_part}{final_alignment_part}｜"
        f"保留 {analysis.retained_ratio * 100:.1f}%｜"
        f"裁剪 L{x0} T{y0} R{x1} B{y1}"
    )

def _export_diagnostic_json_impl(
    page: Path,
    analysis: PreprocessAnalysis,
    destination: Path,
    *,
    output_path: Path | None = None,
    canvas: OutputCanvasInfo | None = None,
    settings: AppSettings | None = None,
    canvas_info_factory: Callable[..., OutputCanvasInfo],
) -> Path:
    payload = analysis.to_dict()
    payload["page"] = Path(page).name
    payload["source_path_name"] = Path(page).name
    payload["effective_settings"] = (
        {
            "layout_writing_mode": str(settings.layout_writing_mode),
            "layout_text_direction": str(settings.layout_text_direction),
            "layout_transform": str(settings.layout_transform),
            "layout_columns_policy": str(settings.layout_columns_policy),
            "fixed_columns": int(settings.columns),
            "layout_column_separator_mode": str(
                settings.layout_column_separator_mode
            ),
            "analysis_threshold_mode": str(settings.analysis_threshold_mode),
            "preprocess_auto_deskew": bool(
                settings.preprocess_auto_deskew
            ),
            "preprocess_safety_margin_px": int(
                settings.preprocess_safety_margin_px
            ),
            "preprocess_geometry_mode": str(
                settings.preprocess_geometry_mode
            ),
            "preprocess_export_canvas_enabled": bool(
                settings.preprocess_export_canvas_enabled
            ),
            "preprocess_export_canvas_mode": str(
                settings.preprocess_export_canvas_mode
            ),
            "preprocess_export_canvas_width": int(
                settings.preprocess_export_canvas_width
            ),
            "preprocess_export_canvas_height": int(
                settings.preprocess_export_canvas_height
            ),
            "preprocess_export_margin_top": int(
                settings.preprocess_export_margin_top
            ),
            "preprocess_export_margin_bottom": int(
                settings.preprocess_export_margin_bottom
            ),
            "preprocess_export_margin_left": int(
                settings.preprocess_export_margin_left
            ),
            "preprocess_export_margin_right": int(
                settings.preprocess_export_margin_right
            ),
            "preprocess_export_align_x": str(
                settings.preprocess_export_align_x
            ),
            "preprocess_export_align_y": str(
                settings.preprocess_export_align_y
            ),
        }
        if settings is not None else None
    )
    payload["algorithm_constants"] = {
        "max_auto_deskew_deg": DEFAULT_MAX_AUTO_DESKEW_DEG,
        "deskew_dead_zone_deg": DEFAULT_DESKEW_DEAD_ZONE_DEG,
        "auto_homography_horizontal_scale_span_max": (
            AUTO_HOMOGRAPHY_HORIZONTAL_SCALE_SPAN_MAX
        ),
        "auto_homography_vertical_scale_span_max": (
            AUTO_HOMOGRAPHY_VERTICAL_SCALE_SPAN_MAX
        ),
        "auto_homography_area_scale_span_max": (
            AUTO_HOMOGRAPHY_AREA_SCALE_SPAN_MAX
        ),
        "auto_homography_anisotropy_p95_max": (
            AUTO_HOMOGRAPHY_ANISOTROPY_P95_MAX
        ),
        "orthogonal_auto_min_confidence": ORTHOGONAL_AUTO_MIN_CONFIDENCE,
        "orthogonal_auto_min_score_improvement": (
            ORTHOGONAL_AUTO_MIN_SCORE_IMPROVEMENT
        ),
        "orthogonal_auto_gains": list(ORTHOGONAL_AUTO_GAINS),
        "orthogonal_min_safe_gain": ORTHOGONAL_MIN_SAFE_GAIN,
        "orthogonal_scale_safety_fraction": ORTHOGONAL_SCALE_SAFETY_FRACTION,
        "orthogonal_tail_progress_ratio": ORTHOGONAL_TAIL_PROGRESS_RATIO,
        "orthogonal_tail_max_regression_px": (
            ORTHOGONAL_TAIL_MAX_REGRESSION_PX
        ),
        "pixel_row_bottom_tail_p90_max_px": (
            PIXEL_ROW_BOTTOM_TAIL_P90_MAX_PX
        ),
        "pixel_row_bottom_tail_worst_max_px": (
            PIXEL_ROW_BOTTOM_TAIL_WORST_MAX_PX
        ),
        "orthogonal_max_auto_passes": ORTHOGONAL_MAX_AUTO_PASSES,
        "post_perspective_redetect_min_boxes": (
            POST_PERSPECTIVE_REDETECT_MIN_BOXES
        ),
        "orthogonal_warp_max_scale_deviation": (
            ORTHOGONAL_WARP_MAX_SCALE_DEVIATION
        ),
        "orthogonal_vertical_max_span_min_px": (
            ORTHOGONAL_VERTICAL_MAX_SPAN_MIN_PX
        ),
        "orthogonal_vertical_max_span_width_ratio": (
            ORTHOGONAL_VERTICAL_MAX_SPAN_WIDTH_RATIO
        ),
        "horizontal_alignment_max_edge_pair_delta_deg": (
            HORIZONTAL_ALIGNMENT_MAX_EDGE_PAIR_DELTA_DEG
        ),
        "text_scale_inline_span_max": TEXT_SCALE_INLINE_SPAN_MAX,
        "text_scale_cross_span_max": TEXT_SCALE_CROSS_SPAN_MAX,
        "text_scale_inline_gradient_max": TEXT_SCALE_INLINE_GRADIENT_MAX,
        "text_scale_cross_gradient_max": TEXT_SCALE_CROSS_GRADIENT_MAX,
        "text_scale_anisotropy_p95_max": TEXT_SCALE_ANISOTROPY_P95_MAX,
        "horizontal_vp_min_rows": HORIZONTAL_VP_MIN_ROWS,
        "horizontal_vp_min_trend_deg": HORIZONTAL_VP_MIN_TREND_DEG,
        "horizontal_alignment_min_improvement": (
            HORIZONTAL_ALIGNMENT_MIN_IMPROVEMENT
        ),
        "horizontal_alignment_max_after_trend_deg": (
            HORIZONTAL_ALIGNMENT_MAX_AFTER_TREND_DEG
        ),
        "horizontal_alignment_max_after_edge_deg": (
            HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG
        ),
        "horizontal_vp_column_spread_max_deg": (
            HORIZONTAL_VP_COLUMN_SPREAD_MAX_DEG
        ),
        "horizontal_strength_min": HORIZONTAL_STRENGTH_MIN,
        "horizontal_strength_coarse_step": HORIZONTAL_STRENGTH_COARSE_STEP,
        "horizontal_strength_fine_step": HORIZONTAL_STRENGTH_FINE_STEP,
        "separator_curve_span_min": SEPARATOR_CURVE_SPAN_MIN,
        "separator_track_quality_min": SEPARATOR_TRACK_QUALITY_MIN,
        "separator_curvature_score_min": SEPARATOR_CURVATURE_SCORE_MIN,
        "separator_curve_width_ratio_threshold": (
            SEPARATOR_CURVE_WIDTH_RATIO_THRESHOLD
        ),
        "separator_jump_min_px": SEPARATOR_JUMP_MIN_PX,
        "separator_jump_width_ratio_max": SEPARATOR_JUMP_WIDTH_RATIO_MAX,
    }
    payload["export"] = {
        "output_filename": Path(output_path).name if output_path is not None else None,
        "content_width": max(1, analysis.crop_box[2] - analysis.crop_box[0]),
        "content_height": max(1, analysis.crop_box[3] - analysis.crop_box[1]),
        "canvas": (
            canvas.to_dict()
            if canvas is not None
            else canvas_info_factory(analysis, enabled=False).to_dict()
        ),
    }
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination

