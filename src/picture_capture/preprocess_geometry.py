from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .layout_detection import LayoutEstimate, infer_layout_from_boxes
from .models import AppSettings


@dataclass(frozen=True, slots=True)
class PerspectiveEstimate:
    """Projective correction inferred from structural column-left trajectories."""

    matrix: tuple[float, ...]
    source_quad: tuple[float, ...]
    target_quad: tuple[float, ...]
    strength_px: float


@dataclass(frozen=True, slots=True)
class LayoutDewarpEstimate:
    """Compact horizontal mesh that straightens column trajectories over Y."""

    y_samples: tuple[float, ...]
    target_starts: tuple[float, ...]
    source_starts: tuple[tuple[float, ...], ...]
    strength_px: float


def polygon_boxes(
    polygons: Iterable[np.ndarray],
    width: int,
    height: int,
) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for raw in polygons:
        poly = np.asarray(raw, dtype=float)
        if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
            continue
        x0 = max(0, min(width - 1, math.floor(float(poly[:, 0].min()))))
        y0 = max(0, min(height - 1, math.floor(float(poly[:, 1].min()))))
        x1 = max(1, min(width, math.ceil(float(poly[:, 0].max())) + 1))
        y1 = max(1, min(height, math.ceil(float(poly[:, 1].max())) + 1))
        if x1 - x0 >= 3 and y1 - y0 >= 3:
            boxes.append((x0, y0, x1, y1))
    return boxes


def _layout(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings,
) -> tuple[list[tuple[int, int, int, int]], LayoutEstimate]:
    width, height = size
    boxes = polygon_boxes(polygons, width, height)
    if len(boxes) < 8:
        raise RuntimeError("高级几何纠正需要更多有效文本框")
    estimate = infer_layout_from_boxes(
        boxes,
        size,
        display_scale=1.0,
        ink_mask=None,
        columns_policy=settings.layout_columns_policy,
        fixed_columns=settings.columns,
        column_separator_mode=settings.layout_column_separator_mode,
    )
    if len(estimate.column_starts) < 2:
        raise RuntimeError("高级几何纠正至少需要两栏结构")
    return boxes, estimate


def _column_pitch(starts: tuple[int, ...], index: int, width: int) -> float:
    if len(starts) <= 1:
        return max(20.0, float(width) * 0.5)
    if index == 0:
        return float(starts[1] - starts[0])
    if index == len(starts) - 1:
        return float(starts[-1] - starts[-2])
    return float(min(starts[index] - starts[index - 1], starts[index + 1] - starts[index]))


def _column_left_samples(
    boxes: list[tuple[int, int, int, int]],
    estimate: LayoutEstimate,
    width: int,
) -> list[list[tuple[float, float]]]:
    starts = tuple(int(v) for v in estimate.column_starts)
    samples: list[list[tuple[float, float]]] = [[] for _ in starts]
    char_h = max(4.0, float(estimate.character_height))
    top = float(estimate.start_y) - char_h * 1.2
    bottom = float(estimate.bottom_y) + char_h * 1.2

    for box in boxes:
        x0, y0, _x1, y1 = box
        yc = (float(y0) + float(y1)) / 2.0
        if yc < top or yc > bottom:
            continue
        distances = [abs(float(x0) - float(start)) for start in starts]
        index = int(np.argmin(distances))
        pitch = max(20.0, _column_pitch(starts, index, width))
        # Only boxes that genuinely begin near a structural column edge are
        # useful trajectory anchors. Continuation/indented lines are excluded.
        tolerance = max(char_h * 2.0, min(pitch * 0.28, float(estimate.column_width) * 0.32))
        if distances[index] <= tolerance:
            samples[index].append((yc, float(x0)))
    return samples


def _robust_line(samples: list[tuple[float, float]]) -> tuple[float, float]:
    if len(samples) < 5:
        raise RuntimeError("栏左轨迹样本不足")
    ys = np.asarray([p[0] for p in samples], dtype=float)
    xs = np.asarray([p[1] for p in samples], dtype=float)
    keep = np.ones(len(samples), dtype=bool)
    for _ in range(3):
        if int(keep.sum()) < 5:
            break
        slope, intercept = np.polyfit(ys[keep], xs[keep], 1)
        residual = xs - (slope * ys + intercept)
        center = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - center)))
        threshold = max(2.5, mad * 3.5)
        new_keep = np.abs(residual - center) <= threshold
        if int(new_keep.sum()) == int(keep.sum()):
            keep = new_keep
            break
        keep = new_keep
    if int(keep.sum()) < 5:
        raise RuntimeError("栏左轨迹异常值过多")
    slope, intercept = np.polyfit(ys[keep], xs[keep], 1)
    return float(slope), float(intercept)


def _homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Return a 3x3 matrix mapping src XY coordinates to dst XY coordinates."""
    if src.shape != (4, 2) or dst.shape != (4, 2):
        raise ValueError("Homography requires four 2D source and destination points")
    rows: list[list[float]] = []
    values: list[float] = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        values.append(u)
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        values.append(v)
    coeff = np.linalg.solve(np.asarray(rows, dtype=float), np.asarray(values, dtype=float))
    matrix = np.asarray(
        [
            [coeff[0], coeff[1], coeff[2]],
            [coeff[3], coeff[4], coeff[5]],
            [coeff[6], coeff[7], 1.0],
        ],
        dtype=float,
    )
    return matrix


def estimate_perspective_from_polygons(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings,
) -> PerspectiveEstimate:
    width, _height = size
    polygons = list(polygons)
    boxes, estimate = _layout(polygons, size, settings)
    starts = tuple(int(v) for v in estimate.column_starts)
    samples = _column_left_samples(boxes, estimate, width)

    first_line = _robust_line(samples[0])
    last_line = _robust_line(samples[-1])
    top = float(max(0, estimate.start_y))
    bottom = float(max(estimate.start_y + 1, estimate.bottom_y))

    def at(line: tuple[float, float], y: float) -> float:
        return line[0] * y + line[1]

    left_top = at(first_line, top)
    left_bottom = at(first_line, bottom)
    right_top = at(last_line, top)
    right_bottom = at(last_line, bottom)
    if min(right_top - left_top, right_bottom - left_bottom) < max(20.0, width * 0.12):
        raise RuntimeError("栏间跨度不足，无法稳定估计透视")

    target_left = float(np.median([x for _y, x in samples[0]]))
    target_right = float(np.median([x for _y, x in samples[-1]]))
    if target_right - target_left < max(20.0, width * 0.12):
        raise RuntimeError("目标栏间跨度不足，无法稳定估计透视")

    src = np.asarray(
        [
            [left_top, top],
            [right_top, top],
            [right_bottom, bottom],
            [left_bottom, bottom],
        ],
        dtype=float,
    )
    dst = np.asarray(
        [
            [target_left, top],
            [target_right, top],
            [target_right, bottom],
            [target_left, bottom],
        ],
        dtype=float,
    )
    matrix = _homography(src, dst)
    strength = float(np.max(np.linalg.norm(src - dst, axis=1)))
    return PerspectiveEstimate(
        matrix=tuple(float(v) for v in matrix.reshape(-1)),
        source_quad=tuple(float(v) for v in src.reshape(-1)),
        target_quad=tuple(float(v) for v in dst.reshape(-1)),
        strength_px=strength,
    )


def transform_points_homography(points: np.ndarray, matrix: Iterable[float]) -> np.ndarray:
    mat = np.asarray(tuple(matrix), dtype=float).reshape(3, 3)
    raw = np.asarray(points, dtype=float)
    flat = raw.reshape(-1, 2)
    hom = np.column_stack([flat, np.ones(len(flat), dtype=float)])
    mapped = hom @ mat.T
    denom = mapped[:, 2:3]
    denom[np.abs(denom) < 1e-9] = 1e-9
    xy = mapped[:, :2] / denom
    return xy.reshape(raw.shape)


def transform_polygons_homography(
    polygons: Iterable[np.ndarray], matrix: Iterable[float],
) -> list[np.ndarray]:
    return [
        transform_points_homography(np.asarray(poly, dtype=float), matrix)
        for poly in polygons
    ]


def _paper_fill(image: Image.Image) -> tuple[int, int, int]:
    source = normalize_page_rgb(image)
    w, h = source.size
    pw = max(1, round(w * 0.04))
    ph = max(1, round(h * 0.04))
    samples = [
        np.asarray(source.crop((0, 0, pw, ph)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((max(0, w - pw), 0, w, ph)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((0, max(0, h - ph), pw, h)), dtype=np.uint8).reshape(-1, 3),
        np.asarray(source.crop((max(0, w - pw), max(0, h - ph), w, h)), dtype=np.uint8).reshape(-1, 3),
    ]
    median = np.median(np.concatenate(samples, axis=0), axis=0)
    return tuple(int(round(v)) for v in median[:3])


def apply_homography_image(image: Image.Image, matrix: Iterable[float]) -> Image.Image:
    source = normalize_page_rgb(image)
    mat = np.asarray(tuple(matrix), dtype=float).reshape(3, 3)
    inverse = np.linalg.inv(mat)
    inverse /= inverse[2, 2]
    coeff = (
        float(inverse[0, 0]), float(inverse[0, 1]), float(inverse[0, 2]),
        float(inverse[1, 0]), float(inverse[1, 1]), float(inverse[1, 2]),
        float(inverse[2, 0]), float(inverse[2, 1]),
    )
    return source.transform(
        source.size,
        Image.Transform.PERSPECTIVE,
        coeff,
        resample=Image.Resampling.BICUBIC,
        fillcolor=_paper_fill(source),
    )


def _fill_series(values: np.ndarray) -> np.ndarray:
    result = values.astype(float, copy=True)
    valid = np.isfinite(result)
    if int(valid.sum()) < 2:
        raise RuntimeError("局部栏左轨迹样本不足")
    idx = np.arange(len(result), dtype=float)
    result[~valid] = np.interp(idx[~valid], idx[valid], result[valid])
    if len(result) >= 3:
        # A small deterministic low-pass filter suppresses OCR box jitter while
        # preserving genuine slow page curvature.
        padded = np.pad(result, (1, 1), mode="edge")
        result = (
            padded[:-2] * 0.25
            + padded[1:-1] * 0.50
            + padded[2:] * 0.25
        )
    return result


def estimate_layout_dewarp_from_polygons(
    polygons: Iterable[np.ndarray],
    size: tuple[int, int],
    settings: AppSettings,
    *,
    samples_y: int = 13,
) -> LayoutDewarpEstimate:
    width, _height = size
    polygons = list(polygons)
    boxes, estimate = _layout(polygons, size, settings)
    starts = tuple(int(v) for v in estimate.column_starts)
    samples = _column_left_samples(boxes, estimate, width)
    if min(len(samples[0]), len(samples[-1])) < 8:
        raise RuntimeError("首末栏轨迹样本不足，无法去弯曲")

    top = float(max(0, estimate.start_y))
    bottom = float(max(estimate.start_y + 1, estimate.bottom_y))
    count = max(7, min(25, int(samples_y)))
    ys = np.linspace(top, bottom, count)
    half = max(float(estimate.character_height) * 2.2, (bottom - top) / max(8.0, count * 1.4))

    local = np.full((count, len(starts)), np.nan, dtype=float)
    for yi, yc in enumerate(ys):
        for ci, column_samples in enumerate(samples):
            nearby = [x for y, x in column_samples if abs(y - yc) <= half]
            if nearby:
                local[yi, ci] = float(np.median(nearby))

    for ci in range(local.shape[1]):
        local[:, ci] = _fill_series(local[:, ci])

    targets = np.median(local, axis=0)
    # Enforce the detected column order and a small minimum separation.
    for ci in range(1, len(targets)):
        targets[ci] = max(targets[ci], targets[ci - 1] + 10.0)
    residual = local - targets[None, :]
    strength = float(np.percentile(np.abs(residual), 95))
    return LayoutDewarpEstimate(
        y_samples=tuple(float(v) for v in ys),
        target_starts=tuple(float(v) for v in targets),
        source_starts=tuple(
            tuple(float(v) for v in row)
            for row in local
        ),
        strength_px=strength,
    )


def _starts_at_y(
    y: float,
    y_samples: tuple[float, ...],
    source_starts: tuple[tuple[float, ...], ...],
) -> np.ndarray:
    ys = np.asarray(y_samples, dtype=float)
    grid = np.asarray(source_starts, dtype=float)
    if grid.ndim != 2 or grid.shape[0] != len(ys):
        raise ValueError("无效的去弯曲网格")
    return np.asarray(
        [
            np.interp(float(y), ys, grid[:, ci])
            for ci in range(grid.shape[1])
        ],
        dtype=float,
    )


def apply_layout_dewarp_image(
    image: Image.Image,
    estimate: LayoutDewarpEstimate,
) -> Image.Image:
    source = normalize_page_rgb(image)
    array = np.asarray(source, dtype=np.float32)
    height, width = array.shape[:2]
    output = np.empty_like(array)
    x_out = np.arange(width, dtype=float)
    targets = np.asarray(estimate.target_starts, dtype=float)
    if targets.size < 2:
        return source.copy()

    for y in range(height):
        local = _starts_at_y(y, estimate.y_samples, estimate.source_starts)
        left_delta = float(local[0] - targets[0])
        right_delta = float(local[-1] - targets[-1])
        target_anchors = np.concatenate(([0.0], targets, [float(width - 1)]))
        source_anchors = np.concatenate(
            (
                [max(0.0, min(float(width - 1), left_delta))],
                local,
                [max(0.0, min(float(width - 1), float(width - 1) + right_delta))],
            )
        )
        # Keep mapping monotone even when noisy OCR anchors nearly cross.
        source_anchors = np.maximum.accumulate(source_anchors)
        source_anchors[-1] = max(source_anchors[-1], source_anchors[-2] + 1e-3)
        src_x = np.interp(x_out, target_anchors, source_anchors)
        src_x = np.clip(src_x, 0.0, float(width - 1))
        x0 = np.floor(src_x).astype(np.int32)
        x1 = np.minimum(x0 + 1, width - 1)
        frac = (src_x - x0).astype(np.float32)[:, None]
        output[y] = array[y, x0] * (1.0 - frac) + array[y, x1] * frac

    return Image.fromarray(np.clip(output, 0, 255).astype(np.uint8), mode="RGB")


def transform_polygons_layout_dewarp(
    polygons: Iterable[np.ndarray],
    estimate: LayoutDewarpEstimate,
    width: int,
) -> list[np.ndarray]:
    targets = np.asarray(estimate.target_starts, dtype=float)
    transformed: list[np.ndarray] = []
    for raw in polygons:
        poly = np.asarray(raw, dtype=float).copy()
        if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
            continue
        for index, (x, y) in enumerate(poly[:, :2]):
            local = _starts_at_y(float(y), estimate.y_samples, estimate.source_starts)
            source_anchors = np.concatenate(
                (
                    [max(0.0, float(local[0] - targets[0]))],
                    local,
                    [min(float(width - 1), float(width - 1 + local[-1] - targets[-1]))],
                )
            )
            target_anchors = np.concatenate(([0.0], targets, [float(width - 1)]))
            source_anchors = np.maximum.accumulate(source_anchors)
            poly[index, 0] = float(
                np.interp(float(x), source_anchors, target_anchors)
            )
        transformed.append(poly)
    return transformed


def dewarp_estimate_from_payload(
    y_samples: Iterable[float],
    target_starts: Iterable[float],
    source_starts: Iterable[Iterable[float]],
    strength_px: float = 0.0,
) -> LayoutDewarpEstimate:
    return LayoutDewarpEstimate(
        y_samples=tuple(float(v) for v in y_samples),
        target_starts=tuple(float(v) for v in target_starts),
        source_starts=tuple(tuple(float(v) for v in row) for row in source_starts),
        strength_px=float(strength_px),
    )
