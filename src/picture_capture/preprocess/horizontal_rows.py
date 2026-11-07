"""N-column horizontal row grouping and polygon edge geometry; no GUI or layout imports.

The geometry compatibility boundary supplies layout detection, settings defaults,
and previous patchpoints at each invocation, with no runtime global hooks.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Iterable
import numpy as np


def normalize_text_angle(angle: float) -> float:
    value = float(angle)
    while value >= 90.0:
        value -= 180.0
    while value < -90.0:
        value += 180.0
    return value


def weighted_median_pairs(values: list[tuple[float, float]]) -> float:
    if not values:
        return 0.0
    ordered = sorted(
        (float(value), max(0.0, float(weight)))
        for value, weight in values
    )
    total = sum(weight for _value, weight in ordered)
    if total <= 0.0:
        return float(np.median([value for value, _weight in ordered]))
    target = total / 2.0
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= target:
            return value
    return ordered[-1][0]


def weighted_percentile_pairs(values: list[tuple[float, float]], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(
        (float(value), max(0.0, float(weight)))
        for value, weight in values
    )
    total = sum(weight for _value, weight in ordered)
    if total <= 0.0:
        return float(np.percentile([value for value, _weight in ordered], percentile))
    target = total * max(0.0, min(100.0, float(percentile))) / 100.0
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= target:
            return value
    return ordered[-1][0]


def horizontal_polygon_edge_angles(raw: np.ndarray, *, normalize_angle: Callable[[float], float]) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Return independent top/bottom edge angles for one OCR text polygon.

    True row horizontality requires *both* long horizontal edges to be level.
    Collapsing a quadrilateral to one representative angle can hide a trapezoid
    or projective shear where the top edge and bottom edge tilt in opposite
    directions.
    """
    poly = np.asarray(raw, dtype=float)
    if poly.ndim != 2 or poly.shape[0] < 4 or poly.shape[1] < 2:
        return None
    points = poly[:, :2]
    if not np.isfinite(points).all():
        return None
    width = float(points[:, 0].max() - points[:, 0].min())
    height = float(points[:, 1].max() - points[:, 1].min())
    if width < max(12.0, height * 1.35) or height < 3.0:
        return None

    edges: list[tuple[float, float, float]] = []
    for index in range(len(points)):
        p0 = points[index]
        p1 = points[(index + 1) % len(points)]
        dx = float(p1[0] - p0[0])
        dy = float(p1[1] - p0[1])
        length = math.hypot(dx, dy)
        if length < max(8.0, height * 1.2):
            continue
        angle = normalize_angle(math.degrees(math.atan2(dy, dx)))
        if abs(angle) <= 20.0 and abs(dx) >= abs(dy):
            midpoint_y = float((p0[1] + p1[1]) / 2.0)
            edges.append((midpoint_y, angle, length))
    if len(edges) < 2:
        return None

    ordered = sorted(edges, key=lambda item: item[0])
    top = ordered[0]
    bottom = ordered[-1]
    if top is bottom:
        return None
    return (
        (float(top[1]), float(top[2])),
        (float(bottom[1]), float(bottom[2])),
    )


def horizontal_polygon_sample(raw: np.ndarray, *, edge_angles: Callable[..., Any]) -> tuple[float, float, float, float, float] | None:
    poly = np.asarray(raw, dtype=float)
    if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
        return None
    points = poly[:, :2]
    if not np.isfinite(points).all():
        return None
    x0 = float(points[:, 0].min())
    x1 = float(points[:, 0].max())
    y0 = float(points[:, 1].min())
    y1 = float(points[:, 1].max())
    width = x1 - x0
    height = y1 - y0
    if width < max(12.0, height * 1.35) or height < 3.0:
        return None

    edge_pair = edge_angles(poly)
    if edge_pair is None:
        return None
    (top_angle, top_length), (bottom_angle, bottom_length) = edge_pair
    total_length = max(1e-9, top_length + bottom_length)
    # Angles are constrained to ±20°, so a length-weighted mean is stable and
    # uses both boundaries instead of silently selecting only one of them.
    angle = (
        top_angle * top_length + bottom_angle * bottom_length
    ) / total_length
    center = points.mean(axis=0)
    return (
        float(center[0]),
        float(center[1]),
        float(angle),
        max(1.0, width),
        max(1.0, height),
    )


def horizontal_polygon_edge_metrics(polygons: list[np.ndarray], groups: list[list[int]], *, edge_angles: Callable[..., Any], normalize_angle: Callable[[float], float], percentile_pairs: Callable[..., float]) -> tuple[int, float, float, float, float]:
    """Robust dual-edge audit, equalized by column.

    Returns (sample_count, top_abs_p90, bottom_abs_p90, pair_delta_p90,
    worst_edge). Each populated column is summarized first, then the worst
    column is retained so one bad column cannot disappear in a page average.
    """
    column_top: list[float] = []
    column_bottom: list[float] = []
    column_delta: list[float] = []
    sample_count = 0
    for indices in groups:
        top_values: list[tuple[float, float]] = []
        bottom_values: list[tuple[float, float]] = []
        delta_values: list[tuple[float, float]] = []
        for index in indices:
            if not (0 <= index < len(polygons)):
                continue
            edge_pair = edge_angles(polygons[index])
            if edge_pair is None:
                continue
            (top_angle, top_length), (bottom_angle, bottom_length) = edge_pair
            weight = max(1.0, min(float(top_length), float(bottom_length)))
            top_values.append((abs(float(top_angle)), weight))
            bottom_values.append((abs(float(bottom_angle)), weight))
            delta_values.append(
                (
                    abs(
                        normalize_angle(
                            float(top_angle) - float(bottom_angle)
                        )
                    ),
                    weight,
                )
            )
        if len(top_values) < 5:
            continue
        sample_count += len(top_values)
        column_top.append(percentile_pairs(top_values, 90.0))
        column_bottom.append(percentile_pairs(bottom_values, 90.0))
        column_delta.append(percentile_pairs(delta_values, 90.0))

    top_p90 = max(column_top, default=0.0)
    bottom_p90 = max(column_bottom, default=0.0)
    pair_p90 = max(column_delta, default=0.0)
    return (
        int(sample_count),
        float(top_p90),
        float(bottom_p90),
        float(pair_p90),
        float(max(top_p90, bottom_p90)),
    )


def cluster_horizontal_samples(samples: list[tuple[float, float, float, float, float]], *, median_pairs: Callable[..., float]) -> list[tuple[float, float, float, float]]:
    """Cluster text-box orientation samples into rows *within one column*."""
    if not samples:
        return []
    samples = list(samples)
    median_height = float(np.median([sample[4] for sample in samples]))
    tolerance = max(4.0, median_height * 0.72)
    samples.sort(key=lambda item: item[1])

    clusters: list[list[tuple[float, float, float, float, float]]] = []
    for sample in samples:
        if not clusters:
            clusters.append([sample])
            continue
        cluster_y = median_pairs(
            [(item[1], item[3]) for item in clusters[-1]]
        )
        if abs(sample[1] - cluster_y) <= tolerance:
            clusters[-1].append(sample)
        else:
            clusters.append([sample])

    rows: list[tuple[float, float, float, float]] = []
    for cluster in clusters:
        x = median_pairs([(item[0], item[3]) for item in cluster])
        y = median_pairs([(item[1], item[3]) for item in cluster])
        angle = median_pairs([(item[2], item[3]) for item in cluster])
        weight = sum(item[3] for item in cluster)
        rows.append((x, y, angle, max(1.0, weight)))
    return rows


def horizontal_rows(polygons: Iterable[np.ndarray], *, sample_polygon: Callable[..., Any], cluster_samples: Callable[..., Any]) -> list[tuple[float, float, float, float]]:
    """Legacy/global helper; N-column analysis uses per-column clustering."""
    samples = [
        sample
        for raw in polygons
        if (sample := sample_polygon(np.asarray(raw, dtype=float)))
        is not None
    ]
    return cluster_samples(samples)


def horizontal_column_indices(polygons: list[np.ndarray], size: tuple[int, int], settings: Any = None, *, settings_type: Callable[[], Any], polygon_boxes: Callable[..., Any], infer_layout: Callable[..., Any], sample_polygon: Callable[..., Any]) -> tuple[list[list[int]], tuple[int, ...]]:
    """Assign text polygons to 1..N structural columns without cross-column rows.

    Layout detection supplies column starts/rights. A polygon is assigned to one
    column by maximal horizontal overlap; page-spanning headers/rules are
    deliberately excluded from column row geometry.
    """
    width, height = size
    if not polygons:
        return [], ()
    active_settings = settings or settings_type()
    boxes = polygon_boxes(polygons, width, height)
    try:
        estimate = infer_layout(
            boxes,
            size,
            display_scale=1.0,
            ink_mask=None,
            columns_policy=active_settings.layout_columns_policy,
            fixed_columns=active_settings.columns,
            column_separator_mode=active_settings.layout_column_separator_mode,
        )
        starts = tuple(int(v) for v in estimate.column_starts)
        rights = tuple(int(v) for v in estimate.column_rights)
    except Exception:
        starts = ()
        rights = ()

    if not starts:
        return [list(range(len(polygons)))], (0,)
    if len(rights) != len(starts):
        inferred_rights: list[int] = []
        for index, left in enumerate(starts):
            if index + 1 < len(starts):
                inferred_rights.append(
                    int(round((left + starts[index + 1]) / 2.0))
                )
            else:
                inferred_rights.append(width)
        rights = tuple(inferred_rights)

    bounds: list[tuple[float, float]] = []
    for index, left in enumerate(starts):
        right = rights[index] if index < len(rights) else width
        if right <= left:
            right = (
                starts[index + 1]
                if index + 1 < len(starts)
                else width
            )
        bounds.append(
            (
                max(0.0, float(left)),
                min(float(width), max(float(left) + 1.0, float(right))),
            )
        )

    typical_width = float(
        np.median([max(1.0, right - left) for left, right in bounds])
    )
    groups: list[list[int]] = [[] for _ in bounds]
    for poly_index, raw in enumerate(polygons):
        sample = sample_polygon(raw)
        if sample is None:
            continue
        center_x, _center_y, _angle, box_width, _box_height = sample
        x0 = center_x - box_width / 2.0
        x1 = center_x + box_width / 2.0

        # Headers and other elements spanning more than one designed column do
        # not define the baseline orientation of any individual column.
        if len(bounds) > 1 and box_width > typical_width * 1.35:
            continue

        overlaps = [
            max(0.0, min(x1, right) - max(x0, left))
            for left, right in bounds
        ]
        best_index = int(np.argmax(overlaps))
        best_overlap = overlaps[best_index]
        left, right = bounds[best_index]
        center_inside = left <= center_x <= right
        if best_overlap >= max(3.0, box_width * 0.42) or center_inside:
            groups[best_index].append(poly_index)

    # Keep all detected columns in diagnostics, even when a sparse column has
    # too few usable row boxes; sparse columns simply do not drive the fit.
    return groups, starts


def horizontal_column_rows(polygons: list[np.ndarray], size: tuple[int, int], settings: Any = None, *, fixed_groups: list[list[int]] | None = None, column_indices: Callable[..., Any], sample_polygon: Callable[..., Any], cluster_samples: Callable[..., Any]) -> tuple[list[list[tuple[float, float, float, float]]], list[list[int]]]:
    groups, _starts = (
        column_indices(polygons, size, settings)
        if fixed_groups is None
        else (fixed_groups, ())
    )
    result: list[list[tuple[float, float, float, float]]] = []
    for indices in groups:
        samples = [
            sample
            for index in indices
            if 0 <= index < len(polygons)
            and (
                sample := sample_polygon(polygons[index])
            )
            is not None
        ]
        result.append(cluster_samples(samples))
    return result, groups


def public_horizontal_column_rows(polygons: Iterable[np.ndarray], size: tuple[int, int], settings: Any = None, *, column_rows: Callable[..., Any]) -> list[list[tuple[float, float, float, float]]]:
    """Public read-only N-column row reconstruction for geometry diagnostics."""
    polygon_list = [np.asarray(poly, dtype=float) for poly in polygons]
    rows, _groups = column_rows(
        polygon_list, size, settings,
    )
    return rows
