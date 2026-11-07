"""Paired text-box scale stability audit independent of GUI and geometry facade.

Results remain the original geometry.TextScaleStabilityAudit class (pickle ABI).
Caller injects the class, helper hooks and five published safety thresholds
at invocation time; no import cycle or reverse dependency on geometry.py.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Iterable

import numpy as np


def polygon_inline_cross_size(
    polygon: np.ndarray,
    *,
    writing_mode: str,
) -> tuple[float, float, float, float] | None:
    poly = np.asarray(polygon, dtype=float)
    if poly.ndim != 2 or poly.shape[0] < 4 or poly.shape[1] < 2:
        return None
    points = poly[:4, :2]
    if not np.isfinite(points).all():
        return None
    edge_a1 = points[1] - points[0]
    edge_a2 = points[2] - points[3]
    edge_b1 = points[2] - points[1]
    edge_b2 = points[3] - points[0]
    length_a = (float(np.linalg.norm(edge_a1)) + float(np.linalg.norm(edge_a2))) / 2.0
    length_b = (float(np.linalg.norm(edge_b1)) + float(np.linalg.norm(edge_b2))) / 2.0
    if min(length_a, length_b) < 1.0:
        return None

    vector_a = (edge_a1 + edge_a2) / 2.0
    vector_b = (edge_b1 + edge_b2) / 2.0
    vertical = str(writing_mode or "horizontal-tb").startswith("vertical")
    if vertical:
        score_a = abs(float(vector_a[1])) / max(1e-9, float(np.linalg.norm(vector_a)))
        score_b = abs(float(vector_b[1])) / max(1e-9, float(np.linalg.norm(vector_b)))
    else:
        score_a = abs(float(vector_a[0])) / max(1e-9, float(np.linalg.norm(vector_a)))
        score_b = abs(float(vector_b[0])) / max(1e-9, float(np.linalg.norm(vector_b)))
    if score_a >= score_b:
        inline, cross = length_a, length_b
    else:
        inline, cross = length_b, length_a
    center = points.mean(axis=0)
    return float(center[0]), float(center[1]), float(inline), float(cross)


def robust_spatial_gradient_ratio(
    samples: list[tuple[float, float, float]],
    size: tuple[int, int],
) -> float:
    """Estimate multiplicative size drift across the page with robust log-plane fit."""
    if len(samples) < 12:
        return 0.0
    width, height = size
    values = np.asarray([sample[2] for sample in samples], dtype=float)
    xs = np.asarray([sample[0] for sample in samples], dtype=float)
    ys = np.asarray([sample[1] for sample in samples], dtype=float)
    valid = np.isfinite(values) & np.isfinite(xs) & np.isfinite(ys) & (values > 0.0)
    if int(valid.sum()) < 12:
        return 0.0
    values = values[valid]
    xs = xs[valid] / max(1.0, float(width)) - 0.5
    ys = ys[valid] / max(1.0, float(height)) - 0.5
    logs = np.log(values)
    design = np.column_stack([np.ones(len(logs)), xs, ys])
    keep = np.ones(len(logs), dtype=bool)
    coeff = np.zeros(3, dtype=float)
    for _ in range(4):
        if int(keep.sum()) < 10:
            break
        coeff, *_ = np.linalg.lstsq(design[keep], logs[keep], rcond=None)
        residual = logs - design @ coeff
        center = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - center)))
        threshold = max(0.08, mad * 3.5)
        new_keep = np.abs(residual - center) <= threshold
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep
    if int(keep.sum()) < 10:
        return 0.0
    coeff, *_ = np.linalg.lstsq(design[keep], logs[keep], rcond=None)
    gradient = math.hypot(float(coeff[1]), float(coeff[2]))
    return max(0.0, math.exp(gradient) - 1.0)


def audit_text_scale_stability(
    before_polygons: Iterable[np.ndarray],
    after_polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    *,
    writing_mode: str = "horizontal-tb",
    audit_type: Callable[..., Any],
    polygon_measure: Callable[..., tuple[float, float, float, float] | None],
    gradient_ratio: Callable[[list[tuple[float, float, float]], tuple[int, int]], float],
    limits: tuple[float, float, float, float, float],
) -> Any:
    """Measure the transform-induced scale field using paired text polygons."""
    (
        inline_span_max, cross_span_max, inline_gradient_max,
        cross_gradient_max, anisotropy_max,
    ) = limits
    before_list = list(before_polygons)
    after_list = list(after_polygons)
    count = min(len(before_list), len(after_list))
    if count < 12:
        return audit_type(sample_count=count)

    before_inline: list[tuple[float, float, float]] = []
    before_cross: list[tuple[float, float, float]] = []
    after_inline: list[tuple[float, float, float]] = []
    after_cross: list[tuple[float, float, float]] = []
    inline_ratio_samples: list[tuple[float, float, float]] = []
    cross_ratio_samples: list[tuple[float, float, float]] = []
    anisotropy: list[float] = []
    inline_ratios: list[float] = []
    cross_ratios: list[float] = []

    for before, after in zip(before_list[:count], after_list[:count]):
        first = polygon_measure(before, writing_mode=writing_mode)
        second = polygon_measure(after, writing_mode=writing_mode)
        if first is None or second is None:
            continue
        bx, by, bi, bc = first
        ax, ay, ai, ac = second
        if min(bi, bc, ai, ac) <= 1e-9:
            continue
        inline_ratio = float(ai / bi)
        cross_ratio = float(ac / bc)
        if (
            not math.isfinite(inline_ratio)
            or not math.isfinite(cross_ratio)
            or inline_ratio <= 0.0
            or cross_ratio <= 0.0
        ):
            continue

        before_inline.append((bx, by, bi))
        before_cross.append((bx, by, bc))
        after_inline.append((ax, ay, ai))
        after_cross.append((ax, ay, ac))
        inline_ratio_samples.append((bx, by, inline_ratio))
        cross_ratio_samples.append((bx, by, cross_ratio))
        inline_ratios.append(inline_ratio)
        cross_ratios.append(cross_ratio)
        anisotropy.append(
            max(inline_ratio / cross_ratio, cross_ratio / inline_ratio) - 1.0
        )

    paired = len(inline_ratios)
    if paired < 12:
        return audit_type(sample_count=paired)

    inline_values = np.asarray(inline_ratios, dtype=float)
    cross_values = np.asarray(cross_ratios, dtype=float)
    anisotropy_values = np.asarray(anisotropy, dtype=float)
    inline_p05, inline_median, inline_p95 = np.quantile(
        inline_values, [0.05, 0.50, 0.95]
    )
    cross_p05, cross_median, cross_p95 = np.quantile(
        cross_values, [0.05, 0.50, 0.95]
    )
    inline_span = (
        float(inline_p95 - inline_p05) / max(1e-9, float(inline_median))
    )
    cross_span = (
        float(cross_p95 - cross_p05) / max(1e-9, float(cross_median))
    )
    inline_gradient = gradient_ratio(
        inline_ratio_samples, size
    )
    cross_gradient = gradient_ratio(
        cross_ratio_samples, size
    )
    anisotropy_p95 = float(np.quantile(anisotropy_values, 0.95))

    # Absolute size trends are useful for diagnostics but can be confounded by
    # genuine typography (headwords, phonetics, mixed font sizes). They no
    # longer decide whether the transform is safe.
    before_inline_gradient = gradient_ratio(before_inline, size)
    after_inline_gradient = gradient_ratio(after_inline, size)
    before_cross_gradient = gradient_ratio(before_cross, size)
    after_cross_gradient = gradient_ratio(after_cross, size)
    before_score = 0.30 * before_inline_gradient + 0.70 * before_cross_gradient
    after_score = 0.30 * after_inline_gradient + 0.70 * after_cross_gradient

    # Slightly looser than the analytic Jacobian budget because polygon edge
    # lengths also carry detector quantization/orientation noise.
    safe = bool(
        inline_span <= inline_span_max
        and cross_span <= cross_span_max
        and inline_gradient <= inline_gradient_max
        and cross_gradient <= cross_gradient_max
        and anisotropy_p95 <= anisotropy_max
    )
    verdict = "stable" if safe else "worse"
    return audit_type(
        sample_count=paired,
        inline_ratio_p05=float(inline_p05),
        inline_ratio_median=float(inline_median),
        inline_ratio_p95=float(inline_p95),
        cross_ratio_p05=float(cross_p05),
        cross_ratio_median=float(cross_median),
        cross_ratio_p95=float(cross_p95),
        inline_ratio_span_ratio=max(0.0, inline_span),
        cross_ratio_span_ratio=max(0.0, cross_span),
        inline_ratio_gradient_ratio=max(0.0, inline_gradient),
        cross_ratio_gradient_ratio=max(0.0, cross_gradient),
        anisotropy_p95_ratio=max(0.0, anisotropy_p95),
        before_inline_gradient_ratio=before_inline_gradient,
        after_inline_gradient_ratio=after_inline_gradient,
        before_cross_gradient_ratio=before_cross_gradient,
        after_cross_gradient_ratio=after_cross_gradient,
        before_score=before_score,
        after_score=after_score,
        verdict=verdict,
    )
