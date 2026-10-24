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
from .geometry import column_offsets as _column_offsets
from .geometry import geometry_construction as _geometry_construction
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
from .ordinary import legacy_brightness_sampling as _legacy_brightness_sampling
from .ordinary import legacy_separator_search as _legacy_separator_search
from .ordinary import legacy_page_detection as _legacy_page_detection
from .ordinary import cjk_marker_reconciliation as _cjk_marker_reconciliation
from .quality import detection_entry_fusion as _detection_entry_fusion
from .geometry import column_path_tracking as _column_path_tracking
from .ocr import ordinary_marker_text_enrichment as _ordinary_marker_text_enrichment
from .detection import page_method_dispatch as _page_method_dispatch
from .refinement import existing_entry_positions as _existing_entry_positions
from .ocr import legacy_entry_text_reading as _legacy_entry_text_reading
from .ordinary import separator_position_policy as _separator_policy
from .ordinary import auto_layout_policy as _auto_layout_policy
from .ordinary import fusion_entry_mapping as _fusion_entry_mapping
from .ordinary import review_signals as _review_signals
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
    """Historical curved column path tracking with live processing callbacks."""
    return _column_path_tracking.estimate_column_paths(
        analysis, scale, starts_analysis, widths_analysis,
        top_analysis, bottom_analysis, settings, geometry_to_analysis,
        deps={
            "_source_px": _source_px,
            "_adaptive_dark_mask": _adaptive_dark_mask,
            "_COLUMN_TRACK_ADAPTIVE_BLOCK": _COLUMN_TRACK_ADAPTIVE_BLOCK,
            "_COLUMN_TRACK_ADAPTIVE_C": _COLUMN_TRACK_ADAPTIVE_C,
            "_column_tracking_dimensions": _column_tracking_dimensions,
            "_smooth_track": _smooth_track,
            "ColumnPath": ColumnPath,
            "np": np,
            "ImageOps": ImageOps,
        },
    )


def _column_start_offsets_canonical(
    settings: AppSettings, count: int, canonical_width: int,
) -> list[int]:
    """Historical persisted per-column offsets; preserve current pixel conversion."""
    return _column_offsets.column_start_offsets_canonical(
        settings, count, canonical_width, source_px_fn=_source_px,
    )


def apply_column_start_offsets(
    base_starts: list[int], offsets: list[int], *, gutter: int, max_x: int,
) -> list[int]:
    """Historical column ordering policy, delegated to pure geometry."""
    return _column_offsets.apply_column_start_offsets(
        base_starts, offsets, gutter=gutter, max_x=max_x,
    )

def _derive_nominal_geometry_canonical(
    image_width: int, image_height: int, settings: AppSettings,
) -> Geometry:
    return _geometry_construction.derive_nominal_geometry_canonical(
        image_width, image_height, settings,
        source_px_fn=_source_px, offsets_fn=_column_start_offsets_canonical,
        apply_offsets_fn=apply_column_start_offsets, column_path_cls=ColumnPath,
        geometry_cls=Geometry,
    )


def derive_nominal_geometry(image_width: int, image_height: int, settings: AppSettings) -> Geometry:
    return _geometry_construction.derive_nominal_geometry(
        image_width, image_height, settings,
        transform_cls=LayoutTransform,
        derive_canonical_fn=_derive_nominal_geometry_canonical,
    )


def _derive_geometry_canonical(image: Image.Image, settings: AppSettings) -> Geometry:
    return _geometry_construction.derive_geometry_canonical(
        image, settings,
        analysis_fn=_analysis_image, source_px_fn=_source_px,
        offsets_fn=_column_start_offsets_canonical,
        apply_offsets_fn=apply_column_start_offsets,
        estimate_paths_fn=_estimate_column_paths,
        column_path_cls=ColumnPath, geometry_cls=Geometry,
    )


def derive_geometry(image: Image.Image, settings: AppSettings) -> Geometry:
    return _geometry_construction.derive_geometry(
        image, settings,
        normalize_rgb_fn=normalize_page_rgb, transform_cls=LayoutTransform,
        derive_canonical_fn=_derive_geometry_canonical,
    )

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
    """Historical VB point brightness gate; retain original signature."""
    return _legacy_brightness_sampling.legacy_is_point(
        rgb_sum, x, y, area_x, area_y, max_brightness_percent,
        direction=direction, np_module=np,
    )


def _legacy_row_brightness_1000(
    rgb_sum: np.ndarray,
    y: int,
    x: int,
    width: int,
    *,
    direction: int = 1,
) -> int | None:
    """Historical VB row brightness score; retain original signature."""
    return _legacy_brightness_sampling.legacy_row_brightness_1000(
        rgb_sum, y, x, width, direction=direction, np_module=np,
    )


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
    """Historical VB.NET separator search, retaining the patchable core path."""
    return _legacy_separator_search.find_separator_y(
        rgb_sum, candidate_x, candidate_y,
        column_width=column_width, direction=direction, row_height=row_height,
        upward_ratio=upward_ratio, ordinary_right_divisor=ordinary_right_divisor,
        darkness_threshold=darkness_threshold,
        white_threshold_high=white_threshold_high,
        white_threshold_low=white_threshold_low,
        whitespace_adjustment=whitespace_adjustment, top=top, x_min=x_min,
        x_max=x_max, np_module=np,
        row_brightness_fn=_legacy_row_brightness_1000,
        brightness_scores_fn=legacy_row_brightness_scores_1000,
    )


def _ordinary_source_column_edge(
    geometry: Geometry, column: int, y: int
) -> tuple[int, int]:
    """Historical full-resolution left column edge with canonical transforms."""
    return _legacy_page_detection.source_column_edge(geometry, column, y)


def _detect_entries_left_edge(
    image: Image.Image,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], Geometry]:
    """Historical VB full-resolution detector; use current core dependencies."""
    return _legacy_page_detection.detect_entries_left_edge(
        image, settings, page_sections,
        deps={
            "normalize_page_rgb": normalize_page_rgb,
            "derive_geometry": derive_geometry,
            "np": np,
            "ImageOps": ImageOps,
            "_source_px": _source_px,
            "normalize_page_sections": normalize_page_sections,
            "_ordinary_source_column_edge": _ordinary_source_column_edge,
            "_legacy_is_point": _legacy_is_point,
            "_legacy_find_separator_y": _legacy_find_separator_y,
            "Entry": Entry,
            "_collapse_ordinary_oversized_cjk_split_markers": _collapse_ordinary_oversized_cjk_split_markers,
            "_recover_ordinary_oversized_cjk_missing_markers": _recover_ordinary_oversized_cjk_missing_markers,
            "sort_entries_reading_order": sort_entries_reading_order,
        },
    )


def _collapse_ordinary_oversized_cjk_split_markers(
    image: Image.Image,
    entries: list[Entry],
    geometry: Geometry,
    settings: AppSettings,
) -> list[Entry]:
    """Historical OCR-independent oversized CJK duplicate-marker correction."""
    return _cjk_marker_reconciliation.collapse_oversized_cjk_split_markers(
        image, entries, geometry, settings,
        deps={
            "normalize_page_rgb": normalize_page_rgb,
            "np": np,
            "ImageOps": ImageOps,
            "column_index_for_click": column_index_for_click,
            "_left_edge_otsu_threshold": _left_edge_otsu_threshold,
            "sort_entries_reading_order": sort_entries_reading_order,
        },
    )


def _recover_ordinary_oversized_cjk_missing_markers(
    image: Image.Image,
    entries: list[Entry],
    geometry: Geometry,
    settings: AppSettings,
) -> list[Entry]:
    """Historical independent oversized CJK marker rescue."""
    return _cjk_marker_reconciliation.recover_oversized_cjk_missing_markers(
        image, entries, geometry, settings,
        deps={
            "normalize_page_rgb": normalize_page_rgb,
            "np": np,
            "ImageOps": ImageOps,
            "column_index_for_click": column_index_for_click,
            "_left_edge_otsu_threshold": _left_edge_otsu_threshold,
            "_ordinary_source_column_edge": _ordinary_source_column_edge,
            "sort_entries_reading_order": sort_entries_reading_order,
            "Entry": Entry,
        },
    )


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
    return _review_signals.has_strong_positive_visual(candidate)


def _review_candidate_hard_negative_level(candidate: dict) -> str:
    """Historical consensus semantics: distinct single/dual hard negatives."""
    return _review_signals.hard_negative_level(
        candidate,
        positive_fn=_review_candidate_has_strong_positive_visual,
        hard_reasons=_COMBINED_HARD_NEGATIVE_REASONS,
    )


def _review_candidate_hard_negative_consensus(candidate: dict) -> bool:
    return _review_signals.hard_negative_consensus(
        candidate, level_fn=_review_candidate_hard_negative_level,
    )


def _latent_review_rows(
    review_candidates: list[dict] | None,
    geometry: Geometry,
) -> list[tuple[dict, int, int]]:
    """Historical latent review row projection in canonical reading coordinates."""
    return _review_signals.latent_review_rows(
        review_candidates, geometry, column_fn=column_index_for_click,
    )

def _fuse_detection_entries(
    ordinary_entries: list[Entry],
    ocr_entries: list[Entry],
    geometry: Geometry,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
    review_candidates: list[dict] | None = None,
    image: Image.Image | None = None,
) -> list[Entry]:
    """Historical fused entry events with live geometry/OCR seam callbacks."""
    return _detection_entry_fusion.fuse_detection_entries(
        ordinary_entries, ocr_entries, geometry, settings,
        page_sections, review_candidates, image,
        deps={
            "sort_entries_reading_order": sort_entries_reading_order,
            "_latent_review_rows": _latent_review_rows,
            "column_index_for_click": column_index_for_click,
            "_is_single_cjk_headword": _is_single_cjk_headword,
            "_review_candidate_hard_negative_level": _review_candidate_hard_negative_level,
            "_review_candidate_to_entry": _review_candidate_to_entry,
            "_review_candidate_hard_negative_consensus": _review_candidate_hard_negative_consensus,
            "_entry_with_fused_metadata": _entry_with_fused_metadata,
            "_prefer_ocr_separator_position": _prefer_ocr_separator_position,
            "np": np,
            "ImageOps": ImageOps,
            "normalize_page_rgb": normalize_page_rgb,
        },
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
    """Historical Profile-aware ordinary/OCR/combined entrypoint."""
    return _page_method_dispatch.detect_entries_impl(
        image, settings, paddle_cache_path, force_paddle_refresh,
        paddle_filter_rules_path, profile_page_index, page_sections,
        left_edge_detector,
        deps={{
            "_detect_entries_left_edge": _detect_entries_left_edge,
            "normalize_page_rgb": normalize_page_rgb,
            "effective_page_settings": effective_page_settings,
            "page_template_analysis_image": page_template_analysis_image,
            "derive_geometry": derive_geometry,
            "ordinary_page_layout_settings": ordinary_page_layout_settings,
            "_fuse_detection_entries": _fuse_detection_entries,
            "entry_allowed_by_page_template": entry_allowed_by_page_template,
            "v_is_inside_sections": v_is_inside_sections,
            "sort_entries_reading_order": sort_entries_reading_order,
            "json": json,
        }},
    )


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
    """Historical Y refinement with current core geometry/ink callbacks."""
    return _existing_entry_positions.refine_existing_entries_with_geometry_impl(
        entries, effective, analysis_source, geometry,
        align_to_ink_top=align_to_ink_top,
        fixed_half_gutter=fixed_half_gutter,
        deps={{
            "_source_px": _source_px,
            "column_index": column_index,
            "replace": replace,
            "np": np,
            "ImageOps": ImageOps,
        }},
    )


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
    """Historical OCR text fill for existing markers; never modifies X/Y."""
    return _ordinary_marker_text_enrichment.ocr_existing_entry_words_from_markers_impl(
        image, entries, settings, replace_rules,
        profile_page_index=profile_page_index,
        page_sections=page_sections,
        profile_path=profile_path, only_blank=only_blank,
        deps={
            "_page_geometry_context": _page_geometry_context,
            "sort_entries_reading_order": sort_entries_reading_order,
            "_ordinary_marker_local_crop": _ordinary_marker_local_crop,
            "process_ocr_text": process_ocr_text,
        },
    )


def ocr_entries(
    image: Image.Image,
    entries: list[Entry],
    settings: AppSettings,
    replace_rules: list[tuple[str, str, str]],
    *,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
) -> list[str]:
    """Historical text-only OCR through currently configured engine and crop."""
    return _legacy_entry_text_reading.ocr_entries_impl(
        image, entries, settings, replace_rules,
        profile_page_index=profile_page_index, page_sections=page_sections,
        deps={{
            "_page_geometry_context": _page_geometry_context,
            "sort_entries_reading_order": sort_entries_reading_order,
            "line_box": line_box,
            "run_tesseract": run_tesseract,
            "resolved_tesseract_language": resolved_tesseract_language,
            "process_ocr_text": process_ocr_text,
        }},
    )


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
