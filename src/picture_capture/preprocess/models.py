from __future__ import annotations

"""Stable data models and serialization contract for image preprocessing."""

from dataclasses import asdict, dataclass

PREPROCESS_FORMAT = "picture-capture-image-preprocess"
PREPROCESS_FORMAT_VERSION = 24
DEFAULT_SAFETY_MARGIN_PX = 20


@dataclass(frozen=True, slots=True)
class OutputCanvasInfo:
    enabled: bool
    mode: str
    requested_width: int
    requested_height: int
    width: int
    height: int
    margin_top: int
    margin_bottom: int
    margin_left: int
    margin_right: int
    body_box: tuple[int, int, int, int]
    align_x: str
    align_y: str
    content_box: tuple[int, int, int, int]
    expanded_width: bool = False
    expanded_height: bool = False

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["body_box"] = list(self.body_box)
        payload["content_box"] = list(self.content_box)
        payload["background"] = "white"
        return payload


@dataclass(slots=True)
class PreprocessAnalysis:
    source_width: int
    source_height: int
    correction_angle_deg: float
    applied_angle_deg: float
    crop_box: tuple[int, int, int, int]
    raw_content_box: tuple[int, int, int, int]
    text_box: tuple[int, int, int, int] | None
    source_boxes: int
    angle_samples: int
    angle_mad_deg: float
    retained_ratio: float
    confidence: float
    status: str
    method: str
    ocr_correction_angle_deg: float = 0.0
    deskew_anchor_source: str = "ocr"
    source_header_rule_point_count: int = 0
    source_header_rule_angle_deg: float = 0.0
    source_header_rule_residual_px: float = 0.0
    warnings: tuple[str, ...] = ()
    safety_margin_px: int = DEFAULT_SAFETY_MARGIN_PX
    auto_deskew: bool = True
    requested_geometry_mode: str = "auto"
    geometry_mode: str = "deskew"
    geometry_strength_px: float = 0.0
    perspective_matrix: tuple[float, ...] | None = None
    perspective_source_quad: tuple[float, ...] | None = None
    perspective_target_quad: tuple[float, ...] | None = None
    perspective_classification: str = "none"
    perspective_candidate_source: str = "none"
    perspective_horizontal_vanishing_x: float = 0.0
    perspective_horizontal_vanishing_y: float = 0.0
    perspective_horizontal_row_count: int = 0
    perspective_horizontal_column_count: int = 0
    perspective_horizontal_vp_column_spread_deg: float = 0.0
    perspective_horizontal_strength: float = 0.0
    perspective_row_valid_column_count: int = 0
    perspective_row_valid_column_indices: tuple[int, ...] = ()
    perspective_row_column_row_counts: tuple[int, ...] = ()
    perspective_row_after_worst_region_deg: float = 0.0
    perspective_row_after_worst_column_metric_deg: float = 0.0
    perspective_row_after_worst_column_index: int = -1
    perspective_row_before_column_top_angles_deg: tuple[float, ...] = ()
    perspective_row_after_column_top_angles_deg: tuple[float, ...] = ()
    perspective_row_before_column_middle_angles_deg: tuple[float, ...] = ()
    perspective_row_after_column_middle_angles_deg: tuple[float, ...] = ()
    perspective_row_before_column_bottom_angles_deg: tuple[float, ...] = ()
    perspective_row_after_column_bottom_angles_deg: tuple[float, ...] = ()
    perspective_row_before_column_trends_deg: tuple[float, ...] = ()
    perspective_row_after_column_trends_deg: tuple[float, ...] = ()
    perspective_structural_applied: bool = False
    perspective_structural_safe: bool = False
    perspective_row_before_top_angle_deg: float = 0.0
    perspective_row_after_top_angle_deg: float = 0.0
    perspective_row_before_bottom_angle_deg: float = 0.0
    perspective_row_after_bottom_angle_deg: float = 0.0
    perspective_row_before_trend_deg: float = 0.0
    perspective_row_after_trend_deg: float = 0.0
    perspective_row_before_metric_deg: float = 0.0
    perspective_row_after_metric_deg: float = 0.0
    perspective_row_improvement_ratio: float = 0.0
    perspective_row_alignment_verdict: str = "insufficient"
    perspective_candidate_strength_px: float = 0.0
    perspective_left_drift_px: float = 0.0
    perspective_right_drift_px: float = 0.0
    perspective_common_drift_px: float = 0.0
    perspective_width_delta_px: float = 0.0
    perspective_width_change_ratio: float = 0.0
    perspective_scale_top: float = 1.0
    perspective_scale_bottom: float = 1.0
    perspective_scale_delta_ratio: float = 0.0
    perspective_jacobian_samples: int = 0
    perspective_jacobian_horizontal_scale_span_ratio: float = 0.0
    perspective_jacobian_vertical_scale_span_ratio: float = 0.0
    perspective_jacobian_area_scale_span_ratio: float = 0.0
    perspective_jacobian_anisotropy_p95_ratio: float = 0.0
    perspective_jacobian_min_determinant: float = 1.0
    perspective_text_scale_samples: int = 0
    perspective_text_scale_inline_ratio_p05: float = 1.0
    perspective_text_scale_inline_ratio_median: float = 1.0
    perspective_text_scale_inline_ratio_p95: float = 1.0
    perspective_text_scale_cross_ratio_p05: float = 1.0
    perspective_text_scale_cross_ratio_median: float = 1.0
    perspective_text_scale_cross_ratio_p95: float = 1.0
    perspective_text_scale_inline_ratio_span_ratio: float = 0.0
    perspective_text_scale_cross_ratio_span_ratio: float = 0.0
    perspective_text_scale_inline_ratio_gradient_ratio: float = 0.0
    perspective_text_scale_cross_ratio_gradient_ratio: float = 0.0
    perspective_text_scale_anisotropy_p95_ratio: float = 0.0
    perspective_text_scale_before_inline_gradient_ratio: float = 0.0
    perspective_text_scale_after_inline_gradient_ratio: float = 0.0
    perspective_text_scale_before_cross_gradient_ratio: float = 0.0
    perspective_text_scale_after_cross_gradient_ratio: float = 0.0
    perspective_text_scale_before_score: float = 0.0
    perspective_text_scale_after_score: float = 0.0
    perspective_text_scale_verdict: str = "insufficient"
    perspective_auto_safe: bool = False
    manual_perspective_quad: tuple[float, ...] | None = None
    orthogonal_applied: bool = False
    orthogonal_passes: int = 0
    orthogonal_steps: tuple[dict[str, object], ...] = ()
    orthogonal_row_count: int = 0
    orthogonal_valid_column_count: int = 0
    orthogonal_separator_point_count: int = 0
    orthogonal_row_gain: float = 0.0
    orthogonal_reference_x: float = 0.0
    orthogonal_y_knots: tuple[float, ...] = ()
    orthogonal_angle_knots_deg: tuple[float, ...] = ()
    orthogonal_x_knots: tuple[float, ...] = ()
    orthogonal_row_grid_rows: int = 0
    orthogonal_row_grid_cols: int = 0
    orthogonal_row_angle_grid_deg: tuple[float, ...] = ()
    orthogonal_row_displacement_grid_px: tuple[float, ...] = ()
    orthogonal_separator_y_knots: tuple[float, ...] = ()
    orthogonal_separator_shift_knots_px: tuple[float, ...] = ()
    orthogonal_horizontal_rule_point_count: int = 0
    orthogonal_horizontal_rule_y: float = 0.0
    orthogonal_before_horizontal_rule_angle_deg: float = 0.0
    orthogonal_after_horizontal_rule_angle_deg: float = 0.0
    orthogonal_before_horizontal_rule_residual_px: float = 0.0
    orthogonal_after_horizontal_rule_residual_px: float = 0.0
    orthogonal_horizontal_rule_verdict: str = "insufficient"
    orthogonal_pixel_angle_sample_count: int = 0
    orthogonal_pixel_angle_used_count: int = 0
    orthogonal_pixel_angle_confidence: float = 0.0
    orthogonal_pixel_row_sample_count: int = 0
    orthogonal_before_pixel_row_p90_px: float = 0.0
    orthogonal_after_pixel_row_p90_px: float = 0.0
    orthogonal_before_pixel_row_worst_px: float = 0.0
    orthogonal_after_pixel_row_worst_px: float = 0.0
    orthogonal_pixel_row_verdict: str = "insufficient"
    orthogonal_bottom_tail_sample_count: int = 0
    orthogonal_before_bottom_tail_p90_px: float = 0.0
    orthogonal_after_bottom_tail_p90_px: float = 0.0
    orthogonal_before_bottom_tail_worst_px: float = 0.0
    orthogonal_after_bottom_tail_worst_px: float = 0.0
    orthogonal_bottom_tail_verdict: str = "insufficient"
    orthogonal_safe_gain_cap: float = 0.0
    orthogonal_confidence: float = 0.0
    orthogonal_column_spread_deg: float = 0.0
    orthogonal_max_row_angle_deg: float = 0.0
    orthogonal_row_angle_span_deg: float = 0.0
    orthogonal_max_horizontal_shift_px: float = 0.0
    orthogonal_max_vertical_shift_px: float = 0.0
    orthogonal_max_scale_deviation: float = 0.0
    orthogonal_before_quality_score: float = 0.0
    orthogonal_after_quality_score: float = 0.0
    orthogonal_before_separator_span_px: float = 0.0
    orthogonal_after_separator_span_px: float = 0.0
    orthogonal_vertical_verdict: str = "insufficient"
    orthogonal_alignment_verdict: str = "insufficient"
    final_alignment_row_count: int = 0
    final_alignment_valid_column_count: int = 0
    final_alignment_edge_pair_count: int = 0
    final_alignment_top_edge_p90_abs_deg: float = 0.0
    final_alignment_bottom_edge_p90_abs_deg: float = 0.0
    final_alignment_edge_pair_delta_p90_deg: float = 0.0
    final_alignment_worst_edge_deg: float = 0.0
    final_alignment_worst_region_deg: float = 0.0
    final_alignment_worst_tail_p90_abs_deg: float = 0.0
    final_alignment_column_top_tail_p90_abs_deg: tuple[float, ...] = ()
    final_alignment_column_bottom_tail_p90_abs_deg: tuple[float, ...] = ()
    final_alignment_trend_deg: float = 0.0
    final_alignment_worst_column_trend_deg: float = 0.0
    final_alignment_quality_score: float = 0.0
    final_alignment_verdict: str = "insufficient"
    line_geometry_rows: int = 0
    line_geometry_global_angle_deg: float = 0.0
    line_geometry_top_angle_deg: float = 0.0
    line_geometry_middle_angle_deg: float = 0.0
    line_geometry_bottom_angle_deg: float = 0.0
    line_geometry_trend_deg: float = 0.0
    line_geometry_residual_mad_deg: float = 0.0
    line_geometry_residual_span_deg: float = 0.0
    line_geometry_columns: int = 0
    line_geometry_valid_columns: int = 0
    line_geometry_valid_column_indices: tuple[int, ...] = ()
    line_geometry_column_row_counts: tuple[int, ...] = ()
    line_geometry_column_trends_deg: tuple[float, ...] = ()
    line_geometry_worst_column_index: int = -1
    line_geometry_worst_column_trend_deg: float = 0.0
    line_geometry_worst_region_angle_deg: float = 0.0
    line_geometry_separator_found: bool = False
    line_geometry_separator_residual_px: float = 0.0
    line_geometry_separator_span_ratio: float = 0.0
    line_geometry_separator_slope_px_per_1000y: float = 0.0
    line_geometry_separator_drift_px: float = 0.0
    line_geometry_separator_track_quality: float = 0.0
    line_geometry_separator_track_jump_p95_px: float = 0.0
    line_geometry_separator_curvature_score: float = 0.0
    line_geometry_separator_curve_reliable: bool = False
    line_geometry_recommendation: str = "insufficient"
    line_geometry_confidence: float = 0.0
    source_size_bytes: int = 0
    source_mtime_ns: int = 0

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["format"] = PREPROCESS_FORMAT
        payload["format_version"] = PREPROCESS_FORMAT_VERSION
        payload["crop_box"] = list(self.crop_box)
        payload["raw_content_box"] = list(self.raw_content_box)
        payload["text_box"] = list(self.text_box) if self.text_box is not None else None
        payload["warnings"] = list(self.warnings)
        payload["perspective_matrix"] = (
            list(self.perspective_matrix)
            if self.perspective_matrix is not None else None
        )
        payload["perspective_source_quad"] = (
            list(self.perspective_source_quad)
            if self.perspective_source_quad is not None else None
        )
        payload["perspective_target_quad"] = (
            list(self.perspective_target_quad)
            if self.perspective_target_quad is not None else None
        )
        payload["manual_perspective_quad"] = (
            list(self.manual_perspective_quad)
            if self.manual_perspective_quad is not None else None
        )
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "PreprocessAnalysis":
        if not isinstance(payload, dict):
            raise ValueError("图片预处理结果格式无效")
        if (
            payload.get("format") != PREPROCESS_FORMAT
            or int(payload.get("format_version", 0) or 0) != PREPROCESS_FORMAT_VERSION
        ):
            raise ValueError("图片预处理结果版本已过期，需要重新分析")
        crop = tuple(int(v) for v in payload.get("crop_box", ()))
        raw = tuple(int(v) for v in payload.get("raw_content_box", ()))
        text = payload.get("text_box")
        text_box = tuple(int(v) for v in text) if isinstance(text, (list, tuple)) and len(text) == 4 else None
        if len(crop) != 4 or len(raw) != 4:
            raise ValueError("图片预处理结果缺少裁剪坐标")
        return cls(
            source_width=max(1, int(payload.get("source_width", 1))),
            source_height=max(1, int(payload.get("source_height", 1))),
            correction_angle_deg=float(payload.get("correction_angle_deg", 0.0)),
            applied_angle_deg=float(payload.get("applied_angle_deg", 0.0)),
            crop_box=crop,  # type: ignore[arg-type]
            raw_content_box=raw,  # type: ignore[arg-type]
            text_box=text_box,  # type: ignore[arg-type]
            source_boxes=max(0, int(payload.get("source_boxes", 0))),
            angle_samples=max(0, int(payload.get("angle_samples", 0))),
            angle_mad_deg=max(0.0, float(payload.get("angle_mad_deg", 0.0))),
            retained_ratio=max(0.0, min(1.0, float(payload.get("retained_ratio", 1.0)))),
            confidence=max(0.0, min(1.0, float(payload.get("confidence", 0.0)))),
            status=str(payload.get("status", "review") or "review"),
            method=str(payload.get("method", "unknown") or "unknown"),
            ocr_correction_angle_deg=float(
                payload.get("ocr_correction_angle_deg", 0.0)
            ),
            deskew_anchor_source=str(
                payload.get("deskew_anchor_source", "ocr") or "ocr"
            ),
            source_header_rule_point_count=max(
                0, int(payload.get("source_header_rule_point_count", 0))
            ),
            source_header_rule_angle_deg=float(
                payload.get("source_header_rule_angle_deg", 0.0)
            ),
            source_header_rule_residual_px=max(
                0.0, float(payload.get("source_header_rule_residual_px", 0.0))
            ),
            warnings=tuple(str(item) for item in payload.get("warnings", ()) if str(item).strip()),
            safety_margin_px=max(
                0, int(payload.get("safety_margin_px", DEFAULT_SAFETY_MARGIN_PX))
            ),
            auto_deskew=bool(payload.get("auto_deskew", True)),
            requested_geometry_mode=str(
                payload.get("requested_geometry_mode", "auto") or "auto"
            ),
            geometry_mode=str(payload.get("geometry_mode", "deskew") or "deskew"),
            geometry_strength_px=max(
                0.0, float(payload.get("geometry_strength_px", 0.0))
            ),
            perspective_matrix=(
                tuple(float(v) for v in payload.get("perspective_matrix", ()))
                if isinstance(payload.get("perspective_matrix"), (list, tuple))
                and len(payload.get("perspective_matrix", ())) == 9
                else None
            ),
            perspective_source_quad=(
                tuple(float(v) for v in payload.get("perspective_source_quad", ()))
                if isinstance(payload.get("perspective_source_quad"), (list, tuple))
                and len(payload.get("perspective_source_quad", ())) == 8
                else None
            ),
            perspective_target_quad=(
                tuple(float(v) for v in payload.get("perspective_target_quad", ()))
                if isinstance(payload.get("perspective_target_quad"), (list, tuple))
                and len(payload.get("perspective_target_quad", ())) == 8
                else None
            ),
            perspective_classification=str(
                payload.get("perspective_classification", "none") or "none"
            ),
            perspective_candidate_source=str(
                payload.get("perspective_candidate_source", "none") or "none"
            ),
            perspective_horizontal_vanishing_x=float(
                payload.get("perspective_horizontal_vanishing_x", 0.0)
            ),
            perspective_horizontal_vanishing_y=float(
                payload.get("perspective_horizontal_vanishing_y", 0.0)
            ),
            perspective_horizontal_row_count=max(
                0, int(payload.get("perspective_horizontal_row_count", 0))
            ),
            perspective_horizontal_column_count=max(
                0, int(payload.get("perspective_horizontal_column_count", 0))
            ),
            perspective_horizontal_vp_column_spread_deg=max(
                0.0,
                float(
                    payload.get(
                        "perspective_horizontal_vp_column_spread_deg", 0.0
                    )
                ),
            ),
            perspective_horizontal_strength=max(
                0.0,
                min(
                    1.0,
                    float(payload.get("perspective_horizontal_strength", 0.0)),
                ),
            ),
            perspective_structural_applied=bool(
                payload.get("perspective_structural_applied", False)
            ),
            perspective_structural_safe=bool(
                payload.get("perspective_structural_safe", False)
            ),
            perspective_row_valid_column_count=max(
                0, int(payload.get("perspective_row_valid_column_count", 0))
            ),
            perspective_row_valid_column_indices=tuple(
                int(v)
                for v in payload.get(
                    "perspective_row_valid_column_indices", ()
                )
            ),
            perspective_row_column_row_counts=tuple(
                int(v)
                for v in payload.get("perspective_row_column_row_counts", ())
            ),
            perspective_row_after_worst_region_deg=max(
                0.0,
                float(payload.get("perspective_row_after_worst_region_deg", 0.0)),
            ),
            perspective_row_after_worst_column_metric_deg=max(
                0.0,
                float(
                    payload.get(
                        "perspective_row_after_worst_column_metric_deg", 0.0
                    )
                ),
            ),
            perspective_row_after_worst_column_index=int(
                payload.get("perspective_row_after_worst_column_index", -1)
            ),
            perspective_row_before_column_top_angles_deg=tuple(
                float(v)
                for v in payload.get(
                    "perspective_row_before_column_top_angles_deg", ()
                )
            ),
            perspective_row_after_column_top_angles_deg=tuple(
                float(v)
                for v in payload.get(
                    "perspective_row_after_column_top_angles_deg", ()
                )
            ),
            perspective_row_before_column_middle_angles_deg=tuple(
                float(v)
                for v in payload.get(
                    "perspective_row_before_column_middle_angles_deg", ()
                )
            ),
            perspective_row_after_column_middle_angles_deg=tuple(
                float(v)
                for v in payload.get(
                    "perspective_row_after_column_middle_angles_deg", ()
                )
            ),
            perspective_row_before_column_bottom_angles_deg=tuple(
                float(v)
                for v in payload.get(
                    "perspective_row_before_column_bottom_angles_deg", ()
                )
            ),
            perspective_row_after_column_bottom_angles_deg=tuple(
                float(v)
                for v in payload.get(
                    "perspective_row_after_column_bottom_angles_deg", ()
                )
            ),
            perspective_row_before_column_trends_deg=tuple(
                float(v)
                for v in payload.get(
                    "perspective_row_before_column_trends_deg", ()
                )
            ),
            perspective_row_after_column_trends_deg=tuple(
                float(v)
                for v in payload.get(
                    "perspective_row_after_column_trends_deg", ()
                )
            ),
            perspective_row_before_top_angle_deg=float(
                payload.get("perspective_row_before_top_angle_deg", 0.0)
            ),
            perspective_row_after_top_angle_deg=float(
                payload.get("perspective_row_after_top_angle_deg", 0.0)
            ),
            perspective_row_before_bottom_angle_deg=float(
                payload.get("perspective_row_before_bottom_angle_deg", 0.0)
            ),
            perspective_row_after_bottom_angle_deg=float(
                payload.get("perspective_row_after_bottom_angle_deg", 0.0)
            ),
            perspective_row_before_trend_deg=float(
                payload.get("perspective_row_before_trend_deg", 0.0)
            ),
            perspective_row_after_trend_deg=float(
                payload.get("perspective_row_after_trend_deg", 0.0)
            ),
            perspective_row_before_metric_deg=max(
                0.0, float(payload.get("perspective_row_before_metric_deg", 0.0))
            ),
            perspective_row_after_metric_deg=max(
                0.0, float(payload.get("perspective_row_after_metric_deg", 0.0))
            ),
            perspective_row_improvement_ratio=float(
                payload.get("perspective_row_improvement_ratio", 0.0)
            ),
            perspective_row_alignment_verdict=str(
                payload.get("perspective_row_alignment_verdict", "insufficient")
                or "insufficient"
            ),
            perspective_candidate_strength_px=max(
                0.0, float(payload.get("perspective_candidate_strength_px", 0.0))
            ),
            perspective_left_drift_px=float(
                payload.get("perspective_left_drift_px", 0.0)
            ),
            perspective_right_drift_px=float(
                payload.get("perspective_right_drift_px", 0.0)
            ),
            perspective_common_drift_px=float(
                payload.get("perspective_common_drift_px", 0.0)
            ),
            perspective_width_delta_px=float(
                payload.get("perspective_width_delta_px", 0.0)
            ),
            perspective_width_change_ratio=max(
                0.0, float(payload.get("perspective_width_change_ratio", 0.0))
            ),
            perspective_scale_top=max(
                0.0, float(payload.get("perspective_scale_top", 1.0))
            ),
            perspective_scale_bottom=max(
                0.0, float(payload.get("perspective_scale_bottom", 1.0))
            ),
            perspective_scale_delta_ratio=max(
                0.0, float(payload.get("perspective_scale_delta_ratio", 0.0))
            ),
            perspective_jacobian_samples=max(
                0, int(payload.get("perspective_jacobian_samples", 0))
            ),
            perspective_jacobian_horizontal_scale_span_ratio=max(
                0.0,
                float(
                    payload.get(
                        "perspective_jacobian_horizontal_scale_span_ratio", 0.0
                    )
                ),
            ),
            perspective_jacobian_vertical_scale_span_ratio=max(
                0.0,
                float(
                    payload.get(
                        "perspective_jacobian_vertical_scale_span_ratio", 0.0
                    )
                ),
            ),
            perspective_jacobian_area_scale_span_ratio=max(
                0.0,
                float(
                    payload.get(
                        "perspective_jacobian_area_scale_span_ratio", 0.0
                    )
                ),
            ),
            perspective_jacobian_anisotropy_p95_ratio=max(
                0.0,
                float(
                    payload.get(
                        "perspective_jacobian_anisotropy_p95_ratio", 0.0
                    )
                ),
            ),
            perspective_jacobian_min_determinant=float(
                payload.get("perspective_jacobian_min_determinant", 1.0)
            ),
            perspective_text_scale_samples=max(
                0, int(payload.get("perspective_text_scale_samples", 0))
            ),
            perspective_text_scale_inline_ratio_p05=max(
                0.0, float(payload.get("perspective_text_scale_inline_ratio_p05", 1.0))
            ),
            perspective_text_scale_inline_ratio_median=max(
                0.0, float(payload.get("perspective_text_scale_inline_ratio_median", 1.0))
            ),
            perspective_text_scale_inline_ratio_p95=max(
                0.0, float(payload.get("perspective_text_scale_inline_ratio_p95", 1.0))
            ),
            perspective_text_scale_cross_ratio_p05=max(
                0.0, float(payload.get("perspective_text_scale_cross_ratio_p05", 1.0))
            ),
            perspective_text_scale_cross_ratio_median=max(
                0.0, float(payload.get("perspective_text_scale_cross_ratio_median", 1.0))
            ),
            perspective_text_scale_cross_ratio_p95=max(
                0.0, float(payload.get("perspective_text_scale_cross_ratio_p95", 1.0))
            ),
            perspective_text_scale_inline_ratio_span_ratio=max(
                0.0,
                float(payload.get("perspective_text_scale_inline_ratio_span_ratio", 0.0)),
            ),
            perspective_text_scale_cross_ratio_span_ratio=max(
                0.0,
                float(payload.get("perspective_text_scale_cross_ratio_span_ratio", 0.0)),
            ),
            perspective_text_scale_inline_ratio_gradient_ratio=max(
                0.0,
                float(payload.get("perspective_text_scale_inline_ratio_gradient_ratio", 0.0)),
            ),
            perspective_text_scale_cross_ratio_gradient_ratio=max(
                0.0,
                float(payload.get("perspective_text_scale_cross_ratio_gradient_ratio", 0.0)),
            ),
            perspective_text_scale_anisotropy_p95_ratio=max(
                0.0,
                float(payload.get("perspective_text_scale_anisotropy_p95_ratio", 0.0)),
            ),
            perspective_text_scale_before_inline_gradient_ratio=max(
                0.0,
                float(
                    payload.get(
                        "perspective_text_scale_before_inline_gradient_ratio", 0.0
                    )
                ),
            ),
            perspective_text_scale_after_inline_gradient_ratio=max(
                0.0,
                float(
                    payload.get(
                        "perspective_text_scale_after_inline_gradient_ratio", 0.0
                    )
                ),
            ),
            perspective_text_scale_before_cross_gradient_ratio=max(
                0.0,
                float(
                    payload.get(
                        "perspective_text_scale_before_cross_gradient_ratio", 0.0
                    )
                ),
            ),
            perspective_text_scale_after_cross_gradient_ratio=max(
                0.0,
                float(
                    payload.get(
                        "perspective_text_scale_after_cross_gradient_ratio", 0.0
                    )
                ),
            ),
            perspective_text_scale_before_score=max(
                0.0, float(payload.get("perspective_text_scale_before_score", 0.0))
            ),
            perspective_text_scale_after_score=max(
                0.0, float(payload.get("perspective_text_scale_after_score", 0.0))
            ),
            perspective_text_scale_verdict=str(
                payload.get("perspective_text_scale_verdict", "insufficient")
                or "insufficient"
            ),
            perspective_auto_safe=bool(
                payload.get("perspective_auto_safe", False)
            ),
            manual_perspective_quad=(
                tuple(float(v) for v in payload.get("manual_perspective_quad", ()))
                if isinstance(payload.get("manual_perspective_quad"), (list, tuple))
                and len(payload.get("manual_perspective_quad", ())) == 8
                else None
            ),
            orthogonal_applied=bool(payload.get("orthogonal_applied", False)),
            orthogonal_passes=max(0, int(payload.get("orthogonal_passes", 0))),
            orthogonal_steps=tuple(
                dict(item)
                for item in payload.get("orthogonal_steps", ())
                if isinstance(item, dict)
            ),
            orthogonal_row_count=max(0, int(payload.get("orthogonal_row_count", 0))),
            orthogonal_valid_column_count=max(
                0, int(payload.get("orthogonal_valid_column_count", 0))
            ),
            orthogonal_separator_point_count=max(
                0, int(payload.get("orthogonal_separator_point_count", 0))
            ),
            orthogonal_row_gain=max(
                0.0, float(payload.get("orthogonal_row_gain", 0.0))
            ),
            orthogonal_reference_x=float(
                payload.get("orthogonal_reference_x", 0.0)
            ),
            orthogonal_y_knots=tuple(
                float(v) for v in payload.get("orthogonal_y_knots", ())
            ),
            orthogonal_angle_knots_deg=tuple(
                float(v) for v in payload.get("orthogonal_angle_knots_deg", ())
            ),
            orthogonal_x_knots=tuple(
                float(v) for v in payload.get("orthogonal_x_knots", ())
            ),
            orthogonal_row_grid_rows=max(
                0, int(payload.get("orthogonal_row_grid_rows", 0))
            ),
            orthogonal_row_grid_cols=max(
                0, int(payload.get("orthogonal_row_grid_cols", 0))
            ),
            orthogonal_row_angle_grid_deg=tuple(
                float(v)
                for v in payload.get("orthogonal_row_angle_grid_deg", ())
            ),
            orthogonal_row_displacement_grid_px=tuple(
                float(v)
                for v in payload.get(
                    "orthogonal_row_displacement_grid_px", ()
                )
            ),
            orthogonal_separator_y_knots=tuple(
                float(v)
                for v in payload.get("orthogonal_separator_y_knots", ())
            ),
            orthogonal_separator_shift_knots_px=tuple(
                float(v)
                for v in payload.get(
                    "orthogonal_separator_shift_knots_px", ()
                )
            ),
            orthogonal_horizontal_rule_point_count=max(
                0,
                int(payload.get("orthogonal_horizontal_rule_point_count", 0)),
            ),
            orthogonal_horizontal_rule_y=float(
                payload.get("orthogonal_horizontal_rule_y", 0.0)
            ),
            orthogonal_before_horizontal_rule_angle_deg=float(
                payload.get(
                    "orthogonal_before_horizontal_rule_angle_deg", 0.0
                )
            ),
            orthogonal_after_horizontal_rule_angle_deg=float(
                payload.get(
                    "orthogonal_after_horizontal_rule_angle_deg", 0.0
                )
            ),
            orthogonal_before_horizontal_rule_residual_px=max(
                0.0,
                float(
                    payload.get(
                        "orthogonal_before_horizontal_rule_residual_px", 0.0
                    )
                ),
            ),
            orthogonal_after_horizontal_rule_residual_px=max(
                0.0,
                float(
                    payload.get(
                        "orthogonal_after_horizontal_rule_residual_px", 0.0
                    )
                ),
            ),
            orthogonal_horizontal_rule_verdict=str(
                payload.get(
                    "orthogonal_horizontal_rule_verdict", "insufficient"
                )
                or "insufficient"
            ),
            orthogonal_pixel_angle_sample_count=max(
                0, int(payload.get("orthogonal_pixel_angle_sample_count", 0))
            ),
            orthogonal_pixel_angle_used_count=max(
                0, int(payload.get("orthogonal_pixel_angle_used_count", 0))
            ),
            orthogonal_pixel_angle_confidence=max(
                0.0,
                float(payload.get("orthogonal_pixel_angle_confidence", 0.0)),
            ),
            orthogonal_pixel_row_sample_count=max(
                0, int(payload.get("orthogonal_pixel_row_sample_count", 0))
            ),
            orthogonal_before_pixel_row_p90_px=max(
                0.0, float(payload.get("orthogonal_before_pixel_row_p90_px", 0.0))
            ),
            orthogonal_after_pixel_row_p90_px=max(
                0.0, float(payload.get("orthogonal_after_pixel_row_p90_px", 0.0))
            ),
            orthogonal_before_pixel_row_worst_px=max(
                0.0, float(payload.get("orthogonal_before_pixel_row_worst_px", 0.0))
            ),
            orthogonal_after_pixel_row_worst_px=max(
                0.0, float(payload.get("orthogonal_after_pixel_row_worst_px", 0.0))
            ),
            orthogonal_pixel_row_verdict=str(
                payload.get("orthogonal_pixel_row_verdict", "insufficient")
                or "insufficient"
            ),
            orthogonal_bottom_tail_sample_count=max(
                0, int(payload.get("orthogonal_bottom_tail_sample_count", 0))
            ),
            orthogonal_before_bottom_tail_p90_px=max(
                0.0, float(payload.get("orthogonal_before_bottom_tail_p90_px", 0.0))
            ),
            orthogonal_after_bottom_tail_p90_px=max(
                0.0, float(payload.get("orthogonal_after_bottom_tail_p90_px", 0.0))
            ),
            orthogonal_before_bottom_tail_worst_px=max(
                0.0, float(payload.get("orthogonal_before_bottom_tail_worst_px", 0.0))
            ),
            orthogonal_after_bottom_tail_worst_px=max(
                0.0, float(payload.get("orthogonal_after_bottom_tail_worst_px", 0.0))
            ),
            orthogonal_bottom_tail_verdict=str(
                payload.get("orthogonal_bottom_tail_verdict", "insufficient")
                or "insufficient"
            ),
            orthogonal_safe_gain_cap=max(
                0.0, float(payload.get("orthogonal_safe_gain_cap", 0.0))
            ),
            orthogonal_confidence=max(
                0.0, min(1.0, float(payload.get("orthogonal_confidence", 0.0)))
            ),
            orthogonal_column_spread_deg=max(
                0.0, float(payload.get("orthogonal_column_spread_deg", 0.0))
            ),
            orthogonal_max_row_angle_deg=max(
                0.0, float(payload.get("orthogonal_max_row_angle_deg", 0.0))
            ),
            orthogonal_row_angle_span_deg=max(
                0.0, float(payload.get("orthogonal_row_angle_span_deg", 0.0))
            ),
            orthogonal_max_horizontal_shift_px=max(
                0.0, float(payload.get("orthogonal_max_horizontal_shift_px", 0.0))
            ),
            orthogonal_max_vertical_shift_px=max(
                0.0, float(payload.get("orthogonal_max_vertical_shift_px", 0.0))
            ),
            orthogonal_max_scale_deviation=max(
                0.0, float(payload.get("orthogonal_max_scale_deviation", 0.0))
            ),
            orthogonal_before_quality_score=max(
                0.0, float(payload.get("orthogonal_before_quality_score", 0.0))
            ),
            orthogonal_after_quality_score=max(
                0.0, float(payload.get("orthogonal_after_quality_score", 0.0))
            ),
            orthogonal_before_separator_span_px=max(
                0.0,
                float(payload.get("orthogonal_before_separator_span_px", 0.0)),
            ),
            orthogonal_after_separator_span_px=max(
                0.0,
                float(payload.get("orthogonal_after_separator_span_px", 0.0)),
            ),
            orthogonal_vertical_verdict=str(
                payload.get("orthogonal_vertical_verdict", "insufficient")
                or "insufficient"
            ),
            orthogonal_alignment_verdict=str(
                payload.get("orthogonal_alignment_verdict", "insufficient")
                or "insufficient"
            ),
            final_alignment_row_count=max(
                0, int(payload.get("final_alignment_row_count", 0))
            ),
            final_alignment_valid_column_count=max(
                0, int(payload.get("final_alignment_valid_column_count", 0))
            ),
            final_alignment_edge_pair_count=max(
                0, int(payload.get("final_alignment_edge_pair_count", 0))
            ),
            final_alignment_top_edge_p90_abs_deg=max(
                0.0, float(payload.get("final_alignment_top_edge_p90_abs_deg", 0.0))
            ),
            final_alignment_bottom_edge_p90_abs_deg=max(
                0.0, float(payload.get("final_alignment_bottom_edge_p90_abs_deg", 0.0))
            ),
            final_alignment_edge_pair_delta_p90_deg=max(
                0.0, float(payload.get("final_alignment_edge_pair_delta_p90_deg", 0.0))
            ),
            final_alignment_worst_edge_deg=max(
                0.0, float(payload.get("final_alignment_worst_edge_deg", 0.0))
            ),
            final_alignment_worst_region_deg=max(
                0.0, float(payload.get("final_alignment_worst_region_deg", 0.0))
            ),
            final_alignment_worst_tail_p90_abs_deg=max(
                0.0,
                float(
                    payload.get(
                        "final_alignment_worst_tail_p90_abs_deg", 0.0
                    )
                ),
            ),
            final_alignment_column_top_tail_p90_abs_deg=tuple(
                float(v)
                for v in payload.get(
                    "final_alignment_column_top_tail_p90_abs_deg", ()
                )
            ),
            final_alignment_column_bottom_tail_p90_abs_deg=tuple(
                float(v)
                for v in payload.get(
                    "final_alignment_column_bottom_tail_p90_abs_deg", ()
                )
            ),
            final_alignment_trend_deg=float(
                payload.get("final_alignment_trend_deg", 0.0)
            ),
            final_alignment_worst_column_trend_deg=max(
                0.0,
                float(payload.get("final_alignment_worst_column_trend_deg", 0.0)),
            ),
            final_alignment_quality_score=max(
                0.0, float(payload.get("final_alignment_quality_score", 0.0))
            ),
            final_alignment_verdict=str(
                payload.get("final_alignment_verdict", "insufficient")
                or "insufficient"
            ),
            line_geometry_rows=max(
                0, int(payload.get("line_geometry_rows", 0))
            ),
            line_geometry_global_angle_deg=float(
                payload.get("line_geometry_global_angle_deg", 0.0)
            ),
            line_geometry_top_angle_deg=float(
                payload.get("line_geometry_top_angle_deg", 0.0)
            ),
            line_geometry_middle_angle_deg=float(
                payload.get("line_geometry_middle_angle_deg", 0.0)
            ),
            line_geometry_bottom_angle_deg=float(
                payload.get("line_geometry_bottom_angle_deg", 0.0)
            ),
            line_geometry_trend_deg=float(
                payload.get("line_geometry_trend_deg", 0.0)
            ),
            line_geometry_residual_mad_deg=max(
                0.0, float(payload.get("line_geometry_residual_mad_deg", 0.0))
            ),
            line_geometry_residual_span_deg=max(
                0.0, float(payload.get("line_geometry_residual_span_deg", 0.0))
            ),
            line_geometry_columns=max(
                0, int(payload.get("line_geometry_columns", 0))
            ),
            line_geometry_valid_columns=max(
                0, int(payload.get("line_geometry_valid_columns", 0))
            ),
            line_geometry_valid_column_indices=tuple(
                int(v)
                for v in payload.get(
                    "line_geometry_valid_column_indices", ()
                )
            ),
            line_geometry_column_row_counts=tuple(
                int(v)
                for v in payload.get("line_geometry_column_row_counts", ())
            ),
            line_geometry_column_trends_deg=tuple(
                float(v)
                for v in payload.get("line_geometry_column_trends_deg", ())
            ),
            line_geometry_worst_column_index=int(
                payload.get("line_geometry_worst_column_index", -1)
            ),
            line_geometry_worst_column_trend_deg=float(
                payload.get("line_geometry_worst_column_trend_deg", 0.0)
            ),
            line_geometry_worst_region_angle_deg=max(
                0.0,
                float(payload.get("line_geometry_worst_region_angle_deg", 0.0)),
            ),
            line_geometry_separator_found=bool(
                payload.get("line_geometry_separator_found", False)
            ),
            line_geometry_separator_residual_px=max(
                0.0, float(payload.get("line_geometry_separator_residual_px", 0.0))
            ),
            line_geometry_separator_span_ratio=max(
                0.0,
                min(
                    1.0,
                    float(payload.get("line_geometry_separator_span_ratio", 0.0)),
                ),
            ),
            line_geometry_separator_slope_px_per_1000y=float(
                payload.get("line_geometry_separator_slope_px_per_1000y", 0.0)
            ),
            line_geometry_separator_drift_px=float(
                payload.get("line_geometry_separator_drift_px", 0.0)
            ),
            line_geometry_separator_track_quality=max(
                0.0, float(payload.get("line_geometry_separator_track_quality", 0.0))
            ),
            line_geometry_separator_track_jump_p95_px=max(
                0.0,
                float(payload.get("line_geometry_separator_track_jump_p95_px", 0.0)),
            ),
            line_geometry_separator_curvature_score=max(
                0.0,
                min(
                    1.0,
                    float(payload.get("line_geometry_separator_curvature_score", 0.0)),
                ),
            ),
            line_geometry_separator_curve_reliable=bool(
                payload.get("line_geometry_separator_curve_reliable", False)
            ),
            line_geometry_recommendation=str(
                payload.get("line_geometry_recommendation", "insufficient")
                or "insufficient"
            ),
            line_geometry_confidence=max(
                0.0,
                min(1.0, float(payload.get("line_geometry_confidence", 0.0))),
            ),
            source_size_bytes=max(0, int(payload.get("source_size_bytes", 0))),
            source_mtime_ns=max(0, int(payload.get("source_mtime_ns", 0))),
        )


# Preserve the historical public class module path for pickle/debug compatibility.
OutputCanvasInfo.__module__ = "picture_capture.image_preprocessing"
PreprocessAnalysis.__module__ = "picture_capture.image_preprocessing"
