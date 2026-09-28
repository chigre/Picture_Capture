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
    """Projective correction inferred from structural column trajectories.

    The diagnostics separate common lateral drift (rotation/shear-like) from
    differential edge drift (true width convergence/divergence). Automatic
    preprocessing can therefore reject a large homography even when OCR-derived
    signals agree that "something" changes over Y.
    """

    matrix: tuple[float, ...]
    source_quad: tuple[float, ...]
    target_quad: tuple[float, ...]
    strength_px: float
    left_drift_px: float = 0.0
    right_drift_px: float = 0.0
    common_drift_px: float = 0.0
    width_delta_px: float = 0.0
    width_change_ratio: float = 0.0
    scale_top: float = 1.0
    scale_bottom: float = 1.0
    scale_delta_ratio: float = 0.0
    classification: str = "unknown"


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
    top_width = float(right_top - left_top)
    bottom_width = float(right_bottom - left_bottom)
    mean_width = max(1.0, (top_width + bottom_width) / 2.0)
    left_drift = float(left_bottom - left_top)
    right_drift = float(right_bottom - right_top)
    common_drift = float((left_drift + right_drift) / 2.0)
    width_delta = float(bottom_width - top_width)
    width_change_ratio = abs(width_delta) / mean_width
    target_width = max(1.0, float(target_right - target_left))
    scale_top = target_width / max(1.0, top_width)
    scale_bottom = target_width / max(1.0, bottom_width)
    scale_mean = max(1e-9, (abs(scale_top) + abs(scale_bottom)) / 2.0)
    scale_delta_ratio = abs(scale_bottom - scale_top) / scale_mean
    same_direction = left_drift * right_drift > 0.0
    parallel_dominant = (
        same_direction
        and abs(common_drift) >= max(4.0, abs(width_delta) * 1.5)
    )
    if parallel_dominant:
        classification = "parallel_drift"
    elif width_change_ratio >= 0.003:
        classification = "keystone"
    else:
        classification = "weak"

    return PerspectiveEstimate(
        matrix=tuple(float(v) for v in matrix.reshape(-1)),
        source_quad=tuple(float(v) for v in src.reshape(-1)),
        target_quad=tuple(float(v) for v in dst.reshape(-1)),
        strength_px=strength,
        left_drift_px=left_drift,
        right_drift_px=right_drift,
        common_drift_px=common_drift,
        width_delta_px=width_delta,
        width_change_ratio=width_change_ratio,
        scale_top=scale_top,
        scale_bottom=scale_bottom,
        scale_delta_ratio=scale_delta_ratio,
        classification=classification,
    )


def perspective_from_quad(
    quad: Iterable[float],
    size: tuple[int, int],
) -> PerspectiveEstimate:
    """Build a manual four-corner rectification on the existing page canvas.

    quad is ordered TL, TR, BR, BL in source-image pixels. The selected
    quadrilateral is mapped to its axis-aligned bounding rectangle, preserving
    the surrounding canvas so downstream layout detection can run normally.
    """
    values = tuple(float(v) for v in quad)
    if len(values) != 8:
        raise ValueError("手动四角必须包含 4 个二维坐标")
    width, height = size
    src = np.asarray(values, dtype=float).reshape(4, 2)
    if not np.isfinite(src).all():
        raise ValueError("手动四角包含无效坐标")
    src[:, 0] = np.clip(src[:, 0], 0.0, max(0.0, float(width - 1)))
    src[:, 1] = np.clip(src[:, 1], 0.0, max(0.0, float(height - 1)))

    tl, tr, br, bl = src
    top_width = float(np.linalg.norm(tr - tl))
    bottom_width = float(np.linalg.norm(br - bl))
    left_height = float(np.linalg.norm(bl - tl))
    right_height = float(np.linalg.norm(br - tr))
    if min(top_width, bottom_width) < max(20.0, width * 0.08):
        raise ValueError("手动四角的页面宽度过小")
    if min(left_height, right_height) < max(20.0, height * 0.08):
        raise ValueError("手动四角的页面高度过小")

    crosses = []
    for index in range(4):
        p0 = src[index]
        p1 = src[(index + 1) % 4]
        p2 = src[(index + 2) % 4]
        first = p1 - p0
        second = p2 - p1
        crosses.append(float(first[0] * second[1] - first[1] * second[0]))
    if not (all(v > 0 for v in crosses) or all(v < 0 for v in crosses)):
        raise ValueError("四角顺序发生交叉，请保持左上→右上→右下→左下")

    left = float(min(tl[0], bl[0]))
    right = float(max(tr[0], br[0]))
    top = float(min(tl[1], tr[1]))
    bottom = float(max(bl[1], br[1]))
    if right - left < 20 or bottom - top < 20:
        raise ValueError("手动四角形成的目标矩形过小")
    dst = np.asarray(
        [[left, top], [right, top], [right, bottom], [left, bottom]],
        dtype=float,
    )
    matrix = _homography(src, dst)
    strength = float(np.max(np.linalg.norm(src - dst, axis=1)))
    top_width = max(1.0, float(np.linalg.norm(tr - tl)))
    bottom_width = max(1.0, float(np.linalg.norm(br - bl)))
    target_width = max(1.0, float(right - left))
    scale_top = target_width / top_width
    scale_bottom = target_width / bottom_width
    scale_mean = max(1e-9, (abs(scale_top) + abs(scale_bottom)) / 2.0)
    return PerspectiveEstimate(
        matrix=tuple(float(v) for v in matrix.reshape(-1)),
        source_quad=tuple(float(v) for v in src.reshape(-1)),
        target_quad=tuple(float(v) for v in dst.reshape(-1)),
        strength_px=strength,
        left_drift_px=float(bl[0] - tl[0]),
        right_drift_px=float(br[0] - tr[0]),
        common_drift_px=float(((bl[0] - tl[0]) + (br[0] - tr[0])) / 2.0),
        width_delta_px=float(bottom_width - top_width),
        width_change_ratio=abs(bottom_width - top_width) / max(1.0, (top_width + bottom_width) / 2.0),
        scale_top=scale_top,
        scale_bottom=scale_bottom,
        scale_delta_ratio=abs(scale_bottom - scale_top) / scale_mean,
        classification="manual",
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


