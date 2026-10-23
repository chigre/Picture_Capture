from __future__ import annotations

from dataclasses import dataclass, field, replace
from io import BytesIO
from pathlib import Path
from typing import Any
import os
import re
import json
import subprocess
import unicodedata

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .crop.auxiliary_lines import read_auxiliary_lines
from .crop import page_workflow as _page_workflow
from .crop import polygon_geometry as _polygon_geometry
from .crop import worker_policy as _crop_worker_policy
from .crop import entry_column_bounds as _entry_column_bounds
from .crop import entry_vertical_bounds as _entry_vertical_bounds
from .crop import line_box_geometry as _line_box_geometry
from .models import AppSettings, Entry, PolygonRegion, resolved_tesseract_language
from .geometry.coordinate_space import SOURCE_COORDINATE_SPACE
from .geometry import column_tracking_math as _column_tracking_math
from .geometry import reading_order as _reading_order
from .preprocess.page_pixels import normalize_page_rgb
from .preprocess import core_analysis_pixels as _analysis_pixels
from .geometry.layout_transform import LayoutTransform
from .persistence.page_sections import (
    PageSection, build_reading_lanes, normalize_page_sections, read_page_sections,
    reading_lane_index, section_index_for_v, v_is_inside_sections,
)
from .profile.semantics import (
    effective_page_settings, entry_allowed_by_page_template, page_template_analysis_image,
)
from .ocr.engines import find_tesseract
from .io.formats import read_pdic, read_ppp, write_pdic, write_ppp
from .persistence.project_storage import pdic_path_for_image, ppp_read_path_for_image, ppp_write_path_for_image, qt_root, special_pages_path
from .crop.publish import _publish_file_transaction, _publish_temp_path
from .crop.export_output import prepare_crop_background
from .illustration.labels import previous_entry_ref_for_image
from .crop.plan_formatting import (
    _normalized_crop_name,
    canonical_polygon_link,
    entry_crop_piece_filename,
    page_crop_plan_dict,
    polygon_display_name,
)
from .ocr.text_io import export_ocred, import_ocred, load_replace_rules, process_ocr_text
from .crop.logging import append_crop_log, append_illustration_crop_log
from .ordinary.vb_brightness import legacy_row_brightness_scores_1000
from .ordinary import ink_threshold as _ink_threshold
from .ordinary import separator_position_policy as _separator_policy
from .ordinary import auto_layout_policy as _auto_layout_policy
from .ordinary import fusion_entry_mapping as _fusion_entry_mapping
from .ocr import ordinary_marker_crop as _ordinary_marker_crop
from .illustration.candidate_size import illustration_candidate_min_dimensions


_COLUMN_TRACK_ADAPTIVE_BLOCK = 19
_COLUMN_TRACK_ADAPTIVE_C = 20
_ANALYSIS_MAX_WIDTH = 1600

ORDINARY_AUTO_LAYOUT_FIELDS: tuple[tuple[str, str], ...] = (
    ("columns", "ordinary_auto_columns"),
    ("start_y", "ordinary_auto_start_y"),
    ("manual_x", "ordinary_auto_manual_x"),
    ("column_width", "ordinary_auto_column_width"),
    ("gutter", "ordinary_auto_gutter"),
    ("character_height", "ordinary_auto_character_height"),
    ("row_padding", "ordinary_auto_row_padding"),
)


def ordinary_page_layout_settings(
    image: Image.Image, settings: AppSettings
) -> tuple[AppSettings, dict[str, int]]:
    """Historical page-specific automatic layout policy entrypoint."""
    return _auto_layout_policy.ordinary_page_layout_settings(
        image, settings,
        replace_fn=replace, field_switches=ORDINARY_AUTO_LAYOUT_FIELDS,
    )

@dataclass(slots=True)
class ColumnPath:
    """Piecewise-linear left edge of one dictionary column."""

    points: list[tuple[int, int]]

    def x_at(self, y: int) -> int:
        if not self.points:
            return 0
        if y <= self.points[0][0]:
            return self.points[0][1]
        if y >= self.points[-1][0]:
            return self.points[-1][1]
        for (y0, x0), (y1, x1) in zip(self.points, self.points[1:]):
            if y0 <= y <= y1:
                if y1 == y0:
                    return x0
                ratio = (y - y0) / (y1 - y0)
                return round(x0 + ratio * (x1 - x0))
        return self.points[-1][1]

    def x_bounds(self, y0: int, y1: int) -> tuple[int, int]:
        samples = [self.x_at(y0), self.x_at(y1)]
        samples.extend(x for y, x in self.points if y0 <= y <= y1)
        return min(samples), max(samples)


@dataclass(slots=True)
class Geometry:
    column_starts: list[int]
    column_widths: list[int]
    top: int
    bottom: int
    column_paths: list[ColumnPath]
    transform: LayoutTransform = LayoutTransform()
    source_size: tuple[int, int] = (0, 0)

    def x_at(self, column: int, y: int) -> int:
        if 0 <= column < len(self.column_paths):
            return self.column_paths[column].x_at(y)
        return self.column_starts[column]

    def x_bounds(self, column: int, y0: int, y1: int) -> tuple[int, int]:
        if 0 <= column < len(self.column_paths):
            return self.column_paths[column].x_bounds(y0, y1)
        x = self.column_starts[column]
        return x, x

    def source_to_canonical(self, x: int, y: int) -> tuple[int, int]:
        if self.source_size == (0, 0):
            return x, y
        return self.transform.source_to_canonical_point(x, y, self.source_size)

    def canonical_to_source(self, x: int, y: int) -> tuple[int, int]:
        if self.source_size == (0, 0):
            return x, y
        return self.transform.canonical_to_source_point(x, y, self.source_size)


@dataclass(slots=True)
class CropRecord:
    page: str
    index: int
    word: str
    filename: str
    box: tuple[int, int, int, int]


@dataclass(slots=True)
class EntryCropPiecePlan:
    output_index: int
    entry_ref_index: int | None
    word: str
    box: tuple[int, int, int, int]
    suffix: str
    source_mode: str = "cleaned"
    merge_polygon_indices: tuple[int, ...] = ()


@dataclass(slots=True)
class IllustrationCropPlan:
    polygon_index: int
    name: str
    associated_entry_index: int | None
    associated_word: str
    relation: str
    standalone: bool
    box: tuple[int, int, int, int] | None


@dataclass(slots=True)
class PageCropPlan:
    entry_pieces: list[EntryCropPiecePlan]
    illustrations: list[IllustrationCropPlan]
    integrate_illustrations: bool = True
    # Preview-only regions after auxiliary stop lines; never included in WW export.
    auxiliary_gaps: list[tuple[int, int, int, int]] = field(default_factory=list)


@dataclass(slots=True)
class IllustrationCropEvent:
    page: str
    polygon_index: int
    name: str
    associated_word: str
    relation: str
    action: str
    filename: str = ""


@dataclass(slots=True)
class IllustrationSplitResult:
    records: list[CropRecord]
    events: list[IllustrationCropEvent]

    # Backward-compatible sequence behaviour for callers that historically
    # treated split_illustrations() as a list of CropRecord.
    def __iter__(self):
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index):
        return self.records[index]


def _analysis_image(image: Image.Image, max_width: int = _ANALYSIS_MAX_WIDTH) -> tuple[Image.Image, float]:
    """Original image-analysis preview hook; retain RGB/resize patch points."""
    return _analysis_pixels.analysis_image(
        image, max_width, normalize_rgb_fn=normalize_page_rgb, image_cls=Image,
    )

def parameter_scale(image: Image.Image, settings: AppSettings) -> float:
    """Settings are already literal original-image pixels."""
    return 1.0


def _source_px(value: int | float) -> int:
    return round(float(value))


def _adaptive_dark_mask(gray_image: Image.Image, block_size: int, c_value: int) -> np.ndarray:
    """Original adaptive threshold hook; preserve live NumPy and Pillow patches."""
    return _analysis_pixels.adaptive_dark_mask(
        gray_image, block_size, c_value, np_module=np, image_filter=ImageFilter,
    )

def _smooth_track(
    values: list[int], max_step: int, *, nominal_x: int | None = None,
) -> list[int]:
    """Historical callable: implementation is in geometry.column_tracking_math."""
    return _column_tracking_math._smooth_track(values, max_step, nominal_x=nominal_x)


def _column_tracking_dimensions(
    column_width: int,
    body_height: int,
    settings: AppSettings,
) -> tuple[int, int, int]:
    """Keep the public/core patch point while delegating pure dimension math."""
    return _column_tracking_math._column_tracking_dimensions(
        column_width, body_height, settings,
    )

def _estimate_column_paths(
    analysis: Image.Image,
    scale: float,
    starts_analysis: list[int],
    widths_analysis: list[int],
    top_analysis: int,
    bottom_analysis: int,
    settings: AppSettings,
    geometry_to_analysis: float,
) -> list[ColumnPath]:
    """Track each column's left text edge with piecewise-linear anchors.

    The legacy VB program estimated a top point, a lower point and one slope.
    Here each vertical block contributes an anchor, which also follows local
    stretching or gentle curvature. Sparse/uncertain blocks inherit the
    nearest reliable position.
    """
    if not settings.follow_column_deformation:
        return [
            ColumnPath([(round(top_analysis / scale), round(x / scale)),
                        (round(bottom_analysis / scale), round(x / scale))])
            for x in starts_analysis
        ]

    body_indent = _source_px(settings.body_indent)
    dark = _adaptive_dark_mask(
        ImageOps.grayscale(analysis),
        max(3, round(_COLUMN_TRACK_ADAPTIVE_BLOCK * geometry_to_analysis)),
        _COLUMN_TRACK_ADAPTIVE_C,
    )
    _height, width = dark.shape
    body_height = max(1, int(bottom_analysis) - int(top_analysis))
    paths: list[ColumnPath] = []

    for nominal_x, column_width in zip(starts_analysis, widths_analysis):
        # Search range follows the actual current-page column width instead of
        # an absolute source-pixel constant, so the same setting survives DPI
        # changes and page-specific layout detection.
        radius, block_height, stable_step = _column_tracking_dimensions(
            column_width, body_height, settings
        )
        search_left = max(0, nominal_x - radius)
        search_right = min(
            width,
            nominal_x + radius + max(6, round(body_indent * geometry_to_analysis * 0.5)),
        )
        anchors_y: list[int] = []
        raw_x: list[int | None] = []
        for y0 in range(top_analysis, bottom_analysis, block_height):
            y1 = min(bottom_analysis, y0 + block_height)
            anchors_y.append((y0 + y1) // 2)
            region = dark[y0:y1, search_left:search_right]
            if region.size == 0:
                raw_x.append(None)
                continue
            # Ignore near-continuous dark rules or scan borders. Ordinary
            # letter strokes occupy only a minority of rows in a block.
            rule_columns = region.mean(axis=0) > 0.45
            if rule_columns.any():
                expanded_rules = rule_columns.copy()
                expanded_rules[1:] |= rule_columns[:-1]
                expanded_rules[:-1] |= rule_columns[1:]
                region = region.copy()
                region[:, expanded_rules] = False
            # Require two dark pixels in a three-pixel horizontal neighborhood
            # so isolated dust does not define a false left edge.
            if region.shape[1] >= 3:
                sturdy = (
                    region[:, :-2].astype(np.uint8)
                    + region[:, 1:-1].astype(np.uint8)
                    + region[:, 2:].astype(np.uint8)
                ) >= 2
                offset = 1
            else:
                sturdy = region
                offset = 0
            valid_rows = sturdy.any(axis=1)
            if int(valid_rows.sum()) < max(3, round((y1 - y0) * 0.025)):
                raw_x.append(None)
                continue
            first_ink = sturdy.argmax(axis=1)[valid_rows] + search_left + offset
            candidate = round(float(np.percentile(first_ink, 12)))
            candidate = min(nominal_x + radius, max(nominal_x - radius, candidate))
            raw_x.append(candidate)

        reliable = [value for value in raw_x if value is not None]
        if not reliable:
            filled = [nominal_x for _ in raw_x]
        else:
            filled: list[int] = []
            for index, value in enumerate(raw_x):
                if value is not None:
                    filled.append(value)
                    continue
                nearest = min(
                    (j for j, candidate in enumerate(raw_x) if candidate is not None),
                    key=lambda j: abs(j - index),
                )
                filled.append(int(raw_x[nearest]))  # type: ignore[arg-type]
        # Max local movement is a slope-like percentage of the current block
        # height.  This keeps the accepted geometric tilt invariant when the
        # user changes block height or scans at another resolution.
        filled = _smooth_track(
            filled, stable_step, nominal_x=int(nominal_x),
        )
        source_points = [
            (round(y / scale), round(x / scale)) for y, x in zip(anchors_y, filled)
        ]
        source_top = round(top_analysis / scale)
        source_bottom = round(bottom_analysis / scale)
        if not source_points:
            source_points = [(source_top, round(nominal_x / scale)),
                             (source_bottom, round(nominal_x / scale))]
        else:
            source_points.insert(0, (source_top, source_points[0][1]))
            source_points.append((source_bottom, source_points[-1][1]))
        paths.append(ColumnPath(source_points))
    return paths


def _column_start_offsets_canonical(
    settings: AppSettings, count: int, canonical_width: int,
) -> list[int]:
    """Resolve persisted per-column nudges into current-page canonical pixels."""
    raw = list(getattr(settings, "column_start_offsets", []) or [])
    resolved: list[int] = []
    for index in range(max(0, int(count))):
        try:
            value = float(raw[index]) if index < len(raw) else 0.0
        except (TypeError, ValueError):
            value = 0.0
        resolved.append(
            _source_px(value)
        )
    return resolved


def apply_column_start_offsets(
    base_starts: list[int], offsets: list[int], *, gutter: int, max_x: int,
) -> list[int]:
    """Apply independent column-left nudges while preserving usable column order."""
    if not base_starts:
        return []
    limit = max(0, int(max_x))
    starts = [
        max(0, min(limit, int(base) + (int(offsets[i]) if i < len(offsets) else 0)))
        for i, base in enumerate(base_starts)
    ]
    # Keep enough room for the configured gutter plus a minimal usable body band.
    # Normal small corrections are unchanged; only pathological/corrupt offsets
    # are clipped so columns can never cross each other.
    min_step = max(11, max(0, int(gutter)) + 10)
    for _ in range(2):
        for index in range(1, len(starts)):
            starts[index] = max(starts[index], starts[index - 1] + min_step)
        starts[-1] = min(limit, starts[-1])
        for index in range(len(starts) - 2, -1, -1):
            starts[index] = min(starts[index], starts[index + 1] - min_step)
        starts[0] = max(0, starts[0])
    return [max(0, min(limit, int(value))) for value in starts]


def _derive_nominal_geometry_canonical(
    image_width: int, image_height: int, settings: AppSettings,
) -> Geometry:
    """Return nominal geometry with settings used as literal full-resolution pixels."""
    width = max(1, int(image_width))
    height = max(1, int(image_height))
    count = max(1, int(settings.columns))

    left = max(0, _source_px(settings.manual_x))
    gutter = max(0, _source_px(settings.gutter))
    column_width = max(10, _source_px(settings.column_width))
    base_starts = [left + i * (column_width + gutter) for i in range(count)]
    offsets = _column_start_offsets_canonical(settings, count, width)
    starts = apply_column_start_offsets(
        base_starts, offsets, gutter=gutter, max_x=width - 1,
    )

    widths: list[int] = []
    for i, start_x in enumerate(starts):
        if i + 1 < len(starts):
            widths.append(max(1, starts[i + 1] - start_x - gutter))
        else:
            widths.append(max(1, width - start_x))

    top = min(height - 1, max(0, _source_px(settings.start_y)))
    bottom_setting = _source_px(settings.bottom_y)
    if settings.crop_to_bottom_y and bottom_setting > top:
        bottom = min(height, max(top + 1, bottom_setting))
    else:
        bottom = height
    paths = [ColumnPath([(top, x), (bottom, x)]) for x in starts]
    return Geometry(starts, widths, top, bottom, paths)

def derive_nominal_geometry(image_width: int, image_height: int, settings: AppSettings) -> Geometry:
    """Return canonical nominal geometry while retaining source mapping metadata."""
    transform = LayoutTransform(str(getattr(settings, "layout_transform", "identity") or "identity"))
    source_size = (max(1, int(image_width)), max(1, int(image_height)))
    canonical_size = transform.canonical_size(source_size)
    geometry = _derive_nominal_geometry_canonical(*canonical_size, settings)
    geometry.transform = transform
    geometry.source_size = source_size
    return geometry


def _derive_geometry_canonical(image: Image.Image, settings: AppSettings) -> Geometry:
    """Build geometry from literal full-resolution pixel settings.

    Image analysis may use a downscaled copy, but configured X/Y values are
    never round-tripped through that analysis scale.
    """
    analysis, analysis_scale = _analysis_image(image)
    analysis_width, analysis_height = analysis.size
    source_width, source_height = image.size
    count = max(1, int(settings.columns))

    left = max(0, _source_px(settings.manual_x))
    gutter = max(0, _source_px(settings.gutter))
    column_width = max(10, _source_px(settings.column_width))
    base_starts = [left + i * (column_width + gutter) for i in range(count)]
    offsets = _column_start_offsets_canonical(settings, count, source_width)
    starts = apply_column_start_offsets(
        base_starts, offsets, gutter=gutter, max_x=source_width - 1,
    )

    widths: list[int] = []
    for i, start_x in enumerate(starts):
        if i + 1 < len(starts):
            widths.append(max(1, starts[i + 1] - start_x - gutter))
        else:
            widths.append(max(1, source_width - start_x))

    top = min(source_height - 1, max(0, _source_px(settings.start_y)))
    bottom_setting = _source_px(settings.bottom_y)
    if settings.crop_to_bottom_y and bottom_setting > top:
        bottom = min(source_height, max(top + 1, bottom_setting))
    else:
        bottom = source_height

    starts_analysis = [
        min(analysis_width - 1, max(0, round(x * analysis_scale)))
        for x in starts
    ]
    widths_analysis = [
        max(1, round(width * analysis_scale)) for width in widths
    ]
    top_analysis = min(
        analysis_height - 1, max(0, round(top * analysis_scale))
    )
    bottom_analysis = min(
        analysis_height, max(top_analysis + 1, round(bottom * analysis_scale))
    )

    if settings.follow_column_deformation:
        paths = _estimate_column_paths(
            analysis,
            analysis_scale,
            starts_analysis,
            widths_analysis,
            top_analysis,
            bottom_analysis,
            settings,
            analysis_scale,
        )
    else:
        paths = [ColumnPath([(top, x), (bottom, x)]) for x in starts]
    return Geometry(starts, widths, top, bottom, paths)

def derive_geometry(image: Image.Image, settings: AppSettings) -> Geometry:
    """Build layout geometry in canonical space without changing source pixels."""
    source = normalize_page_rgb(image)
    transform = LayoutTransform(str(getattr(settings, "layout_transform", "identity") or "identity"))
    canonical = transform.canonical_image_for_analysis(source)
    geometry = _derive_geometry_canonical(canonical, settings)
    geometry.transform = transform
    geometry.source_size = source.size
    return geometry


def _page_geometry_context(
    image: Image.Image,
    settings: AppSettings,
    profile_page_index: int = 0,
) -> tuple[Image.Image, AppSettings, Image.Image, Geometry]:
    """Resolve one page through the single Profile -> geometry boundary.

    Persisted project geometry remains in reference-page canonical pixels.
    Physical Profile percentages are resolved against this source page, and
    page-edge exclusions are applied only to a disposable analysis copy.
    Every downstream consumer can therefore share the same runtime geometry
    while crops/PDIC/PPP continue to use untouched source pixels.
    """
    source = normalize_page_rgb(image)
    effective = effective_page_settings(settings, source.size, profile_page_index)
    analysis_source = page_template_analysis_image(
        source, effective, profile_page_index,
    )
    geometry = derive_geometry(analysis_source, effective)
    return source, effective, analysis_source, geometry


def _left_edge_otsu_threshold(gray: np.ndarray) -> int:
    """Stable legacy core threshold entry; implementation now lives in ordinary."""
    return _ink_threshold.otsu_threshold(gray, np_module=np)


def _left_edge_ink_mask(gray: np.ndarray, settings: AppSettings) -> np.ndarray:
    """Foreground mask through the current threshold callback and image modules."""
    return _ink_threshold.ink_mask(
        gray, settings,
        otsu_fn=_left_edge_otsu_threshold,
        np_module=np,
        image_class=Image,
        image_filter=ImageFilter,
    )

def _legacy_is_point(
    rgb_sum: np.ndarray,
    x: int,
    y: int,
    area_x: int,
    area_y: int,
    max_brightness_percent: float,
    *,
    direction: int = 1,
) -> bool:
    """Faithful full-resolution port of VB.NET IsPoint().

    VB sampled area_x pixels to the reading-right of the anchor and rows from
    -area_y/2 through +area_y/2. Its denominator intentionally remained
    area_x * area_y even though the inclusive row loop can contain one extra
    row. Keeping that detail preserves the old 90% gate.
    """
    height, width = rgb_sum.shape[:2]
    area_x = max(1, int(area_x))
    area_y = max(1, int(area_y))
    direction = 1 if int(direction) >= 0 else -1
    half = max(0, round(area_y * 0.5))
    y0 = int(y) - half
    y1 = int(y) + half
    if y0 < 0 or y1 >= height:
        return False

    xs = int(x) + direction * np.arange(1, area_x + 1, dtype=np.int64)
    if xs.size == 0 or int(xs.min()) < 0 or int(xs.max()) >= width:
        return False
    region = rgb_sum[y0:y1 + 1, xs]
    if region.size == 0:
        return False
    denominator = float(area_x * area_y * 255 * 3)
    brightness_percent = round(float(region.astype(np.float64).sum()) / denominator * 100.0)
    return brightness_percent <= float(max_brightness_percent)


def _legacy_row_brightness_1000(
    rgb_sum: np.ndarray,
    y: int,
    x: int,
    width: int,
    *,
    direction: int = 1,
) -> int | None:
    """Return the VB row-brightness score on its original 0..1000 scale."""
    height, image_width = rgb_sum.shape[:2]
    if not (0 <= int(y) < height):
        return None
    width = max(1, int(width))
    direction = 1 if int(direction) >= 0 else -1
    xs = int(x) + direction * np.arange(1, width + 1, dtype=np.int64)
    if xs.size == 0 or int(xs.min()) < 0 or int(xs.max()) >= image_width:
        return None
    total = float(rgb_sum[int(y), xs].astype(np.float64).sum())
    return int(round(total / float(765 * width) * 1000.0))


def _legacy_find_separator_y(
    rgb_sum: np.ndarray,
    candidate_x: int,
    candidate_y: int,
    *,
    column_width: int,
    direction: int,
    row_height: int,
    upward_ratio: float,
    ordinary_right_divisor: float,
    darkness_threshold: int,
    white_threshold_high: int,
    white_threshold_low: int,
    whitespace_adjustment: int,
    top: int,
    x_min: int,
    x_max: int,
) -> tuple[int | None, dict[str, int | str]]:
    """Port the two-stage Y search from VB.NET Draw_Auto() at source resolution."""
    height, width = rgb_sum.shape[:2]
    if height <= 0 or width <= 0:
        return None, {"reason": "empty_image"}

    direction = 1 if int(direction) >= 0 else -1
    row_height = max(1, int(row_height))
    upward_ratio = max(0.1, float(upward_ratio))
    upward = max(1, int(round(row_height / upward_ratio)))
    divisor = max(1.0, float(ordinary_right_divisor))
    requested_span = max(1, int(round(float(column_width) / divisor * 0.98)))
    if direction > 0:
        room = min(width - 1, int(x_max)) - int(candidate_x)
    else:
        room = int(candidate_x) - max(0, int(x_min))
    span = max(0, min(requested_span, int(room)))
    if span <= 0:
        return None, {"reason": "empty_horizontal_span"}

    high = max(0, min(1000, int(white_threshold_high)))
    low = max(0, min(1000, int(white_threshold_low)))
    if low > high:
        low, high = high, low
    adjust = max(0, int(whitespace_adjustment))
    dark_limit = max(0, min(765, int(darkness_threshold)))
    xs = int(candidate_x) + direction * np.arange(1, span + 1, dtype=np.int64)

    # VB method 1: nearest upward row with no pixel darker than the fixed
    # threshold, followed by a short run-of-white centering correction.
    for ysu in range(1, upward + 1):
        line_y = int(candidate_y) - ysu
        if line_y < int(top):
            break
        row_values = rgb_sum[line_y, xs]
        if bool(np.any(row_values < dark_limit)):
            continue

        extra_white = 0
        if int(candidate_y) - ysu - int(top) > row_height and adjust > 0:
            for offset in range(1, adjust + 1):
                score = _legacy_row_brightness_1000(
                    rgb_sum, line_y - offset, candidate_x, span, direction=direction
                )
                if score is not None and score >= high:
                    extra_white += 1
                else:
                    break
        separator = int(round(int(candidate_y) - (ysu + extra_white * 0.5)))
        separator = min(int(candidate_y), max(int(top), separator))
        return separator, {
            "reason": "vb_full_white",
            "upward_offset": int(ysu),
            "span": int(span),
            "extra_white_rows": int(extra_white),
        }

    row_scores = legacy_row_brightness_scores_1000(
        rgb_sum, xs, int(top), int(candidate_y), upward, span,
    )
    for threshold in range(high, low - 1, -2):
        for ysu in range(1, upward + 1):
            line_y = int(candidate_y) - ysu
            if line_y < int(top):
                break
            score = row_scores.get(line_y)
            if score is None or score <= threshold:
                continue

            separator = line_y
            if adjust > 0 and ysu < adjust:
                for ygiu in range(ysu, upward + 1):
                    probe_y = int(candidate_y) - ygiu
                    if probe_y < int(top):
                        break
                    probe = row_scores.get(probe_y)
                    if probe is None:
                        break
                    if probe < low or probe + 50 < threshold:
                        separator = int(candidate_y) - ygiu + adjust
                        break
            separator = min(int(candidate_y), max(int(top), int(separator)))
            return separator, {
                "reason": "vb_brightness_fallback",
                "upward_offset": int(ysu),
                "span": int(span),
                "threshold": int(threshold),
            }

    return None, {"reason": "no_vb_separator", "span": int(span)}


def _ordinary_source_column_edge(
    geometry: Geometry, column: int, y: int
) -> tuple[int, int]:
    """Return dynamic source-X edge and source reading-right direction."""
    if geometry.transform.kind not in {"identity", "mirror_x"}:
        raise RuntimeError(
            "普通画线仅支持保持原图 Y 轴的横排版面；旋转/竖排页面请使用 OCR 画线。"
        )
    canonical_x = int(round(geometry.x_at(column, int(y))))
    source_x, source_y = geometry.canonical_to_source(canonical_x, int(y))
    next_x, next_y = geometry.canonical_to_source(canonical_x + 1, int(y))
    if int(source_y) != int(y) or int(next_y) != int(y):
        raise RuntimeError("普通画线检测到非水平坐标变换，已停止以避免混用坐标系。")
    direction = 1 if int(next_x) >= int(source_x) else -1
    return int(source_x), direction


def _detect_entries_left_edge(
    image: Image.Image,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], Geometry]:
    """Restore the 2016 VB.NET Draw_Auto ordinary-drawing algorithm.

    The complete candidate/separator chain runs directly on original
    full-resolution source pixels:

      dynamic LX(y) -> 微调判距 dark anchor -> IsPoint 2D support ->
      upward separator search -> full-white first -> 999..700 fallback ->
      whitespace correction -> VB separator Y -> optional small modern refine.

    No downsampled analysis image and no scaled coordinate system participates
    in ordinary candidate or separator placement.
    """
    source = normalize_page_rgb(image)
    geometry = derive_geometry(source, settings)
    rgb = np.asarray(source, dtype=np.uint8)
    rgb_sum = rgb.astype(np.uint16).sum(axis=2)
    gray = np.asarray(ImageOps.grayscale(source), dtype=np.uint8)
    image_height, image_width = rgb_sum.shape[:2]

    body_indent = max(1, _source_px(settings.body_indent))
    character_height = max(1, _source_px(settings.character_height))
    row_padding = int(_source_px(settings.row_padding))
    row_height = max(1, character_height + row_padding)
    horizontal_tolerance = max(0, _source_px(settings.horizontal_tolerance))
    darkness_threshold = max(0, min(765, int(settings.darkness_threshold)))
    support_brightness = max(
        1.0, min(100.0, float(getattr(settings, "dark_area_percent", 90)))
    )
    row_step_multiplier = max(
        0.5, min(3.0, float(getattr(settings, "row_step_multiplier", 1.2)))
    )
    upward_ratio = max(
        0.1, float(getattr(settings, "upward_ratio", 1.5) or 1.5)
    )
    ordinary_right_divisor = max(
        1.0, float(getattr(settings, "ordinary_right_divisor", 1.0) or 1.0)
    )
    white_high = int(getattr(settings, "white_threshold_high", 999))
    white_low = int(getattr(settings, "white_threshold_low", 700))
    whitespace_adjustment = max(
        0, int(getattr(settings, "whitespace_adjustment", 2))
    )

    top = max(0, min(image_height - 1, int(geometry.top)))
    ordinary_bottom = min(image_height, int(geometry.bottom))
    bottom = max(top + 1, ordinary_bottom)

    # SECTION sidecars are the page-specific authority for exceptional body
    # ranges.  Restrict the expensive scan to their outer envelope; the final
    # entry filter below still excludes the gaps between multiple sections.
    if page_sections:
        sections = normalize_page_sections(page_sections, top, bottom)
        if sections:
            top = max(top, min(int(section.top_v) for section in sections))
            bottom = min(bottom, max(int(section.bottom_v) for section in sections))
            bottom = max(top + 1, bottom)

    analysis_left = int(getattr(settings, "analysis_left", 0) or 0)
    analysis_right = int(getattr(settings, "analysis_right", 0) or 0)
    if analysis_right > analysis_left >= 0:
        x_min = max(0, min(image_width - 1, analysis_left))
        x_max = max(x_min, min(image_width - 1, analysis_right))
    else:
        x_min, x_max = 0, image_width - 1

    entries: list[Entry] = []
    for col in range(len(geometry.column_starts)):
        y = top
        while y < bottom:
            edge_x, direction = _ordinary_source_column_edge(geometry, col, y)
            accepted_x: int | None = None

            # Dynamic LX(y) already supplies the modern slope/deformation term;
            # the remaining full-resolution source-pixel lane is 微调判距.
            for offset in range(horizontal_tolerance + 1):
                candidate_x = edge_x + direction * offset
                if candidate_x < x_min or candidate_x > x_max:
                    continue
                if candidate_x < 0 or candidate_x >= image_width:
                    continue
                if int(rgb_sum[y, candidate_x]) >= darkness_threshold:
                    continue
                if _legacy_is_point(
                    rgb_sum,
                    candidate_x,
                    y,
                    body_indent,
                    2 * body_indent,
                    support_brightness,
                    direction=direction,
                ):
                    accepted_x = int(candidate_x)
                    break

            if accepted_x is None:
                y += 2
                continue

            vb_separator_y, _vb_meta = _legacy_find_separator_y(
                rgb_sum,
                accepted_x,
                y,
                column_width=max(1, int(geometry.column_widths[col])),
                direction=direction,
                row_height=row_height,
                upward_ratio=upward_ratio,
                ordinary_right_divisor=ordinary_right_divisor,
                darkness_threshold=darkness_threshold,
                white_threshold_high=white_high,
                white_threshold_low=white_low,
                whitespace_adjustment=whitespace_adjustment,
                top=top,
                x_min=x_min,
                x_max=x_max,
            )

            if vb_separator_y is not None:
                final_y = int(vb_separator_y)

                # Modern enhancement is deliberately post-VB and tightly
                # bounded: it may only nudge an already valid VB separator.
                if settings.paddle_refine_separator_y:
                    from .paddle_headwords import refine_separator_y
                    refine_edge_x, refine_direction = _ordinary_source_column_edge(
                        geometry, col, final_y
                    )
                    col_width = max(10, int(geometry.column_widths[col]))
                    other_x = refine_edge_x + refine_direction * col_width
                    crop_x0 = max(0, min(refine_edge_x, other_x))
                    crop_x1 = min(image_width, max(refine_edge_x, other_x) + 1)
                    if crop_x1 - crop_x0 > 8:
                        refined_y, _refinement = refine_separator_y(
                            gray[:, crop_x0:crop_x1],
                            final_y,
                            max(2, character_height),
                            settings,
                            pixel_scale=1.0,
                            lower_bound=top,
                        )
                        max_delta = max(2, round(row_height * 0.20))
                        final_y += max(
                            -max_delta,
                            min(max_delta, int(refined_y) - final_y),
                        )

                final_y = min(bottom - 1, max(top, int(final_y)))
                marker_x, _direction = _ordinary_source_column_edge(
                    geometry, col, final_y
                )
                vb_reason = str(_vb_meta.get("reason", "") or "")
                if vb_reason == "vb_full_white":
                    ordinary_confidence = 0.98
                    ordinary_issue = ""
                else:
                    threshold = int(_vb_meta.get("threshold", white_low) or white_low)
                    span = max(1, white_high - white_low)
                    whiteness = max(0.0, min(1.0, (threshold - white_low) / span))
                    ordinary_confidence = 0.76 + 0.18 * whiteness
                    ordinary_issue = "ORDINARY_VB_BRIGHTNESS_FALLBACK"
                entries.append(Entry(
                    word="",
                    x=int(marker_x),
                    y=int(final_y),
                    confidence=float(round(ordinary_confidence, 4)),
                    ocr_source="ordinary_vb",
                    issue_type=ordinary_issue,
                ))

                # VB: y = separatorY + rowHeight * 1.2 (default).
                y = max(
                    y + 2,
                    int(final_y + round(row_height * row_step_multiplier)),
                )
            else:
                # VB still advanced after a confirmed anchor even when neither
                # separator method succeeded; emulate that anti-retrigger step.
                upward = max(1, int(round(row_height / upward_ratio)))
                y = max(
                    y + 2,
                    int(y - upward + round(row_height * row_step_multiplier)),
                )

    entries = _collapse_ordinary_oversized_cjk_split_markers(
        source, entries, geometry, settings,
    )
    entries = _recover_ordinary_oversized_cjk_missing_markers(
        source, entries, geometry, settings,
    )
    return sort_entries_reading_order(entries, geometry), geometry




def _collapse_ordinary_oversized_cjk_split_markers(
    image: Image.Image,
    entries: list[Entry],
    geometry: Geometry,
    settings: AppSettings,
) -> list[Entry]:
    """Collapse duplicate ordinary markers created *inside* one oversized Han glyph.

    The restored VB detector deliberately knows nothing about OCR semantics. On
    CJK character dictionaries that is usually an advantage, but a display-size
    one-character headword can be roughly two body rows tall. The ordinary scan
    may then find a second apparently valid separator in an internal white/stroke
    gap and emit two markers for one physical entry.

    This post-pass is OCR-independent. It uses only the original page pixels and
    the existing large-CJK left-strip projection detector. It never creates a
    marker and never globally widens Y de-duplication: it removes a lower ordinary
    marker only when both markers are associated with the same visually confirmed
    oversized glyph run. Thus OCR may miss the character completely and ordinary
    mode can still self-correct its own internal duplicate.
    """
    if len(entries) < 2:
        return list(entries)
    if str(getattr(settings, "layout_writing_mode", "horizontal-tb")).startswith("vertical"):
        return list(entries)
    if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
        return list(entries)

    from .paddle_headwords import (
        _cjk_visual_projection_runs,
        _is_chinese_ocr,
        unwrap_column_band,
    )

    profile_id = str(getattr(settings, "dictionary_profile_id", "") or "").lower()
    if not (_is_chinese_ocr(settings) or "cjk" in profile_id):
        return list(entries)

    source = normalize_page_rgb(image)
    character_height = max(
        2, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    top_margin = max(3, round(character_height * 0.55))
    lower_margin = max(2, round(character_height * 0.15))
    internal_floor = max(3, round(character_height * 0.22))
    strip_width = max(
        100,
        round(character_height * 3.2),
        int(getattr(settings, "paddle_band_left_margin", 0) or 0) + 72,
    )

    rows: list[tuple[Entry, int, int, int]] = []
    for entry in entries:
        u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        col = column_index_for_click(int(entry.x), geometry, int(entry.y))
        rows.append((entry, int(col), int(u), int(v)))
    rows.sort(key=lambda item: (item[1], item[3], item[2]))

    suppressed: set[int] = set()
    keeper_issue: set[int] = set()

    for col in range(len(geometry.column_starts)):
        column_rows = [
            (index, row) for index, row in enumerate(rows)
            if row[1] == col
        ]
        if len(column_rows) < 2:
            continue

        try:
            band, source_top, _left_margin = unwrap_column_band(
                source,
                geometry,
                col,
                settings,
                source_width=strip_width,
            )
        except (IndexError, ValueError):
            continue
        if band.height <= 1 or band.width <= 1:
            continue

        gray = np.asarray(ImageOps.grayscale(band), dtype=np.uint8)
        zone_width, visual_runs = _cjk_visual_projection_runs(
            gray,
            0,
            settings,
            1.0,
            relaxed=False,
        )

        # A large Han glyph may contain a real horizontal white slit wider than
        # the projection detector's tiny-hole filler. That is exactly where the
        # ordinary VB separator can retrigger. Recover such a split glyph only
        # when the two ink fragments are separated by a *very* small vertical
        # gap and occupy strongly overlapping X columns. This is intentionally
        # much stricter than line spacing, so two normal adjacent text rows stay
        # separate.
        projection_width = min(
            gray.shape[1],
            max(48, int(zone_width or 0), 100),
        )
        if projection_width > 0:
            projection = gray[:, :projection_width]
            threshold = _left_edge_otsu_threshold(projection)
            dark = projection <= threshold
            active = dark.sum(axis=1) >= max(
                3, round(projection_width * 0.015)
            )
            active_list = active.tolist()
            raw_runs: list[tuple[int, int]] = []
            index = 0
            while index < len(active_list):
                if not active_list[index]:
                    index += 1
                    continue
                end = index + 1
                while end < len(active_list) and active_list[end]:
                    end += 1
                raw_runs.append((index, end))
                index = end

            bridge_gap = max(2, round(character_height * 0.18))
            bridged: list[tuple[int, int]] = []
            for start, end in raw_runs:
                if not bridged:
                    bridged.append((start, end))
                    continue
                prev_start, prev_end = bridged[-1]
                gap = start - prev_end
                should_bridge = False
                if 0 <= gap <= bridge_gap:
                    prev_cols = dark[prev_start:prev_end].any(axis=0)
                    next_cols = dark[start:end].any(axis=0)
                    smaller = min(
                        int(prev_cols.sum()), int(next_cols.sum())
                    )
                    overlap = int((prev_cols & next_cols).sum())
                    overlap_ratio = (
                        overlap / float(smaller) if smaller > 0 else 0.0
                    )
                    should_bridge = overlap_ratio >= 0.65
                if should_bridge:
                    bridged[-1] = (prev_start, end)
                else:
                    bridged.append((start, end))

            minimum_large = max(
                round(character_height * 1.55),
                character_height + 1,
            )
            for start, end in bridged:
                if end - start < minimum_large:
                    continue
                if not any(
                    max(start, existing_start) < min(end, existing_end)
                    for existing_start, existing_end in visual_runs
                ):
                    visual_runs.append((start, end))
            visual_runs.sort()

        if not visual_runs:
            continue

        for run_start, run_end in visual_runs:
            run_start_v = int(source_top + run_start)
            run_end_v = int(source_top + run_end)
            run_height = max(1, run_end_v - run_start_v)
            if run_height < round(character_height * 1.45):
                continue

            # The true entry separator is normally just above the display glyph;
            # the false VB separator is lower, inside the glyph's vertical span.
            # Associate only rows around this one run and require a top boundary
            # before suppressing anything.
            associated: list[tuple[int, tuple[Entry, int, int, int]]] = []
            for row_index, row in column_rows:
                row_v = row[3]
                if (
                    run_start_v - top_margin
                    <= row_v
                    <= run_end_v + lower_margin
                ):
                    associated.append((row_index, row))
            if len(associated) < 2:
                continue
            associated.sort(key=lambda item: item[1][3])

            keeper_index, keeper_row = associated[0]
            keeper_v = keeper_row[3]
            if keeper_v > run_start_v + max(2, round(character_height * 0.25)):
                # No credible top-of-glyph boundary: do not infer an entry from
                # a large dark object or a title/illustration.
                continue

            local_losers = [
                (row_index, row)
                for row_index, row in associated[1:]
                if (
                    row[3] >= run_start_v + internal_floor
                    and row[3] <= run_end_v + lower_margin
                )
            ]
            if not local_losers:
                continue

            for row_index, _row in local_losers:
                suppressed.add(row_index)
            keeper_issue.add(keeper_index)

    output: list[Entry] = []
    for index, (entry, _col, _u, _v) in enumerate(rows):
        if index in suppressed:
            continue
        if index in keeper_issue:
            issue = "ORDINARY_OVERSIZED_CJK_SPLIT_COLLAPSED"
            existing = [
                part for part in str(entry.issue_type or "").split(",") if part
            ]
            if issue not in existing:
                existing.append(issue)
                entry.issue_type = ",".join(existing)
        output.append(entry)

    return sort_entries_reading_order(output, geometry)


def _recover_ordinary_oversized_cjk_missing_markers(
    image: Image.Image,
    entries: list[Entry],
    geometry: Geometry,
    settings: AppSettings,
) -> list[Entry]:
    """Recover a missed oversized CJK entry from independent image evidence.

    This is deliberately narrower than the OCR visual-rescue path: ordinary
    mode has no recognized word to validate, so a new blank marker is added only
    when three geometry cues agree — an oversized left-strip run, a sparse
    right-side layout characteristic of display heads, and a plausible roughly
    square glyph footprint. Existing markers always win.

    The rescue is OCR-independent and therefore also gives combined mode a
    genuinely independent observation when Paddle misses a large Han head.
    """
    if str(getattr(settings, "layout_writing_mode", "horizontal-tb")).startswith("vertical"):
        return list(entries)
    if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
        return list(entries)

    from .paddle_headwords import (
        _cjk_right_context_metrics,
        _cjk_visual_projection_runs,
        _is_chinese_ocr,
        refine_separator_y_adaptive,
        unwrap_column_band,
    )

    profile_id = str(getattr(settings, "dictionary_profile_id", "") or "").lower()
    if not (_is_chinese_ocr(settings) or "cjk" in profile_id):
        return list(entries)

    source = normalize_page_rgb(image)
    character_height = max(
        2, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    row_padding = max(0, int(round(float(getattr(settings, "row_padding", 0) or 0))))
    strip_width = max(
        100,
        round(character_height * 3.2),
        int(getattr(settings, "paddle_band_left_margin", 0) or 0) + 72,
    )
    # Recovery needs both the left projection *and* independent right-context
    # evidence.  Keep a wider analysis band than the projection zone itself.
    analysis_width = max(strip_width, round(character_height * 6.0), 180)
    duplicate_tolerance = max(5, round(character_height * 0.65))

    existing_by_column: dict[int, list[int]] = {
        col: [] for col in range(len(geometry.column_starts))
    }
    for entry in entries:
        _u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        col = column_index_for_click(int(entry.x), geometry, int(entry.y))
        existing_by_column.setdefault(int(col), []).append(int(v))

    recovered = list(entries)
    for col in range(len(geometry.column_starts)):
        try:
            band, source_top, _left_margin = unwrap_column_band(
                source,
                geometry,
                col,
                settings,
                source_width=analysis_width,
            )
        except (IndexError, ValueError):
            continue
        if band.height <= 1 or band.width <= 1:
            continue

        gray = np.asarray(ImageOps.grayscale(band), dtype=np.uint8)
        zone_width, visual_runs = _cjk_visual_projection_runs(
            gray, 0, settings, 1.0, relaxed=False,
        )
        if not visual_runs or zone_width <= 0:
            continue

        for run_index, (run_start, run_end) in enumerate(visual_runs):
            run_height = max(1, int(run_end) - int(run_start))
            if run_height < round(character_height * 1.50):
                continue

            context = _cjk_right_context_metrics(
                gray, (run_start, run_end), zone_width, settings, header_cutoff=0,
            )
            if not (
                context.get("available")
                and context.get("sparse")
                and int(context.get("sparse_votes", 0) or 0) >= 2
                and float(context.get("baseline_ink_density", 0.0) or 0.0) >= 0.01
            ):
                continue

            # Large Han display glyphs are approximately square. Reject long
            # rules, illustrations and narrow vertical artifacts that can also
            # create a tall left-strip projection.
            projection_width = min(gray.shape[1], max(1, int(zone_width)))
            roi = gray[max(0, run_start):min(gray.shape[0], run_end), :projection_width]
            if roi.size == 0:
                continue
            threshold = _left_edge_otsu_threshold(roi)
            dark = roi <= threshold
            active_columns = np.where(dark.any(axis=0))[0]
            if active_columns.size == 0:
                continue
            glyph_width = max(1, int(active_columns[-1] - active_columns[0] + 1))
            aspect = float(run_height) / float(glyph_width)
            if not 0.55 <= aspect <= 2.20:
                continue

            previous_end = (
                int(visual_runs[run_index - 1][1])
                if run_index > 0 else 0
            )
            preceding_gap = max(0, int(run_start) - previous_end)
            coarse_band_y = max(0, int(run_start) - row_padding)
            refined_band_y, _details = refine_separator_y_adaptive(
                gray,
                coarse_band_y,
                max(2, character_height),
                settings,
                pixel_scale=1.0,
                lower_bound=0,
                content_top=int(run_start),
                preceding_gap_hint=preceding_gap,
            )
            candidate_v = int(source_top + refined_band_y)
            run_specific_tolerance = max(
                duplicate_tolerance, round(run_height * 0.30)
            )
            if any(
                abs(candidate_v - existing_v) <= run_specific_tolerance
                for existing_v in existing_by_column.get(col, [])
            ):
                continue

            marker_x, _direction = _ordinary_source_column_edge(
                geometry, col, candidate_v
            )
            recovered.append(Entry(
                word="",
                x=int(marker_x),
                y=int(candidate_v),
                ocr_source="ordinary_visual",
                issue_type="ORDINARY_CJK_VISUAL_RESCUE",
                ocr_visual_run_height=float(run_height),
                ocr_line_height_reference=float(character_height),
                ocr_single_cjk=True,
                ocr_oversized_cjk=True,
            ))
            existing_by_column.setdefault(col, []).append(candidate_v)

    return sort_entries_reading_order(recovered, geometry)


def _is_single_cjk_headword(word: str) -> bool:
    """Historical single-Han predicate. Logic owned by ordinary separator policy."""
    return _separator_policy.is_single_cjk_headword(word)

def _separator_whitespace_score(
    image: Image.Image,
    entry: Entry,
    geometry: Geometry,
    settings: AppSettings,
    gray: np.ndarray | None = None,
) -> float | None:
    """Historical grayscale boundary score; call-time dependencies preserved."""
    return _separator_policy.separator_whitespace_score(
        image, entry, geometry, settings, gray,
        np_module=np, image_ops=ImageOps,
        normalize_rgb_fn=normalize_page_rgb,
        column_fn=column_index_for_click,
        source_edge_fn=_ordinary_source_column_edge,
        otsu_fn=_left_edge_otsu_threshold,
    )

def _prefer_ocr_separator_position(
    image: Image.Image | None,
    ordinary: Entry,
    ocr: Entry,
    geometry: Geometry,
    settings: AppSettings,
    gray: np.ndarray | None = None,
) -> tuple[bool, float | None, float | None]:
    """Historical OCR-vs-ordinary marker decision with current callbacks."""
    return _separator_policy.prefer_ocr_separator_position(
        image, ordinary, ocr, geometry, settings, gray,
        score_fn=_separator_whitespace_score,
        single_cjk_fn=_is_single_cjk_headword,
    )

def _entry_with_fused_metadata(
    position: Entry,
    semantic: Entry,
    *,
    use_semantic_position: bool = False,
) -> Entry:
    """Historical fusion Entry constructor; keep the runtime class identity."""
    return _fusion_entry_mapping.entry_with_fused_metadata(
        position, semantic,
        use_semantic_position=use_semantic_position, entry_cls=Entry,
    )


def _review_candidate_to_entry(candidate: dict) -> Entry | None:
    """Historical validated review-to-Entry conversion."""
    return _fusion_entry_mapping.review_candidate_to_entry(
        candidate, entry_cls=Entry,
    )

_COMBINED_HARD_NEGATIVE_REASONS = {
    "continuation_fragment",
    "internal_article_symbol",
    "internal_relation_label",
    "internal_locution",
}


def _review_candidate_has_strong_positive_visual(candidate: dict) -> bool:
    for engine in ("paddle", "tesseract", "lens"):
        side = candidate.get(engine, {}) or {}
        if not isinstance(side, dict):
            continue
        features = side.get("features", {}) or {}
        if not isinstance(features, dict):
            continue
        if any(bool(features.get(key)) for key in (
            "visual_entry_marker",
            "configured_marker_evidence",
            "numbered_prefix_evidence",
            "cjk_single_strong_visual",
            "cjk_visual_projection_rescue",
            "cjk_visual_projection_confirmed",
            "strong_visual_fallback",
        )):
            return True
    return False


def _review_candidate_hard_negative_level(candidate: dict) -> str:
    """Return '', 'single', or 'dual' for specific negative OCR evidence.

    A dual verdict means both local OCR engines independently agree on the same
    internal/continuation class. A single verdict is allowed only for an
    exceptionally confident engine with a matching semantic feature.
    """
    if candidate.get("selected") or candidate.get("manual_override"):
        return ""
    if str(candidate.get("position_variant", "refined")) != "refined":
        return ""
    if _review_candidate_has_strong_positive_visual(candidate):
        return ""

    votes = 0
    strong_single = False
    for engine in ("paddle", "tesseract"):
        side = candidate.get(engine, {}) or {}
        if not isinstance(side, dict) or side.get("y") is None:
            continue
        reason = str(side.get("reason") or "")
        if reason not in _COMBINED_HARD_NEGATIVE_REASONS:
            continue
        try:
            confidence = float(side.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.84:
            continue
        votes += 1
        features = side.get("features", {}) or {}
        if not isinstance(features, dict):
            features = {}
        matching_feature = bool(
            (reason == "continuation_fragment" and features.get("looks_like_continuation"))
            or (reason == "internal_article_symbol" and features.get("internal_article_symbol"))
            or (reason == "internal_relation_label" and features.get("internal_relation_label"))
            or (reason == "internal_locution" and features.get("internal_locution"))
        )
        if confidence >= 0.94 and matching_feature:
            strong_single = True
    if votes >= 2:
        return "dual"
    if strong_single:
        return "single"
    return ""


def _review_candidate_hard_negative_consensus(candidate: dict) -> bool:
    return bool(_review_candidate_hard_negative_level(candidate))

def _latent_review_rows(
    review_candidates: list[dict] | None,
    geometry: Geometry,
) -> list[tuple[dict, int, int]]:
    rows: list[tuple[dict, int, int]] = []
    for candidate in review_candidates or []:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("selected") or candidate.get("manual_override"):
            continue
        if str(candidate.get("position_variant", "refined")) != "refined":
            continue
        try:
            x = int(candidate.get("source_x"))
            y = int(candidate.get("source_y"))
        except (TypeError, ValueError):
            continue
        if y <= 0:
            continue
        _u, v = geometry.source_to_canonical(x, y)
        col = int(candidate.get("column", column_index_for_click(x, geometry, y)))
        rows.append((candidate, col, int(v)))
    return rows


def _fuse_detection_entries(
    ordinary_entries: list[Entry],
    ocr_entries: list[Entry],
    geometry: Geometry,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
    review_candidates: list[dict] | None = None,
    image: Image.Image | None = None,
) -> list[Entry]:
    """Fuse the two independent detectors at the entry-event level.

    Ordinary drawing is treated as a strong geometric observation, while OCR is
    the semantic observation and an independent rescue path. Evidence-fusion v3
    additionally consults *rejected* OCR review candidates: high-confidence hard
    semantic negatives may veto an unmatched ordinary false positive, while soft
    rejected candidates may lend their recognized lemma to a geometrically valid
    ordinary marker. Nearby accepted observations in the same visual column are
    paired one-to-one;
    unmatched observations from either detector survive.  A final strict Y
    collapse guarantees exactly one marker for one physical entry boundary.

    For ordinary/bracketed entries, the restored VB separator is retained when
    both detectors agree.  A one-Han OCR entry keeps its OCR position because the
    OCR path has a dedicated oversized-CJK adaptive separator refiner that is more
    specific than the ordinary normal-line geometry.
    """
    if not ordinary_entries:
        return sort_entries_reading_order(list(ocr_entries), geometry, page_sections)
    if not ocr_entries and not review_candidates:
        return sort_entries_reading_order(list(ordinary_entries), geometry, page_sections)

    line_height = max(2, int(round(float(getattr(settings, "character_height", 26) or 26))))
    try:
        alignment_ratio = float(getattr(settings, "paddle_alignment_y_tolerance_ratio", 0.45) or 0.45)
    except (TypeError, ValueError):
        alignment_ratio = 0.45
    alignment_ratio = max(0.25, min(0.55, alignment_ratio))
    base_tolerance = max(4, round(line_height * alignment_ratio))
    strict_dedup = max(2, round(line_height * 0.22))
    latent_rows = _latent_review_rows(review_candidates, geometry)

    def axis(entry: Entry) -> tuple[int, int, int]:
        u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        col = column_index_for_click(int(entry.x), geometry, int(entry.y))
        return int(col), int(u), int(v)

    ordinary_rows = [(entry, *axis(entry)) for entry in ordinary_entries]
    ocr_rows = [(entry, *axis(entry)) for entry in ocr_entries]
    ordinary_rows.sort(key=lambda row: (row[1], row[3], row[2]))
    ocr_rows.sort(key=lambda row: (row[1], row[3], row[2]))

    # Max-cardinality monotone pairing avoids stealing the only possible
    # OCR partner from a neighboring real headword on dense dictionary pages.
    pair_edges: list[tuple[int, int, int]] = []
    for ordinary_index, (_ordinary, ordinary_col, _ordinary_u, ordinary_v) in enumerate(ordinary_rows):
        for ocr_index, (ocr, ocr_col, _ocr_u, ocr_v) in enumerate(ocr_rows):
            if ocr_col != ordinary_col:
                continue
            tolerance = base_tolerance
            if _is_single_cjk_headword(ocr.word):
                tolerance = max(tolerance, round(line_height * 0.55))
            delta = abs(int(ocr_v) - int(ordinary_v))
            if delta <= tolerance:
                pair_edges.append((delta, ordinary_index, ocr_index))
    from .quality.ordered_marker_matching import match_ordered_markers

    matched_ocr = match_ordered_markers(
        len(ordinary_rows), len(ocr_rows), pair_edges,
    )
    ordinary_to_ocr = dict(matched_ocr)
    used_ocr = {ocr_index for _, ocr_index in matched_ocr}

    # Rejected OCR review candidates are also observations and must be paired
    # one-to-one. Without global assignment, one rejected row could enrich or
    # veto two adjacent ordinary boundaries on dense dictionary pages.
    latent_edges: list[tuple[int, int, int]] = []
    for ordinary_index, (_ordinary, ordinary_col, _ordinary_u, ordinary_v) in enumerate(ordinary_rows):
        if ordinary_index in ordinary_to_ocr:
            continue
        for latent_index, (_candidate, latent_col, latent_v) in enumerate(latent_rows):
            if latent_col != ordinary_col:
                continue
            delta = abs(int(latent_v) - int(ordinary_v))
            if delta <= base_tolerance:
                latent_edges.append((delta, ordinary_index, latent_index))
    # Rejected OCR rows are collected in cache insertion order: sort them by
    # column and canonical reading V before matching, then remap indices.
    latent_order = sorted(range(len(latent_rows)), key=lambda i: (
        latent_rows[i][1], latent_rows[i][2], i,
    ))
    latent_rank = {old: position for position, old in enumerate(latent_order)}
    latent_pairs = match_ordered_markers(
        len(ordinary_rows), len(latent_rows),
        [(delta, ordinary_index, latent_rank[latent_index])
         for delta, ordinary_index, latent_index in latent_edges],
    )
    ordinary_to_latent = {
        ordinary_index: latent_order[rank]
        for ordinary_index, rank in latent_pairs
    }
    used_latent = set(ordinary_to_latent.values())

    # Oversized single-Han heads are taller than one ordinary text row. The
    # ordinary VB detector can therefore fire twice inside the same physical
    # glyph: once at the real entry boundary and once again on a lower ink run.
    # A one-to-one fusion match removes only one of those rows, so the second
    # ordinary-only row used to survive as a false "rescue".
    #
    # Do not solve this by widening global Y de-duplication. Instead, use OCR's
    # own large-glyph geometry to define a *forward occupancy zone* for confirmed
    # oversized single-CJK heads. Only unmatched ordinary rows inside that zone
    # are suppressed. A following OCR headword creates a safety boundary so one
    # large glyph can never swallow the next real entry.
    suppressed_ordinary: set[int] = set()
    suppressed_by_ocr: dict[int, int] = {}

    def oversized_occupancy_span(entry: Entry) -> int:
        normal = float(entry.ocr_line_height_reference or line_height)
        if normal <= 0:
            normal = float(line_height)
        extent_candidates = [
            float(entry.ocr_box_height or 0.0),
            float(entry.ocr_visual_run_height or 0.0),
        ]
        if entry.ocr_leading_height_ratio:
            extent_candidates.append(float(entry.ocr_leading_height_ratio) * normal)
        extent = max(extent_candidates or [0.0])
        oversized = bool(
            entry.ocr_oversized_cjk
            or (
                (entry.ocr_single_cjk or _is_single_cjk_headword(entry.word))
                and extent >= normal * 1.45
            )
        )
        if not oversized:
            return 0
        # Cover the physical glyph plus a small separator margin, but cap the
        # zone so a malformed OCR box cannot consume several following entries.
        return max(
            round(normal * 1.10),
            min(round(normal * 2.80), round(extent + normal * 0.20)),
        )

    for ocr_index, (ocr, ocr_col, _ocr_u, ocr_v) in enumerate(ocr_rows):
        span = oversized_occupancy_span(ocr)
        if span <= 0:
            continue
        upper_v = int(ocr_v) + int(span)
        # Protect the next OCR-confirmed entry in the same column. This is more
        # permissive than a midpoint for the current big glyph but leaves a
        # normal alignment-width guard before the next real headword.
        for next_index in range(ocr_index + 1, len(ocr_rows)):
            _next, next_col, _next_u, next_v = ocr_rows[next_index]
            if next_col != ocr_col:
                if next_col > ocr_col:
                    break
                continue
            next_guard = max(base_tolerance, round(line_height * 0.55))
            upper_v = min(upper_v, int(next_v) - next_guard)
            break
        if upper_v <= int(ocr_v) + strict_dedup:
            continue

        count = 0
        for ordinary_index, (_ordinary, ordinary_col, _ordinary_u, ordinary_v) in enumerate(ordinary_rows):
            if ordinary_index in ordinary_to_ocr or ordinary_col != ocr_col:
                continue
            if int(ocr_v) + strict_dedup < int(ordinary_v) <= upper_v:
                suppressed_ordinary.add(ordinary_index)
                count += 1
        if count:
            suppressed_by_ocr[ocr_index] = count

    separator_gray = (
        np.asarray(ImageOps.grayscale(normalize_page_rgb(image)), dtype=np.uint8)
        if image is not None and ordinary_to_ocr else None
    )
    fused: list[Entry] = []
    for ordinary_index, (ordinary, _ordinary_col, _ordinary_u, _ordinary_v) in enumerate(ordinary_rows):
        ocr_index = ordinary_to_ocr.get(ordinary_index)
        if ocr_index is None:
            if ordinary_index in suppressed_ordinary:
                continue

            # Candidate-level fusion: a rejected OCR row can still carry useful
            # semantics, or in the opposite direction can provide a highly
            # specific negative explanation for an ordinary false positive.
            latent_index = ordinary_to_latent.get(ordinary_index)
            nearest_latent = (
                latent_rows[latent_index][0]
                if latent_index is not None else None
            )

            hard_negative_level = (
                _review_candidate_hard_negative_level(nearest_latent)
                if nearest_latent is not None else ""
            )
            if hard_negative_level:
                # A pristine full-white VB separator is itself strong,
                # independent image evidence. One OCR engine is not enough to
                # erase it; require dual semantic agreement. A weaker
                # brightness-fallback ordinary marker may be vetoed by one
                # exceptionally confident, feature-backed semantic negative.
                ordinary_strength = float(
                    ordinary.confidence if ordinary.confidence is not None else 0.0
                )
                if hard_negative_level == "dual" or ordinary_strength < 0.96:
                    continue

            if nearest_latent is not None:
                latent_entry = _review_candidate_to_entry(nearest_latent)
                if (
                    latent_entry is not None
                    and latent_entry.word
                    and (latent_entry.confidence or 0.0) >= 0.65
                    and not _review_candidate_hard_negative_consensus(nearest_latent)
                ):
                    ordinary = _entry_with_fused_metadata(
                        ordinary, latent_entry, use_semantic_position=False,
                    )
                    issues = [
                        part for part in str(ordinary.issue_type or "").split(",")
                        if part
                    ]
                    if "COMBINED_LATENT_OCR_METADATA" not in issues:
                        issues.append("COMBINED_LATENT_OCR_METADATA")
                        ordinary.issue_type = ",".join(issues)
            fused.append(ordinary)
            continue
        ocr = ocr_rows[ocr_index][0]
        use_semantic_position, ordinary_ws, ocr_ws = _prefer_ocr_separator_position(
            image, ordinary, ocr, geometry, settings, separator_gray,
        )
        merged_entry = _entry_with_fused_metadata(
            ordinary,
            ocr,
            use_semantic_position=use_semantic_position,
        )
        if (
            ordinary_ws is not None
            and ocr_ws is not None
            and abs(float(ordinary_ws) - float(ocr_ws)) >= 0.055
        ):
            issue = "FUSION_WHITESPACE_POSITION_ARBITRATION"
            existing = [
                part for part in str(merged_entry.issue_type or "").split(",") if part
            ]
            if issue not in existing:
                existing.append(issue)
                merged_entry.issue_type = ",".join(existing)
        if suppressed_by_ocr.get(ocr_index):
            issue = "FUSION_OVERSIZED_CJK_ORDINARY_SUPPRESSED"
            existing = [part for part in str(merged_entry.issue_type or "").split(",") if part]
            if issue not in existing:
                existing.append(issue)
                merged_entry.issue_type = ",".join(existing)
        fused.append(merged_entry)

    for ocr_index, (ocr, _col, _u, _v) in enumerate(ocr_rows):
        if ocr_index not in used_ocr:
            if suppressed_by_ocr.get(ocr_index):
                issue = "FUSION_OVERSIZED_CJK_ORDINARY_SUPPRESSED"
                existing = [part for part in str(ocr.issue_type or "").split(",") if part]
                if issue not in existing:
                    existing.append(issue)
                    ocr.issue_type = ",".join(existing)
            fused.append(ocr)

    # Second-stage de-duplication is intentionally tighter than cross-detector
    # pairing.  It catches residual same-boundary duplicates without collapsing
    # genuinely adjacent dictionary entries.
    ranked: list[tuple[Entry, int, int, int]] = []
    for entry in fused:
        col, u, v = axis(entry)
        ranked.append((entry, col, u, v))
    ranked.sort(key=lambda row: (row[1], row[3], row[2]))

    output: list[tuple[Entry, int, int, int]] = []
    for row in ranked:
        if output and row[1] == output[-1][1] and abs(row[3] - output[-1][3]) <= strict_dedup:
            current = output[-1][0]
            incoming = row[0]

            def priority(item: Entry) -> tuple[int, int, float]:
                source = str(item.ocr_source or "")
                return (
                    1 if item.manually_selected else 0,
                    3 if source.startswith("combined:") else (2 if item.word or item.candidate_id or item.final_engine else 1),
                    float(item.confidence if item.confidence is not None else -1.0),
                )

            if priority(incoming) > priority(current):
                output[-1] = row
            continue
        output.append(row)

    return sort_entries_reading_order(
        [row[0] for row in output], geometry, page_sections
    )

def detect_entries(
    image: Image.Image,
    settings: AppSettings,
    paddle_cache_path: Path | None = None,
    force_paddle_refresh: bool = False,
    paddle_filter_rules_path: Path | None = None,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    left_edge_detector: Any | None = None,
) -> tuple[list[Entry], Geometry]:
    """Detect markers with the active Project Profile page template applied."""
    detect_left_edge = left_edge_detector or _detect_entries_left_edge
    source = normalize_page_rgb(image)
    effective = effective_page_settings(settings, source.size, profile_page_index)
    analysis_source = page_template_analysis_image(source, effective, profile_page_index)
    method = effective.detection_method.strip().lower()
    if method in {"paddleocr", "combined"}:
        geometry = derive_geometry(analysis_source, effective)
        from .paddle_headwords import detect_paddle_headwords
        ocr_entries = detect_paddle_headwords(
            analysis_source, geometry, effective,
            cache_path=paddle_cache_path,
            force_refresh=force_paddle_refresh,
            filter_rules_path=paddle_filter_rules_path,
            page_sections=page_sections,
        )
        if method == "combined":
            # Run the restored ordinary detector unchanged, including its
            # page-specific auto-layout and VB separator chain.  The OCR path
            # likewise keeps its own existing geometry/parser/refinement logic;
            # only their final entry observations are fused.
            ordinary_effective, _applied_layout = ordinary_page_layout_settings(
                analysis_source, effective
            )
            ordinary_entries, _ordinary_geometry = detect_left_edge(
                analysis_source, ordinary_effective, page_sections=page_sections
            )
            review_candidates: list[dict] = []
            if paddle_cache_path is not None and paddle_cache_path.exists():
                try:
                    cached_payload = json.loads(
                        paddle_cache_path.read_text(encoding="utf-8")
                    )
                    if isinstance(cached_payload, dict):
                        review_candidates = [
                            item for item in list(
                                cached_payload.get("review_candidates") or []
                            )
                            if isinstance(item, dict)
                        ]
                except (OSError, ValueError, TypeError):
                    review_candidates = []
            entries = _fuse_detection_entries(
                ordinary_entries, ocr_entries, geometry, effective, page_sections,
                review_candidates=review_candidates,
                image=analysis_source,
            )
        else:
            entries = ocr_entries
    else:
        ordinary_effective, _applied_layout = ordinary_page_layout_settings(
            analysis_source, effective
        )
        entries, geometry = detect_left_edge(
            analysis_source, ordinary_effective, page_sections=page_sections
        )

    entries = [
        entry for entry in entries
        if entry_allowed_by_page_template(
            entry.x, entry.y, source.size, effective, profile_page_index,
        )
        and (
            not page_sections
            or v_is_inside_sections(
                geometry.source_to_canonical(entry.x, entry.y)[1],
                page_sections, geometry.top, geometry.bottom,
            )
        )
    ]
    return sort_entries_reading_order(entries, geometry, page_sections), geometry


def refine_existing_entries(
    image: Image.Image,
    entries: list[Entry],
    settings: AppSettings,
    *,
    profile_page_index: int = 0,
    source_image_path: Path | None = None,
    fixed_half_gutter: bool = False,
) -> tuple[list[Entry], dict[str, int]]:
    """Refine saved Y while preserving entry identity and text."""
    if source_image_path is None:
        source, effective, analysis_source, geometry = _page_geometry_context(
            image, settings, profile_page_index,
        )
        return _refine_existing_entries_with_geometry(
            entries, effective, analysis_source, geometry,
        )

    from .refinement.analysis import prepare_refinement_analysis

    prep_kwargs = {"fixed_half_gutter": True} if fixed_half_gutter else {}
    source, effective, analysis_source = prepare_refinement_analysis(
        image, settings, profile_page_index, source_image_path=source_image_path,
        **prep_kwargs,
    )
    try:
        geometry = derive_geometry(analysis_source, effective)
        return _refine_existing_entries_with_geometry(
            entries, effective, analysis_source, geometry,
            align_to_ink_top=True, fixed_half_gutter=fixed_half_gutter,
        )
    finally:
        analysis_source.close()
        source.close()


def _refine_existing_entries_with_geometry(
    entries: list[Entry],
    effective: AppSettings,
    analysis_source: Image.Image,
    geometry: Geometry,
    *,
    align_to_ink_top: bool = False,
    fixed_half_gutter: bool = False,
) -> tuple[list[Entry], dict[str, int]]:
    """Refine Y without reclassifying Layout rows."""
    canonical = geometry.transform.canonical_image_for_analysis(analysis_source)
    gray = np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8)

    if align_to_ink_top:
        from .refinement.top_edge import refine_existing_marker_to_ink_top
    else:
        from .paddle_headwords import refine_separator_y

    line_height = max(
        2,
        _source_px(effective.character_height),
    )
    source_pixel_scale = 1.0
    search_ratio = max(0.05, min(0.80, float(effective.paddle_separator_search_ratio)))
    max_delta = (
        max(0, round(line_height * max(0.0, min(1.5, float(effective.separator_y_max_shift_ratio)))))
        if align_to_ink_top
        else max(2, round(line_height * search_ratio))
    )

    refined_entries: list[Entry] = []
    moved = 0
    limited = 0
    unverified = 0
    for entry in entries:
        canonical_u, canonical_v = geometry.source_to_canonical(entry.x, entry.y)
        col = column_index(entry.x, geometry, entry.y)
        column_x = max(0, round(geometry.x_at(col, canonical_v)))
        column_right = min(
            gray.shape[1],
            column_x + max(10, min(int(geometry.column_widths[col]), int(effective.column_width))),
        )
        if align_to_ink_top:
            from .refinement.fixed_band import fixed_half_gutter_band
            column_x, column_right = fixed_half_gutter_band(
                geometry, col, int(canonical_v), gray.shape[1],
                int(effective.column_width), int(effective.gutter),
            )
        new_v = int(canonical_v)
        if column_right > column_x:
            if align_to_ink_top:
                candidate_v, _details = refine_existing_marker_to_ink_top(
                    gray, int(canonical_v), line_height, effective,
                    anchor_x=int(canonical_u),
                    column_left=column_x, column_right=column_right,
                    lower_bound=max(0, int(geometry.top)),
                    upper_bound=int(geometry.bottom),
                )
                if not str(_details.get("reason", "")).startswith("verified_whole_column_"):
                    unverified += 1
            else:
                candidate_v, _details = refine_separator_y(
                    gray[:, column_x:column_right],
                    int(canonical_v),
                    line_height,
                    effective,
                    pixel_scale=source_pixel_scale,
                    lower_bound=max(0, int(geometry.top)),
                )
            delta = int(candidate_v) - int(canonical_v)
            if abs(delta) > max_delta:
                limited += 1
                delta = max(-max_delta, min(max_delta, delta))
            new_v = int(canonical_v) + delta

        if new_v != int(canonical_v):
            moved += 1
        new_x, new_y = geometry.canonical_to_source(int(canonical_u), int(new_v))
        refined_entries.append(replace(entry, x=int(new_x), y=int(new_y)))

    return refined_entries, {
        "total": len(entries),
        "moved": moved,
        "limited": limited,
        "max_delta": int(max_delta),
        "unverified": unverified,
    }


def detect_entries_job(
    image_path: str,
    settings: AppSettings,
    pages: tuple[str, str, str],
    profile_page_index: int = 0,
) -> int:
    """Spawn-safe ordinary-line detection job that commits one PDIC page."""
    page = Path(image_path)
    with Image.open(page) as opened:
        image = normalize_page_rgb(opened)
    settings.detection_method = "left_edge"
    entries, _geometry = detect_entries(
        image, settings, profile_page_index=profile_page_index,
        page_sections=read_page_sections(page),
    )
    write_pdic(pdic_path_for_image(page), entries, image.width, pages)
    return len(entries)




def run_tesseract(image: Image.Image, language: str, executable: str = "tesseract", psm: int = 7) -> str:
    resolved = find_tesseract(executable)
    if not resolved:
        raise RuntimeError(
            "未找到 Tesseract OCR。请在环境中心安装/选择 Tesseract 可执行程序，并检查当前项目所需语言包。"
        )
    payload = BytesIO()
    normalize_page_rgb(image).save(payload, format="PNG")
    command = [str(resolved), "stdin", "stdout", "-l", language, "--psm", str(psm)]
    try:
        result = subprocess.run(
            command, input=payload.getvalue(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Tesseract OCR 超时（120 秒）；已终止本次识别。") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Tesseract OCR 失败：{detail}")
    return result.stdout.decode("utf-8", errors="replace")


def column_index(x: int, geometry: Geometry, y: int = 0) -> int:
    """Classify a saved/detected X using the same visual intervals as clicks.

    Automatically detected column starts are robust percentiles, so an actual
    PDIC marker may legitimately sit a few pixels to the left of its estimated
    start.  The historical floor-by-start rule then assigned that marker to the
    preceding column even though it was much closer to the next column.  Use
    the interval/gutter-distance classifier everywhere so sorting, rendering,
    cropping, and export all agree on the marker's visual column.
    """
    return column_index_for_click(x, geometry, y)


def column_index_for_click(x: int, geometry: Geometry, y: int = 0) -> int:
    """Historical public/processing column classifier."""
    return _reading_order.column_index_for_click(x, geometry, y)


def entry_reading_order_key(
    entry: Entry,
    geometry: Geometry,
    page_sections: list[PageSection] | tuple[PageSection, ...] | None = None,
) -> tuple[int, int, int, int]:
    """Preserve SECTION/column/V/U ordering and live historical patch points."""
    return _reading_order.entry_reading_order_key(
        entry, geometry, page_sections,
        column_fn=column_index_for_click, section_fn=section_index_for_v,
    )


def sort_entries_reading_order(
    entries: list[Entry],
    geometry: Geometry,
    page_sections: list[PageSection] | tuple[PageSection, ...] | None = None,
) -> list[Entry]:
    return _reading_order.sort_entries_reading_order(
        entries, geometry, page_sections,
        column_fn=column_index_for_click, section_fn=section_index_for_v,
        normalize_fn=normalize_page_sections,
    )


def sort_entries_column_y(
    entries: list[Entry],
    geometry: Geometry,
    page_sections: list[PageSection] | tuple[PageSection, ...] | None = None,
) -> list[Entry]:
    return _reading_order.sort_entries_column_y(
        entries, geometry, page_sections,
        column_fn=column_index_for_click, section_fn=section_index_for_v,
        normalize_fn=normalize_page_sections,
    )

def clamp_box(box: tuple[int, int, int, int], image: Image.Image) -> tuple[int, int, int, int]:
    """Keep the historical half-open PIL box clamp."""
    return _line_box_geometry.clamp_box(box, image)


def line_box(entry: Entry, geometry: Geometry, image: Image.Image, settings: AppSettings) -> tuple[int, int, int, int]:
    """Preserve live column, source-pixel and box-clamp facade hooks."""
    return _line_box_geometry.line_box(
        entry, geometry, image, settings,
        column_fn=column_index, source_px_fn=_source_px, clamp_fn=clamp_box,
    )

def _ordinary_marker_local_crop(
    canonical: Image.Image,
    entry: Entry,
    geometry: Geometry,
    settings: AppSettings,
    *,
    row_metrics=None,
    source_image: Image.Image | None = None,
) -> tuple[Image.Image, bool]:
    """Historical marker OCR crop; leave source pixel direction unchanged."""
    return _ordinary_marker_crop.ordinary_marker_local_crop(
        canonical, entry, geometry, settings,
        row_metrics=row_metrics, source_image=source_image,
        normalize_rgb_fn=normalize_page_rgb,
    )

def ocr_existing_entry_words_from_markers(
    image: Image.Image,
    entries: list[Entry],
    settings: AppSettings,
    replace_rules: list[tuple[str, str, str]],
    *,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    profile_path: Path | None = None,
    only_blank: bool = True,
) -> tuple[list[Entry], dict[str, int]]:
    """Fill existing markers through the shared multi-engine OCR channel.

    Marker coordinates/count remain immutable. Crop geometry comes from
    canonical Entry classification plus physical row metrics, while one
    OCR channel session is reused for every eligible marker on the page.
    """
    _source, effective, analysis_source, geometry = _page_geometry_context(
        image, settings, profile_page_index,
    )
    canonical = geometry.transform.canonical_image_for_analysis(analysis_source)
    ordered = sort_entries_reading_order(entries, geometry, page_sections)

    from .profile.dictionary import effective_project_profile_id, load_dictionary_profile
    from .ocr.entry_crop import resolve_entry_ocr_row_metrics
    from .ocr_channel import OcrChannelSession, OcrTextChoice, choose_ocr_text
    from .paddle_headwords import parse_headword_text
    from .ordinary.marker_ocr_text import bracketed_ocr_lemma

    row_metrics = resolve_entry_ocr_row_metrics(
        image,
        effective,
        page_index=profile_page_index,
    )
    profile = load_dictionary_profile(
        profile_path,
        preset=effective_project_profile_id(effective, profile_path),
        language=effective.ocr_language,
    )
    stats = {
        "total": len(ordered),
        "filled": 0,
        "large": 0,
        "regular": 0,
        "failed": 0,
        "skipped_existing": 0,
        "skipped_manual": 0,
    }
    targets = [
        entry for entry in ordered
        if not bool(entry.manually_selected)
        and not (only_blank and str(entry.word or "").strip())
    ]
    # Preserve the established blank-only stats contract: populated manual
    # entries are also reported as pre-existing words in that legacy mode.
    stats["skipped_existing"] = sum(
        1 for entry in ordered if only_blank and str(entry.word or "").strip()
    )
    stats["skipped_manual"] = sum(
        1 for entry in ordered
        if bool(entry.manually_selected)
        and not (only_blank and str(entry.word or "").strip())
    )
    if not targets:
        return ordered, stats

    channel = OcrChannelSession(effective)
    # This path fills already-drawn markers, not OCR-line detection. Only
    # CJK bracketed dictionary profiles authorize the optional one-sided
    # 【/】 text cleanup; the user replacement-rule toggle is independent.
    bracket_profile = bool(
        getattr(effective, "profile_cjk_allow_bracketed_headword", False)
        and profile.uses_parser("cjk_bracketed")
    )

    def parsed_or_raw(raw: str) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        bracketed = bracketed_ocr_lemma(text, enabled=bracket_profile)
        if bracketed is not None:
            return bracketed
        parsed = parse_headword_text(text, effective, profile=profile)
        if parsed is not None and str(parsed.normalized or "").strip():
            return str(parsed.normalized).strip()
        first_line = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            "",
        )
        return first_line[:64].strip()

    def resolve_candidate(
        candidate,
        *,
        is_large: bool,
        crop_width: int,
    ) -> OcrTextChoice | None:
        if not candidate.ok:
            return None
        word = ""
        confidence = candidate.confidence

        if candidate.engine == "paddle" and candidate.records:
            from .paddle_headwords import (
                _single_cjk_from_local_records,
                group_ocr_records,
            )

            records = list(candidate.records)
            if is_large:
                word, confidence_value, _source_text = _single_cjk_from_local_records(
                    records,
                    effective,
                    profile,
                    max_left_x=max(
                        16,
                        round(max(1, int(crop_width)) * 0.75),
                    ),
                )
                if word:
                    confidence = float(confidence_value)
            else:
                lines = group_ocr_records(
                    records,
                    float(
                        getattr(
                            effective,
                            "paddle_line_merge_y_ratio",
                            0.55,
                        )
                        or 0.55
                    ),
                )
                for line in sorted(
                    lines,
                    key=lambda value: (
                        int(value.box[0]),
                        int(value.box[1]),
                        -float(value.confidence),
                    ),
                ):
                    word = parsed_or_raw(str(line.text or ""))
                    if word:
                        confidence = float(line.confidence)
                        break

        if not word:
            word = parsed_or_raw(candidate.text)
        if not word:
            return None
        return OcrTextChoice(
            engine=candidate.engine,
            text=str(word).strip(),
            confidence=confidence,
        )

    for entry in targets:
        original_x, original_y = int(entry.x), int(entry.y)
        crop, is_large = _ordinary_marker_local_crop(
            canonical,
            entry,
            geometry,
            effective,
            row_metrics=row_metrics,
            source_image=_source,
        )
        stats["large" if is_large else "regular"] += 1

        psm = (
            5
            if str(
                getattr(effective, "layout_writing_mode", "")
            ).startswith("vertical")
            else 7
        )
        result = channel.recognize_crop(crop, tesseract_psm=psm)
        resolved: list[OcrTextChoice] = []
        for candidate in result.candidates:
            choice = resolve_candidate(
                candidate,
                is_large=is_large,
                crop_width=int(crop.width),
            )
            if choice is not None:
                resolved.append(choice)

        selected, _agreed = choose_ocr_text(result.plan, resolved)
        word = str(selected.text).strip() if selected is not None else ""
        confidence = selected.confidence if selected is not None else None

        if word:
            bracketed = bracketed_ocr_lemma(word, enabled=bracket_profile)
            if bracketed is not None:
                word = bracketed
            if effective.ocr_replace:
                word = process_ocr_text(
                    word,
                    replace_rules,
                    bool(effective.lowercase_ocr),
                )
            entry.word = str(word).strip()
            entry.confidence = confidence
            engine = str(selected.engine)
            entry.ocr_source = f"ordinary_marker:{engine}"
            entry.final_engine = engine
            issue = "ORDINARY_MARKER_TEXT_OCR"
            existing = [
                part
                for part in str(entry.issue_type or "").split(",")
                if part
            ]
            if issue not in existing:
                existing.append(issue)
                entry.issue_type = ",".join(existing)
            stats["filled"] += 1
        else:
            stats["failed"] += 1
            if not only_blank:
                # Explicit OCR replacement must not leave previous OCR text
                # masquerading as the result of this fresh recognition pass.
                # Manual selections never reach this branch.
                entry.word = ""
                entry.confidence = None
                entry.ocr_source = ""
                entry.final_engine = ""

        if int(entry.x) != original_x or int(entry.y) != original_y:
            raise RuntimeError("普通画线后OCR文字不得修改任何画线坐标")

    return ordered, stats


def ocr_entries(
    image: Image.Image,
    entries: list[Entry],
    settings: AppSettings,
    replace_rules: list[tuple[str, str, str]],
    *,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
) -> list[str]:
    source, effective, _analysis_source, geometry = _page_geometry_context(
        image, settings, profile_page_index,
    )
    results: list[str] = []
    # The legacy text-only OCR consumer must use the same bracketed-lemma
    # boundary as ordinary drawn-marker OCR. A concrete CJK Profile and the
    # user's bracket-structure toggle are both required.
    from .profile.dictionary import effective_project_profile_id, load_dictionary_profile
    from .ordinary.marker_ocr_text import bracketed_ocr_lemma
    profile = load_dictionary_profile(
        None,
        preset=effective_project_profile_id(effective, None),
        language=effective.ocr_language,
    )
    bracket_profile = bool(
        getattr(effective, "profile_cjk_allow_bracketed_headword", False)
        and profile.uses_parser("cjk_bracketed")
    )
    paddle_engine = None
    if effective.ocr_engine == "paddleocr":
        from .paddle_headwords import get_paddle_engine
        paddle_engine = get_paddle_engine(effective)
    for entry in sort_entries_reading_order(entries, geometry, page_sections):
        crop = source.crop(line_box(entry, geometry, source, effective))
        if effective.ocr_engine == "paddleocr":
            from .paddle_headwords import recognize_paddle_text
            raw = recognize_paddle_text(crop, effective, engine=paddle_engine)
        else:
            psm = 5 if str(getattr(effective, "layout_writing_mode", "")).startswith("vertical") else 7
            raw = run_tesseract(
                crop, resolved_tesseract_language(effective), effective.ocr_executable, psm=psm
            )
        text = process_ocr_text(
            raw, replace_rules, effective.lowercase_ocr,
        ) if effective.ocr_replace else str(raw or "").strip()
        # Clean after replacement as well: user rules may preserve or rewrite
        # delimiters. Otherwise use the same untouched result as before.
        lemma = bracketed_ocr_lemma(text, enabled=bracket_profile)
        results.append(lemma if lemma is not None else text)
    return results




def _save_crop(
    image: Image.Image, output: Path, box: tuple[int, int, int, int],
    *, transparent_background: bool = False,
) -> tuple[int, int, int, int]:
    box = clamp_box(box, image)
    output.parent.mkdir(parents=True, exist_ok=True)
    crop = image.crop(box)
    try:
        if transparent_background:
            result = prepare_crop_background(crop, transparent=True)
            try:
                result.save(output, "PNG")
            finally:
                result.close()
        else:
            crop.save(output, "PNG")
    finally:
        crop.close()
    return box


def _stage_text_file(target: Path, text: str, *, encoding: str = "utf-8") -> Path:
    temp = _publish_temp_path(target)
    try:
        with temp.open("w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        return temp
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _stage_crop(
    image: Image.Image, target: Path, box: tuple[int, int, int, int],
    *, transparent_background: bool = False,
) -> tuple[tuple[int, int, int, int], Path]:
    temp = _publish_temp_path(target)
    try:
        saved_box = _save_crop(image, temp, box, transparent_background=transparent_background)
        return saved_box, temp
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def split_single_lines(
    image_path: Path, entries: list[Entry], settings: AppSettings, output_dir: Path,
    *, profile_page_index: int = 0, page_sections: list[PageSection] | None = None,
    write_manifest: bool = True,
) -> list[CropRecord]:
    with Image.open(image_path) as opened:
        image = normalize_page_rgb(opened)
    source, effective, _analysis_source, geometry = _page_geometry_context(
        image, settings, profile_page_index,
    )
    from .refinement.analysis import whiten_illustrations_for_export as whiten
    source = whiten(source, effective, profile_page_index, source_image_path=image_path)
    if page_sections is None:
        page_sections = read_page_sections(image_path)
    records: list[CropRecord] = []
    manifest: list[str] = []
    replacements: list[tuple[Path, Path]] = []
    staged: list[Path] = []
    try:
        for index, entry in enumerate(sort_entries_reading_order(entries, geometry, page_sections)):
            filename = f"{image_path.stem}_SW_{index:03d}.png"
            target = output_dir / filename
            box, temp = _stage_crop(
                source, target, line_box(entry, geometry, source, effective),
            )
            staged.append(temp)
            replacements.append((temp, target))
            records.append(CropRecord(image_path.name, index, entry.word, filename, box))
            manifest.append(filename)
        manifest_target = output_dir / f"{image_path.stem}.PSWords"
        if write_manifest:
            manifest_temp = _stage_text_file(
                manifest_target, "\n".join(manifest) + ("\n" if manifest else ""),
            )
            staged.append(manifest_temp)
            replacements.append((manifest_temp, manifest_target))
        stale = list(output_dir.glob(f"{image_path.stem}_SW_*.png"))
        if not write_manifest:
            stale.append(manifest_target)
        if replacements:
            _publish_file_transaction(replacements, stale_paths=stale)
        else:
            for path in stale:
                path.unlink(missing_ok=True)
    except Exception:
        for temp in staged:
            temp.unlink(missing_ok=True)
        raise
    return records


def _special_bounds(
    root: Path, page_stem: str, geometry: Geometry,
) -> tuple[int, int]:
    """Historical special-page bounds hook, with the current path resolver."""
    return _entry_vertical_bounds.special_bounds(
        root, page_stem, geometry, special_path_fn=special_pages_path,
    )


def entry_crop_bounds(
    image: Image.Image, settings: AppSettings, *, top_y: int | None = None, bottom_y: int | None = None,
    root: Path | None = None, page_stem: str = "",
) -> tuple[int, int]:
    """Historical full-resolution bounds hook with live geometry dependencies."""
    return _entry_vertical_bounds.entry_crop_bounds(
        image, settings, top_y=top_y, bottom_y=bottom_y, root=root, page_stem=page_stem,
        geometry_fn=derive_geometry, special_bounds_fn=_special_bounds,
        source_px_fn=_source_px,
    )

def _entry_crop_box_for_column(
    image: Image.Image, settings: AppSettings, geometry: Geometry, col: int, y0: int, y1: int,
    *, extra_left: int = 0, extra_right: int = 0,
) -> tuple[int, int, int, int]:
    """Historical crop geometry hook: delegates without freezing patchable globals."""
    return _entry_column_bounds.entry_crop_box_for_column(
        image, settings, geometry, col, y0, y1,
        extra_left=extra_left, extra_right=extra_right,
        source_px_fn=_source_px, clamp_fn=clamp_box, np_module=np,
    )

def entry_crop_column_boxes(
    image: Image.Image, settings: AppSettings, *, top_y: int | None = None, bottom_y: int | None = None,
    extra_left: int = 0, extra_right: int = 0, profile_page_index: int = 0,
) -> list[tuple[int, int, int, int]]:
    """Return full-height boxes using the exact Profile-resolved horizontal geometry."""
    source, effective, _analysis_source, geometry = _page_geometry_context(
        image, settings, profile_page_index,
    )
    top, bottom = entry_crop_bounds(source, effective, top_y=top_y, bottom_y=bottom_y)
    return [
        _entry_crop_box_for_column(
            source, effective, geometry, col, top, bottom,
            extra_left=extra_left, extra_right=extra_right,
        )
        for col in range(len(geometry.column_starts))
    ]

def _point_in_rect(point: tuple[int, int], box: tuple[int, int, int, int]) -> bool:
    return _polygon_geometry.point_in_rect(point, box)


def _point_in_polygon(point: tuple[int, int], points: list[tuple[int, int]]) -> bool:
    return _polygon_geometry.point_in_polygon(point, points)


def _orientation(a, b, c) -> int:
    return _polygon_geometry.orientation(a, b, c)


def _on_segment(a, b, c) -> bool:
    return _polygon_geometry.on_segment(a, b, c)


def _segments_intersect(p1, q1, p2, q2) -> bool:
    return _polygon_geometry.segments_intersect(
        p1, q1, p2, q2, orientation_fn=_orientation, on_segment_fn=_on_segment,
    )


def polygon_intersects_box(points: list[tuple[int, int]], box: tuple[int, int, int, int]) -> bool:
    return _polygon_geometry.polygon_intersects_box(
        points, box,
        point_in_rect_fn=_point_in_rect,
        point_in_polygon_fn=_point_in_polygon,
        segments_intersect_fn=_segments_intersect,
    )


def polygon_fully_inside_boxes(points: list[tuple[int, int]], boxes: list[tuple[int,int,int,int]]) -> bool:
    return _polygon_geometry.polygon_fully_inside_boxes(
        points, boxes, point_in_rect_fn=_point_in_rect,
    )


def _box_intersection_area(a: tuple[int,int,int,int], b: tuple[int,int,int,int]) -> int:
    return _polygon_geometry.box_intersection_area(a, b)

def _crop_workflow_deps() -> _page_workflow.CropWorkflowDeps:
    """Capture compatibility constructors/callbacks at call time for patchability."""
    return _page_workflow.CropWorkflowDeps(
        EntryCropPiecePlan=EntryCropPiecePlan,
        IllustrationCropPlan=IllustrationCropPlan,
        PageCropPlan=PageCropPlan,
        CropRecord=CropRecord,
        _page_geometry_context=_page_geometry_context,
        _source_px=_source_px,
        entry_crop_bounds=entry_crop_bounds,
        normalize_page_sections=normalize_page_sections,
        build_reading_lanes=build_reading_lanes,
        sort_entries_reading_order=sort_entries_reading_order,
        _entry_crop_box_for_column=_entry_crop_box_for_column,
        reading_lane_index=reading_lane_index,
        column_index=column_index,
        effective_page_settings=effective_page_settings,
        illustration_crop_bounds=illustration_crop_bounds,
        _normalized_crop_name=_normalized_crop_name,
        polygon_display_name=polygon_display_name,
        canonical_polygon_link=canonical_polygon_link,
        _polygon_bbox=_polygon_bbox,
        polygon_fully_inside_boxes=polygon_fully_inside_boxes,
        polygon_intersects_box=polygon_intersects_box,
        _box_intersection_area=_box_intersection_area,
        illustration_polygon_box=illustration_polygon_box,
        _base_entry_crop_pieces=_base_entry_crop_pieces,
        _stage_text_file=_stage_text_file,
        qt_root=qt_root,
        page_crop_plan_dict=page_crop_plan_dict,
        _publish_file_transaction=_publish_file_transaction,
        _stage_page_crop_plan=_stage_page_crop_plan,
        _save_crop=_save_crop,
        clamp_box=clamp_box,
        prepare_crop_background=prepare_crop_background,
        normalize_page_rgb=normalize_page_rgb,
        read_page_sections=read_page_sections,
        build_page_crop_plan=build_page_crop_plan,
        read_auxiliary_lines=read_auxiliary_lines,
        entry_crop_piece_filename=entry_crop_piece_filename,
        _stage_crop=_stage_crop,
        _publish_temp_path=_publish_temp_path,
        _whitefill_polygons=_whitefill_polygons,
        _save_union_crop=_save_union_crop,
    )


def _base_entry_crop_pieces(
    image: Image.Image, entries: list[Entry], settings: AppSettings,
    *, top_y: int | None = None, bottom_y: int | None = None,
    entry_left_padding: int = 0, entry_right_padding: int = 0,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], list[EntryCropPiecePlan]]:
    return _page_workflow._base_entry_crop_pieces(
        _crop_workflow_deps(), image, entries, settings, top_y=top_y, bottom_y=bottom_y,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        profile_page_index=profile_page_index, page_sections=page_sections,
    )


def build_page_crop_plan(
    image: Image.Image, entries: list[Entry], polygons: list[PolygonRegion], settings: AppSettings,
    *, top_y: int | None = None, bottom_y: int | None = None, illustration_margin: int = 0,
    entry_left_padding: int = 0, entry_right_padding: int = 0,
    integrate_illustrations: bool = True, profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None, auxiliary_lines=None,
    page_stem: str | None = None,
    previous_entry_ref: tuple[str, int] | None = None,
) -> PageCropPlan:
    return _page_workflow.build_page_crop_plan(
        _crop_workflow_deps(), image, entries, polygons, settings,
        top_y=top_y, bottom_y=bottom_y, illustration_margin=illustration_margin,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        integrate_illustrations=integrate_illustrations,
        profile_page_index=profile_page_index, page_sections=page_sections,
        auxiliary_lines=auxiliary_lines, page_stem=page_stem,
        previous_entry_ref=previous_entry_ref,
    )


def _stage_page_crop_plan(
    root: Path, page_stem: str, plan: PageCropPlan,
) -> tuple[Path, Path]:
    return _page_workflow._stage_page_crop_plan(
        _crop_workflow_deps(), root, page_stem, plan,
    )


def write_page_crop_plan(root: Path, page_stem: str, plan: PageCropPlan) -> Path:
    return _page_workflow.write_page_crop_plan(
        _crop_workflow_deps(), root, page_stem, plan,
    )


def _whitefill_polygons(image: Image.Image, polygons: list[PolygonRegion], skip: set[int] | None = None) -> Image.Image:
    return _page_workflow._whitefill_polygons(
        _crop_workflow_deps(), image, polygons, skip,
    )


def _save_union_crop(image: Image.Image, path: Path, base_box: tuple[int,int,int,int], regions: list[PolygonRegion], *, transparent_background: bool = False) -> tuple[int,int,int,int]:
    return _page_workflow._save_union_crop(
        _crop_workflow_deps(), image, path, base_box, regions,
        transparent_background=transparent_background,
    )


def split_whole_entries(
    image_path: Path, entries: list[Entry], settings: AppSettings, output_dir: Path,
    *, top_y: int | None = None, bottom_y: int | None = None, polygons: list[PolygonRegion] | None = None,
    entry_left_padding: int = 0, entry_right_padding: int = 0,
    integrate_illustrations: bool = True, profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    transparent_background: bool = False,
    previous_entry_ref: tuple[str, int] | None = None,
) -> list[CropRecord]:
    return _page_workflow.split_whole_entries(
        _crop_workflow_deps(), image_path, entries, settings, output_dir,
        top_y=top_y, bottom_y=bottom_y, polygons=polygons,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        integrate_illustrations=integrate_illustrations,
        profile_page_index=profile_page_index, page_sections=page_sections,
        transparent_background=transparent_background,
        previous_entry_ref=previous_entry_ref,
    )




# Historical public entry points remain here for callers and existing patches.
from .illustration.detection import (
    AUTO_ILLUSTRATION_LABEL_TOKEN,
    _rle_components,
    _box_gap,
    _merge_nearby_boxes,
    _polygon_bbox,
    _overlap_fraction,
    is_auto_illustration_region,
    detect_illustration_regions_from_image as _detect_illustration_regions_from_image,
)


def detect_illustration_regions_from_image(
    image: Image.Image,
    settings: AppSettings,
    *,
    analysis_column_width: int = 520,
    profile_page_index: int = 0,
) -> list[PolygonRegion]:
    """Compatible entry point delegating the detector to its own module."""
    return _detect_illustration_regions_from_image(
        image, settings,
        analysis_column_width=analysis_column_width,
        profile_page_index=profile_page_index,
        page_geometry_context=_page_geometry_context,
        source_px=_source_px,
        adaptive_dark_mask=_adaptive_dark_mask,
    )


def detect_illustration_regions(
    image_path: Path,
    settings: AppSettings,
    *,
    analysis_column_width: int = 520,
    profile_page_index: int = 0,
) -> list[PolygonRegion]:
    """Historical path API backed by the shared in-memory detector."""
    with Image.open(Path(image_path)) as opened:
        image = normalize_page_rgb(opened)
    try:
        return detect_illustration_regions_from_image(
            image,
            settings,
            analysis_column_width=int(analysis_column_width),
            profile_page_index=int(profile_page_index),
        )
    finally:
        image.close()

def detect_illustrations_to_ppp(
    image_path: Path, settings: AppSettings, *, profile_page_index: int = 0,
    detected_regions: list[PolygonRegion] | None = None,
) -> dict[str, int]:
    """Detect illustrations and safely update one page's PPP file.

    Manual polygons are never overwritten.  Re-running detection replaces only
    previous AUTO polygons, making the operation idempotent and safe to tune.
    """
    image_path = Path(image_path)
    read_path = ppp_read_path_for_image(image_path)
    write_path = ppp_write_path_for_image(image_path)
    existing = read_ppp(read_path)
    manual = [r for r in existing if not is_auto_illustration_region(r)]
    detected = (
        list(detected_regions) if detected_regions is not None else
        detect_illustration_regions(
            image_path, settings, profile_page_index=profile_page_index,
        )
    )
    manual_boxes = [b for r in manual if (b := _polygon_bbox(r)) is not None]
    accepted: list[PolygonRegion] = []
    for region in detected:
        box = _polygon_bbox(region)
        if box is None:
            continue
        if any(_overlap_fraction(box, mb) >= 0.25 for mb in manual_boxes):
            continue
        accepted.append(region)
    from .illustration.labels import write_ordered_auto_ppp
    write_ordered_auto_ppp(write_path, manual, accepted, image_path, settings, profile_page_index)
    return {"manual": len(manual), "auto": len(accepted), "total": len(manual) + len(accepted)}


def detect_illustrations_job(
    image_path: str, settings: AppSettings, profile_page_index: int = 0,
) -> dict[str, int]:
    """Background-safe one-page illustration detector used by the GUI batch runner."""
    return detect_illustrations_to_ppp(
        Path(image_path), settings, profile_page_index=profile_page_index,
    )

def illustration_crop_bounds(
    image: Image.Image,
    settings: AppSettings | None = None,
    *,
    top_y: int = 0,
    bottom_y: int = 0,
    margin: int = 0,
    page_sections: list[PageSection] | None = None,
) -> tuple[int, int, int]:
    """Resolve persisted crop settings to current source-image pixels.

    Crop Settings v6 stores distances in canonical reference-page pixels. For
    ordinary horizontal pages canonical V equals source Y. For 90-degree page
    transforms, illustration polygons are still source-space annotations, so
    only isotropic scalar distances such as margin are reused directly;
    transformed whole-entry cropping is handled through canonical geometry.
    A bottom value of 0 remains the physical image-bottom sentinel.
    """
    effective = settings or AppSettings()
    transform = LayoutTransform(
        str(getattr(effective, "layout_transform", "identity") or "identity")
    )
    canonical_width, canonical_height = transform.canonical_size(image.size)
    if page_sections:
        effective_sections = normalize_page_sections(page_sections, 0, canonical_height)
        top_canonical = effective_sections[0].top_v
        bottom_canonical = effective_sections[-1].bottom_v
    else:
        top_canonical = _source_px(max(0, int(top_y)))
        bottom_canonical = (
            _source_px(max(0, int(bottom_y)))
            if int(bottom_y) > 0 else 0
        )
    margin_px = max(
        0, _source_px(max(0, int(margin))),
    )
    # Illustration polygons are persisted in source XY. Horizontal layouts are
    # the supported physical top/bottom crop convention; rotated layouts keep
    # the full source-height guard rather than mislabel canonical V as source Y.
    if transform.kind in {"identity", "mirror_x"}:
        top = max(0, min(image.height - 1, top_canonical))
        bottom = (
            max(top + 1, min(image.height, bottom_canonical))
            if bottom_canonical > 0 else image.height
        )
    else:
        top = 0
        bottom = image.height
    return top, bottom, margin_px

def illustration_polygon_box(
    image: Image.Image,
    region: PolygonRegion,
    *,
    top: int = 0,
    bottom: int | None = None,
    margin_px: int = 0,
) -> tuple[int, int, int, int] | None:
    """Return the effective illustration crop box after page-boundary clipping."""
    if len(region.points) < 3:
        return None
    bottom = image.height if bottom is None else max(1, min(image.height, int(bottom)))
    xs = [point[0] for point in region.points]
    ys = [point[1] for point in region.points]
    raw = (
        min(xs) - margin_px,
        min(ys) - margin_px,
        max(xs) + 1 + margin_px,
        max(ys) + 1 + margin_px,
    )
    box = clamp_box(raw, image)
    clipped = (box[0], max(box[1], int(top)), box[2], min(box[3], int(bottom)))
    if clipped[2] - clipped[0] <= 1 or clipped[3] - clipped[1] <= 1:
        return None
    return clipped


def split_illustrations(
    image_path: Path,
    polygons: list[PolygonRegion],
    output_dir: Path,
    settings: AppSettings | None = None,
    *,
    top_y: int = 0,
    bottom_y: int = 0,
    margin: int = 0,
    entries: list[Entry] | None = None,
    entry_left_padding: int = 0,
    entry_right_padding: int = 0,
    integrate_illustrations: bool = True,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    transparent_background: bool = False,
    previous_entry_ref: tuple[str, int] | None = None,
) -> IllustrationSplitResult:
    """Export only PPPs that are not already carried by an associated entry crop."""
    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    effective_settings = settings or AppSettings()
    if page_sections is None:
        page_sections = read_page_sections(image_path)
    rgb_for_plan = image.convert("RGB")
    try:
        plan = build_page_crop_plan(
            rgb_for_plan, list(entries or []), polygons, effective_settings,
            top_y=top_y, bottom_y=bottom_y, illustration_margin=margin,
            entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
            integrate_illustrations=integrate_illustrations,
            profile_page_index=profile_page_index, page_sections=page_sections,
            auxiliary_lines=read_auxiliary_lines(image_path),
            page_stem=image_path.stem, previous_entry_ref=previous_entry_ref,
        )
    finally:
        rgb_for_plan.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[CropRecord] = []
    events: list[IllustrationCropEvent] = []
    manifest: list[str] = []
    replacements: list[tuple[Path, Path]] = []
    staged: list[Path] = []
    p_counter: dict[int, int] = {}
    try:
        for decision in plan.illustrations:
            region = polygons[decision.polygon_index]
            if not decision.standalone:
                action = (
                    "跳过：已完整包含于词条切图"
                    if decision.relation == "contained"
                    else "跳过：与词条切图部分相交，已合并到词条切图"
                )
                events.append(IllustrationCropEvent(
                    image_path.name, decision.polygon_index + 1, decision.name,
                    decision.associated_word, decision.relation, action, "",
                ))
                manifest.append(
                    f"{decision.polygon_index+1:03d}|{decision.name}|SKIP|"
                    f"{decision.relation}|{decision.associated_word}"
                )
                continue
            box = decision.box
            if box is None:
                events.append(IllustrationCropEvent(
                    image_path.name, decision.polygon_index + 1, decision.name,
                    decision.associated_word, decision.relation,
                    "跳过：超出有效切图范围", "",
                ))
                continue
            crop = image.crop(box)
            mask = Image.new("L", crop.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.polygon([(x-box[0], y-box[1]) for x, y in region.points], fill=255)
            crop.putalpha(mask)
            formatted = prepare_crop_background(crop, transparent=transparent_background)
            if decision.associated_entry_index is not None and decision.associated_entry_index >= 0:
                ei = decision.associated_entry_index
                p_counter[ei] = p_counter.get(ei, 0) + 1
                filename = f"{image_path.stem}_WW_{ei:03d}(P{p_counter[ei]}).png"
            else:
                filename = f"{image_path.stem}_PIC_{decision.polygon_index+1:03d}.png"
            target = output_dir / filename
            temp = _publish_temp_path(target)
            try:
                formatted.save(temp, "PNG")
            except Exception:
                temp.unlink(missing_ok=True)
                raise
            finally:
                crop.close()
                formatted.close()
                mask.close()
            staged.append(temp)
            replacements.append((temp, target))
            label = region.label or (
                f"{image_path.stem}|P_{decision.polygon_index+1:02d}|1|{image_path.stem}|"
            )
            records.append(CropRecord(
                image_path.name, decision.polygon_index + 1,
                decision.associated_word or label, filename, box,
            ))
            if decision.relation == "partial" and not integrate_illustrations:
                action = "单独插图切图（部分超出词条；未综合插图）"
            else:
                action = (
                    "单独插图切图（关联词条外部）"
                    if decision.associated_entry_index is not None
                    else "单独插图切图（未关联词条）"
                )
            events.append(IllustrationCropEvent(
                image_path.name, decision.polygon_index + 1, decision.name,
                decision.associated_word, decision.relation, action, filename,
            ))
            manifest.append(
                f"{decision.polygon_index+1:03d}|{label}|{filename}|"
                f"{decision.relation}|{decision.associated_word}"
            )

        manifest_target = output_dir / f"{image_path.stem}.PPPictures"
        manifest_temp = _stage_text_file(
            manifest_target, "\n".join(manifest) + ("\n" if manifest else ""),
        )
        staged.append(manifest_temp)
        replacements.append((manifest_temp, manifest_target))
        plan_temp, plan_target = _stage_page_crop_plan(
            image_path.parent, image_path.stem, plan,
        )
        staged.append(plan_temp)
        replacements.append((plan_temp, plan_target))
        stale = [
            *output_dir.glob(f"{image_path.stem}_WW_*.png"),
            *output_dir.glob(f"{image_path.stem}_PIC_*.png"),
        ]
        _publish_file_transaction(replacements, stale_paths=stale)
    except Exception:
        for temp in staged:
            temp.unlink(missing_ok=True)
        raise
    finally:
        image.close()
    return IllustrationSplitResult(records, events)


def resolve_crop_worker_count(configured: int = 0, cpu_count: int | None = None) -> int:
    """Historical core entrypoint; obtain patched dependencies at call time."""
    return _crop_worker_policy.resolve_crop_worker_count(
        configured, cpu_count, cpu_count_provider=os.cpu_count,
    )

def split_whole_entries_job(
    image_path: str | Path,
    pdic_file: str | Path,
    settings: AppSettings,
    output_dir: str | Path,
    top_y: int | None = None,
    bottom_y: int | None = None,
    ppp_file: str | Path | None = None,
    entry_left_padding: int = 0,
    entry_right_padding: int = 0,
    integrate_illustrations: bool = True,
    profile_page_index: int = 0,
    transparent_background: bool = False,
    previous_image_path: str | Path | None = None,
) -> list[CropRecord]:
    """Spawn-safe worker: build the crop plan first, then execute it."""
    page = Path(image_path)
    entries = read_pdic(Path(pdic_file))
    polygons = read_ppp(Path(ppp_file)) if ppp_file else []
    return split_whole_entries(
        page, entries, settings, Path(output_dir), top_y=top_y, bottom_y=bottom_y, polygons=polygons,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        integrate_illustrations=integrate_illustrations,
        profile_page_index=profile_page_index,
        transparent_background=transparent_background,
        previous_entry_ref=previous_entry_ref_for_image(previous_image_path),
    )


def split_illustrations_job(
    image_path: str | Path,
    ppp_file: str | Path,
    output_dir: str | Path,
    settings: AppSettings | None = None,
    top_y: int = 0,
    bottom_y: int = 0,
    margin: int = 0,
    pdic_file: str | Path | None = None,
    entry_left_padding: int = 0,
    entry_right_padding: int = 0,
    integrate_illustrations: bool = True,
    profile_page_index: int = 0,
    transparent_background: bool = False,
    previous_image_path: str | Path | None = None,
) -> IllustrationSplitResult:
    """Spawn-safe worker: plan PPP/entry relations before exporting standalone PPPs."""
    page = Path(image_path)
    polygons = read_ppp(Path(ppp_file))
    entries = read_pdic(Path(pdic_file)) if pdic_file else []
    return split_illustrations(
        page, polygons, Path(output_dir), settings, top_y=top_y, bottom_y=bottom_y, margin=margin, entries=entries,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        integrate_illustrations=integrate_illustrations,
        profile_page_index=profile_page_index,
        transparent_background=transparent_background,
        previous_entry_ref=previous_entry_ref_for_image(previous_image_path),
    )
