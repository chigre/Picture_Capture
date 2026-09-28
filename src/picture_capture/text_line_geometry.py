from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .layout_detection import infer_layout_from_boxes
from .models import AppSettings
from .preprocess_geometry import horizontal_column_rows, polygon_boxes


SEPARATOR_CURVE_SPAN_MIN = 0.72
SEPARATOR_TRACK_QUALITY_MIN = 0.12
SEPARATOR_CURVATURE_SCORE_MIN = 0.35
SEPARATOR_CURVE_WIDTH_RATIO_THRESHOLD = 0.0015
SEPARATOR_JUMP_MIN_PX = 4.0
SEPARATOR_JUMP_WIDTH_RATIO_MAX = 0.003


@dataclass(frozen=True, slots=True)
class _SeparatorTrack:
    residual_span_px: float
    span_ratio: float
    quality: float
    slope_px_per_1000y: float
    drift_px: float
    jump_p95_px: float
    curvature_score: float
    xs: tuple[float, ...] = ()
    ys: tuple[float, ...] = ()


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
    column_count: int = 0
    valid_column_count: int = 0
    valid_column_indices: tuple[int, ...] = ()
    column_row_counts: tuple[int, ...] = ()
    column_trends_deg: tuple[float, ...] = ()
    worst_column_index: int = -1
    worst_column_trend_deg: float = 0.0
    worst_region_angle_deg: float = 0.0
    separator_found: bool = False
    separator_residual_px: float = 0.0
    separator_span_ratio: float = 0.0
    separator_slope_px_per_1000y: float = 0.0
    separator_drift_px: float = 0.0
    separator_track_quality: float = 0.0
    separator_track_jump_p95_px: float = 0.0
    separator_curvature_score: float = 0.0
    separator_curve_reliable: bool = False
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


def _separator_score_rows(
    gray: np.ndarray,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
) -> tuple[np.ndarray, np.ndarray]:
    bins = max(12, min(30, int(round((y1 - y0) / 48.0))))
    edges = np.linspace(y0, y1, bins + 1, dtype=int)
    rows: list[np.ndarray] = []
    for index in range(bins):
        ya = int(edges[index])
        yb = int(edges[index + 1])
        local = gray[ya:yb, x0:x1]
        if local.size == 0:
            rows.append(np.zeros(max(1, x1 - x0), dtype=float))
            continue
        dark_fraction = (local < 175).mean(axis=0)
        mean_dark = np.clip(
            215.0 - local.astype(float), 0.0, 215.0
        ).mean(axis=0) / 215.0
        rows.append(dark_fraction * 0.78 + mean_dark * 0.22)
    return np.vstack(rows), edges


def _best_linear_separator_seed(
    scores: np.ndarray,
) -> tuple[float, float, float, float] | None:
    """Find a persistent straight/slanted dark track before local curve fitting.

    Searching a family of linear paths is more robust than anchoring on one
    full-height X column: a real separator can move tens of pixels from top to
    bottom after scan rotation, while repeated text strokes can otherwise win
    the fixed-X persistence score.
    """
    bins, band_width = scores.shape
    if bins < 6 or band_width < 4:
        return None
    t = np.linspace(0.0, 1.0, bins)
    max_drift = min(120, max(12, int(round(band_width * 0.55))))
    best: tuple[float, float, float, float, float, float] | None = None

    def consider(drift_values: Iterable[int]) -> None:
        nonlocal best
        for drift in drift_values:
            lo = max(0, -int(drift))
            hi = min(band_width - 1, band_width - 1 - int(drift))
            if hi < lo:
                continue
            starts = np.arange(lo, hi + 1, dtype=int)
            positions = np.rint(
                starts[None, :] + float(drift) * t[:, None]
            ).astype(int)
            values = scores[np.arange(bins)[:, None], positions]
            median = np.median(values, axis=0)
            q20 = np.quantile(values, 0.20, axis=0)
            mean = values.mean(axis=0)
            objective = median * 0.55 + q20 * 0.35 + mean * 0.10
            index = int(np.argmax(objective))
            candidate = (
                float(objective[index]),
                float(drift),
                float(starts[index]),
                float(median[index]),
                float(q20[index]),
                float(mean[index]),
            )
            if best is None or candidate[0] > best[0]:
                best = candidate

    # Coarse-to-fine search keeps this cheap enough for multi-thousand-page
    # dictionary projects while still resolving 1 px of total top-bottom drift.
    consider(range(-max_drift, max_drift + 1, 2))
    if best is None:
        return None
    coarse_drift = int(round(best[1]))
    consider(range(
        max(-max_drift, coarse_drift - 3),
        min(max_drift, coarse_drift + 3) + 1,
    ))
    assert best is not None
    _objective, drift, start, median_strength, q20_strength, mean_strength = best
    # A genuinely curved line can leave any single straight seed for several
    # bins, so Q20 may legitimately be near zero. Require a strong median/mean
    # seed, then let the local continuity tracker and final coverage/curvature
    # checks decide whether this is a physical line.
    if median_strength < 0.08 or mean_strength < 0.10:
        return None
    return start, drift, median_strength, q20_strength


def _separator_curvature_score(
    residual: np.ndarray,
) -> float:
    """Return 0..1 smooth-curvature coherence after removing the best line."""
    values = np.asarray(residual, dtype=float)
    if values.size < 7:
        return 0.0
    smooth = np.empty_like(values)
    for index in range(len(values)):
        lo = max(0, index - 2)
        hi = min(len(values), index + 3)
        smooth[index] = float(np.median(values[lo:hi]))
    smooth_span = float(
        np.percentile(smooth, 90) - np.percentile(smooth, 10)
    )
    noise = values - smooth
    noise_center = float(np.median(noise))
    noise_mad = float(np.median(np.abs(noise - noise_center)))
    denominator = smooth_span + 6.0 * noise_mad
    if denominator <= 1e-9:
        return 0.0
    return max(0.0, min(1.0, smooth_span / denominator))


def _fit_separator_track(
    gray: np.ndarray,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
) -> _SeparatorTrack | None:
    if x1 - x0 < 4 or y1 - y0 < 80:
        return None

    scores, edges = _separator_score_rows(gray, x0, x1, y0, y1)
    seed = _best_linear_separator_seed(scores)
    if seed is None:
        return None
    start, total_drift, median_strength, q20_strength = seed

    bins, band_width = scores.shape
    predicted = start + total_drift * np.linspace(0.0, 1.0, bins)
    # Allow enough local freedom to follow real smooth curvature, but penalize
    # sudden departures from the predicted/previous path so short text strokes
    # cannot pull independent bins to unrelated X positions.
    local_radius = max(5, min(12, int(round(band_width * 0.06))))
    expected_step = total_drift / max(1.0, float(bins - 1))
    xs: list[float] = []
    ys: list[float] = []
    strengths: list[float] = []
    previous_local_x: float | None = None

    for index in range(bins):
        center = int(round(predicted[index]))
        xa = max(0, center - local_radius)
        xb = min(band_width, center + local_radius + 1)
        if xb <= xa:
            continue
        local_scores = scores[index, xa:xb]
        positions = np.arange(xa, xb, dtype=float)
        if previous_local_x is None:
            reference = float(predicted[index])
        else:
            continued = previous_local_x + expected_step
            reference = 0.72 * continued + 0.28 * float(predicted[index])
        distance_penalty = 0.018 * np.abs(positions - reference)
        adjusted = local_scores - distance_penalty
        pos = int(np.argmax(adjusted))
        strength = float(local_scores[pos])
        if strength < max(0.06, min(median_strength * 0.35, q20_strength * 0.65)):
            continue
        chosen_local_x = float(xa + pos)
        previous_local_x = chosen_local_x
        xs.append(float(x0) + chosen_local_x)
        ys.append(float((int(edges[index]) + int(edges[index + 1]) - 1) / 2.0))
        strengths.append(strength)

    if len(xs) < max(8, int(math.ceil(bins * 0.65))):
        return None

    x_values = np.asarray(xs, dtype=float)
    y_values = np.asarray(ys, dtype=float)
    strength_values = np.asarray(strengths, dtype=float)
    weights = np.sqrt(np.maximum(0.05, strength_values))

    keep = np.ones(len(x_values), dtype=bool)
    for _ in range(3):
        if int(keep.sum()) < 7:
            return None
        slope, intercept = np.polyfit(
            y_values[keep], x_values[keep], 1, w=weights[keep],
        )
        residual = x_values - (slope * y_values + intercept)
        center = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - center)))
        threshold = max(2.0, mad * 4.0)
        new_keep = np.abs(residual - center) <= threshold
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep

    if int(keep.sum()) < max(7, int(math.ceil(bins * 0.55))):
        return None
    x_values = x_values[keep]
    y_values = y_values[keep]
    strength_values = strength_values[keep]
    weights = weights[keep]

    slope, intercept = np.polyfit(
        y_values, x_values, 1, w=weights,
    )
    residual = x_values - (slope * y_values + intercept)
    residual_span = float(
        np.percentile(residual, 90) - np.percentile(residual, 10)
    )
    span_ratio = float(len(x_values)) / float(bins)
    quality = (
        float(np.median(strength_values))
        * span_ratio
        * min(1.0, median_strength / 0.18)
    )
    drift_px = float(slope * (y1 - y0))
    slope_per_1000y = float(slope * 1000.0)
    jumps = np.abs(np.diff(x_values))
    jump_p95 = float(np.percentile(jumps, 95)) if len(jumps) else 0.0
    curvature_score = _separator_curvature_score(residual)
    return _SeparatorTrack(
        residual_span_px=max(0.0, residual_span),
        span_ratio=span_ratio,
        quality=max(0.0, quality),
        slope_px_per_1000y=slope_per_1000y,
        drift_px=drift_px,
        jump_p95_px=max(0.0, jump_p95),
        curvature_score=curvature_score,
        xs=tuple(float(v) for v in x_values),
        ys=tuple(float(v) for v in y_values),
    )

def _selected_separator_track(
    image: Image.Image,
    polygons: list[np.ndarray],
    settings: AppSettings,
) -> _SeparatorTrack | None:
    """Return the best persistent physical separator track, including points."""
    width, height = image.size
    boxes = polygon_boxes(polygons, width, height)
    if len(boxes) < 8:
        return None
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
        return None
    starts = tuple(int(v) for v in layout.column_starts)
    if len(starts) < 2:
        return None
    rights = tuple(int(v) for v in layout.column_rights)
    gray = np.asarray(normalize_page_rgb(image).convert("L"), dtype=np.uint8)
    body_top = max(0, int(layout.start_y))
    body_bottom = min(height, int(layout.bottom_y))
    if body_bottom - body_top < 80:
        return None

    candidates: list[_SeparatorTrack] = []
    for index in range(len(starts) - 1):
        left = (
            rights[index]
            if len(rights) == len(starts)
            else starts[index] + int(layout.column_width)
        )
        right = starts[index + 1]
        gap = right - left

        search_bands: list[tuple[int, int]] = []
        if gap >= 6:
            inset = max(1, round(gap * 0.05))
            search_bands.append((
                max(0, left + inset),
                min(width, right - inset),
            ))

        pitch = max(1, starts[index + 1] - starts[index])
        if gap >= 6:
            center = (left + right) / 2.0
        else:
            center = (starts[index] + starts[index + 1]) / 2.0
        half = max(14, min(90, round(pitch * 0.18)))
        search_bands.append((
            max(0, round(center - half)),
            min(width, round(center + half)),
        ))

        seen: set[tuple[int, int]] = set()
        for xa, xb in search_bands:
            band_key = (int(xa), int(xb))
            if band_key in seen or xb - xa < 4:
                continue
            seen.add(band_key)
            result = _fit_separator_track(
                gray, int(xa), int(xb), body_top, body_bottom,
            )
            if result is not None:
                candidates.append(result)

    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            item.quality / (1.0 + 0.08 * item.jump_p95_px),
            item.span_ratio,
            -item.jump_p95_px,
        ),
    )


def separator_track_points(
    image: Image.Image,
    polygons: Iterable[np.ndarray],
    settings: AppSettings,
) -> tuple[tuple[float, float], ...]:
    """Return robust (y, x) samples of the strongest physical column separator."""
    polygon_list = [np.asarray(poly, dtype=float) for poly in polygons]
    selected = _selected_separator_track(image, polygon_list, settings)
    if selected is None:
        return ()
    return tuple(
        (float(y), float(x))
        for y, x in zip(selected.ys, selected.xs)
    )


def horizontal_rule_track_points(
    image: Image.Image,
    polygons: Iterable[np.ndarray],
    settings: AppSettings,
) -> tuple[tuple[float, float], ...]:
    """Return robust (x, y) samples of the strongest page-header horizontal rule.

    Dictionary scans often contain a long rule between the running header and
    the two-column body. That rule is stronger structural evidence for absolute
    horizontal orientation than the mean OCR angle: global deskew can make the
    middle body look level while rotating an already-near-horizontal header rule
    visibly away from level.

    Reuse the persistent-track detector on a transposed image. In transposed
    coordinates it tracks original-Y as a function of original-X, which is
    exactly a horizontal rule y(x).
    """
    source = normalize_page_rgb(image)
    width, height = source.size
    polygon_list = [np.asarray(poly, dtype=float) for poly in polygons]
    boxes = polygon_boxes(polygon_list, width, height)
    if len(boxes) < 8:
        return ()
    try:
        layout = infer_layout_from_boxes(
            boxes,
            source.size,
            display_scale=1.0,
            ink_mask=None,
            columns_policy=settings.layout_columns_policy,
            fixed_columns=settings.columns,
            column_separator_mode=settings.layout_column_separator_mode,
        )
    except Exception:
        return ()

    body_top = max(0, min(height - 1, int(layout.start_y)))
    if body_top < 40:
        return ()

    # Search a conservative band ending just below the inferred body start.
    # The band is intentionally much taller than a rule stroke but far smaller
    # than the full page, so text baselines cannot dominate a persistent track.
    search_top = max(
        0,
        body_top - max(90, int(round(height * 0.075))),
    )
    search_bottom = min(
        height,
        body_top + max(12, int(round(height * 0.008))),
    )
    if search_bottom - search_top < 12:
        return ()

    # Use the text/body envelope horizontally, with a small inset to avoid scan
    # edge marks. The header rule normally spans both columns.
    box_left = min(item[0] for item in boxes)
    box_right = max(item[2] for item in boxes)
    inset = max(2, int(round(width * 0.01)))
    content_left = max(inset, int(box_left))
    content_right = min(width - inset, int(box_right))
    if content_right - content_left < max(120, int(round(width * 0.45))):
        content_left = inset
        content_right = width - inset

    gray = np.asarray(source.convert("L"), dtype=np.uint8)
    transposed = gray.T
    selected = _fit_separator_track(
        transposed,
        search_top,
        search_bottom,
        content_left,
        content_right,
    )
    if selected is None:
        return ()
    if selected.span_ratio < 0.65 or selected.quality < 0.10:
        return ()
    # In the transposed image:
    # selected.ys = original X, selected.xs = original Y.
    return tuple(
        (float(x), float(y))
        for x, y in zip(selected.ys, selected.xs)
    )


def _separator_geometry(
    image: Image.Image,
    polygons: list[np.ndarray],
    settings: AppSettings,
) -> tuple[bool, float, float, float, float, float, float, float]:
    selected = _selected_separator_track(image, polygons, settings)
    if selected is None:
        return False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    return (
        True,
        float(selected.residual_span_px),
        float(selected.span_ratio),
        float(selected.slope_px_per_1000y),
        float(selected.drift_px),
        float(selected.quality),
        float(selected.jump_p95_px),
        float(selected.curvature_score),
    )

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
    column_rows_xy = horizontal_column_rows(
        polygon_list, image.size, settings,
    )
    column_rows = [
        [(row[1], row[2], row[3]) for row in rows]
        for rows in column_rows_xy
    ]
    valid_columns = [rows for rows in column_rows if len(rows) >= 5]
    rows = [row for column in valid_columns for row in column]
    if len(rows) < 5:
        return TextLineGeometryAnalysis(
            row_count=len(rows),
            column_count=len(column_rows),
            valid_column_count=len(valid_columns),
            valid_column_indices=tuple(
                index
                for index, column in enumerate(column_rows)
                if len(column) >= 5
            ),
            column_row_counts=tuple(len(column) for column in column_rows),
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

    column_trends: list[float] = []
    column_region_angles: list[float] = []
    valid_column_indices: list[int] = []
    for index, column in enumerate(column_rows):
        if len(column) < 5:
            continue
        try:
            (
                _column_global,
                column_top,
                column_middle,
                column_bottom,
                column_trend,
                _column_mad,
                _column_span,
            ) = _robust_angle_trend(column)
        except RuntimeError:
            continue
        column_trends.append(float(column_trend))
        column_region_angles.append(
            max(
                abs(float(column_top)),
                abs(float(column_middle)),
                abs(float(column_bottom)),
            )
        )
        valid_column_indices.append(index)

    if column_trends:
        worst_position = int(np.argmax(np.abs(column_trends)))
        worst_column_index = valid_column_indices[worst_position]
        worst_column_trend = float(column_trends[worst_position])
        worst_region_angle = max(column_region_angles)
    else:
        worst_column_index = -1
        worst_column_trend = 0.0
        worst_region_angle = max(
            abs(float(top_angle)),
            abs(float(middle_angle)),
            abs(float(bottom_angle)),
        )
    (
        separator_found,
        separator_residual,
        separator_span_ratio,
        separator_slope_per_1000y,
        separator_drift_px,
        separator_track_quality,
        separator_track_jump_p95_px,
        separator_curvature_score,
    ) = _separator_geometry(image, polygon_list, settings)

    row_factor = min(1.0, len(rows) / 18.0)
    residual_factor = max(0.25, 1.0 - min(1.0, residual_mad / 0.45))
    # Physical separators are optional structural evidence. Their absence must
    # not reduce confidence in a coherent text-line trend, because many
    # dictionaries have no ruling lines at all.
    confidence = max(
        0.0,
        min(1.0, row_factor * residual_factor),
    )

    # A real long separator is a much stronger nonlinear-geometry witness than
    # OCR text starts. Perspective/rotation may tilt a straight line but cannot
    # bend it; a large post-linear-fit residual therefore supports UVDoc review.
    separator_curve_threshold = max(
        3.0, image.width * SEPARATOR_CURVE_WIDTH_RATIO_THRESHOLD
    )
    separator_jump_limit = max(
        SEPARATOR_JUMP_MIN_PX,
        image.width * SEPARATOR_JUMP_WIDTH_RATIO_MAX,
    )
    separator_curve_reliable = bool(
        separator_found
        and separator_span_ratio >= SEPARATOR_CURVE_SPAN_MIN
        and separator_track_quality >= SEPARATOR_TRACK_QUALITY_MIN
        and separator_track_jump_p95_px <= separator_jump_limit
        and separator_curvature_score >= SEPARATOR_CURVATURE_SCORE_MIN
        and separator_residual >= separator_curve_threshold
    )
    if separator_curve_reliable:
        recommendation = "uvdoc_review"
    elif (
        max(abs(angle_trend), abs(worst_column_trend)) >= 0.18
        and residual_mad <= 0.22
        and len(rows) >= 8
    ):
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
        column_count=len(column_rows),
        valid_column_count=len(valid_columns),
        valid_column_indices=tuple(valid_column_indices),
        column_row_counts=tuple(len(column) for column in column_rows),
        column_trends_deg=tuple(round(float(v), 4) for v in column_trends),
        worst_column_index=int(worst_column_index),
        worst_column_trend_deg=round(float(worst_column_trend), 4),
        worst_region_angle_deg=round(float(worst_region_angle), 4),
        separator_found=bool(separator_found),
        separator_residual_px=round(float(separator_residual), 3),
        separator_span_ratio=round(float(separator_span_ratio), 4),
        separator_slope_px_per_1000y=round(float(separator_slope_per_1000y), 3),
        separator_drift_px=round(float(separator_drift_px), 3),
        separator_track_quality=round(float(separator_track_quality), 4),
        separator_track_jump_p95_px=round(float(separator_track_jump_p95_px), 3),
        separator_curvature_score=round(float(separator_curvature_score), 4),
        separator_curve_reliable=bool(separator_curve_reliable),
        recommendation=recommendation,
        confidence=round(float(confidence), 4),
    )
