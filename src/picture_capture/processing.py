from __future__ import annotations

from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
import os
import re
import json
import subprocess
import unicodedata

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .models import AppSettings, Entry, PolygonRegion, read_noncomment_lines, resolved_tesseract_language
from .coordinate_space import (
    SOURCE_COORDINATE_SPACE,
    canonical_to_analysis_scale,
    geometry_uses_canonical_pixels,
    legacy_parameter_scale,
    reference_to_analysis,
    reference_to_canonical,
    stored_geometry_to_canonical,
)
from .image_utils import normalize_page_rgb
from .layout_transform import LayoutTransform
from .profile_semantics import (
    effective_page_settings, entry_allowed_by_page_template, page_template_analysis_image,
)
from .ocr_engines import find_tesseract
from .formats import read_pdic, read_ppp, write_pdic, write_ppp
from .project_storage import crop_log_path, ppp_read_path_for_image, ppp_write_path_for_image, qt_root, special_pages_path


_COLUMN_TRACK_ADAPTIVE_BLOCK = 19
_COLUMN_TRACK_ADAPTIVE_C = 20


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


def entry_crop_piece_filename(page_stem: str, piece: EntryCropPiecePlan) -> str:
    """Return the exact output filename used for an entry crop-plan piece."""
    return f"{page_stem}_WW_{piece.output_index:03d}{piece.suffix}.png"


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


def _analysis_image(image: Image.Image, max_width: int = 1400) -> tuple[Image.Image, float]:
    source = normalize_page_rgb(image)
    if source.width <= max_width:
        return source.copy(), 1.0
    scale = max_width / source.width
    return source.resize((max_width, max(1, round(source.height * scale))), Image.Resampling.LANCZOS), scale


def parameter_scale(image: Image.Image, settings: AppSettings) -> float:
    """Compatibility scale for pre-v2 display-coordinate projects.

    Modern project geometry is already stored in full-resolution canonical
    pixels, so its runtime scale is exactly 1. Old projects keep the historical
    conversion until ProjectState migrates them.
    """
    if geometry_uses_canonical_pixels(settings):
        return 1.0
    return legacy_parameter_scale(image.width, settings)


def _adaptive_dark_mask(gray_image: Image.Image, block_size: int, c_value: int) -> np.ndarray:
    """Create an adaptive dark-ink mask without requiring OpenCV."""
    block_size = max(3, int(block_size))
    if block_size % 2 == 0:
        block_size += 1
    radius = max(1, block_size // 2)
    gray = np.asarray(gray_image, dtype=np.int16)
    local_mean = np.asarray(gray_image.filter(ImageFilter.BoxBlur(radius)), dtype=np.int16)
    return gray < (local_mean - max(0, int(c_value)))


def _smooth_track(values: list[int], max_step: int) -> list[int]:
    """Median-filter anchors and constrain implausible block-to-block jumps."""
    if len(values) < 2:
        return values
    median_filtered: list[int] = []
    for index in range(len(values)):
        window = values[max(0, index - 1):min(len(values), index + 2)]
        median_filtered.append(round(float(np.median(window))))
    max_step = max(1, int(max_step))
    forward = median_filtered.copy()
    for index in range(1, len(forward)):
        forward[index] = min(forward[index - 1] + max_step, max(forward[index - 1] - max_step, forward[index]))
    for index in range(len(forward) - 2, -1, -1):
        forward[index] = min(forward[index + 1] + max_step, max(forward[index + 1] - max_step, forward[index]))
    return forward


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

    canonical_width = max(1, round(analysis.width / max(scale, 1e-9)))
    body_indent = stored_geometry_to_canonical(
        settings.body_indent, canonical_width, settings,
    )
    block_height_value = stored_geometry_to_canonical(
        settings.column_track_block_height, canonical_width, settings,
    )
    radius_value = stored_geometry_to_canonical(
        settings.column_track_radius, canonical_width, settings,
    )
    max_step_value = stored_geometry_to_canonical(
        settings.column_track_max_step, canonical_width, settings,
    )
    dark = _adaptive_dark_mask(
        ImageOps.grayscale(analysis),
        max(3, round(_COLUMN_TRACK_ADAPTIVE_BLOCK * geometry_to_analysis)),
        _COLUMN_TRACK_ADAPTIVE_C,
    )
    height, width = dark.shape
    block_height = max(30, round(block_height_value * geometry_to_analysis))
    radius = max(8, round(radius_value * geometry_to_analysis))
    paths: list[ColumnPath] = []

    for nominal_x, column_width in zip(starts_analysis, widths_analysis):
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
        filled = _smooth_track(
            filled,
            max(1, round(max_step_value * geometry_to_analysis)),
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


def _derive_nominal_geometry_canonical(
    image_width: int, image_height: int, settings: AppSettings,
) -> Geometry:
    """Return nominal geometry in full-resolution canonical pixels."""
    width = max(1, int(image_width))
    height = max(1, int(image_height))
    analysis_scale = min(1.0, 1400.0 / width)
    analysis_width = max(1, round(width * analysis_scale))

    def canonical_value(name: str) -> int:
        return stored_geometry_to_canonical(
            getattr(settings, name), width, settings,
        )

    count = max(1, settings.columns)
    left = max(0, round(canonical_value("manual_x") * analysis_scale))
    gutter = max(0, round(canonical_value("gutter") * analysis_scale))
    column_width = max(10, round(canonical_value("column_width") * analysis_scale))
    configured_right = left + count * column_width + (count - 1) * gutter
    if configured_right > analysis_width * 1.08 or configured_right < analysis_width * 0.55:
        left = max(2, round(analysis_width * 0.025))
        gutter = max(4, round(analysis_width * 0.035)) if count > 1 else 0
        column_width = max(
            10, (analysis_width - 2 * left - (count - 1) * gutter) // count
        )

    starts_analysis = [
        left + i * (column_width + gutter) for i in range(count)
    ]
    starts = [
        min(width - 1, max(0, round(x / analysis_scale)))
        for x in starts_analysis
    ]
    gutter_canonical = round(gutter / analysis_scale)
    widths: list[int] = []
    for i, start_x in enumerate(starts):
        if i + 1 < len(starts):
            widths.append(max(1, starts[i + 1] - start_x - gutter_canonical))
        else:
            widths.append(max(1, width - start_x))

    top = min(height - 1, max(0, canonical_value("start_y")))
    bottom_setting = canonical_value("bottom_y")
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
    """Build geometry in full-resolution canonical pixels.

    Version-2 settings are already stored in this space. Legacy display-scaled
    values are converted only at this boundary, so downstream code never needs
    to know about GUI zoom or parameter_display_width.
    """
    analysis, analysis_scale = _analysis_image(image)
    analysis_width, analysis_height = analysis.size
    canonical_width, canonical_height = image.size

    def canonical_value(name: str) -> int:
        return stored_geometry_to_canonical(
            getattr(settings, name), canonical_width, settings,
        )

    count = max(1, settings.columns)
    left = max(0, round(canonical_value("manual_x") * analysis_scale))
    gutter = max(0, round(canonical_value("gutter") * analysis_scale))
    column_width = max(10, round(canonical_value("column_width") * analysis_scale))
    configured_right = left + count * column_width + (count - 1) * gutter
    if configured_right > analysis_width * 1.08 or configured_right < analysis_width * 0.55:
        left = max(2, round(analysis_width * 0.025))
        gutter = max(4, round(analysis_width * 0.035)) if count > 1 else 0
        column_width = max(
            10,
            (analysis_width - 2 * left - (count - 1) * gutter) // count,
        )

    starts_analysis = [
        left + i * (column_width + gutter) for i in range(count)
    ]
    widths_analysis: list[int] = []
    for i, start_x in enumerate(starts_analysis):
        if i + 1 < len(starts_analysis):
            widths_analysis.append(
                max(1, starts_analysis[i + 1] - start_x - gutter)
            )
        else:
            widths_analysis.append(max(1, analysis_width - start_x))

    starts = [
        min(canonical_width - 1, max(0, round(x / analysis_scale)))
        for x in starts_analysis
    ]
    gutter_canonical = round(gutter / analysis_scale)
    widths: list[int] = []
    for i, start_x in enumerate(starts):
        if i + 1 < len(starts):
            widths.append(
                max(1, starts[i + 1] - start_x - gutter_canonical)
            )
        else:
            widths.append(max(1, canonical_width - start_x))

    top = min(
        canonical_height - 1,
        max(0, canonical_value("start_y")),
    )
    bottom_setting = canonical_value("bottom_y")
    if settings.crop_to_bottom_y and bottom_setting > top:
        bottom = min(canonical_height, max(top + 1, bottom_setting))
    else:
        bottom = canonical_height

    top_analysis = min(
        analysis_height - 1, max(0, round(top * analysis_scale))
    )
    bottom_analysis = min(
        analysis_height,
        max(top_analysis + 1, round(bottom * analysis_scale)),
    )
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


def _left_edge_otsu_threshold(gray: np.ndarray) -> int:
    """Return a stable Otsu threshold for ordinary left-edge detection."""
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = float(hist.sum())
    if total <= 0:
        return 127
    probability = hist / total
    omega = np.cumsum(probability)
    means = np.cumsum(probability * np.arange(256, dtype=np.float64))
    global_mean = means[-1]
    denominator = omega * (1.0 - omega)
    score = np.zeros(256, dtype=np.float64)
    valid = denominator > 1e-12
    score[valid] = ((global_mean * omega[valid] - means[valid]) ** 2) / denominator[valid]
    return int(min(235, max(40, int(np.argmax(score)))))


def _left_edge_ink_mask(gray: np.ndarray, settings: AppSettings) -> np.ndarray:
    """Build the ordinary-drawing foreground mask from the shared threshold policy.

    Ordinary drawing historically always used the legacy fixed RGB-sum threshold.
    That made otherwise identical layouts behave differently when paper tone,
    scan exposure, or yellowing changed.  The ordinary mode now follows the same
    user-facing threshold policy as layout analysis: automatic/Otsu by default,
    adaptive for uneven backgrounds, and fixed only for compatibility/tuning.
    """
    mode = str(getattr(settings, "analysis_threshold_mode", "auto") or "auto").strip().lower()
    if mode == "fixed":
        threshold = int(round(float(getattr(settings, "darkness_threshold", 600)) / 3.0))
        return gray < min(255, max(0, threshold))
    if mode == "adaptive":
        radius = max(3, round(min(gray.shape[:2]) * 0.008))
        local = np.asarray(
            Image.fromarray(gray, mode="L").filter(ImageFilter.BoxBlur(radius=radius)),
            dtype=np.int16,
        )
        return gray.astype(np.int16) < (local - 10)
    return gray < _left_edge_otsu_threshold(gray)


def _detect_entries_left_edge(image: Image.Image, settings: AppSettings) -> tuple[list[Entry], Geometry]:
    """Detect dictionary headword rows near each column's left edge.

    This preserves the old program's core assumption: a headword starts with
    dark ink inside a narrow strip at the left of a dictionary column. Runs are
    consolidated and filtered using the configured character height.
    """
    source = normalize_page_rgb(image)
    geometry = derive_geometry(source, settings)
    canonical = geometry.transform.canonical_image_for_analysis(source)
    analysis, scale = _analysis_image(canonical)
    canonical_width = canonical.width
    body_indent = stored_geometry_to_canonical(
        settings.body_indent, canonical_width, settings,
    )
    character_height = stored_geometry_to_canonical(
        settings.character_height, canonical_width, settings,
    )
    row_padding = stored_geometry_to_canonical(
        settings.row_padding, canonical_width, settings,
    )
    row_height = max(1, character_height + row_padding)
    gray = np.asarray(ImageOps.grayscale(analysis), dtype=np.uint8)
    dark = _left_edge_ink_mask(gray, settings)
    top = round(geometry.top * scale)
    bottom = min(gray.shape[0], round(geometry.bottom * scale))
    strip_width = max(3, round(body_indent * scale))
    min_gap = max(3, round(row_height * scale * 0.55))
    entries: list[Entry] = []

    for col, source_x in enumerate(geometry.column_starts):
        if bottom <= top:
            continue
        counts = np.zeros(bottom - top, dtype=np.int32)
        actual_widths = np.zeros(bottom - top, dtype=np.int32)
        for offset, y_analysis in enumerate(range(top, bottom)):
            y_source = round(y_analysis / scale)
            tracked_x = geometry.x_at(col, y_source)
            x0 = min(gray.shape[1] - 1, max(0, round(tracked_x * scale)))
            x1 = min(gray.shape[1], x0 + strip_width)
            if x1 > x0:
                counts[offset] = int(dark[y_analysis, x0:x1].sum())
                actual_widths[offset] = x1 - x0
        # A single speck must not become a marker.  Derive the row-density
        # floor from this column instead of hard-coding 10% for every scan/font.
        # Thin type stays detectable, while dark/noisy scans still require a
        # meaningful amount of left-edge ink.
        density = np.divide(
            counts.astype(np.float64),
            np.maximum(1, actual_widths),
            out=np.zeros_like(counts, dtype=np.float64),
            where=actual_widths > 0,
        )
        positive = density[density > 0]
        if positive.size:
            q35 = float(np.percentile(positive, 35))
            density_floor = min(0.12, max(0.035, q35 * 0.55))
        else:
            density_floor = 0.10
        active = counts >= np.maximum(
            2, np.rint(actual_widths * density_floor).astype(np.int32)
        )
        # Close tiny vertical gaps inside letters/diacritics.
        if active.size >= 3:
            active = np.convolve(active.astype(np.uint8), np.ones(3, dtype=np.uint8), mode="same") > 0
        runs: list[tuple[int, int]] = []
        start: int | None = None
        for offset, value in enumerate(active):
            if value and start is None:
                start = offset
            elif not value and start is not None:
                runs.append((start, offset - 1))
                start = None
        if start is not None:
            runs.append((start, len(active) - 1))

        last_y = -10**9
        for run_start, run_end in runs:
            run_height = run_end - run_start + 1
            if run_height < 2:
                continue
            y_analysis = max(
                top,
                top + run_start - max(1, round(row_padding * scale)),
            )
            y_source = round(y_analysis / scale)
            if settings.paddle_refine_separator_y:
                # Reuse the OCR mode's horizontal-valley refinement for the
                # coarse Y produced by left-edge projection. Restrict analysis
                # to this column so neighbouring columns cannot influence it.
                from .paddle_headwords import refine_separator_y
                reference_to_source = canonical.width / 1400.0
                column_x = max(0, round(geometry.x_at(col, y_source)))
                column_right = min(
                    gray.shape[1],
                    column_x + max(10, geometry.column_widths[col]),
                )
                if column_right > column_x:
                    y_source, _refinement = refine_separator_y(
                        gray[:, column_x:column_right],
                        y_source,
                        max(2, character_height),
                        settings,
                        reference_to_canonical_scale=reference_to_source,
                        lower_bound=max(0, geometry.top),
                    )
            if y_source - last_y < round(min_gap / scale):
                continue
            source_point = geometry.canonical_to_source(source_x, y_source)
            entries.append(Entry(word="", x=source_point[0], y=source_point[1]))
            last_y = y_source

    return sort_entries_reading_order(entries, geometry), geometry



def detect_entries(
    image: Image.Image,
    settings: AppSettings,
    paddle_cache_path: Path | None = None,
    force_paddle_refresh: bool = False,
    paddle_filter_rules_path: Path | None = None,
    profile_page_index: int = 0,
) -> tuple[list[Entry], Geometry]:
    """Detect markers with the active Project Profile page template applied."""
    source = normalize_page_rgb(image)
    effective = effective_page_settings(settings, source.size, profile_page_index)
    analysis_source = page_template_analysis_image(source, effective, profile_page_index)
    method = effective.detection_method.strip().lower()
    if method == "paddleocr":
        geometry = derive_geometry(analysis_source, effective)
        from .paddle_headwords import detect_paddle_headwords
        entries = detect_paddle_headwords(
            analysis_source, geometry, effective,
            cache_path=paddle_cache_path,
            force_refresh=force_paddle_refresh,
            filter_rules_path=paddle_filter_rules_path,
        )
    else:
        entries, geometry = _detect_entries_left_edge(analysis_source, effective)

    entries = [
        entry for entry in entries
        if entry_allowed_by_page_template(
            entry.x, entry.y, source.size, effective, profile_page_index,
        )
    ]
    return sort_entries_reading_order(entries, geometry), geometry


def refine_existing_entries(
    image: Image.Image,
    entries: list[Entry],
    settings: AppSettings,
) -> tuple[list[Entry], dict[str, int]]:
    """Refine only existing marker positions without adding or removing rows.

    The current PDIC markers are treated as the coarse localization.  The same
    local ink-valley refiner used by automatic drawing is called again in
    canonical layout space.  Each marker is constrained to the refiner's own
    local search radius, which acts as a hard safety bound on canonical Y
    movement.  Entry text/order/count and every non-coordinate field are kept.
    """
    source = normalize_page_rgb(image)
    geometry = derive_geometry(source, settings)
    canonical = geometry.transform.canonical_image_for_analysis(source)
    gray = np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8)

    from .paddle_headwords import refine_separator_y

    canonical_width = canonical.width
    line_height = max(
        2,
        stored_geometry_to_canonical(
            settings.character_height, canonical_width, settings,
        ),
    )
    source_per_reference = canonical_width / 1400.0
    search_ratio = max(0.05, min(0.80, float(settings.paddle_separator_search_ratio)))
    max_delta = max(2, round(line_height * search_ratio))

    refined_entries: list[Entry] = []
    moved = 0
    limited = 0
    for entry in entries:
        canonical_u, canonical_v = geometry.source_to_canonical(entry.x, entry.y)
        col = column_index(entry.x, geometry, entry.y)
        column_x = max(0, round(geometry.x_at(col, canonical_v)))
        column_right = min(
            gray.shape[1],
            column_x + max(10, int(geometry.column_widths[col])),
        )
        new_v = int(canonical_v)
        if column_right > column_x:
            candidate_v, _details = refine_separator_y(
                gray[:, column_x:column_right],
                int(canonical_v),
                line_height,
                settings,
                reference_to_canonical_scale=source_per_reference,
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
    )
    write_pdic(pdic_path_for_image(page), entries, image.width, pages)
    return len(entries)


def load_replace_rules(path: Path) -> list[tuple[str, str, str]]:
    if not path.exists():
        return []
    rules: list[tuple[str, str, str]] = []
    for line in read_noncomment_lines(path):
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] in {"N", "R"}:
            rules.append((parts[0], parts[1], parts[2] if len(parts) >= 3 else ""))
    return rules


def process_ocr_text(text: str, rules: list[tuple[str, str, str]], lowercase: bool) -> str:
    text = text.replace("'", "").strip()
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    if nonempty:
        multiword = [line for line in nonempty if len(line.split()) > 1]
        text = multiword[0] if multiword else nonempty[0]
    for kind, search, replacement in rules:
        text = text.replace(search, replacement) if kind == "N" else re.sub(search, replacement, text)
    return text.lower() if lowercase else text


def run_tesseract(image: Image.Image, language: str, executable: str = "tesseract", psm: int = 7) -> str:
    resolved = find_tesseract(executable)
    if not resolved:
        raise RuntimeError(
            "未找到 Tesseract OCR。请安装 Tesseract，并在设置中填写 tesseract.exe 的完整路径。"
        )
    payload = BytesIO()
    normalize_page_rgb(image).save(payload, format="PNG")
    command = [str(resolved), "stdin", "stdout", "-l", language, "--psm", str(psm)]
    result = subprocess.run(command, input=payload.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
    """Return the visual column containing a manual click.

    Manual drawing must use each column's full horizontal interval, not the
    nearest column start. If the click is genuinely in a gutter or outside all
    columns, choose the interval boundary nearest to the click.
    """
    x, _canonical_y = geometry.source_to_canonical(int(x), int(y))
    if not geometry.column_starts:
        return 0
    intervals: list[tuple[int, int]] = []
    for i, start in enumerate(geometry.column_starts):
        width = geometry.column_widths[i] if i < len(geometry.column_widths) else 1
        right = int(start) + max(1, int(width))
        intervals.append((int(start), right))
        if int(start) <= x < right or (i == len(geometry.column_starts) - 1 and x == right):
            return i

    def distance_to_interval(pair: tuple[int, tuple[int, int]]) -> tuple[int, int]:
        i, (left, right) = pair
        if x < left:
            distance = left - x
        elif x > right:
            distance = x - right
        else:
            distance = 0
        return distance, i

    return min(enumerate(intervals), key=distance_to_interval)[0]



def entry_reading_order_key(entry: Entry, geometry: Geometry) -> tuple[int, int, int]:
    """Canonical dictionary reading order: column first, then top-to-bottom.

    Manual lines are snapped to the tracked column edge while OCR lines retain
    their measured text X. Sorting by raw ``(x, y)`` therefore groups manual
    lines ahead of OCR lines inside the same column.  Classify both sources
    into the same visual column first so their source never affects order.
    """
    u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
    return (column_index_for_click(int(entry.x), geometry, int(entry.y)), v, u)


def sort_entries_reading_order(entries: list[Entry], geometry: Geometry) -> list[Entry]:
    return sorted(entries, key=lambda entry: entry_reading_order_key(entry, geometry))


def sort_entries_column_y(entries: list[Entry], geometry: Geometry) -> list[Entry]:
    """Stable PDIC repair order: visual column, then Y only.

    X is deliberately excluded.  If two records share the same column and Y,
    Python's stable sort preserves their existing PDIC order.
    """
    return sorted(
        entries,
        key=lambda entry: (
            column_index_for_click(int(entry.x), geometry, int(entry.y)),
            geometry.source_to_canonical(int(entry.x), int(entry.y))[1],
        ),
    )

def clamp_box(box: tuple[int, int, int, int], image: Image.Image) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    left = min(image.width - 1, max(0, int(left)))
    top = min(image.height - 1, max(0, int(top)))
    right = min(image.width, max(left + 1, int(right)))
    bottom = min(image.height, max(top + 1, int(bottom)))
    return left, top, right, bottom


def line_box(entry: Entry, geometry: Geometry, image: Image.Image, settings: AppSettings) -> tuple[int, int, int, int]:
    _entry_u, entry_v = geometry.source_to_canonical(entry.x, entry.y)
    idx = column_index(entry.x, geometry, entry.y)
    canonical_width = geometry.transform.canonical_size(image.size)[0]
    row_padding = stored_geometry_to_canonical(
        settings.row_padding, canonical_width, settings,
    )
    character_height = stored_geometry_to_canonical(
        settings.character_height, canonical_width, settings,
    )
    vertical_pad = abs(row_padding)
    height = character_height + 2 * abs(row_padding)
    width = round(geometry.column_widths[idx] * min(100.0, max(1.0, settings.right_ratio)) / 100.0)
    left_extension = round(geometry.column_starts[0] * 0.5)
    tracked_x = geometry.x_at(idx, entry_v)
    canonical_box = (
        tracked_x - left_extension,
        entry_v - vertical_pad,
        tracked_x + width,
        entry_v - vertical_pad + height,
    )
    return clamp_box(geometry.transform.canonical_box_to_source(canonical_box, geometry.source_size), image)


def ocr_entries(
    image: Image.Image,
    entries: list[Entry],
    settings: AppSettings,
    replace_rules: list[tuple[str, str, str]],
) -> list[str]:
    geometry = derive_geometry(image, settings)
    results: list[str] = []
    paddle_engine = None
    if settings.ocr_engine == "paddleocr":
        from .paddle_headwords import get_paddle_engine
        paddle_engine = get_paddle_engine(settings)
    for entry in sort_entries_reading_order(entries, geometry):
        crop = image.crop(line_box(entry, geometry, image, settings))
        if settings.ocr_engine == "paddleocr":
            from .paddle_headwords import recognize_paddle_text
            raw = recognize_paddle_text(crop, settings, engine=paddle_engine)
        else:
            psm = 5 if str(getattr(settings, "layout_writing_mode", "")).startswith("vertical") else 7
            raw = run_tesseract(
                crop, resolved_tesseract_language(settings), settings.ocr_executable, psm=psm
            )
        results.append(process_ocr_text(raw, replace_rules, settings.lowercase_ocr) if settings.ocr_replace else raw.strip())
    return results


def export_ocred(path: Path, texts: list[str]) -> None:
    path.write_text("".join(f"{i:03d}|`{text}\n" for i, text in enumerate(texts)), encoding="utf-8")


def import_ocred(path: Path) -> list[str]:
    texts: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        texts.append(line.split("`", 1)[1] if "`" in line else line)
    return texts


def _save_crop(image: Image.Image, output: Path, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    box = clamp_box(box, image)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.crop(box).save(output, "PNG")
    return box


def split_single_lines(
    image_path: Path, entries: list[Entry], settings: AppSettings, output_dir: Path
) -> list[CropRecord]:
    with Image.open(image_path) as opened:
        image = normalize_page_rgb(opened)
    geometry = derive_geometry(image, settings)
    records: list[CropRecord] = []
    manifest: list[str] = []
    for index, entry in enumerate(sort_entries_reading_order(entries, geometry)):
        filename = f"{image_path.stem}_SW_{index:03d}.png"
        box = _save_crop(image, output_dir / filename, line_box(entry, geometry, image, settings))
        records.append(CropRecord(image_path.name, index, entry.word, filename, box))
        manifest.append(filename)
    (output_dir / f"{image_path.stem}.PSWords").write_text("\n".join(manifest) + ("\n" if manifest else ""), encoding="utf-8")
    return records


def _special_bounds(
    root: Path, page_stem: str, geometry: Geometry, legacy_source_scale: float,
) -> tuple[int, int]:
    path = special_pages_path(root)
    if not path.exists():
        return geometry.top, geometry.bottom
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if fields and fields[0] == page_stem:
            top = round(int(fields[1]) * legacy_source_scale) if len(fields) > 1 and fields[1].strip() else geometry.top
            bottom = round(int(fields[2]) * legacy_source_scale) if len(fields) > 2 and fields[2].strip() else geometry.bottom
            return max(0, top), max(top + 1, bottom)
    return geometry.top, geometry.bottom


def entry_crop_bounds(
    image: Image.Image, settings: AppSettings, *, top_y: int | None = None, bottom_y: int | None = None,
    root: Path | None = None, page_stem: str = "",
) -> tuple[int, int]:
    """Resolve whole-entry crop bounds in canonical full-resolution pixels.

    Current Crop Settings values use the same canonical reference-page contract
    as persisted page layout geometry. The historical _SpecialPages.txt file remains a legacy
    input and is converted explicitly with the saved old display width.
    """
    geometry = derive_geometry(image, settings)
    canonical_width, canonical_height = geometry.transform.canonical_size(image.size)
    if top_y is None and bottom_y is None and root is not None:
        legacy_source_scale = 1.0 / max(
            legacy_parameter_scale(canonical_width, settings), 1e-9,
        )
        top, bottom = _special_bounds(
            root, page_stem, geometry, legacy_source_scale,
        )
        return max(0, top), min(canonical_height, bottom)

    top_value = (
        stored_geometry_to_canonical(settings.start_y, canonical_width, settings)
        if top_y is None
        else stored_geometry_to_canonical(max(0, int(top_y)), canonical_width, settings)
    )
    bottom_value = (
        0
        if bottom_y is None or int(bottom_y) <= 0
        else stored_geometry_to_canonical(max(0, int(bottom_y)), canonical_width, settings)
    )
    top = max(0, min(canonical_height - 1, int(top_value)))
    bottom = canonical_height if bottom_value <= 0 else max(
        top + 1, min(canonical_height, int(bottom_value))
    )
    return top, bottom

def _entry_crop_box_for_column(
    image: Image.Image, settings: AppSettings, geometry: Geometry, col: int, y0: int, y1: int,
    *, extra_left: int = 0, extra_right: int = 0,
) -> tuple[int, int, int, int]:
    """Return a whole-entry crop box whose horizontal borders fall in whitespace.

    Older builds stopped the right edge at the nominal printed column width and
    used the first-page margin as the same left extension for every column. On
    multi-column dictionaries this visibly clipped glyph overhang/illustrations
    at the right edge and left unused gutter whitespace.  The stable geometric
    rule is to split each inter-column gutter at its midpoint: the left half
    belongs to the column on the right and the right half to the column on the
    left.  The outer page margins use half of the first-column margin.

    ``extra_left``/``extra_right`` are persisted reference-page distances and
    are resolved to the current page's canonical full-resolution pixels here.
    """
    col = max(0, min(len(geometry.column_starts) - 1, int(col)))
    canonical_width = geometry.transform.canonical_size(image.size)[0]
    extra_left_px = max(
        0, stored_geometry_to_canonical(int(extra_left), canonical_width, settings),
    )
    extra_right_px = max(
        0, stored_geometry_to_canonical(int(extra_right), canonical_width, settings),
    )

    # Use the robust width of the ordinary columns. derive_geometry intentionally
    # lets the final column extend to the page edge for detection, which is not
    # the correct width for dictionary-entry cropping.
    widths = list(geometry.column_widths[:-1]) if len(geometry.column_widths) > 1 else list(geometry.column_widths)
    nominal_width = max(1, round(float(np.median(widths or geometry.column_widths or [image.width]))))
    gutter_px = max(
        0,
        stored_geometry_to_canonical(settings.gutter, canonical_width, settings),
    )
    half_gutter = gutter_px // 2
    outer_margin = max(0, geometry.column_starts[0] // 2)

    left_margin = outer_margin if col == 0 else half_gutter
    right_margin = outer_margin if col == len(geometry.column_starts) - 1 else gutter_px - half_gutter
    path_left, path_right = geometry.x_bounds(col, y0, y1)
    canonical_size = geometry.transform.canonical_size(image.size)
    canonical_box = (
        path_left - left_margin - extra_left_px,
        y0,
        path_right + nominal_width + right_margin + extra_right_px,
        y1,
    )
    canonical_box = (
        max(0, canonical_box[0]),
        max(0, canonical_box[1]),
        min(canonical_size[0], canonical_box[2]),
        min(canonical_size[1], canonical_box[3]),
    )
    return clamp_box(geometry.transform.canonical_box_to_source(canonical_box, image.size), image)


def entry_crop_column_boxes(
    image: Image.Image, settings: AppSettings, *, top_y: int | None = None, bottom_y: int | None = None,
    extra_left: int = 0, extra_right: int = 0,
) -> list[tuple[int, int, int, int]]:
    """Return full-height boxes using the exact whole-entry horizontal geometry."""
    geometry = derive_geometry(image, settings)
    top, bottom = entry_crop_bounds(image, settings, top_y=top_y, bottom_y=bottom_y)
    return [
        _entry_crop_box_for_column(
            image, settings, geometry, col, top, bottom,
            extra_left=extra_left, extra_right=extra_right,
        )
        for col in range(len(geometry.column_starts))
    ]

def _normalized_crop_name(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).strip().casefold()
    value = re.sub(r"\s+", " ", value)
    # A PPP may already carry a display suffix such as (P1); it still belongs
    # to the headword before that suffix.
    value = re.sub(r"\s*\(p\d+\)\s*$", "", value, flags=re.I)
    return value


def polygon_display_name(region: PolygonRegion, index: int) -> str:
    label = str(region.label or "").strip()
    fields = label.split("|")
    if len(fields) >= 3 and fields[1].strip():
        return fields[1].strip()
    return label or f"P_{index + 1:02d}"


def _point_in_rect(point: tuple[int, int], box: tuple[int, int, int, int]) -> bool:
    x, y = point
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _point_in_polygon(point: tuple[int, int], points: list[tuple[int, int]]) -> bool:
    x, y = point
    inside = False
    n = len(points)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = points[i]; xj, yj = points[j]
        if ((yi > y) != (yj > y)):
            denom = (yj - yi) or 1e-12
            cross_x = (xj - xi) * (y - yi) / denom + xi
            if x <= cross_x:
                inside = not inside
        j = i
    return inside


def _orientation(a, b, c) -> int:
    v = (b[1]-a[1])*(c[0]-b[0]) - (b[0]-a[0])*(c[1]-b[1])
    if abs(v) < 1e-9: return 0
    return 1 if v > 0 else 2


def _on_segment(a, b, c) -> bool:
    return min(a[0], c[0]) <= b[0] <= max(a[0], c[0]) and min(a[1], c[1]) <= b[1] <= max(a[1], c[1])


def _segments_intersect(p1, q1, p2, q2) -> bool:
    o1, o2, o3, o4 = _orientation(p1,q1,p2), _orientation(p1,q1,q2), _orientation(p2,q2,p1), _orientation(p2,q2,q1)
    if o1 != o2 and o3 != o4: return True
    if o1 == 0 and _on_segment(p1,p2,q1): return True
    if o2 == 0 and _on_segment(p1,q2,q1): return True
    if o3 == 0 and _on_segment(p2,p1,q2): return True
    if o4 == 0 and _on_segment(p2,q1,q2): return True
    return False


def polygon_intersects_box(points: list[tuple[int, int]], box: tuple[int, int, int, int]) -> bool:
    if len(points) < 3:
        return False
    if any(_point_in_rect(p, box) for p in points):
        return True
    corners = [(box[0],box[1]),(box[2],box[1]),(box[2],box[3]),(box[0],box[3])]
    if any(_point_in_polygon(c, points) for c in corners):
        return True
    rect_edges = list(zip(corners, corners[1:]+corners[:1]))
    poly_edges = list(zip(points, points[1:]+points[:1]))
    return any(_segments_intersect(a,b,c,d) for a,b in poly_edges for c,d in rect_edges)


def polygon_fully_inside_boxes(points: list[tuple[int, int]], boxes: list[tuple[int,int,int,int]]) -> bool:
    return bool(points) and all(any(_point_in_rect(point, box) for box in boxes) for point in points)


def _box_intersection_area(a: tuple[int,int,int,int], b: tuple[int,int,int,int]) -> int:
    x0,y0=max(a[0],b[0]),max(a[1],b[1]); x1,y1=min(a[2],b[2]),min(a[3],b[3])
    return max(0,x1-x0)*max(0,y1-y0)


def _base_entry_crop_pieces(
    image: Image.Image, entries: list[Entry], settings: AppSettings,
    *, top_y: int | None = None, bottom_y: int | None = None,
    entry_left_padding: int = 0, entry_right_padding: int = 0,
) -> tuple[list[Entry], list[EntryCropPiecePlan]]:
    geometry = derive_geometry(image, settings)
    canonical_width = geometry.transform.canonical_size(image.size)[0]
    character_height = stored_geometry_to_canonical(
        settings.character_height, canonical_width, settings,
    )
    row_padding = stored_geometry_to_canonical(
        settings.row_padding, canonical_width, settings,
    )
    row_height = max(1, character_height + row_padding)
    top, bottom = entry_crop_bounds(
        image, settings, top_y=top_y, bottom_y=bottom_y,
    )
    ordered = sort_entries_reading_order(entries, geometry)
    row_guard = round(row_height * 0.6)
    pieces: list[EntryCropPiecePlan] = []
    piece_counts: dict[int, int] = {}

    def col_box(col: int, y0: int, y1: int) -> tuple[int,int,int,int]:
        return _entry_crop_box_for_column(
            image, settings, geometry, col, y0, y1,
            extra_left=entry_left_padding, extra_right=entry_right_padding,
        )

    def add(output_index: int, entry_ref: int | None, word: str, box, suffix: str | None = None):
        if box[3]-box[1] <= 1: return
        if suffix is None:
            piece_counts[output_index]=piece_counts.get(output_index,0)+1
            suffix=f"({piece_counts[output_index]})"
        pieces.append(EntryCropPiecePlan(output_index, entry_ref, word, box, suffix))

    if not ordered:
        for col in range(len(geometry.column_starts)):
            add(0, None, "_上页末词条_", col_box(col,top,bottom), f"(0-{col+1})")
        return ordered, pieces
    _first_u, first_v = geometry.source_to_canonical(ordered[0].x, ordered[0].y)
    first_col=column_index(ordered[0].x, geometry, ordered[0].y)
    for col in range(first_col): add(0,None,"_上页末词条_",col_box(col,top,bottom),f"(0-{col+1})")
    if first_v-top>row_guard: add(0,None,"_上页末词条_",col_box(first_col,top,first_v),f"(0-{first_col+1})")
    for index, entry in enumerate(ordered):
        _entry_u, entry_v = geometry.source_to_canonical(entry.x, entry.y)
        col=column_index(entry.x,geometry,entry.y)
        next_entry=ordered[index+1] if index+1<len(ordered) else None
        next_v = geometry.source_to_canonical(next_entry.x, next_entry.y)[1] if next_entry else bottom
        next_col=column_index(next_entry.x,geometry,next_entry.y) if next_entry else len(geometry.column_starts)
        y0=max(top,entry_v-abs(row_padding))
        y1=next_v if next_entry and next_col==col else bottom
        add(index,index,entry.word,col_box(col,y0,y1))
        if next_entry and next_col>col:
            for continuation_col in range(col+1,next_col): add(index,index,entry.word,col_box(continuation_col,top,bottom))
            if next_v-top>row_guard: add(index,index,entry.word,col_box(next_col,top,next_v))
        elif next_entry is None:
            for continuation_col in range(col+1,len(geometry.column_starts)): add(index,index,entry.word,col_box(continuation_col,top,bottom))
    return ordered, pieces


def build_page_crop_plan(
    image: Image.Image, entries: list[Entry], polygons: list[PolygonRegion], settings: AppSettings,
    *, top_y: int | None = None, bottom_y: int | None = None, illustration_margin: int = 0,
    entry_left_padding: int = 0, entry_right_padding: int = 0,
    integrate_illustrations: bool = True,
) -> PageCropPlan:
    """Plan entry and PPP crops before any pixels are written.

    PPP display names associate to headwords by normalized exact name.  Linked
    PPPs contained by or intersecting their entry crop travel with that entry;
    linked PPPs completely outside become standalone P images. Unlinked PPPs are
    standalone and are removed from ordinary entry crops.
    """
    ordered, pieces = _base_entry_crop_pieces(
        image, entries, settings, top_y=top_y, bottom_y=bottom_y,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
    )
    boxes_by_entry: dict[int,list[tuple[int,int,int,int]]] = {}
    piece_indices_by_entry: dict[int,list[int]] = {}
    for pos,piece in enumerate(pieces):
        if piece.entry_ref_index is not None:
            boxes_by_entry.setdefault(piece.entry_ref_index,[]).append(piece.box)
            piece_indices_by_entry.setdefault(piece.entry_ref_index,[]).append(pos)
    names: dict[str,list[int]] = {}
    for i,entry in enumerate(ordered): names.setdefault(_normalized_crop_name(entry.word),[]).append(i)
    illustration_top = settings.start_y if top_y is None else int(top_y)
    illustration_bottom = 0 if bottom_y is None else int(bottom_y)
    top,bottom,margin_px=illustration_crop_bounds(image,settings,top_y=illustration_top,bottom_y=illustration_bottom,margin=illustration_margin)
    illustrations: list[IllustrationCropPlan] = []
    linked_inside: dict[int,list[int]] = {}
    partial_merge: dict[int,list[int]] = {}
    for pi,region in enumerate(polygons):
        name=polygon_display_name(region,pi)
        candidates=names.get(_normalized_crop_name(name),[])
        chosen=None; relation="unassociated"
        if candidates:
            scored=[]
            pbox=_polygon_bbox(region)
            for ei in candidates:
                boxes=boxes_by_entry.get(ei,[])
                if polygon_fully_inside_boxes(region.points,boxes): rank=2; rel="contained"
                elif any(polygon_intersects_box(region.points,b) for b in boxes): rank=1; rel="partial"
                else: rank=0; rel="outside"
                overlap=sum(_box_intersection_area(pbox,b) for b in boxes) if pbox else 0
                scored.append((rank,overlap,-ei,ei,rel))
            _rank,_overlap,_neg,chosen,relation=max(scored)
        word=ordered[chosen].word if chosen is not None else ""
        box=illustration_polygon_box(image,region,top=top,bottom=bottom,margin_px=margin_px)
        standalone = relation in {"outside", "unassociated"} or (relation == "partial" and not integrate_illustrations)
        illustrations.append(IllustrationCropPlan(pi,name,chosen,word,relation,standalone,box))
        if integrate_illustrations and chosen is not None and relation in {"contained","partial"}:
            linked_inside.setdefault(chosen,[]).append(pi)
        if integrate_illustrations and chosen is not None and relation=="partial":
            pbox=_polygon_bbox(region)
            candidates_pieces=piece_indices_by_entry.get(chosen,[])
            if candidates_pieces:
                best=max(candidates_pieces,key=lambda pos:_box_intersection_area(pbox,pieces[pos].box) if pbox else 0)
                partial_merge.setdefault(best,[]).append(pi)
    illustrated_entries=set(linked_inside)
    for pos,piece in enumerate(pieces):
        if piece.entry_ref_index in illustrated_entries:
            piece.source_mode="linked_original"
        if pos in partial_merge:
            piece.merge_polygon_indices=tuple(partial_merge[pos])
    return PageCropPlan(pieces,illustrations,bool(integrate_illustrations))


def page_crop_plan_dict(plan: PageCropPlan) -> dict:
    return {
        "version": 3,
        "coordinate_space": SOURCE_COORDINATE_SPACE,
        "box_format": "source_xyxy",
        "integrate_illustrations": bool(plan.integrate_illustrations),
        "entry_pieces": [
            {
                "output_index": p.output_index,
                "entry_ref_index": p.entry_ref_index,
                "word": p.word,
                "box": list(p.box),
                "suffix": p.suffix,
                "source_mode": p.source_mode,
                "merge_polygon_indices": list(p.merge_polygon_indices),
            }
            for p in plan.entry_pieces
        ],
        "illustrations": [
            {
                "polygon_index": d.polygon_index,
                "name": d.name,
                "associated_entry_index": d.associated_entry_index,
                "associated_word": d.associated_word,
                "relation": d.relation,
                "standalone": d.standalone,
                "box": list(d.box) if d.box is not None else None,
            }
            for d in plan.illustrations
        ],
    }


def write_page_crop_plan(root: Path, page_stem: str, plan: PageCropPlan) -> Path:
    folder = qt_root(Path(root)) / "CropPlan"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{page_stem}.json"
    tmp = folder / f".{page_stem}.json.tmp"
    tmp.write_text(json.dumps(page_crop_plan_dict(plan), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def _whitefill_polygons(image: Image.Image, polygons: list[PolygonRegion], skip: set[int] | None = None) -> Image.Image:
    out=image.copy().convert("RGB")
    draw=ImageDraw.Draw(out)
    skip=skip or set()
    for i,region in enumerate(polygons):
        if i in skip or len(region.points)<3: continue
        draw.polygon(region.points,fill=(255,255,255))
    return out


def _save_union_crop(image: Image.Image, path: Path, base_box: tuple[int,int,int,int], regions: list[PolygonRegion]) -> tuple[int,int,int,int]:
    boxes=[base_box]+[b for r in regions if (b:=_polygon_bbox(r)) is not None]
    union=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
    union=clamp_box(union,image)
    crop=image.crop(union).convert("RGB")
    mask=Image.new("L",crop.size,0); d=ImageDraw.Draw(mask)
    d.rectangle((base_box[0]-union[0],base_box[1]-union[1],base_box[2]-union[0],base_box[3]-union[1]),fill=255)
    for region in regions:
        d.polygon([(x-union[0],y-union[1]) for x,y in region.points],fill=255)
    white=Image.new("RGB",crop.size,"white"); white.paste(crop,(0,0),mask); path.parent.mkdir(parents=True,exist_ok=True); white.save(path)
    crop.close(); mask.close(); white.close()
    return union


def split_whole_entries(
    image_path: Path, entries: list[Entry], settings: AppSettings, output_dir: Path,
    *, top_y: int | None = None, bottom_y: int | None = None, polygons: list[PolygonRegion] | None = None,
    entry_left_padding: int = 0, entry_right_padding: int = 0,
    integrate_illustrations: bool = True,
) -> list[CropRecord]:
    with Image.open(image_path) as opened:
        image = normalize_page_rgb(opened)
    polygons = list(polygons or [])
    plan = build_page_crop_plan(
        image, entries, polygons, settings, top_y=top_y, bottom_y=bottom_y,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        integrate_illustrations=integrate_illustrations,
    )
    write_page_crop_plan(image_path.parent, image_path.stem, plan)
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[CropRecord] = []

    if not integrate_illustrations:
        # The user explicitly requested pure headword geometry.  PPPs neither
        # expand/union entry crops nor alter the crop order, and are not white-
        # filled from headword images.  Illustrations already inside an entry
        # therefore remain naturally visible in that headword crop.
        for piece in plan.entry_pieces:
            filename = entry_crop_piece_filename(image_path.stem, piece)
            saved = _save_crop(image, output_dir / filename, piece.box)
            records.append(CropRecord(image_path.name, piece.output_index, piece.word, filename, saved))
        image.close()
    else:
        # Linked-illustration entries are exported first. Keep only their own linked
        # PPPs; unrelated PPPs are whitened even at this stage.
        illustrated_entries = sorted({p.entry_ref_index for p in plan.entry_pieces if p.source_mode == "linked_original" and p.entry_ref_index is not None})
        completed_positions: set[int] = set()
        for entry_ref in illustrated_entries:
            keep = {i.polygon_index for i in plan.illustrations if i.associated_entry_index == entry_ref and i.relation in {"contained", "partial"}}
            source = _whitefill_polygons(image, polygons, skip=keep)
            try:
                for pos, piece in enumerate(plan.entry_pieces):
                    if piece.entry_ref_index != entry_ref:
                        continue
                    filename = entry_crop_piece_filename(image_path.stem, piece)
                    merge_regions = [polygons[i] for i in piece.merge_polygon_indices if 0 <= i < len(polygons)]
                    if merge_regions:
                        saved_box = _save_union_crop(source, output_dir / filename, piece.box, merge_regions)
                    else:
                        saved_box = _save_crop(source, output_dir / filename, piece.box)
                    records.append(CropRecord(image_path.name, piece.output_index, piece.word, filename, saved_box))
                    completed_positions.add(pos)
            finally:
                source.close()

        # All PPPs are then removed before ordinary headword crops are produced.
        cleaned = _whitefill_polygons(image, polygons)
        try:
            for pos, piece in enumerate(plan.entry_pieces):
                if pos in completed_positions:
                    continue
                filename = entry_crop_piece_filename(image_path.stem, piece)
                saved = _save_crop(cleaned, output_dir / filename, piece.box)
                records.append(CropRecord(image_path.name, piece.output_index, piece.word, filename, saved))
        finally:
            cleaned.close(); image.close()

    # Pixel operations intentionally run illustrated entries first, but the
    # manifest and returned record order remain the dictionary/page order.
    # This preserves downstream PicDic expectations while retaining the safe
    # white-fill execution sequence.
    by_filename = {r.filename: r for r in records}
    ordered_records: list[CropRecord] = []
    for piece in plan.entry_pieces:
        filename = entry_crop_piece_filename(image_path.stem, piece)
        record = by_filename.get(filename)
        if record is not None:
            ordered_records.append(record)
    manifest = "".join(f"{r.page}|{r.index:03d}|{r.word}|{r.filename}\n" for r in ordered_records)
    (output_dir / f"{image_path.stem}.PWWords").write_text(manifest, encoding="utf-8")
    return ordered_records


def append_crop_log(root: Path, records: list[CropRecord]) -> None:
    if not records:
        return
    log = crop_log_path(root)
    with log.open("a", encoding="utf-8") as handle:
        for record in records:
            left, top, right, bottom = record.box
            handle.write(
                f"{record.page}\t{record.filename}\t{left}\t{top}\t{right-left}\t{bottom-top}\n"
            )



AUTO_ILLUSTRATION_LABEL_TOKEN = "|AUTO_"


def _rle_components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """Connected components for a small binary mask using row runs.

    This avoids an OpenCV/SciPy dependency.  The detector works on a reduced
    analysis image, so run-length union/find is both fast and memory-light.
    Returned boxes are ``(x0, y0, x1, y1, area)`` with x1/y1 exclusive.
    """
    mask = np.asarray(mask, dtype=bool)
    h, w = mask.shape
    parent: list[int] = []
    rank: list[int] = []
    boxes: list[list[int]] = []

    def make(x0: int, x1: int, y: int) -> int:
        i = len(parent)
        parent.append(i); rank.append(0)
        boxes.append([x0, y, x1, y + 1, x1 - x0])
        return i

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> int:
        ra, rb = find(a), find(b)
        if ra == rb:
            return ra
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1
        return ra

    prev: list[tuple[int, int, int]] = []
    for y in range(h):
        row = mask[y]
        padded = np.r_[False, row, False].astype(np.int8)
        changes = np.diff(padded)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        current: list[tuple[int, int, int]] = []
        j = 0
        for x0, x1 in zip(starts.tolist(), ends.tolist()):
            cid = make(x0, x1, y)
            while j < len(prev) and prev[j][1] < x0 - 1:
                j += 1
            k = j
            while k < len(prev) and prev[k][0] <= x1 + 1:
                px0, px1, pid = prev[k]
                if px1 >= x0 - 1:
                    union(cid, pid)
                k += 1
            current.append((x0, x1, cid))
        prev = current

    merged: dict[int, list[int]] = {}
    for i, box in enumerate(boxes):
        r = find(i)
        target = merged.setdefault(r, [box[0], box[1], box[2], box[3], 0])
        target[0] = min(target[0], box[0]); target[1] = min(target[1], box[1])
        target[2] = max(target[2], box[2]); target[3] = max(target[3], box[3])
        target[4] += box[4]
    return [tuple(v) for v in merged.values()]


def _box_gap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int]:
    ax0, ay0, ax1, ay1 = a; bx0, by0, bx1, by1 = b
    gx = max(0, max(ax0, bx0) - min(ax1, bx1))
    gy = max(0, max(ay0, by0) - min(ay1, by1))
    return gx, gy


def _merge_nearby_boxes(boxes: list[tuple[int, int, int, int]], gap: int) -> list[tuple[int, int, int, int]]:
    boxes = [tuple(map(int, b)) for b in boxes]
    changed = True
    while changed and len(boxes) > 1:
        changed = False
        out: list[tuple[int, int, int, int]] = []
        used = [False] * len(boxes)
        for i, box in enumerate(boxes):
            if used[i]:
                continue
            x0, y0, x1, y1 = box
            used[i] = True
            for j in range(i + 1, len(boxes)):
                if used[j]:
                    continue
                other = boxes[j]
                gx, gy = _box_gap((x0, y0, x1, y1), other)
                # Merge close fragments of one drawing, but do not bridge two
                # separate text columns or distant illustrations.
                vertical_overlap = min(y1, other[3]) - max(y0, other[1])
                horizontal_overlap = min(x1, other[2]) - max(x0, other[0])
                if (gx <= gap and gy <= gap and (vertical_overlap > 0 or horizontal_overlap > 0)):
                    x0 = min(x0, other[0]); y0 = min(y0, other[1])
                    x1 = max(x1, other[2]); y1 = max(y1, other[3])
                    used[j] = True; changed = True
            out.append((x0, y0, x1, y1))
        boxes = out
    return boxes


def _polygon_bbox(region: PolygonRegion) -> tuple[int, int, int, int] | None:
    if len(region.points) < 3:
        return None
    xs = [p[0] for p in region.points]; ys = [p[1] for p in region.points]
    return min(xs), min(ys), max(xs), max(ys)


def _overlap_fraction(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / area


def is_auto_illustration_region(region: PolygonRegion) -> bool:
    return AUTO_ILLUSTRATION_LABEL_TOKEN in str(region.label or "").upper()


def detect_illustration_regions(
    image_path: Path, settings: AppSettings, *, analysis_column_width: int = 520,
) -> list[PolygonRegion]:
    """Detect large non-text illustration-like ink components on a dictionary page.

    The detector deliberately uses only Pillow/NumPy so the feature works in the
    normal installation.  Detection is performed column-by-column on a reduced
    image.  A slight 3x3 dilation joins strokes within drawings while the minimum
    height/area tests reject ordinary text lines and page rules.  Results are
    rectangular four-point polygons in original-image coordinates, compatible
    with the existing PPP editor/cropper.
    """
    with Image.open(image_path) as opened:
        image = normalize_page_rgb(opened)
    try:
        geometry = derive_geometry(image, settings)
        work_image = geometry.transform.canonical_image_for_analysis(image)
        canonical_width = geometry.transform.canonical_size(image.size)[0]
        source_margin = max(
            2,
            stored_geometry_to_canonical(
                max(0, int(getattr(settings, "illustration_detect_padding", 8))),
                canonical_width,
                settings,
            ),
        )
        source_margin_right = max(
            source_margin,
            stored_geometry_to_canonical(
                max(0, int(getattr(settings, "illustration_detect_right_padding", 16))),
                canonical_width,
                settings,
            ),
        )
        results: list[PolygonRegion] = []
        for column, start in enumerate(geometry.column_starts):
            width = geometry.column_widths[column]
            base_x0 = max(0, int(start))
            base_x1 = min(work_image.width, int(start + width))
            # Illustrations frequently extend a little into the inter-column
            # gutter. The old detector clipped analysis exactly at column_width,
            # which systematically shortened the right edge. Borrow only the
            # near half of the gutter so the next text column cannot be swallowed.
            if column + 1 < len(geometry.column_starts):
                next_start = int(geometry.column_starts[column + 1])
                free_right = max(0, next_start - base_x1)
                right_room = min(max(source_margin_right, free_right // 2), max(source_margin_right, round(width * 0.10)))
            else:
                free_right = max(0, work_image.width - base_x1)
                right_room = min(free_right, max(source_margin_right, round(width * 0.08)))
            x0 = base_x0
            x1 = min(work_image.width, base_x1 + max(0, right_room))
            y0 = max(0, int(geometry.top)); y1 = min(work_image.height, int(geometry.bottom))
            if x1 - x0 < 40 or y1 - y0 < 80:
                continue
            crop = work_image.crop((x0, y0, x1, y1)).convert("L")
            try:
                a_scale = min(1.0, analysis_column_width / max(1, crop.width))
                aw = max(1, round(crop.width * a_scale)); ah = max(1, round(crop.height * a_scale))
                small = crop if a_scale == 1.0 else crop.resize((aw, ah), Image.Resampling.BILINEAR)
                try:
                    # Mix adaptive and absolute-dark masks: adaptive catches light
                    # halftones/line art, absolute-dark keeps strong contours.
                    adaptive = _adaptive_dark_mask(small, 19, 16)
                    arr = np.asarray(small, dtype=np.uint8)
                    dark = np.logical_or(adaptive, arr < 170)
                    mask_img = Image.fromarray((dark.astype(np.uint8) * 255), mode="L")
                    try:
                        joined = np.asarray(mask_img.filter(ImageFilter.MaxFilter(3)), dtype=np.uint8) > 0
                    finally:
                        mask_img.close()
                    comps = _rle_components(joined)
                    min_h = max(18, round(0.028 * ah))
                    min_w = max(18, round(0.055 * aw))
                    min_bbox_area = max(500, round(0.0022 * aw * ah))
                    candidates: list[tuple[int, int, int, int]] = []
                    for cx0, cy0, cx1, cy1, area in comps:
                        bw, bh = cx1 - cx0, cy1 - cy0
                        bbox_area = bw * bh
                        if bw < min_w or bh < min_h or bbox_area < min_bbox_area:
                            continue
                        # Connected occupancy rejects large whitespace boxes, while
                        # the height threshold rejects normal dictionary text lines.
                        occupancy = area / max(1, bbox_area)
                        if occupancy < 0.035:
                            continue
                        if bw / max(1, bh) > 7.0 and bh < 0.08 * ah:
                            continue
                        candidates.append((cx0, cy0, cx1, cy1))
                    gap = max(5, round(0.018 * aw))
                    candidates = _merge_nearby_boxes(candidates, gap)
                    for cx0, cy0, cx1, cy1 in candidates:
                        bw, bh = cx1 - cx0, cy1 - cy0
                        if bh < min_h or bw < min_w:
                            continue
                        sx0 = x0 + round(cx0 / a_scale) - source_margin
                        sy0 = y0 + round(cy0 / a_scale) - source_margin
                        sx1 = x0 + round(cx1 / a_scale) + source_margin_right
                        sy1 = y0 + round(cy1 / a_scale) + source_margin
                        sx0 = max(x0, sx0); sy0 = max(y0, sy0)
                        sx1 = min(x1, sx1); sy1 = min(y1, sy1)
                        if sx1 - sx0 < 8 or sy1 - sy0 < 8:
                            continue
                        results.append(PolygonRegion("", [(sx0, sy0), (sx1, sy0), (sx1, sy1), (sx0, sy1)]))
                finally:
                    if small is not crop:
                        small.close()
            finally:
                crop.close()
        # Merge any boxes touching a column boundary only if they truly overlap;
        # most dictionary illustrations stay within one column, so this is rare.
        if geometry.transform.kind == "identity":
            return results
        return [
            PolygonRegion(
                region.label,
                [geometry.canonical_to_source(x, y) for x, y in region.points],
            )
            for region in results
        ]
    finally:
        if "work_image" in locals():
            work_image.close()
        image.close()


def detect_illustrations_to_ppp(image_path: Path, settings: AppSettings) -> dict[str, int]:
    """Detect illustrations and safely update one page's PPP file.

    Manual polygons are never overwritten.  Re-running detection replaces only
    previous AUTO polygons, making the operation idempotent and safe to tune.
    """
    image_path = Path(image_path)
    read_path = ppp_read_path_for_image(image_path)
    write_path = ppp_write_path_for_image(image_path)
    existing = read_ppp(read_path)
    manual = [r for r in existing if not is_auto_illustration_region(r)]
    detected = detect_illustration_regions(image_path, settings)
    manual_boxes = [b for r in manual if (b := _polygon_bbox(r)) is not None]
    accepted: list[PolygonRegion] = []
    for region in detected:
        box = _polygon_bbox(region)
        if box is None:
            continue
        if any(_overlap_fraction(box, mb) >= 0.25 for mb in manual_boxes):
            continue
        accepted.append(region)
    for index, region in enumerate(accepted, 1):
        region.label = f"{image_path.stem}|AUTO_{index:02d}|1|{image_path.stem}|"
    write_ppp(write_path, manual + accepted, image_path.stem)
    return {"manual": len(manual), "auto": len(accepted), "total": len(manual) + len(accepted)}


def detect_illustrations_job(image_path: str, settings: AppSettings) -> dict[str, int]:
    """Background-safe one-page illustration detector used by the GUI batch runner."""
    return detect_illustrations_to_ppp(Path(image_path), settings)

def illustration_crop_bounds(
    image: Image.Image,
    settings: AppSettings | None = None,
    *,
    top_y: int = 0,
    bottom_y: int = 0,
    margin: int = 0,
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
    canonical_width, _canonical_height = transform.canonical_size(image.size)
    top_canonical = stored_geometry_to_canonical(
        max(0, int(top_y)), canonical_width, effective,
    )
    bottom_canonical = (
        stored_geometry_to_canonical(max(0, int(bottom_y)), canonical_width, effective)
        if int(bottom_y) > 0 else 0
    )
    margin_px = max(
        0, stored_geometry_to_canonical(max(0, int(margin)), canonical_width, effective),
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
) -> IllustrationSplitResult:
    """Export only PPPs that are not already carried by an associated entry crop."""
    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    effective_settings = settings or AppSettings(geometry_reference_width=image.width)
    rgb_for_plan = image.convert("RGB")
    try:
        plan = build_page_crop_plan(
            rgb_for_plan, list(entries or []), polygons, effective_settings,
            top_y=top_y, bottom_y=bottom_y, illustration_margin=margin,
            entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
            integrate_illustrations=integrate_illustrations,
        )
    finally:
        rgb_for_plan.close()
    write_page_crop_plan(image_path.parent, image_path.stem, plan)
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[CropRecord] = []
    events: list[IllustrationCropEvent] = []
    manifest: list[str] = []
    p_counter: dict[int,int] = {}
    for decision in plan.illustrations:
        region=polygons[decision.polygon_index]
        if not decision.standalone:
            action="跳过：已完整包含于词条切图" if decision.relation=="contained" else "跳过：与词条切图部分相交，已合并到词条切图"
            events.append(IllustrationCropEvent(image_path.name,decision.polygon_index+1,decision.name,decision.associated_word,decision.relation,action,""))
            manifest.append(f"{decision.polygon_index+1:03d}|{decision.name}|SKIP|{decision.relation}|{decision.associated_word}")
            continue
        box=decision.box
        if box is None:
            events.append(IllustrationCropEvent(image_path.name,decision.polygon_index+1,decision.name,decision.associated_word,decision.relation,"跳过：超出有效切图范围",""))
            continue
        crop=image.crop(box)
        mask=Image.new("L",crop.size,0); draw=ImageDraw.Draw(mask)
        draw.polygon([(x-box[0],y-box[1]) for x,y in region.points],fill=255)
        crop.putalpha(mask)
        if decision.associated_entry_index is not None:
            ei=decision.associated_entry_index
            p_counter[ei]=p_counter.get(ei,0)+1
            filename=f"{image_path.stem}_WW_{ei:03d}(P{p_counter[ei]}).png"
        else:
            filename=f"{image_path.stem}_PIC_{decision.polygon_index+1:03d}.png"
        crop.save(output_dir/filename); crop.close(); mask.close()
        label=region.label or f"{image_path.stem}|P_{decision.polygon_index+1:02d}|1|{image_path.stem}|"
        records.append(CropRecord(image_path.name,decision.polygon_index+1,decision.associated_word or label,filename,box))
        if decision.relation == "partial" and not integrate_illustrations:
            action = "单独插图切图（部分超出词条；未综合插图）"
        else:
            action="单独插图切图（关联词条外部）" if decision.associated_entry_index is not None else "单独插图切图（未关联词条）"
        events.append(IllustrationCropEvent(image_path.name,decision.polygon_index+1,decision.name,decision.associated_word,decision.relation,action,filename))
        manifest.append(f"{decision.polygon_index+1:03d}|{label}|{filename}|{decision.relation}|{decision.associated_word}")
    (output_dir/f"{image_path.stem}.PPPictures").write_text("\n".join(manifest)+("\n" if manifest else ""),encoding="utf-8")
    image.close()
    return IllustrationSplitResult(records,events)


def append_illustration_crop_log(root: Path, events: list[IllustrationCropEvent]) -> None:
    if not events: return
    path=qt_root(root)/"_illustration_crop_log.txt"; path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as handle:
        for e in events:
            handle.write(f"{e.page}\tPPP{e.polygon_index:03d}\t{e.name}\t{e.associated_word}\t{e.relation}\t{e.action}\t{e.filename}\n")


def resolve_crop_worker_count(configured: int = 0, cpu_count: int | None = None) -> int:
    """Resolve a conservative process count for page-level crop jobs.

    Cropping large dictionary scans can be memory hungry because every worker
    holds one full source image.  Automatic mode therefore uses at most four
    workers even on large machines; users may explicitly request up to eight.
    Setting the value to 1 preserves serial behaviour.
    """
    cpus = max(1, int(cpu_count if cpu_count is not None else (os.cpu_count() or 1)))
    try:
        requested = int(configured)
    except (TypeError, ValueError):
        requested = 0
    if requested > 0:
        return max(1, min(requested, cpus, 8))
    if cpus <= 2:
        return 1
    return min(4, max(2, cpus // 2))


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
) -> list[CropRecord]:
    """Spawn-safe worker: build the crop plan first, then execute it."""
    page = Path(image_path)
    entries = read_pdic(Path(pdic_file))
    polygons = read_ppp(Path(ppp_file)) if ppp_file else []
    return split_whole_entries(
        page, entries, settings, Path(output_dir), top_y=top_y, bottom_y=bottom_y, polygons=polygons,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        integrate_illustrations=integrate_illustrations,
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
) -> IllustrationSplitResult:
    """Spawn-safe worker: plan PPP/entry relations before exporting standalone PPPs."""
    page = Path(image_path)
    polygons = read_ppp(Path(ppp_file))
    entries = read_pdic(Path(pdic_file)) if pdic_file else []
    return split_illustrations(
        page, polygons, Path(output_dir), settings, top_y=top_y, bottom_y=bottom_y, margin=margin, entries=entries,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        integrate_illustrations=integrate_illustrations,
    )
