"""Generate and select structural and residual-horizontal projective candidates.

Operations and automatic-safety policy values are supplied by composition. The
selection contains diagnostics only; this owner never warps source pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..models import AppSettings
from .text_line_geometry import TextLineGeometryAnalysis


@dataclass(frozen=True, slots=True)
class ProjectiveSelection:
    """Selected and rejected evidence passed to existing transform diagnostics."""

    selected_entry: dict | None
    selected_candidate: object | None
    selected_horizontal_strength: float
    diagnostic_entry: dict | None
    diagnostic_candidate: object | None
    diagnostic_horizontal_strength: float
    perspective_structural_applied: bool
    perspective_structural_safe: bool
    structural_auto_safe: bool
    horizontal_auto_safe: bool
    structural_candidate: object | None
    structural_entry: dict | None
    line_supports_perspective: bool
    horizontal_total_candidate: object | None
    horizontal_full: object | None
    horizontal_row_audit: object | None
    horizontal_strength: float


def select_projective_candidate(
    polygons: list[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings,
    *,
    source_width: int,
    line_geometry: TextLineGeometryAnalysis,
    requested_geometry_mode: str,
    polygon_transformer: Callable,
    jacobian_auditor: Callable,
    scale_auditor: Callable,
    row_auditor: Callable,
    structural_estimator: Callable,
    horizontal_estimator: Callable,
    strength_optimizer: Callable,
    perspective_composer: Callable,
    horizontal_scale_span_max: float,
    vertical_scale_span_max: float,
    area_scale_span_max: float,
    anisotropy_p95_max: float,
    horizontal_min_rows: int,
    horizontal_min_trend_deg: float,
    horizontal_column_spread_max_deg: float,
) -> ProjectiveSelection:
    perspective_structural_applied = False
    original_projective_polygons = list(polygons)
    perspective_threshold = max(5.0, source_width * 0.002)
    line_supports_perspective = bool(
        line_geometry.recommendation == "perspective"
        and line_geometry.confidence >= 0.35
        and not line_geometry.separator_curve_reliable
    )

    def distortion_audit(candidate, *, row_before_polygons=None) -> dict:
        mapped_polygons = polygon_transformer(
            original_projective_polygons,
            candidate.matrix,
        )
        jacobian = jacobian_auditor(
            candidate.matrix,
            size,
            polygons=original_projective_polygons,
        )
        text_scale = scale_auditor(
            original_projective_polygons,
            mapped_polygons,
            size,
            writing_mode=settings.layout_writing_mode,
        )
        row_source = original_projective_polygons if row_before_polygons is None else row_before_polygons
        row_alignment = row_auditor(
            row_source,
            mapped_polygons,
            size=size,
            settings=settings,
        )
        jacobian_safe = bool(
            jacobian.valid
            and (jacobian.horizontal_scale_span_ratio <= horizontal_scale_span_max)
            and (jacobian.vertical_scale_span_ratio <= vertical_scale_span_max)
            and (jacobian.area_scale_span_ratio <= area_scale_span_max)
            and (jacobian.anisotropy_p95_ratio <= anisotropy_p95_max)
        )
        text_scale_safe = text_scale.verdict in {"stable", "insufficient"}
        distortion_cost = (
            jacobian.anisotropy_p95_ratio
            + 0.35 * jacobian.horizontal_scale_span_ratio
            + 0.35 * jacobian.vertical_scale_span_ratio
            + 0.20 * text_scale.anisotropy_p95_ratio
        )
        return {
            "candidate": candidate,
            "polygons": mapped_polygons,
            "jacobian": jacobian,
            "text_scale": text_scale,
            "row": row_alignment,
            "jacobian_safe": jacobian_safe,
            "text_scale_safe": text_scale_safe,
            "distortion_safe": bool(jacobian_safe and text_scale_safe),
            "distortion_cost": float(distortion_cost),
        }

    structural_candidate = None
    structural_entry = None
    try:
        structural_candidate = structural_estimator(
            original_projective_polygons,
            size,
            settings,
        )
        structural_entry = distortion_audit(structural_candidate)
    except Exception:
        structural_candidate = None
        structural_entry = None

    structural_evidence_safe = bool(
        structural_candidate is not None
        and float(getattr(structural_candidate, "strength_px", 0.0)) >= perspective_threshold
        and line_supports_perspective
        and str(getattr(structural_candidate, "classification", "unknown")) == "keystone"
    )
    structural_auto_safe = bool(
        structural_entry is not None and structural_evidence_safe and structural_entry["distortion_safe"]
    )
    perspective_structural_safe = structural_auto_safe

    # Stage A: in auto mode only a structurally justified + distortion-safe
    # keystone becomes the base. Explicit perspective mode remains an
    # intentional user override and can keep the structural candidate even
    # when the automatic safety gate rejects it.
    base_candidate = None
    base_polygons = original_projective_polygons
    if requested_geometry_mode == "auto":
        if structural_auto_safe:
            base_candidate = structural_candidate
            base_polygons = structural_entry["polygons"]
            perspective_structural_applied = True
    elif structural_candidate is not None:
        if float(getattr(structural_candidate, "strength_px", 0.0)) >= 0.75:
            base_candidate = structural_candidate
            base_polygons = structural_entry["polygons"]
            perspective_structural_applied = True

    # Stage B: estimate the residual horizontal projective direction on the
    # current base, then optimize only its strength. The optimizer transforms
    # polygons only, so evaluating ~10-20 strengths is inexpensive.
    horizontal_full = None
    horizontal_partial = None
    horizontal_row_audit = None
    horizontal_strength = 0.0
    horizontal_total_candidate = None
    horizontal_total_entry = None
    horizontal_evidence_safe = False
    try:
        horizontal_full = horizontal_estimator(
            base_polygons,
            size,
            settings,
        )
        (
            horizontal_partial,
            horizontal_row_audit,
            horizontal_strength,
        ) = strength_optimizer(
            base_polygons,
            size,
            horizontal_full,
            settings,
        )
        if base_candidate is not None:
            horizontal_total_candidate = perspective_composer(
                base_candidate,
                horizontal_partial,
                size,
            )
        else:
            horizontal_total_candidate = horizontal_partial

        horizontal_total_entry = distortion_audit(
            horizontal_total_candidate,
            row_before_polygons=base_polygons,
        )
        # Use the optimizer's row audit here because it measures exactly the
        # residual horizontal stage (base→partial VP), not source→combined.
        horizontal_total_entry["row"] = horizontal_row_audit
        before_column_trend = max(
            (
                abs(float(value))
                for value in getattr(
                    horizontal_row_audit,
                    "before_column_trends_deg",
                    (),
                )
            ),
            default=0.0,
        )
        horizontal_driver_trend = max(
            abs(float(horizontal_row_audit.before_trend_deg)),
            before_column_trend,
            abs(
                float(
                    getattr(
                        horizontal_row_audit,
                        "before_worst_region_span_deg",
                        0.0,
                    )
                )
            ),
        )
        vp_column_spread = float(
            getattr(
                horizontal_full,
                "horizontal_vp_column_spread_deg",
                0.0,
            )
        )
        # A reliable nonlinear separator curve is a reason to keep the
        # UVDoc review recommendation, but it must not veto a *separate*
        # low-distortion global horizontal correction. Pages such as 0010
        # and 0014 can have both: ~1° residual projective row drift that a
        # safe homography removes, plus smaller nonlinear curvature that
        # still deserves optional UVDoc review.
        horizontal_evidence_safe = bool(
            int(getattr(horizontal_full, "horizontal_row_count", 0)) >= horizontal_min_rows
            and line_geometry.confidence >= 0.35
            and not line_geometry.separator_curve_reliable
            and horizontal_driver_trend >= horizontal_min_trend_deg
            and (vp_column_spread <= horizontal_column_spread_max_deg or vp_column_spread <= 0.0)
            and horizontal_row_audit.verdict == "improved"
        )
    except Exception:
        horizontal_full = None
        horizontal_partial = None
        horizontal_row_audit = None
        horizontal_strength = 0.0
        horizontal_total_candidate = None
        horizontal_total_entry = None
        horizontal_evidence_safe = False

    horizontal_auto_safe = bool(
        horizontal_total_entry is not None and horizontal_evidence_safe and horizontal_total_entry["distortion_safe"]
    )

    selected_entry = None
    selected_candidate = None
    selected_horizontal_strength = 0.0

    if requested_geometry_mode == "auto":
        if horizontal_auto_safe:
            selected_entry = horizontal_total_entry
            selected_candidate = horizontal_total_candidate
            selected_horizontal_strength = horizontal_strength
        elif structural_auto_safe:
            selected_entry = structural_entry
            selected_candidate = structural_candidate
    else:
        # Explicit perspective is still an override, but prefer the optimized
        # residual-horizontal version when it actually improves row geometry.
        if (
            horizontal_total_entry is not None
            and horizontal_row_audit is not None
            and horizontal_row_audit.after_metric_deg < horizontal_row_audit.before_metric_deg
        ):
            selected_entry = horizontal_total_entry
            selected_candidate = horizontal_total_candidate
            selected_horizontal_strength = horizontal_strength
        elif structural_entry is not None:
            selected_entry = structural_entry
            selected_candidate = structural_candidate
        elif horizontal_total_entry is not None:
            selected_entry = horizontal_total_entry
            selected_candidate = horizontal_total_candidate
            selected_horizontal_strength = horizontal_strength

    # If auto mode applied no candidate, retain the most informative rejected
    # candidate in diagnostics without applying it.
    diagnostic_entry = selected_entry
    diagnostic_candidate = selected_candidate
    diagnostic_horizontal_strength = selected_horizontal_strength
    if diagnostic_entry is None:
        rejected_options: list[tuple[float, dict, object, float]] = []
        if structural_entry is not None and structural_candidate is not None:
            rejected_options.append(
                (
                    float(structural_entry["distortion_cost"]),
                    structural_entry,
                    structural_candidate,
                    0.0,
                )
            )
        if horizontal_total_entry is not None and horizontal_total_candidate is not None:
            row_metric = float(horizontal_row_audit.after_metric_deg) if horizontal_row_audit is not None else 999.0
            rejected_options.append(
                (
                    row_metric + float(horizontal_total_entry["distortion_cost"]),
                    horizontal_total_entry,
                    horizontal_total_candidate,
                    horizontal_strength,
                )
            )
        if rejected_options:
            _score, diagnostic_entry, diagnostic_candidate, diagnostic_horizontal_strength = min(
                rejected_options, key=lambda item: item[0]
            )

    return ProjectiveSelection(
        selected_entry=selected_entry,
        selected_candidate=selected_candidate,
        selected_horizontal_strength=selected_horizontal_strength,
        diagnostic_entry=diagnostic_entry,
        diagnostic_candidate=diagnostic_candidate,
        diagnostic_horizontal_strength=diagnostic_horizontal_strength,
        perspective_structural_applied=perspective_structural_applied,
        perspective_structural_safe=perspective_structural_safe,
        structural_auto_safe=structural_auto_safe,
        horizontal_auto_safe=horizontal_auto_safe,
        structural_candidate=structural_candidate,
        structural_entry=structural_entry,
        line_supports_perspective=line_supports_perspective,
        horizontal_total_candidate=horizontal_total_candidate,
        horizontal_full=horizontal_full,
        horizontal_row_audit=horizontal_row_audit,
        horizontal_strength=horizontal_strength,
    )
