"""Collect source-page geometry evidence before any pixel transforms.

Detection failures, fallback angle estimation and physical header anchoring share
one owner. Operations and policy values are supplied explicitly by composition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from PIL import Image

from ..models import AppSettings
from .text_line_geometry import TextLineGeometryAnalysis


@dataclass(frozen=True, slots=True)
class SourceGeometryEvidence:
    """Per-page evidence handed to later transform stages; never persisted."""

    warnings: list[str]
    polygons: list[np.ndarray]
    method_parts: list[str]
    line_geometry: TextLineGeometryAnalysis
    ocr_correction: float
    angle_samples: int
    angle_mad: float
    correction: float
    deskew_anchor_source: str
    source_header_rule_point_count: int
    source_header_rule_angle_deg: float
    source_header_rule_residual_px: float
    applied: float


def collect_source_geometry_evidence(
    source: Image.Image,
    settings: AppSettings,
    *,
    requested_geometry_mode: str,
    auto_deskew: bool,
    text_detector: Callable,
    line_analyzer: Callable,
    line_geometry_factory: Callable,
    skew_estimator: Callable,
    projection_estimator: Callable,
    rule_metrics: Callable,
    separator_curve_width_ratio: float,
    header_residual_min_px: float,
    header_residual_width_ratio: float,
    max_auto_deskew_deg: float,
    deskew_dead_zone_deg: float,
) -> SourceGeometryEvidence:
    width = source.width
    warnings: list[str] = []
    polygons: list[np.ndarray] = []
    method_parts = ["paddle_layout_roi"]

    try:
        polygons = text_detector(source, settings)
        if len(polygons) < 4:
            raise RuntimeError("Paddle文本框过少")
    except Exception as exc:
        polygons = []
        method_parts = ["projection_fallback"]
        warnings.append(f"版面结构检测不可用，裁边已使用投影回退：{exc}")

    line_geometry = line_geometry_factory()
    if polygons:
        try:
            line_geometry = line_analyzer(
                source,
                polygons,
                settings,
            )
            method_parts.append("line_geometry")
            if line_geometry.recommendation == "uvdoc_review" and requested_geometry_mode not in {"auto", "uvdoc"}:
                warnings.append(
                    "检测到可靠的平滑非线性弯曲；当前模式不会自动执行正交网格展平，可改用自动模式或手动UVDoc复核。"
                )
            elif line_geometry.recommendation == "manual_review":
                if line_geometry.separator_found and line_geometry.separator_residual_px < max(3.0, width * 0.0015):
                    warnings.append(
                        "文本行方向存在局部不一致，但长直分隔线保持笔直；更可能是版式/OCR波动，不自动做非线性矫正。"
                    )
                else:
                    warnings.append("文本行方向存在不一致，当前证据不足以支持非线性矫正。")
            separator_curve_threshold = max(3.0, width * separator_curve_width_ratio)
            if (
                line_geometry.separator_found
                and line_geometry.separator_residual_px >= separator_curve_threshold * 1.5
                and not line_geometry.separator_curve_reliable
            ):
                warnings.append(
                    "实体长线候选残差较大，但轨迹连续性或曲率一致性不足；该候选不作为 UVDoc 非线性形变证据。"
                )
        except Exception as exc:
            warnings.append(f"文本行几何分析不可用：{exc}")

    ocr_correction, angle_samples, angle_mad = skew_estimator(
        polygons,
        writing_mode=settings.layout_writing_mode,
    )
    if angle_samples < 4:
        if method_parts[0] != "projection_fallback":
            method_parts.append("projection_angle")
        try:
            ocr_correction = projection_estimator(
                source,
                settings,
                writing_mode=settings.layout_writing_mode,
            )
            warnings.append("文本框角度样本较少，倾斜角由投影法补充估计。")
        except Exception as exc:
            ocr_correction = 0.0
            warnings.append(f"倾斜角回退估计失败：{exc}")

    correction = float(ocr_correction)
    deskew_anchor_source = "ocr"
    source_header_rule_point_count = 0
    source_header_rule_angle_deg = 0.0
    source_header_rule_residual_px = 0.0
    if polygons and not str(settings.layout_writing_mode or "horizontal-tb").startswith("vertical"):
        try:
            (
                source_header_rule_point_count,
                source_header_rule_angle_deg,
                source_header_rule_residual_px,
                _source_header_rule_y,
            ) = rule_metrics(source, polygons, settings)
            header_residual_limit = max(
                header_residual_min_px,
                width * header_residual_width_ratio,
            )
            header_anchor_reliable = bool(
                source_header_rule_point_count >= 7
                and abs(float(source_header_rule_angle_deg)) <= max_auto_deskew_deg
                and float(source_header_rule_residual_px) <= header_residual_limit
            )
            if header_anchor_reliable:
                correction = float(source_header_rule_angle_deg)
                deskew_anchor_source = "header_rule"
                method_parts.append("header_rule_deskew")
                if abs(float(ocr_correction) - correction) >= 0.12:
                    warnings.append(
                        "正文OCR平均倾角与页眉实体横线不一致："
                        f"OCR {float(ocr_correction):+.2f}°，"
                        f"页眉 {correction:+.2f}°；"
                        "全局旋转采用实体横线，正文残差交由局部像素场矫正。"
                    )
        except Exception as exc:
            warnings.append(f"页眉实体横线全局锚定不可用：{exc}")

    if abs(correction) < deskew_dead_zone_deg:
        applied = 0.0
    elif abs(correction) <= max_auto_deskew_deg and auto_deskew:
        applied = float(correction)
    else:
        applied = 0.0
        if auto_deskew and abs(correction) > max_auto_deskew_deg:
            warnings.append(f"检测倾斜 {correction:+.2f}° 超过自动纠偏上限 {max_auto_deskew_deg:.1f}°，未自动旋转。")

    return SourceGeometryEvidence(
        warnings=warnings,
        polygons=polygons,
        method_parts=method_parts,
        line_geometry=line_geometry,
        ocr_correction=ocr_correction,
        angle_samples=angle_samples,
        angle_mad=angle_mad,
        correction=correction,
        deskew_anchor_source=deskew_anchor_source,
        source_header_rule_point_count=source_header_rule_point_count,
        source_header_rule_angle_deg=source_header_rule_angle_deg,
        source_header_rule_residual_px=source_header_rule_residual_px,
        applied=applied,
    )
