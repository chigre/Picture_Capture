from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .layout_detection import infer_layout_from_boxes
from .models import AppSettings
from .preprocess_geometry import polygon_boxes


@dataclass(frozen=True, slots=True)
class TextLineGeometryAnalysis:
    """Diagnostic geometry derived from text-line directions, not text starts."""

    row_count: int = 0
    global_angle_deg: float = 0.0
    top_angle_deg: float = 0.0
    middle_angle_deg: float = 0.0
    bottom_angle_deg: float = 0.0
    angle_trend_deg: float = 0.0
    residual_mad_deg: float = 0.0
    residual_span_deg: float = 0.0
    separator_found: bool = False
    separator_residual_px: float = 0.0
    separator_span_ratio: float = 0.0
    recommendation: str = "insufficient"
    confidence: float = 0.0


def _normalize_half_turn(angle: float) -> float:
    value = float(angle)
    while value >= 90.0:
        value -= 180.0
    while value < -90.0:
        value += 180.0
    return value


def _weighted_median(values: Iterable[tuple[float, float]]) -> float:
    ordered = sorted(
        (float(value), max(0.0, float(weight)))
        for value, weight in values
    )
    if not ordered:
        return 0.0
    total = sum(weight for _value, weight in ordered)
    if total <= 0:
        return float(np.median([value for value, _weight in ordered]))
    target = total / 2.0
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= target:
            return value
    return ordered[-1][0]


def _polygon_orientation_sample(
    raw: np.ndarray,
) -> tuple[float, float, float, float] | None:
    poly = np.asarray(raw, dtype=float)
    if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
        return None
    x0 = float(poly[:, 0].min())
    x1 = float(poly[:, 0].max())
    y0 = float(poly[:, 1].min())
    y1 = float(poly[:, 1].max())
    width = x1 - x0
    height = y1 - y0
    if width < max(12.0, height * 1.35) or height < 3.0:
        return None

    edges: list[tuple[float, float]] = []
    for index in range(poly.shape[0]):
        p0 = poly[index, :2]
        p1 = poly[(index + 1) % poly.shape[0], :2]
        dx = float(p1[0] - p0[0])
        dy = float(p1[1] - p0[1])
        length = math.hypot(dx, dy)
        if length < max(8.0, height * 1.2):
            continue
        angle = _normalize_half_turn(math.degrees(math.atan2(dy, dx)))
        if abs(angle) <= 20.0 and abs(dx) >= abs(dy):
            edges.append((angle, length))
    if not edges:
        return None
    selected = sorted(edges, key=lambda item: item[1], reverse=True)[:2]
    angle = _weighted_median(selected)
    return (float((y0 + y1) / 2.0), angle, max(1.0, width), max(1.0, height))


def _cluster_rows(
    polygons: Iterable[np.ndarray],
) -> list[tuple[float, float, float]]:
    samples = [
        sample
        for raw in polygons
        if (sample := _polygon_orientation_sample(raw)) is not None
    ]
    if not samples:
        return []
    median_height = float(np.median([sample[3] for sample in samples]))
    tolerance = max(4.0, median_height * 0.72)
    samples.sort(key=lambda item: item[0])

    clusters: list[list[tuple[float, float, float, float]]] = []
    for sample in samples:
        if not clusters:
            clusters.append([sample])
            continue
        cluster_y = _weighted_median(
            (item[0], item[2]) for item in clusters[-1]
        )
        if abs(sample[0] - cluster_y) <= tolerance:
            clusters[-1].append(sample)
        else:
            clusters.append([sample])

    rows: list[tuple[float, float, float]] = []
    for cluster in clusters:
        y = _weighted_median((item[0], item[2]) for item in cluster)
        angle = _weighted_median((item[1], item[2]) for item in cluster)
        weight = sum(item[2] for item in cluster)
        rows.append((y, angle, max(1.0, weight)))
    return rows


def _robust_angle_trend(
    rows: list[tuple[float, float, float]],
) -> tuple[float, float, float, float, float, float, float]:
    if len(rows) < 5:
        raise RuntimeError("有效文本行不足")
    ys = np.asarray([row[0] for row in rows], dtype=float)
    angles = np.asarray([row[1] for row in rows], dtype=float)
    weights = np.sqrt(np.asarray([row[2] for row in rows], dtype=float))
    y_min = float(ys.min())
    y_max = float(ys.max())
    span = max(1.0, y_max - y_min)
    norm_y = (ys - y_min) / span - 0.5
    keep = np.ones(len(rows), dtype=bool)

    slope = 0.0
    intercept = float(np.median(angles))
    for _ in range(4):
        if int(keep.sum()) < 5:
            break
        slope, intercept = np.polyfit(
            norm_y[keep], angles[keep], 1, w=weights[keep],
        )
        residual = angles - (slope * norm_y + intercept)
        center = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - center)))
        threshold = max(0.12, mad * 3.5)
        new_keep = np.abs(residual - center) <= threshold
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep

    if int(keep.sum()) >= 5:
        slope, intercept = np.polyfit(
            norm_y[keep], angles[keep], 1, w=weights[keep],
        )
    predicted = slope * norm_y + intercept
    residual = angles - predicted
    valid_residual = residual[keep] if int(keep.sum()) else residual
    residual_center = float(np.median(valid_residual))
    residual_mad = float(np.median(np.abs(valid_residual - residual_center)))
    residual_span = float(
        np.percentile(valid_residual, 95) - np.percentile(valid_residual, 5)
    )
    top = float(intercept - slope * 0.5)
    middle = float(intercept)
    bottom = float(intercept + slope * 0.5)
    return (
        middle,
        top,
        middle,
        bottom,
        float(slope),
        max(0.0, residual_mad),
        max(0.0, residual_span),
    )


def _fit_separator_track(
    gray: np.ndarray,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
) -> tuple[float, float, float] | None:
    if x1 - x0 < 4 or y1 - y0 < 80:
        return None
    band = gray[y0:y1, x0:x1]
    dark = np.clip(215.0 - band.astype(float), 0.0, 215.0)
    dark_fraction = (band < 175).mean(axis=0)
    mean_dark = dark.mean(axis=0) / 215.0
    score = dark_fraction * 0.72 + mean_dark * 0.28
    best_local = int(np.argmax(score))
    best_score = float(score[best_local])
    if best_score < 0.16:
        return None
    peak_x = x0 + best_local

    bins = max(12, min(28, int(round((y1 - y0) / 55.0))))
    edges = np.linspace(y0, y1, bins + 1, dtype=int)
    radius = max(3, min(18, round((x1 - x0) * 0.18)))
    xs: list[float] = []
    ys: list[float] = []
    weights: list[float] = []
    for index in range(bins):
        ya = int(edges[index])
        yb = int(edges[index + 1])
        if yb - ya < 3:
            continue
        xa = max(x0, peak_x - radius)
        xb = min(x1, peak_x + radius + 1)
        local = gray[ya:yb, xa:xb]
        if local.size == 0:
            continue
        local_dark_fraction = (local < 175).mean(axis=0)
        local_mean_dark = np.clip(
            215.0 - local.astype(float), 0.0, 215.0
        ).mean(axis=0) / 215.0
        local_score = local_dark_fraction * 0.72 + local_mean_dark * 0.28
        pos = int(np.argmax(local_score))
        strength = float(local_score[pos])
        if strength < max(0.08, best_score * 0.25):
            continue
        xs.append(float(xa + pos))
        ys.append(float((ya + yb - 1) / 2.0))
        weights.append(max(0.05, strength))

    if len(xs) < max(8, bins // 2):
        return None

    x_values = np.asarray(xs, dtype=float)
    y_values = np.asarray(ys, dtype=float)
    w_values = np.sqrt(np.asarray(weights, dtype=float))
    keep = np.ones(len(xs), dtype=bool)
    for _ in range(4):
        if int(keep.sum()) < 6:
            break
        slope, intercept = np.polyfit(
            y_values[keep], x_values[keep], 1, w=w_values[keep],
        )
        residual = x_values - (slope * y_values + intercept)
        center = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - center)))
        threshold = max(1.25, mad * 3.5)
        new_keep = np.abs(residual - center) <= threshold
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep

    if int(keep.sum()) < 6:
        return None
    slope, intercept = np.polyfit(
        y_values[keep], x_values[keep], 1, w=w_values[keep],
    )
    residual = x_values[keep] - (
        slope * y_values[keep] + intercept
    )
    residual_span = float(
        np.percentile(residual, 95) - np.percentile(residual, 5)
    )
    span_ratio = float(keep.sum()) / float(bins)
    quality = best_score * span_ratio
    return max(0.0, residual_span), span_ratio, quality


def _separator_geometry(
    image: Image.Image,
    polygons: list[np.ndarray],
    settings: AppSettings,
) -> tuple[bool, float, float]:
    width, height = image.size
    boxes = polygon_boxes(polygons, width, height)
    if len(boxes) < 8:
        return False, 0.0, 0.0
    try:
        layout = infer_layout_from_boxes(
            boxes,
            image.size,
            display_scale=1.0,
            ink_mask=None,
            columns_policy=settings.layout_columns_policy,
            fixed_columns=settings.columns,
            column_separator_mode=settings.layout_column_separator_mode,
        )
    except Exception:
        return False, 0.0, 0.0
    starts = tuple(int(v) for v in layout.column_starts)
    if len(starts) < 2:
        return False, 0.0, 0.0
    rights = tuple(int(v) for v in layout.column_rights)
    gray = np.asarray(normalize_page_rgb(image).convert("L"), dtype=np.uint8)
    body_top = max(0, int(layout.start_y))
    body_bottom = min(height, int(layout.bottom_y))
    if body_bottom - body_top < 80:
        return False, 0.0, 0.0

    candidates: list[tuple[float, float, float]] = []
    for index in range(len(starts) - 1):
        left = (
            rights[index]
            if len(rights) == len(starts)
            else starts[index] + int(layout.column_width)
        )
        right = starts[index + 1]
        gap = right - left
        if gap < 6:
            continue
        inset = max(1, round(gap * 0.08))
        result = _fit_separator_track(
            gray,
            max(0, left + inset),
            min(width, right - inset),
            body_top,
            body_bottom,
        )
        if result is not None:
            candidates.append(result)

    if not candidates:
        return False, 0.0, 0.0
    residual, span_ratio, _quality = max(
        candidates, key=lambda item: item[2]
    )
    return True, float(residual), float(span_ratio)


def analyze_text_line_geometry(
    image: Image.Image,
    polygons: Iterable[np.ndarray],
    settings: AppSettings,
) -> TextLineGeometryAnalysis:
    """Analyze page geometry from text-line direction plus real straight lines.

    This function is diagnostic only.  It never creates a nonlinear warp.
    """
    if str(settings.layout_writing_mode or "horizontal-tb").startswith("vertical"):
        return TextLineGeometryAnalysis(recommendation="insufficient")

    polygon_list = [np.asarray(poly, dtype=float) for poly in polygons]
    rows = _cluster_rows(polygon_list)
    if len(rows) < 5:
        return TextLineGeometryAnalysis(
            row_count=len(rows),
            recommendation="insufficient",
            confidence=min(0.35, len(rows) / 12.0),
        )

    (
        global_angle,
        top_angle,
        middle_angle,
        bottom_angle,
        angle_trend,
        residual_mad,
        residual_span,
    ) = _robust_angle_trend(rows)
    separator_found, separator_residual, separator_span_ratio = (
        _separator_geometry(image, polygon_list, settings)
    )

    row_factor = min(1.0, len(rows) / 18.0)
    residual_factor = max(0.25, 1.0 - min(1.0, residual_mad / 0.45))
    separator_factor = 1.0 if separator_found else 0.78
    confidence = max(
        0.0,
        min(1.0, row_factor * residual_factor * separator_factor),
    )

    # A real long separator is a much stronger nonlinear-geometry witness than
    # OCR text starts. Perspective/rotation may tilt a straight line but cannot
    # bend it; a large post-linear-fit residual therefore supports UVDoc review.
    separator_curve_threshold = max(3.0, image.width * 0.0015)
    if (
        separator_found
        and separator_span_ratio >= 0.55
        and separator_residual >= separator_curve_threshold
    ):
        recommendation = "uvdoc_review"
    elif abs(angle_trend) >= 0.18 and residual_mad <= 0.22 and len(rows) >= 8:
        recommendation = "perspective"
    elif abs(global_angle) >= 0.12 and len(rows) >= 6:
        recommendation = "deskew"
    elif residual_span >= 0.55 and len(rows) >= 10:
        # If the real separator remains straight, disagreement among OCR line
        # angles is more likely layout/detection noise than page curvature.
        recommendation = "manual_review"
    else:
        recommendation = "none"

    return TextLineGeometryAnalysis(
        row_count=len(rows),
        global_angle_deg=round(float(global_angle), 4),
        top_angle_deg=round(float(top_angle), 4),
        middle_angle_deg=round(float(middle_angle), 4),
        bottom_angle_deg=round(float(bottom_angle), 4),
        angle_trend_deg=round(float(angle_trend), 4),
        residual_mad_deg=round(float(residual_mad), 4),
        residual_span_deg=round(float(residual_span), 4),
        separator_found=bool(separator_found),
        separator_residual_px=round(float(separator_residual), 3),
        separator_span_ratio=round(float(separator_span_ratio), 4),
        recommendation=recommendation,
        confidence=round(float(confidence), 4),
    )
