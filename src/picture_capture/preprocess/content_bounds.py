"""Preprocessing content frames and projection fallback with explicit detectors."""
from __future__ import annotations

from typing import Callable, Iterable

import numpy as np
from PIL import Image, ImageOps

from ..image_utils import normalize_page_rgb
from ..layout.detection import LayoutEstimate
from ..models import AppSettings
from .deskew import _polygon_boxes


def _smooth_1d(values: np.ndarray, width: int) -> np.ndarray:
    width = max(1, int(width))
    if width <= 1:
        return values.astype(float, copy=False)
    kernel = np.ones(width, dtype=float) / float(width)
    return np.convolve(values.astype(float, copy=False), kernel, mode="same")



def _projection_content_box(
    image: Image.Image, settings: AppSettings, *,
    ink_mask_builder: Callable,
) -> tuple[int, int, int, int]:
    """Find a conservative nonblank content envelope without OCR recognition."""
    source = normalize_page_rgb(image)
    scale = min(1.0, 1800.0 / max(1, max(source.size)))
    work = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.BILINEAR,
    ) if scale < 1.0 else source
    gray = np.asarray(ImageOps.grayscale(work), dtype=np.uint8)
    ink = ink_mask_builder(gray, settings).copy()
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



def _layout_content_box_from_polygons(
    polygons: Iterable[np.ndarray],
    width: int,
    height: int,
    settings: AppSettings,
    *, layout_estimator: Callable,
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

    estimate = layout_estimator(
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



def _projection_skew_fallback(
    image: Image.Image, settings: AppSettings, *, writing_mode: str,
    ink_mask_builder: Callable,
) -> float:
    """Slow but dependency-free skew fallback used only when Paddle gives no boxes."""
    source = normalize_page_rgb(image)
    scale = min(1.0, 1000.0 / max(1, max(source.size)))
    work = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.BILINEAR,
    ) if scale < 1.0 else source
    gray = np.asarray(ImageOps.grayscale(work), dtype=np.uint8)
    ink = ink_mask_builder(gray, settings).astype(np.uint8) * 255
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



# Root API exports this helper too; preserve its callable identity.
_smooth_1d.__module__ = "picture_capture.image_preprocessing"
