"""Finalize reviewed-page diagnostics, retained bounds and confidence.

The caller supplies the current image/detection/layout operations. This owner
never imports the public preprocessing facade or changes accepted transforms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from PIL import Image

from ..models import AppSettings


@dataclass(frozen=True, slots=True)
class FinalPreprocessResult:
    """Per-page final measurements consumed by the existing persisted model."""

    raw_content_box: tuple[int, int, int, int]
    crop_box: tuple[int, int, int, int]
    text_box: tuple[int, int, int, int] | None
    retained_ratio: float
    evidence_boxes: int
    confidence: float
    status: str
    final_alignment_row_count: int
    final_alignment_valid_column_count: int
    final_alignment_edge_pair_count: int
    final_alignment_top_edge_p90_abs_deg: float
    final_alignment_bottom_edge_p90_abs_deg: float
    final_alignment_edge_pair_delta_p90_deg: float
    final_alignment_worst_edge_deg: float
    final_alignment_worst_region_deg: float
    final_alignment_worst_tail_p90_abs_deg: float
    final_alignment_column_top_tail_p90_abs_deg: tuple[float, ...]
    final_alignment_column_bottom_tail_p90_abs_deg: tuple[float, ...]
    final_alignment_trend_deg: float
    final_alignment_worst_column_trend_deg: float
    final_alignment_quality_score: float
    final_alignment_verdict: str


def finalize_preprocess_page(
    working: Image.Image,
    settings: AppSettings,
    *,
    source_size: tuple[int, int],
    polygons: list[np.ndarray],
    working_polygons: list[np.ndarray],
    actual_geometry_mode: str,
    advanced_redetected: bool,
    safety_margin_px: int,
    angle_samples: int,
    angle_mad: float,
    correction: float,
    warnings: list[str],
    method_parts: list[str],
    text_detector: Callable,
    horizontal_auditor: Callable,
    quality_evaluator: Callable,
    layout_bounds: Callable,
    projection_bounds: Callable,
    box_expander: Callable,
    text_bounds: Callable,
) -> FinalPreprocessResult:
    width, height = source_size
    layout_source_boxes = 0
    # Advanced transforms change the page geometry. Re-run TextDetection on the
    # corrected image before final structural cropping. If that second pass
    # fails, the mathematically transformed original polygons remain a safe
    # fallback and preserve non-destructive export.
    final_polygons = working_polygons
    if polygons and actual_geometry_mode in {"manual_perspective", "perspective", "uvdoc"} and not advanced_redetected:
        try:
            redetected = text_detector(working, settings)
            if len(redetected) >= 4:
                final_polygons = redetected
                method_parts.append("redetect")
            else:
                warnings.append("高级纠正后文本框过少，最终裁边沿用变换后的原检测框。")
        except Exception as exc:
            warnings.append(f"高级纠正后版面复检失败，沿用变换后的原检测框：{exc}")

    final_alignment_row_count = 0
    final_alignment_valid_column_count = 0
    final_alignment_edge_pair_count = 0
    final_alignment_top_edge_p90_abs_deg = 0.0
    final_alignment_bottom_edge_p90_abs_deg = 0.0
    final_alignment_edge_pair_delta_p90_deg = 0.0
    final_alignment_worst_edge_deg = 0.0
    final_alignment_worst_region_deg = 0.0
    final_alignment_worst_tail_p90_abs_deg = 0.0
    final_alignment_column_top_tail_p90_abs_deg: tuple[float, ...] = ()
    final_alignment_column_bottom_tail_p90_abs_deg: tuple[float, ...] = ()
    final_alignment_trend_deg = 0.0
    final_alignment_worst_column_trend_deg = 0.0
    final_alignment_quality_score = 0.0
    final_alignment_verdict = "insufficient"
    if final_polygons and not str(settings.layout_writing_mode or "horizontal-tb").startswith("vertical"):
        try:
            final_audit = horizontal_auditor(
                final_polygons,
                final_polygons,
                size=working.size,
                settings=settings,
            )
            final_alignment_row_count = int(final_audit.row_count)
            final_alignment_valid_column_count = int(final_audit.valid_column_count)
            final_alignment_edge_pair_count = int(final_audit.edge_pair_count)
            final_alignment_top_edge_p90_abs_deg = float(final_audit.after_top_edge_p90_abs_deg)
            final_alignment_bottom_edge_p90_abs_deg = float(final_audit.after_bottom_edge_p90_abs_deg)
            final_alignment_edge_pair_delta_p90_deg = float(final_audit.after_edge_pair_delta_p90_deg)
            final_alignment_worst_edge_deg = float(final_audit.after_worst_edge_deg)
            final_alignment_worst_region_deg = float(final_audit.after_worst_region_deg)
            final_alignment_worst_tail_p90_abs_deg = float(getattr(final_audit, "after_worst_tail_p90_abs_deg", 0.0))
            final_alignment_column_top_tail_p90_abs_deg = tuple(
                float(v)
                for v in getattr(
                    final_audit,
                    "after_column_top_tail_p90_abs_deg",
                    (),
                )
            )
            final_alignment_column_bottom_tail_p90_abs_deg = tuple(
                float(v)
                for v in getattr(
                    final_audit,
                    "after_column_bottom_tail_p90_abs_deg",
                    (),
                )
            )
            final_alignment_trend_deg = float(final_audit.after_trend_deg)
            final_alignment_worst_column_trend_deg = max(
                [abs(float(final_audit.after_trend_deg))]
                + [abs(float(value)) for value in final_audit.after_column_trends_deg]
            )
            (
                final_alignment_verdict,
                final_alignment_quality_score,
            ) = quality_evaluator(final_audit)
            if final_alignment_verdict == "failed":
                warnings.append(
                    "成品双边缘水平验收未通过："
                    f"上缘P90 {final_alignment_top_edge_p90_abs_deg:.2f}°，"
                    f"下缘P90 {final_alignment_bottom_edge_p90_abs_deg:.2f}°，"
                    "上下缘差P90 "
                    f"{final_alignment_edge_pair_delta_p90_deg:.2f}°，"
                    f"最差区域 {final_alignment_worst_region_deg:.2f}°，"
                    "页首/页尾最差P90 "
                    f"{final_alignment_worst_tail_p90_abs_deg:.2f}°，"
                    "最差栏趋势 "
                    f"{final_alignment_worst_column_trend_deg:.2f}°。"
                )
            elif final_alignment_verdict == "insufficient" and actual_geometry_mode == "uvdoc":
                warnings.append("UVDoc 展平后有效双边缘文本行不足，无法完成最终水平验收。")
        except Exception as exc:
            if actual_geometry_mode == "uvdoc":
                warnings.append(f"UVDoc 展平后水平验收不可用：{exc}")

    layout_box: tuple[int, int, int, int] | None = None
    if final_polygons:
        try:
            layout_box, layout_estimate = layout_bounds(
                final_polygons,
                width,
                height,
                settings,
            )
            layout_source_boxes = int(layout_estimate.source_boxes)
        except Exception as exc:
            warnings.append(f"纠正后结构裁边失败，已使用投影回退：{exc}")

    if layout_box is not None:
        raw_content_box = layout_box
        crop_box = box_expander(
            raw_content_box,
            width,
            height,
            safety_margin_px,
        )
    else:
        if method_parts[0] != "projection_fallback":
            method_parts.insert(0, "projection_fallback")
        raw_content_box = projection_bounds(working, settings)
        crop_box = box_expander(
            raw_content_box,
            width,
            height,
            safety_margin_px,
        )

    text_box = (
        text_bounds(
            final_polygons,
            width,
            height,
            0.0,
        )
        if final_polygons
        else None
    )

    x0, y0, x1, y1 = crop_box
    retained_ratio = max(
        0.0,
        min(1.0, ((x1 - x0) * (y1 - y0)) / float(width * height)),
    )

    if angle_samples and angle_mad > 0.65:
        warnings.append(f"文本框倾斜角离散较大（MAD {angle_mad:.2f}°）。")
    if abs(correction) > 3.0:
        warnings.append(f"页面倾斜较大（{correction:+.2f}°），建议人工确认。")
    if polygons and len(polygons) < 8:
        warnings.append(f"有效文本框仅 {len(polygons)} 个，建议人工确认裁边。")
    if retained_ratio < 0.45:
        warnings.append(f"仅保留页面 {retained_ratio * 100:.1f}% 面积，裁剪幅度较大。")
    if retained_ratio > 0.975:
        warnings.append(f"保留页面 {retained_ratio * 100:.1f}% 面积，几乎未裁边。")

    evidence_boxes = layout_source_boxes or len(final_polygons) or len(polygons)
    confidence = min(1.0, evidence_boxes / 40.0)
    if angle_samples:
        confidence *= max(0.25, 1.0 - min(1.0, angle_mad / 1.5))
    else:
        confidence *= 0.45
    if "projection_fallback" in method_parts:
        confidence *= 0.55
    confidence = max(0.0, min(1.0, confidence))
    status = "review" if warnings or confidence < 0.45 else "normal"

    return FinalPreprocessResult(
        raw_content_box=raw_content_box,
        crop_box=crop_box,
        text_box=text_box,
        retained_ratio=retained_ratio,
        evidence_boxes=evidence_boxes,
        confidence=confidence,
        status=status,
        final_alignment_row_count=final_alignment_row_count,
        final_alignment_valid_column_count=final_alignment_valid_column_count,
        final_alignment_edge_pair_count=final_alignment_edge_pair_count,
        final_alignment_top_edge_p90_abs_deg=final_alignment_top_edge_p90_abs_deg,
        final_alignment_bottom_edge_p90_abs_deg=final_alignment_bottom_edge_p90_abs_deg,
        final_alignment_edge_pair_delta_p90_deg=final_alignment_edge_pair_delta_p90_deg,
        final_alignment_worst_edge_deg=final_alignment_worst_edge_deg,
        final_alignment_worst_region_deg=final_alignment_worst_region_deg,
        final_alignment_worst_tail_p90_abs_deg=final_alignment_worst_tail_p90_abs_deg,
        final_alignment_column_top_tail_p90_abs_deg=final_alignment_column_top_tail_p90_abs_deg,
        final_alignment_column_bottom_tail_p90_abs_deg=final_alignment_column_bottom_tail_p90_abs_deg,
        final_alignment_trend_deg=final_alignment_trend_deg,
        final_alignment_worst_column_trend_deg=final_alignment_worst_column_trend_deg,
        final_alignment_quality_score=final_alignment_quality_score,
        final_alignment_verdict=final_alignment_verdict,
    )
