from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .document_unwarping import unwarp_document_image
from .image_utils import normalize_page_rgb
from .layout_detection import (
    LayoutEstimate,
    analysis_ink_mask,
    detect_text_polygons,
    infer_layout_from_boxes,
)
from .models import AppSettings
from .preprocess_geometry import (
    apply_homography_image,
    estimate_perspective_from_polygons,
    perspective_from_quad,
    transform_polygons_homography,
)
from .text_line_geometry import (
    TextLineGeometryAnalysis,
    analyze_text_line_geometry,
)
from .project_storage import image_preprocess_data_root, image_preprocess_output_root


PREPROCESS_FORMAT = "picture-capture-image-preprocess"
PREPROCESS_FORMAT_VERSION = 9
DEFAULT_SAFETY_MARGIN_PX = 20
DEFAULT_MAX_AUTO_DESKEW_DEG = 5.0
DEFAULT_DESKEW_DEAD_ZONE_DEG = 0.12
PREVIEW_YELLOW = (255, 225, 110, 94)
PREVIEW_OUTLINE = (218, 164, 24, 255)


@dataclass(frozen=True, slots=True)
class OutputCanvasInfo:
    enabled: bool
    mode: str
    requested_width: int
    requested_height: int
    width: int
    height: int
    align_x: str
    align_y: str
    content_box: tuple[int, int, int, int]
    expanded_width: bool = False
    expanded_height: bool = False

    def to_dict(self) -> dict:
        payload = asdict(self)
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
    perspective_candidate_strength_px: float = 0.0
    perspective_left_drift_px: float = 0.0
    perspective_right_drift_px: float = 0.0
    perspective_common_drift_px: float = 0.0
    perspective_width_delta_px: float = 0.0
    perspective_width_change_ratio: float = 0.0
    perspective_scale_top: float = 1.0
    perspective_scale_bottom: float = 1.0
    perspective_scale_delta_ratio: float = 0.0
    perspective_auto_safe: bool = False
    manual_perspective_quad: tuple[float, ...] | None = None
    line_geometry_rows: int = 0
    line_geometry_global_angle_deg: float = 0.0
    line_geometry_top_angle_deg: float = 0.0
    line_geometry_middle_angle_deg: float = 0.0
    line_geometry_bottom_angle_deg: float = 0.0
    line_geometry_trend_deg: float = 0.0
    line_geometry_residual_mad_deg: float = 0.0
    line_geometry_residual_span_deg: float = 0.0
    line_geometry_separator_found: bool = False
    line_geometry_separator_residual_px: float = 0.0
    line_geometry_separator_span_ratio: float = 0.0
    line_geometry_separator_slope_px_per_1000y: float = 0.0
    line_geometry_separator_drift_px: float = 0.0
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
            perspective_auto_safe=bool(
                payload.get("perspective_auto_safe", False)
            ),
            manual_perspective_quad=(
                tuple(float(v) for v in payload.get("manual_perspective_quad", ()))
                if isinstance(payload.get("manual_perspective_quad"), (list, tuple))
                and len(payload.get("manual_perspective_quad", ())) == 8
                else None
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


def _normalize_half_turn(angle: float) -> float:
    value = float(angle)
    while value >= 90.0:
        value -= 180.0
    while value < -90.0:
        value += 180.0
    return value


def _weighted_median(values: list[tuple[float, float]]) -> float:
    if not values:
        return 0.0
    ordered = sorted((float(value), max(0.0, float(weight))) for value, weight in values)
    total = sum(weight for _value, weight in ordered)
    if total <= 0:
        return float(np.median([value for value, _weight in ordered]))
    halfway = total / 2.0
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= halfway:
            return value
    return ordered[-1][0]


def estimate_skew_from_polygons(
    polygons: Iterable[np.ndarray], *, writing_mode: str = "horizontal-tb",
) -> tuple[float, int, float]:
    """Estimate the small correction angle represented by detected text boxes.

    Angles use Pillow's rotation sign convention: a positive value is the
    counter-clockwise correction that should be applied to the source image.
    """
    vertical = str(writing_mode or "horizontal-tb").startswith("vertical")
    samples: list[tuple[float, float]] = []
    for raw in polygons:
        poly = np.asarray(raw, dtype=float)
        if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
            continue
        edges: list[tuple[float, float]] = []
        for index in range(poly.shape[0]):
            p0 = poly[index, :2]
            p1 = poly[(index + 1) % poly.shape[0], :2]
            dx = float(p1[0] - p0[0])
            dy = float(p1[1] - p0[1])
            length = math.hypot(dx, dy)
            if length < 6.0:
                continue
            angle = _normalize_half_turn(math.degrees(math.atan2(dy, dx)))
            deviation = _normalize_half_turn(angle - 90.0) if vertical else angle
            if abs(deviation) <= 20.0:
                edges.append((deviation, length))
        if not edges:
            continue
        # Two long parallel sides carry most of the orientation information and
        # avoid over-weighting irregular multi-point detector polygons.
        for deviation, length in sorted(edges, key=lambda item: item[1], reverse=True)[:2]:
            samples.append((deviation, length))

    if not samples:
        return 0.0, 0, 0.0
    center = _weighted_median(samples)
    mad = _weighted_median([(abs(value - center), weight) for value, weight in samples])
    kept = [(value, weight) for value, weight in samples if abs(value - center) <= max(0.35, mad * 3.5)]
    if len(kept) >= 4:
        center = _weighted_median(kept)
        mad = _weighted_median([(abs(value - center), weight) for value, weight in kept])
        samples = kept
    return float(center), len(samples), float(mad)


def _smooth_1d(values: np.ndarray, width: int) -> np.ndarray:
    width = max(1, int(width))
    if width <= 1:
        return values.astype(float, copy=False)
    kernel = np.ones(width, dtype=float) / float(width)
    return np.convolve(values.astype(float, copy=False), kernel, mode="same")


def _projection_content_box(image: Image.Image, settings: AppSettings) -> tuple[int, int, int, int]:
    """Find a conservative nonblank content envelope without OCR recognition."""
    source = normalize_page_rgb(image)
    scale = min(1.0, 1800.0 / max(1, max(source.size)))
    work = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.BILINEAR,
    ) if scale < 1.0 else source
    gray = np.asarray(ImageOps.grayscale(work), dtype=np.uint8)
    ink = analysis_ink_mask(gray, settings).copy()
    h, w = ink.shape

    # Scanner shadows and cut marks commonly live on the physical edge.  Ignore
    # only a very narrow rim; meaningful page content is recovered below by the
    # Paddle text envelope and the user-facing safety margin.
    mx = max(1, round(w * 0.005))
    my = max(1, round(h * 0.005))
    ink[:my, :] = False
    ink[-my:, :] = False
    ink[:, :mx] = False
    ink[:, -mx:] = False

    rows = _smooth_1d(ink.mean(axis=1), max(3, round(h * 0.0015)))
    cols = _smooth_1d(ink.mean(axis=0), max(3, round(w * 0.0025)))
    positive_rows = rows[rows > 0]
    positive_cols = cols[cols > 0]
    row_floor = (
        max(0.0015, float(np.percentile(positive_rows, 15)) * 0.35)
        if positive_rows.size else 0.0015
    )
    col_floor = (
        max(0.0015, float(np.percentile(positive_cols, 15)) * 0.35)
        if positive_cols.size else 0.0015
    )
    active_y = np.flatnonzero(rows > row_floor)
    active_x = np.flatnonzero(cols > col_floor)
    if not active_y.size or not active_x.size:
        raise RuntimeError("未检测到足够的页面墨迹，无法估计保留区域。")

    back = 1.0 / max(scale, 1e-9)
    return (
        max(0, round(int(active_x[0]) * back)),
        max(0, round(int(active_y[0]) * back)),
        min(source.width, round(int(active_x[-1] + 1) * back)),
        min(source.height, round(int(active_y[-1] + 1) * back)),
    )


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
    pixels = np.concatenate(samples, axis=0)
    median = np.median(pixels, axis=0)
    return tuple(int(round(value)) for value in median[:3])


def deskew_image(image: Image.Image, correction_angle_deg: float) -> Image.Image:
    source = normalize_page_rgb(image)
    angle = float(correction_angle_deg)
    if abs(angle) < 1e-6:
        return source.copy()
    return source.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=False,
        fillcolor=_paper_fill(source),
    )


def _rotate_point_same_canvas(
    x: float, y: float, width: int, height: int, angle_deg: float,
) -> tuple[float, float]:
    """Map a source point through Pillow-style positive CCW rotation, expand=False."""
    if abs(float(angle_deg)) < 1e-9:
        return float(x), float(y)
    cx = (float(width) - 1.0) / 2.0
    cy = (float(height) - 1.0) / 2.0
    dx = float(x) - cx
    dy = float(y) - cy
    radians = math.radians(float(angle_deg))
    cos_a = math.cos(radians)
    sin_a = math.sin(radians)
    return (
        cx + dx * cos_a + dy * sin_a,
        cy - dx * sin_a + dy * cos_a,
    )


def _rotate_polygons_same_canvas(
    polygons: Iterable[np.ndarray],
    width: int,
    height: int,
    angle_deg: float,
) -> list[np.ndarray]:
    rotated: list[np.ndarray] = []
    for raw in polygons:
        poly = np.asarray(raw, dtype=float)
        if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
            continue
        points = [
            _rotate_point_same_canvas(
                float(x), float(y), width, height, angle_deg,
            )
            for x, y in poly[:, :2]
        ]
        rotated.append(np.asarray(points, dtype=float))
    return rotated


def _rotated_text_box(
    polygons: Iterable[np.ndarray], width: int, height: int, angle_deg: float,
) -> tuple[int, int, int, int] | None:
    points: list[tuple[float, float]] = []
    for raw in polygons:
        poly = np.asarray(raw, dtype=float)
        if poly.ndim != 2 or poly.shape[0] < 3 or poly.shape[1] < 2:
            continue
        xs = poly[:, 0]
        ys = poly[:, 1]
        if float(xs.max() - xs.min()) < 3.0 or float(ys.max() - ys.min()) < 3.0:
            continue
        for x, y in poly[:, :2]:
            points.append(_rotate_point_same_canvas(float(x), float(y), width, height, angle_deg))
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (
        max(0, min(width - 1, math.floor(min(xs)))),
        max(0, min(height - 1, math.floor(min(ys)))),
        max(1, min(width, math.ceil(max(xs)) + 1)),
        max(1, min(height, math.ceil(max(ys)) + 1)),
    )


def _polygon_boxes(
    polygons: Iterable[np.ndarray], width: int, height: int,
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


def _layout_content_box_from_polygons(
    polygons: Iterable[np.ndarray],
    width: int,
    height: int,
    settings: AppSettings,
) -> tuple[tuple[int, int, int, int], LayoutEstimate]:
    """Derive the retained content frame from dictionary layout, not page ink.

    Horizontal bounds deliberately follow the same parameters exposed by
    automatic layout detection:
      first column left -> final column right.
    Vertical bounds retain the running header / page text above the body and end
    at the detected body bottom. Scanner specks outside the column span therefore
    cannot enlarge the normal crop.
    """
    boxes = _polygon_boxes(polygons, width, height)
    if len(boxes) < 4:
        raise RuntimeError("Paddle文本框过少，无法建立版面保留范围")

    estimate = infer_layout_from_boxes(
        boxes,
        (width, height),
        display_scale=1.0,
        ink_mask=None,
        columns_policy=settings.layout_columns_policy,
        fixed_columns=settings.columns,
        column_separator_mode=settings.layout_column_separator_mode,
    )
    starts = tuple(int(value) for value in estimate.column_starts)
    left = (
        max(0, min(width - 1, starts[0]))
        if starts else max(0, min(width - 1, int(estimate.manual_x)))
    )
    last_start = (
        starts[-1]
        if starts
        else left
        + max(0, int(estimate.columns) - 1)
        * (max(1, int(estimate.column_width)) + max(0, int(estimate.gutter)))
    )

    # Preprocessing uses the column-specific outer edge retained by automatic
    # layout detection, not the median column width used by drawing/layout logic.
    # This keeps the final crop tied to the actual last occupied column.
    rights = tuple(int(value) for value in estimate.column_rights)
    if rights and len(rights) == len(starts):
        right = rights[-1]
    else:
        right = int(last_start) + max(1, int(estimate.column_width))
    right = max(int(last_start) + 1, min(width, right))

    heights = [box[3] - box[1] for box in boxes]
    median_h = max(4.0, float(np.median(heights)))
    filtered = [
        box for box in boxes
        if box[3] - box[1] >= max(3.0, median_h * 0.40)
        and box[2] - box[0] <= width * 0.92
    ] or boxes

    # Reuse the detector population but estimate the header top independently
    # from body start_y. Only text spatially associated with the detected page
    # layout is eligible, so edge/binding artifacts do not define Y either.
    horizontal_pad = max(8, round(max(estimate.character_height, estimate.column_width * 0.08)))
    upper_limit = int(estimate.start_y) + max(8, round(estimate.character_height * 1.5))
    header_tops = [
        box[1]
        for box in filtered
        if box[1] <= upper_limit
        and left - horizontal_pad <= (box[0] + box[2]) / 2.0 <= right + horizontal_pad
    ]
    header_top = (
        int(min(header_tops))
        if header_tops else max(0, int(estimate.start_y))
    )
    body_bottom = max(header_top + 1, min(height, int(estimate.bottom_y)))
    return (left, max(0, header_top), right, body_bottom), estimate


def _expand_box_px(
    box: tuple[int, int, int, int],
    width: int,
    height: int,
    safety_margin_px: int,
) -> tuple[int, int, int, int]:
    margin = max(0, min(1000, int(safety_margin_px)))
    x0, y0, x1, y1 = box
    return (
        max(0, x0 - margin),
        max(0, y0 - margin),
        min(width, x1 + margin),
        min(height, y1 + margin),
    )


def _rotate_box_same_canvas(
    box: tuple[int, int, int, int],
    width: int,
    height: int,
    angle_deg: float,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    points = [
        _rotate_point_same_canvas(x0, y0, width, height, angle_deg),
        _rotate_point_same_canvas(x1, y0, width, height, angle_deg),
        _rotate_point_same_canvas(x1, y1, width, height, angle_deg),
        _rotate_point_same_canvas(x0, y1, width, height, angle_deg),
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (
        max(0, min(width - 1, math.floor(min(xs)))),
        max(0, min(height - 1, math.floor(min(ys)))),
        max(1, min(width, math.ceil(max(xs)))),
        max(1, min(height, math.ceil(max(ys)))),
    )


def _projection_skew_fallback(
    image: Image.Image, settings: AppSettings, *, writing_mode: str,
) -> float:
    """Slow but dependency-free skew fallback used only when Paddle gives no boxes."""
    source = normalize_page_rgb(image)
    scale = min(1.0, 1000.0 / max(1, max(source.size)))
    work = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.BILINEAR,
    ) if scale < 1.0 else source
    gray = np.asarray(ImageOps.grayscale(work), dtype=np.uint8)
    ink = analysis_ink_mask(gray, settings).astype(np.uint8) * 255
    mask = Image.fromarray(ink, mode="L")
    vertical = str(writing_mode or "horizontal-tb").startswith("vertical")

    def score(angle: float) -> float:
        rotated = mask.rotate(
            angle, resample=Image.Resampling.NEAREST, expand=False, fillcolor=0
        )
        array = np.asarray(rotated, dtype=np.float32) / 255.0
        projection = array.sum(axis=0 if vertical else 1)
        return float(np.square(np.diff(projection)).sum())

    coarse = [step * 0.25 for step in range(-10, 11)]
    coarse_scores = [score(angle) for angle in coarse]
    best = coarse[int(np.argmax(coarse_scores))]
    fine = [best - 0.25 + step * 0.05 for step in range(11)]
    fine_scores = [score(angle) for angle in fine]
    return float(fine[int(np.argmax(fine_scores))])


def _normalize_geometry_mode(value: str | None) -> str:
    mode = str(value or "auto").strip().lower()
    aliases = {
        "auto": "auto",
        "deskew": "deskew",
        "light": "deskew",
        "perspective": "perspective",
        "dewarp": "uvdoc",
        "mesh": "uvdoc",
        "uvdoc": "uvdoc",
        "paddle_unwarp": "uvdoc",
    }
    return aliases.get(mode, "auto")


def geometry_corrected_image(
    image: Image.Image,
    analysis: PreprocessAnalysis,
) -> Image.Image:
    """Apply the saved geometric correction without cropping.

    Export/preview reuse the exact analysis transform; they do not run Paddle
    again, so a reviewed result remains deterministic.
    """
    corrected = deskew_image(image, analysis.applied_angle_deg)
    if analysis.perspective_matrix is not None:
        corrected = apply_homography_image(
            corrected, analysis.perspective_matrix,
        )
    if analysis.geometry_mode == "uvdoc":
        corrected = unwarp_document_image(corrected)
    return corrected


def analyze_preprocess_page(
    image: Image.Image,
    settings: AppSettings,
    *,
    safety_margin_px: int = DEFAULT_SAFETY_MARGIN_PX,
    auto_deskew: bool = True,
    geometry_mode: str = "auto",
    manual_perspective_quad: tuple[float, ...] | None = None,
) -> PreprocessAnalysis:
    source = normalize_page_rgb(image)
    width, height = source.size
    requested_geometry_mode = _normalize_geometry_mode(geometry_mode)
    manual_quad = (
        tuple(float(v) for v in manual_perspective_quad)
        if manual_perspective_quad is not None and len(manual_perspective_quad) == 8
        else None
    )
    warnings: list[str] = []
    polygons: list[np.ndarray] = []
    method_parts = ["paddle_layout_roi"]
    layout_source_boxes = 0

    try:
        polygons = detect_text_polygons(source, settings)
        if len(polygons) < 4:
            raise RuntimeError("Paddle文本框过少")
    except Exception as exc:
        polygons = []
        method_parts = ["projection_fallback"]
        warnings.append(f"版面结构检测不可用，裁边已使用投影回退：{exc}")

    line_geometry = TextLineGeometryAnalysis()
    if polygons:
        try:
            line_geometry = analyze_text_line_geometry(
                source, polygons, settings,
            )
            method_parts.append("line_geometry")
            if line_geometry.recommendation == "uvdoc_review":
                warnings.append(
                    "文本行与真实长直线共同提示非线性页面形变，建议使用"
                    "“UVDoc展平（Paddle高级）”复核。"
                )
            elif line_geometry.recommendation == "manual_review":
                if (
                    line_geometry.separator_found
                    and line_geometry.separator_residual_px
                    < max(3.0, width * 0.0015)
                ):
                    warnings.append(
                        "文本行方向存在局部不一致，但长直分隔线保持笔直；"
                        "更可能是版式/OCR波动，不自动做非线性矫正。"
                    )
                else:
                    warnings.append(
                        "文本行方向存在不一致，当前证据不足以支持非线性矫正。"
                    )
        except Exception as exc:
            warnings.append(f"文本行几何分析不可用：{exc}")

    correction, angle_samples, angle_mad = estimate_skew_from_polygons(
        polygons, writing_mode=settings.layout_writing_mode,
    )
    if angle_samples < 4:
        if method_parts[0] != "projection_fallback":
            method_parts.append("projection_angle")
        try:
            correction = _projection_skew_fallback(
                source, settings, writing_mode=settings.layout_writing_mode,
            )
            warnings.append("文本框角度样本较少，倾斜角由投影法补充估计。")
        except Exception as exc:
            correction = 0.0
            warnings.append(f"倾斜角回退估计失败：{exc}")

    if abs(correction) < DEFAULT_DESKEW_DEAD_ZONE_DEG:
        applied = 0.0
    elif abs(correction) <= DEFAULT_MAX_AUTO_DESKEW_DEG and auto_deskew:
        applied = float(correction)
    else:
        applied = 0.0
        if auto_deskew and abs(correction) > DEFAULT_MAX_AUTO_DESKEW_DEG:
            warnings.append(
                f"检测倾斜 {correction:+.2f}° 超过自动纠偏上限 "
                f"{DEFAULT_MAX_AUTO_DESKEW_DEG:.1f}°，未自动旋转。"
            )

    working = deskew_image(source, applied)
    working_polygons = (
        _rotate_polygons_same_canvas(polygons, width, height, applied)
        if polygons else []
    )
    actual_geometry_mode = "deskew"
    geometry_strength = 0.0
    perspective_matrix: tuple[float, ...] | None = None
    perspective_source_quad: tuple[float, ...] | None = None
    perspective_target_quad: tuple[float, ...] | None = None
    perspective_classification = "none"
    perspective_candidate_strength_px = 0.0
    perspective_left_drift_px = 0.0
    perspective_right_drift_px = 0.0
    perspective_common_drift_px = 0.0
    perspective_width_delta_px = 0.0
    perspective_width_change_ratio = 0.0
    perspective_scale_top = 1.0
    perspective_scale_bottom = 1.0
    perspective_scale_delta_ratio = 0.0
    perspective_auto_safe = False

    # A saved manual quadrilateral is expressed in original-source pixels.
    # Rotate those four handles through the same small-angle correction first,
    # then rectify before any automatic perspective/dewarp stage.
    if manual_quad is not None:
        try:
            rotated_quad: list[float] = []
            for index in range(0, 8, 2):
                x, y = _rotate_point_same_canvas(
                    manual_quad[index], manual_quad[index + 1],
                    width, height, applied,
                )
                rotated_quad.extend((x, y))
            manual_estimate = perspective_from_quad(
                rotated_quad, working.size,
            )
            perspective_matrix = manual_estimate.matrix
            perspective_source_quad = tuple(manual_estimate.source_quad)
            perspective_target_quad = tuple(manual_estimate.target_quad)
            perspective_classification = str(manual_estimate.classification)
            perspective_candidate_strength_px = float(manual_estimate.strength_px)
            perspective_left_drift_px = float(manual_estimate.left_drift_px)
            perspective_right_drift_px = float(manual_estimate.right_drift_px)
            perspective_common_drift_px = float(manual_estimate.common_drift_px)
            perspective_width_delta_px = float(manual_estimate.width_delta_px)
            perspective_width_change_ratio = float(manual_estimate.width_change_ratio)
            perspective_scale_top = float(manual_estimate.scale_top)
            perspective_scale_bottom = float(manual_estimate.scale_bottom)
            perspective_scale_delta_ratio = float(manual_estimate.scale_delta_ratio)
            geometry_strength = max(
                geometry_strength, float(manual_estimate.strength_px)
            )
            working = apply_homography_image(
                working, perspective_matrix,
            )
            if working_polygons:
                working_polygons = transform_polygons_homography(
                    working_polygons, perspective_matrix,
                )
            actual_geometry_mode = "manual_perspective"
            method_parts.append("manual_perspective")
        except Exception as exc:
            warnings.append(f"手动四角透视纠正不可用：{exc}")

    # PaddleOCR/PaddleX 3.7 ships the official document-preprocessor
    # pipeline with UVDoc as its image-unwarping module.  Keep this explicit
    # rather than silently downloading/running a neural model in automatic mode.
    if requested_geometry_mode == "uvdoc":
        try:
            working = unwarp_document_image(working)
            # UVDoc is non-projective, so the prior polygon coordinates are no
            # longer valid. Final crop must come from a fresh detection pass.
            working_polygons = []
            actual_geometry_mode = "uvdoc"
            method_parts.append("uvdoc")
        except Exception as exc:
            warnings.append(
                f"Paddle UVDoc 展平不可用，已保留前一步几何结果：{exc}"
            )

    # Advanced geometry is deliberately estimated after the global small-angle
    # correction. Perspective handles the remaining trapezoid/shear component.
    # Nonlinear unwarping is intentionally NOT automatic: real-page validation
    # showed that OCR-derived mesh deformation can create visible S-curves.
    if (
        manual_quad is None
        and working_polygons
        and requested_geometry_mode in {"auto", "perspective"}
    ):
        try:
            perspective = estimate_perspective_from_polygons(
                working_polygons, working.size, settings,
            )
            perspective_threshold = max(5.0, width * 0.002)
            strong_candidate = perspective.strength_px >= perspective_threshold
            line_supports_perspective = (
                line_geometry.recommendation == "perspective"
                and line_geometry.confidence >= 0.35
            )

            perspective_source_quad = tuple(perspective.source_quad)
            perspective_target_quad = tuple(perspective.target_quad)
            perspective_candidate_strength_px = float(perspective.strength_px)
            perspective_classification = str(
                getattr(perspective, "classification", "unknown")
            )
            perspective_left_drift_px = float(
                getattr(perspective, "left_drift_px", 0.0)
            )
            perspective_right_drift_px = float(
                getattr(perspective, "right_drift_px", 0.0)
            )
            perspective_common_drift_px = float(
                getattr(perspective, "common_drift_px", 0.0)
            )
            perspective_width_delta_px = float(
                getattr(perspective, "width_delta_px", 0.0)
            )
            perspective_width_change_ratio = max(
                0.0, float(getattr(perspective, "width_change_ratio", 0.0))
            )
            perspective_scale_top = max(
                0.0, float(getattr(perspective, "scale_top", 1.0))
            )
            perspective_scale_bottom = max(
                0.0, float(getattr(perspective, "scale_bottom", 1.0))
            )
            perspective_scale_delta_ratio = max(
                0.0, float(getattr(perspective, "scale_delta_ratio", 0.0))
            )

            is_keystone = perspective_classification == "keystone"
            is_parallel_drift = perspective_classification == "parallel_drift"
            # Missing a physical separator makes the OCR-only geometry less
            # trustworthy, so the automatic scale-gradient ceiling is tighter.
            max_auto_scale_delta = (
                0.030 if line_geometry.separator_found else 0.015
            )
            scale_safe = (
                perspective_scale_delta_ratio <= max_auto_scale_delta
            )
            perspective_auto_safe = bool(
                strong_candidate
                and line_supports_perspective
                and is_keystone
                and not is_parallel_drift
                and scale_safe
            )

            apply_perspective = (
                requested_geometry_mode == "perspective"
                or (
                    requested_geometry_mode == "auto"
                    and perspective_auto_safe
                )
            )

            if requested_geometry_mode == "auto" and strong_candidate:
                review_reasons: list[str] = []
                if not line_supports_perspective:
                    review_reasons.append("文本行几何证据不足或不一致")
                if is_parallel_drift:
                    review_reasons.append(
                        "首末结构边界主要呈同向平行漂移，更像旋转/剪切而非梯形透视"
                    )
                elif not is_keystone:
                    review_reasons.append("上下有效宽度变化不足以支持梯形透视")
                if not scale_safe:
                    review_reasons.append(
                        f"预计上下横向尺度差 {perspective_scale_delta_ratio * 100:.2f}% "
                        f"超过自动安全上限 {max_auto_scale_delta * 100:.1f}%"
                    )
                if review_reasons:
                    warnings.append(
                        "自动透视候选已拦截：" + "；".join(review_reasons)
                        + "。可人工选择“自动透视”复核。"
                    )
                    method_parts.append("perspective_review")
            if (
                requested_geometry_mode == "perspective"
                and perspective.strength_px >= 0.75
                and not perspective_auto_safe
            ):
                warnings.append(
                    "已按用户显式选择执行透视；该候选未通过“自动几何”的保守安全门，"
                    f"分类={perspective_classification}，预计上下横向尺度差 "
                    f"{perspective_scale_delta_ratio * 100:.2f}%。"
                )
            if apply_perspective and perspective.strength_px >= 0.75:
                perspective_matrix = perspective.matrix
                geometry_strength = max(
                    geometry_strength, float(perspective.strength_px)
                )
                working = apply_homography_image(
                    working, perspective_matrix,
                )
                working_polygons = transform_polygons_homography(
                    working_polygons, perspective_matrix,
                )
                actual_geometry_mode = "perspective"
                method_parts.append("perspective")
        except Exception as exc:
            if requested_geometry_mode == "perspective":
                warnings.append(f"自动透视纠正不可用：{exc}")

    # Advanced transforms change the page geometry. Re-run TextDetection on the
    # corrected image before final structural cropping. If that second pass
    # fails, the mathematically transformed original polygons remain a safe
    # fallback and preserve non-destructive export.
    final_polygons = working_polygons
    if polygons and actual_geometry_mode in {"manual_perspective", "perspective", "uvdoc"}:
        try:
            redetected = detect_text_polygons(working, settings)
            if len(redetected) >= 4:
                final_polygons = redetected
                method_parts.append("redetect")
            else:
                warnings.append("高级纠正后文本框过少，最终裁边沿用变换后的原检测框。")
        except Exception as exc:
            warnings.append(f"高级纠正后版面复检失败，沿用变换后的原检测框：{exc}")

    layout_box: tuple[int, int, int, int] | None = None
    if final_polygons:
        try:
            layout_box, layout_estimate = _layout_content_box_from_polygons(
                final_polygons, width, height, settings,
            )
            layout_source_boxes = int(layout_estimate.source_boxes)
        except Exception as exc:
            warnings.append(f"纠正后结构裁边失败，已使用投影回退：{exc}")

    if layout_box is not None:
        raw_content_box = layout_box
        crop_box = _expand_box_px(
            raw_content_box, width, height, safety_margin_px,
        )
    else:
        if method_parts[0] != "projection_fallback":
            method_parts.insert(0, "projection_fallback")
        raw_content_box = _projection_content_box(working, settings)
        crop_box = _expand_box_px(
            raw_content_box, width, height, safety_margin_px,
        )

    text_box = _rotated_text_box(
        final_polygons, width, height, 0.0,
    ) if final_polygons else None

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

    return PreprocessAnalysis(
        source_width=width,
        source_height=height,
        correction_angle_deg=round(float(correction), 4),
        applied_angle_deg=round(float(applied), 4),
        crop_box=crop_box,
        raw_content_box=raw_content_box,
        text_box=text_box,
        source_boxes=evidence_boxes,
        angle_samples=angle_samples,
        angle_mad_deg=round(float(angle_mad), 4),
        retained_ratio=retained_ratio,
        confidence=confidence,
        status=status,
        method="+".join(dict.fromkeys(method_parts)),
        warnings=tuple(warnings),
        safety_margin_px=max(0, int(safety_margin_px)),
        auto_deskew=bool(auto_deskew),
        requested_geometry_mode=requested_geometry_mode,
        geometry_mode=actual_geometry_mode,
        geometry_strength_px=round(float(geometry_strength), 3),
        perspective_matrix=perspective_matrix,
        perspective_source_quad=perspective_source_quad,
        perspective_target_quad=perspective_target_quad,
        perspective_classification=perspective_classification,
        perspective_candidate_strength_px=round(float(perspective_candidate_strength_px), 3),
        perspective_left_drift_px=round(float(perspective_left_drift_px), 3),
        perspective_right_drift_px=round(float(perspective_right_drift_px), 3),
        perspective_common_drift_px=round(float(perspective_common_drift_px), 3),
        perspective_width_delta_px=round(float(perspective_width_delta_px), 3),
        perspective_width_change_ratio=round(float(perspective_width_change_ratio), 6),
        perspective_scale_top=round(float(perspective_scale_top), 6),
        perspective_scale_bottom=round(float(perspective_scale_bottom), 6),
        perspective_scale_delta_ratio=round(float(perspective_scale_delta_ratio), 6),
        perspective_auto_safe=bool(perspective_auto_safe),
        manual_perspective_quad=manual_quad,
        line_geometry_rows=int(line_geometry.row_count),
        line_geometry_global_angle_deg=float(line_geometry.global_angle_deg),
        line_geometry_top_angle_deg=float(line_geometry.top_angle_deg),
        line_geometry_middle_angle_deg=float(line_geometry.middle_angle_deg),
        line_geometry_bottom_angle_deg=float(line_geometry.bottom_angle_deg),
        line_geometry_trend_deg=float(line_geometry.angle_trend_deg),
        line_geometry_residual_mad_deg=float(line_geometry.residual_mad_deg),
        line_geometry_residual_span_deg=float(line_geometry.residual_span_deg),
        line_geometry_separator_found=bool(line_geometry.separator_found),
        line_geometry_separator_residual_px=float(
            line_geometry.separator_residual_px
        ),
        line_geometry_separator_span_ratio=float(
            line_geometry.separator_span_ratio
        ),
        line_geometry_separator_slope_px_per_1000y=float(
            line_geometry.separator_slope_px_per_1000y
        ),
        line_geometry_separator_drift_px=float(
            line_geometry.separator_drift_px
        ),
        line_geometry_recommendation=str(line_geometry.recommendation),
        line_geometry_confidence=float(line_geometry.confidence),
    )

def analyze_preprocess_path(
    path: Path,
    settings: AppSettings,
    *,
    safety_margin_px: int = DEFAULT_SAFETY_MARGIN_PX,
    auto_deskew: bool = True,
    geometry_mode: str = "auto",
    manual_perspective_quad: tuple[float, ...] | None = None,
) -> PreprocessAnalysis:
    path = Path(path)
    with Image.open(path) as opened:
        analysis = analyze_preprocess_page(
            opened,
            settings,
            safety_margin_px=safety_margin_px,
            auto_deskew=auto_deskew,
            geometry_mode=geometry_mode,
            manual_perspective_quad=manual_perspective_quad,
        )
    try:
        stat = path.stat()
        analysis.source_size_bytes = int(stat.st_size)
        analysis.source_mtime_ns = int(stat.st_mtime_ns)
    except OSError:
        pass
    return analysis


def result_path(project_root: Path, page: Path) -> Path:
    root = image_preprocess_data_root(project_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{Path(page).stem}.json"


def save_analysis(project_root: Path, page: Path, analysis: PreprocessAnalysis) -> Path:
    path = result_path(project_root, page)
    payload = analysis.to_dict()
    payload["page"] = Path(page).name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def load_analysis(project_root: Path, page: Path) -> PreprocessAnalysis | None:
    path = result_path(project_root, page)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return PreprocessAnalysis.from_dict(payload)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


MANUAL_GEOMETRY_FORMAT = "picture-capture-manual-perspective"
MANUAL_GEOMETRY_VERSION = 1


def manual_geometry_path(project_root: Path, page: Path) -> Path:
    root = image_preprocess_data_root(project_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{Path(page).stem}.geometry.json"


def load_manual_perspective_quad(
    project_root: Path, page: Path,
) -> tuple[float, ...] | None:
    path = manual_geometry_path(project_root, page)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("format") != MANUAL_GEOMETRY_FORMAT
            or int(payload.get("version", 0) or 0) != MANUAL_GEOMETRY_VERSION
        ):
            return None
        values = payload.get("quad")
        if not isinstance(values, (list, tuple)) or len(values) != 8:
            return None
        quad = tuple(float(v) for v in values)
        return quad if all(math.isfinite(v) for v in quad) else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def save_manual_perspective_quad(
    project_root: Path,
    page: Path,
    quad: Iterable[float],
) -> Path:
    values = tuple(float(v) for v in quad)
    if len(values) != 8 or not all(math.isfinite(v) for v in values):
        raise ValueError("手动四角坐标无效")
    path = manual_geometry_path(project_root, page)
    payload = {
        "format": MANUAL_GEOMETRY_FORMAT,
        "version": MANUAL_GEOMETRY_VERSION,
        "page": Path(page).name,
        "quad": list(values),
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def clear_manual_perspective_quad(project_root: Path, page: Path) -> None:
    path = manual_geometry_path(project_root, page)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def analysis_is_current(
    analysis: PreprocessAnalysis,
    page: Path,
    *,
    safety_margin_px: int,
    auto_deskew: bool,
    geometry_mode: str = "auto",
    manual_perspective_quad: tuple[float, ...] | None = None,
) -> bool:
    page = Path(page)
    if int(analysis.safety_margin_px) != int(safety_margin_px):
        return False
    if bool(analysis.auto_deskew) != bool(auto_deskew):
        return False
    if _normalize_geometry_mode(analysis.requested_geometry_mode) != _normalize_geometry_mode(geometry_mode):
        return False
    expected_quad = (
        tuple(round(float(v), 4) for v in manual_perspective_quad)
        if manual_perspective_quad is not None else None
    )
    actual_quad = (
        tuple(round(float(v), 4) for v in analysis.manual_perspective_quad)
        if analysis.manual_perspective_quad is not None else None
    )
    if actual_quad != expected_quad:
        return False
    try:
        stat = page.stat()
    except OSError:
        return False
    if analysis.source_size_bytes and int(stat.st_size) != int(analysis.source_size_bytes):
        return False
    if analysis.source_mtime_ns and int(stat.st_mtime_ns) != int(analysis.source_mtime_ns):
        return False
    return True


def overlay_excluded_regions(
    image: Image.Image,
    crop_box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int, int] = PREVIEW_YELLOW,
    outline: tuple[int, int, int, int] = PREVIEW_OUTLINE,
) -> Image.Image:
    base = normalize_page_rgb(image).convert("RGBA")
    width, height = base.size
    x0, y0, x1, y1 = (
        max(0, min(width, int(crop_box[0]))),
        max(0, min(height, int(crop_box[1]))),
        max(0, min(width, int(crop_box[2]))),
        max(0, min(height, int(crop_box[3]))),
    )
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    if y0 > 0:
        draw.rectangle((0, 0, width, y0), fill=fill)
    if y1 < height:
        draw.rectangle((0, y1, width, height), fill=fill)
    if x0 > 0 and y1 > y0:
        draw.rectangle((0, y0, x0, y1), fill=fill)
    if x1 < width and y1 > y0:
        draw.rectangle((x1, y0, width, y1), fill=fill)
    draw.rectangle((x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)), outline=outline, width=3)
    return Image.alpha_composite(base, overlay).convert("RGB")


def review_image(image: Image.Image, analysis: PreprocessAnalysis) -> Image.Image:
    corrected = geometry_corrected_image(image, analysis)
    return overlay_excluded_regions(corrected, analysis.crop_box)


def processed_image(image: Image.Image, analysis: PreprocessAnalysis) -> Image.Image:
    corrected = geometry_corrected_image(image, analysis)
    return corrected.crop(analysis.crop_box)


def _normalize_canvas_alignment(value: str, *, axis: str) -> str:
    value = str(value or "").strip().lower()
    if axis == "x":
        return value if value in {"left", "center", "right"} else "center"
    return value if value in {"top", "center", "bottom"} else "top"


def output_canvas_info(
    analysis: PreprocessAnalysis,
    *,
    enabled: bool = False,
    mode: str = "batch_max",
    requested_width: int = 0,
    requested_height: int = 0,
    canvas_width: int | None = None,
    canvas_height: int | None = None,
    align_x: str = "center",
    align_y: str = "top",
) -> OutputCanvasInfo:
    x0, y0, x1, y1 = analysis.crop_box
    content_width = max(1, int(x1) - int(x0))
    content_height = max(1, int(y1) - int(y0))
    align_x = _normalize_canvas_alignment(align_x, axis="x")
    align_y = _normalize_canvas_alignment(align_y, axis="y")
    mode = str(mode or "batch_max").strip().lower()
    if mode not in {"batch_max", "custom"}:
        mode = "batch_max"

    if not enabled:
        width = content_width
        height = content_height
        paste_x = 0
        paste_y = 0
    else:
        width = max(content_width, int(canvas_width or requested_width or content_width))
        height = max(content_height, int(canvas_height or requested_height or content_height))
        if align_x == "left":
            paste_x = 0
        elif align_x == "right":
            paste_x = width - content_width
        else:
            paste_x = (width - content_width) // 2
        if align_y == "top":
            paste_y = 0
        elif align_y == "bottom":
            paste_y = height - content_height
        else:
            paste_y = (height - content_height) // 2

    return OutputCanvasInfo(
        enabled=bool(enabled),
        mode=mode,
        requested_width=max(0, int(requested_width)),
        requested_height=max(0, int(requested_height)),
        width=width,
        height=height,
        align_x=align_x,
        align_y=align_y,
        content_box=(
            int(paste_x), int(paste_y),
            int(paste_x + content_width), int(paste_y + content_height),
        ),
        expanded_width=bool(enabled and width > max(0, int(requested_width)) and mode == "custom"),
        expanded_height=bool(enabled and height > max(0, int(requested_height)) and mode == "custom"),
    )


def processed_image_with_canvas(
    image: Image.Image,
    analysis: PreprocessAnalysis,
    canvas: OutputCanvasInfo | None = None,
) -> Image.Image:
    content = processed_image(image, analysis)
    if canvas is None or not canvas.enabled:
        return content
    # Never rescale the retained scan just to make it fit. The batch export
    # resolves a canvas at least as large as every content crop; this local
    # guard keeps direct callers safe as well.
    width = max(int(canvas.width), content.width)
    height = max(int(canvas.height), content.height)
    if width != canvas.width or height != canvas.height:
        canvas = output_canvas_info(
            analysis,
            enabled=True,
            mode=canvas.mode,
            requested_width=canvas.requested_width,
            requested_height=canvas.requested_height,
            canvas_width=width,
            canvas_height=height,
            align_x=canvas.align_x,
            align_y=canvas.align_y,
        )
    output = Image.new("RGB", (width, height), "white")
    output.paste(content, (canvas.content_box[0], canvas.content_box[1]))
    return output


def preprocess_metadata_output_root(project_root: Path) -> Path:
    path = image_preprocess_output_root(project_root) / "meta"
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_diagnostic_json(
    page: Path,
    analysis: PreprocessAnalysis,
    destination: Path,
    *,
    output_path: Path | None = None,
    canvas: OutputCanvasInfo | None = None,
    settings: AppSettings | None = None,
) -> Path:
    payload = analysis.to_dict()
    payload["page"] = Path(page).name
    payload["source_path_name"] = Path(page).name
    payload["effective_settings"] = (
        {
            "layout_writing_mode": str(settings.layout_writing_mode),
            "layout_text_direction": str(settings.layout_text_direction),
            "layout_transform": str(settings.layout_transform),
            "layout_columns_policy": str(settings.layout_columns_policy),
            "fixed_columns": int(settings.columns),
            "layout_column_separator_mode": str(
                settings.layout_column_separator_mode
            ),
            "analysis_threshold_mode": str(settings.analysis_threshold_mode),
            "preprocess_auto_deskew": bool(
                settings.preprocess_auto_deskew
            ),
            "preprocess_safety_margin_px": int(
                settings.preprocess_safety_margin_px
            ),
            "preprocess_geometry_mode": str(
                settings.preprocess_geometry_mode
            ),
        }
        if settings is not None else None
    )
    payload["algorithm_constants"] = {
        "max_auto_deskew_deg": DEFAULT_MAX_AUTO_DESKEW_DEG,
        "deskew_dead_zone_deg": DEFAULT_DESKEW_DEAD_ZONE_DEG,
    }
    payload["export"] = {
        "output_filename": Path(output_path).name if output_path is not None else None,
        "content_width": max(1, analysis.crop_box[2] - analysis.crop_box[0]),
        "content_height": max(1, analysis.crop_box[3] - analysis.crop_box[1]),
        "canvas": (
            canvas.to_dict()
            if canvas is not None
            else output_canvas_info(analysis, enabled=False).to_dict()
        ),
    }
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def export_summary_csv(
    records: Iterable[tuple[Path, PreprocessAnalysis, Path, OutputCanvasInfo]],
    destination: Path,
) -> Path:
    rows = []
    for page, analysis, output_path, canvas in records:
        rows.append({
            "page": Path(page).name,
            "status": analysis.status,
            "confidence": round(float(analysis.confidence), 4),
            "method": analysis.method,
            "warnings": " | ".join(analysis.warnings),
            "source_width": analysis.source_width,
            "source_height": analysis.source_height,
            "applied_angle_deg": analysis.applied_angle_deg,
            "correction_angle_deg": analysis.correction_angle_deg,
            "angle_samples": analysis.angle_samples,
            "angle_mad_deg": analysis.angle_mad_deg,
            "requested_geometry_mode": analysis.requested_geometry_mode,
            "geometry_mode": analysis.geometry_mode,
            "geometry_strength_px": analysis.geometry_strength_px,
            "perspective_candidate_strength_px": analysis.perspective_candidate_strength_px,
            "perspective_classification": analysis.perspective_classification,
            "perspective_left_drift_px": analysis.perspective_left_drift_px,
            "perspective_right_drift_px": analysis.perspective_right_drift_px,
            "perspective_common_drift_px": analysis.perspective_common_drift_px,
            "perspective_width_delta_px": analysis.perspective_width_delta_px,
            "perspective_width_change_ratio": analysis.perspective_width_change_ratio,
            "perspective_scale_top": analysis.perspective_scale_top,
            "perspective_scale_bottom": analysis.perspective_scale_bottom,
            "perspective_scale_delta_ratio": analysis.perspective_scale_delta_ratio,
            "perspective_auto_safe": analysis.perspective_auto_safe,
            "crop_x0": analysis.crop_box[0],
            "crop_y0": analysis.crop_box[1],
            "crop_x1": analysis.crop_box[2],
            "crop_y1": analysis.crop_box[3],
            "content_width": analysis.crop_box[2] - analysis.crop_box[0],
            "content_height": analysis.crop_box[3] - analysis.crop_box[1],
            "retained_ratio": round(float(analysis.retained_ratio), 6),
            "safety_margin_px": analysis.safety_margin_px,
            "line_geometry_rows": analysis.line_geometry_rows,
            "line_geometry_global_angle_deg": analysis.line_geometry_global_angle_deg,
            "line_geometry_top_angle_deg": analysis.line_geometry_top_angle_deg,
            "line_geometry_middle_angle_deg": analysis.line_geometry_middle_angle_deg,
            "line_geometry_bottom_angle_deg": analysis.line_geometry_bottom_angle_deg,
            "line_geometry_trend_deg": analysis.line_geometry_trend_deg,
            "line_geometry_residual_mad_deg": analysis.line_geometry_residual_mad_deg,
            "line_geometry_residual_span_deg": analysis.line_geometry_residual_span_deg,
            "separator_found": analysis.line_geometry_separator_found,
            "separator_residual_px": analysis.line_geometry_separator_residual_px,
            "separator_span_ratio": analysis.line_geometry_separator_span_ratio,
            "separator_slope_px_per_1000y": analysis.line_geometry_separator_slope_px_per_1000y,
            "separator_drift_px": analysis.line_geometry_separator_drift_px,
            "line_geometry_recommendation": analysis.line_geometry_recommendation,
            "line_geometry_confidence": analysis.line_geometry_confidence,
            "canvas_enabled": canvas.enabled,
            "canvas_mode": canvas.mode,
            "canvas_requested_width": canvas.requested_width,
            "canvas_requested_height": canvas.requested_height,
            "canvas_width": canvas.width,
            "canvas_height": canvas.height,
            "canvas_align_x": canvas.align_x,
            "canvas_align_y": canvas.align_y,
            "canvas_content_x0": canvas.content_box[0],
            "canvas_content_y0": canvas.content_box[1],
            "canvas_content_x1": canvas.content_box[2],
            "canvas_content_y1": canvas.content_box[3],
            "canvas_expanded_width": canvas.expanded_width,
            "canvas_expanded_height": canvas.expanded_height,
            "output_filename": Path(output_path).name,
        })
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "page", "status", "confidence", "warnings", "output_filename"
    ]
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)
    return destination


def preview_output_root(project_root: Path) -> Path:
    path = image_preprocess_output_root(project_root) / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def processed_output_root(project_root: Path) -> Path:
    path = image_preprocess_output_root(project_root) / "processed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_review_preview(
    page: Path,
    analysis: PreprocessAnalysis,
    destination: Path,
    *,
    max_long_side: int = 1400,
) -> Path:
    with Image.open(page) as opened:
        preview = review_image(opened, analysis)
    scale = min(1.0, max(320, int(max_long_side)) / max(preview.size))
    if scale < 1.0:
        preview = preview.resize(
            (max(1, round(preview.width * scale)), max(1, round(preview.height * scale))),
            Image.Resampling.LANCZOS,
        )
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    preview.save(destination, format="JPEG", quality=88, optimize=True)
    return destination


def save_processed_page(
    page: Path,
    analysis: PreprocessAnalysis,
    destination: Path,
    *,
    canvas: OutputCanvasInfo | None = None,
) -> Path:
    with Image.open(page) as opened:
        result = processed_image_with_canvas(opened, analysis, canvas)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix.casefold()
    if suffix in {".jpg", ".jpeg"}:
        result.save(destination, quality=95, subsampling=0)
    elif suffix in {".tif", ".tiff"}:
        result.save(destination, compression="tiff_lzw")
    else:
        result.save(destination)
    return destination


def result_summary(analysis: PreprocessAnalysis) -> str:
    x0, y0, x1, y1 = analysis.crop_box
    label = "需检查" if analysis.status == "review" else "正常"
    geometry_labels = {
        "deskew": "轻量纠偏",
        "perspective": "透视纠正",
        "manual_perspective": "手动四角",
        "uvdoc": "UVDoc 展平",
    }
    geometry = geometry_labels.get(analysis.geometry_mode, analysis.geometry_mode)
    if (
        analysis.manual_perspective_quad is not None
        and analysis.geometry_mode == "uvdoc"
    ):
        geometry = "手动四角+UVDoc"
    strength = (
        f" {analysis.geometry_strength_px:.1f}px"
        if analysis.geometry_mode in {"manual_perspective", "perspective"}        and analysis.geometry_strength_px > 0
        else ""
    )
    line_labels = {
        "none": "无需额外",
        "deskew": "旋转",
        "perspective": "透视",
        "uvdoc_review": "建议UVDoc",
        "manual_review": "人工复核",
        "insufficient": "证据不足",
    }
    perspective_part = ""
    if analysis.perspective_candidate_strength_px > 0:
        perspective_part = (
            f"｜透视候选 {analysis.perspective_candidate_strength_px:.1f}px"
            f" / 尺度差 {analysis.perspective_scale_delta_ratio * 100:.2f}%"
            f" / {analysis.perspective_classification}"
        )
    line_part = ""
    if analysis.line_geometry_rows:
        separator = (
            f"｜直线残差 {analysis.line_geometry_separator_residual_px:.1f}px"
            if analysis.line_geometry_separator_found else ""
        )
        line_part = (
            f"｜行几何 {analysis.line_geometry_rows}行"
            f" Δ角 {analysis.line_geometry_trend_deg:+.2f}°"
            f"{separator}"
            f" → {line_labels.get(analysis.line_geometry_recommendation, analysis.line_geometry_recommendation)}"
        )
    return (
        f"{label}｜{geometry}{strength}｜"
        f"旋转 {analysis.applied_angle_deg:+.2f}°"
        f"（检测 {analysis.correction_angle_deg:+.2f}°）"
        f"{perspective_part}{line_part}｜"
        f"保留 {analysis.retained_ratio * 100:.1f}%｜"
        f"裁剪 L{x0} T{y0} R{x1} B{y1}"
    )
