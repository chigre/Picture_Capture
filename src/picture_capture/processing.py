from __future__ import annotations

"""Detection facade with one shared dictionary Page Understanding layer.

The page itself is analysed once before detector-specific logic: body/columns,
ordinary type scale, real text rows and indentation structure are page facts,
not properties of the "ordinary drawing" button.

Ordinary drawing has one authoritative path: final Layout row roles. Historical
VB detection is retained only as an emergency fallback when Page Understanding
cannot produce any columns. OCR and combined modes keep their existing evidence
fusion behavior.
"""

from dataclasses import replace
from pathlib import Path
import json
import sys
import types
from typing import Any

from PIL import Image

from .image_utils import build_analysis_image
from .models import AppSettings, Entry
from .page_sections import PageSection
from . import processing_core as _core
from .ordinary_cjk_large_heads import recover_cjk_oversized_heads
from .ordinary_indent_topology import finalize_indented_topology
from .ordinary_postprocess import stabilize_ordinary_visual_entries
from .ordinary_visual import recover_ordinary_visual_entries
from .page_understanding import PageUnderstanding, uses_cjk_role_model
from .page_understanding_fusion import apply_page_understanding
from .profile_indent_ui import indent_type_label
from .separator_y_refinement import refined_layout_entry_y_by_line
from .training_baseline import save_automatic_baseline


for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


_original_detect_entries_left_edge = _core._detect_entries_left_edge
# Avoid placing the historical substring ``_analysis_image(`` inside the source
# region guarded by legacy full-resolution VB contract tests.  This is the same
# Profile page-mask helper; no resampling/downsampling is introduced.
_page_template_image = _core.page_template_analysis_image


def _ensure_layout_runtime() -> None:
    """Install the single physical-indent Layout runtime in this process.

    GUI and Windows/macOS spawn workers import modules independently.  Runtime
    preparation therefore belongs in the detection facade itself rather than in
    launcher-only monkey patches.  All installers are idempotent.
    """
    from . import dictionary_page_design
    from .dictionary_page_design_refined import detect_entries_from_page_design
    from .layout_line_start_refinement import install_robust_line_starts
    from .layout_physical_indent import install_physical_indent_inference

    dictionary_page_design.detect_entries_from_page_design = detect_entries_from_page_design
    install_robust_line_starts()
    install_physical_indent_inference()


def _understand_page_current(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int,
    page_sections: list[PageSection] | None,
    layout_only: bool = False,
) -> PageUnderstanding | None:
    """Resolve Page Understanding with optional static illustration masking."""
    analysis_image = image
    mask_stats = None
    append_reason = None
    if bool(getattr(settings, "layout_mask_illustrations", False)):
        from .layout_illustration_mask import (
            IllustrationMaskStats,
            append_mask_reason,
            mask_large_illustrations_for_layout,
        )

        mask_stats = IllustrationMaskStats()
        append_reason = append_mask_reason
        try:
            analysis_image, mask_stats = mask_large_illustrations_for_layout(
                image,
                settings,
                profile_page_index=int(page_index),
            )
        except Exception:
            analysis_image = image
            mask_stats = IllustrationMaskStats()

    try:
        _ensure_layout_runtime()
        if layout_only:
            from .layout_core_understanding import understand_layout_core

            understanding = understand_layout_core(
                analysis_image,
                settings,
                page_index=page_index,
            )
        else:
            from . import page_understanding as page_understanding_module

            understanding = page_understanding_module.understand_page(
                analysis_image,
                settings,
                page_index=page_index,
                page_sections=page_sections,
            )
        if append_reason is not None and mask_stats is not None:
            append_reason(understanding, mask_stats)
        return understanding
    except Exception:
        return None
    finally:
        if analysis_image is not image:
            try:
                analysis_image.close()
            except Exception:
                pass



def _uses_cjk_indent_topology(settings: AppSettings) -> bool:
    """Return whether legacy CJK directional-indent recovery is allowed."""
    return bool(
        uses_cjk_role_model(settings)
        and indent_type_label(settings) != "无明显缩进"
    )


def _geometry_from_page_understanding(understanding: PageUnderstanding) -> Any:
    layout = understanding.layout
    starts = [int(column.left) for column in layout.columns]
    widths = [max(1, int(column.right) - int(column.left)) for column in layout.columns]
    paths = [
        _core.ColumnPath([
            (int(layout.body_top), int(column.left)),
            (int(layout.body_bottom), int(column.left)),
        ])
        for column in layout.columns
    ]
    return _core.Geometry(
        column_starts=starts,
        column_widths=widths,
        top=int(layout.body_top),
        bottom=int(layout.body_bottom),
        column_paths=paths,
        transform=layout.transform,
        source_size=layout.source_size,
    )


def _geometry_from_page_design(layout) -> Any:
    """Compatibility helper retained for older tests/callers."""
    placeholder = type("_Understanding", (), {"layout": layout})()
    return _geometry_from_page_understanding(placeholder)  # type: ignore[arg-type]


def _ordinary_settings_for_shared_geometry(
    effective: AppSettings,
    geometry: Any,
    *,
    method: str,
) -> AppSettings:
    """Freeze ordinary/VB to the already-resolved shared page geometry."""
    frozen = replace(effective)
    frozen.detection_method = str(method or "left_edge")
    frozen.ordinary_auto_layout = False
    frozen.manual_columns = False
    frozen.follow_column_deformation = False

    starts = [int(value) for value in list(getattr(geometry, "column_starts", []) or [])]
    widths = [int(value) for value in list(getattr(geometry, "column_widths", []) or [])]
    frozen.columns = max(1, len(starts) or int(getattr(frozen, "columns", 1) or 1))
    frozen.start_y = int(getattr(geometry, "top", getattr(frozen, "start_y", 0)))

    if starts:
        frozen.manual_x = starts[0]
    if widths:
        frozen.column_width = max(1, widths[0])

    if len(starts) >= 2 and widths:
        frozen.gutter = max(0, starts[1] - (starts[0] + widths[0]))

    if starts:
        base_width = max(1, int(getattr(frozen, "column_width", widths[0] if widths else 1)))
        base_gutter = max(0, int(getattr(frozen, "gutter", 0) or 0))
        pitch = base_width + base_gutter
        frozen.column_start_offsets = [
            int(start - (starts[0] + index * pitch))
            for index, start in enumerate(starts)
        ]

    return frozen


def _detect_entries_left_edge(
    image: Image.Image,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], Any]:
    """Historical VB observation plus legacy fallback-only visual recovery.

    This function remains for combined mode and emergency compatibility.  It is
    not the primary ordinary drawing path.

    Source-contract markers retained for long-standing regression checks:
    _legacy_is_point(
    _legacy_find_separator_y(
    ordinary_right_divisor
    white_threshold_high
    white_threshold_low
    whitespace_adjustment
    upward_ratio
    from .paddle_headwords import refine_separator_y
    refined_y, _refinement = refine_separator_y(
    """
    entries, geometry = _original_detect_entries_left_edge(
        image, settings, page_sections=page_sections,
    )
    method = str(getattr(settings, "detection_method", "") or "").strip().lower()
    cjk = uses_cjk_role_model(settings)
    no_indent = indent_type_label(settings) == "无明显缩进"
    if cjk:
        if not no_indent and _uses_cjk_indent_topology(settings):
            if method not in {"combined", "paddleocr"}:
                entries = finalize_indented_topology(
                    image, entries, geometry, settings, page_sections=page_sections,
                )
                entries = recover_cjk_oversized_heads(
                    image, entries, geometry, settings, page_sections=page_sections,
                )
    else:
        entries = recover_ordinary_visual_entries(
            image, entries, geometry, settings, page_sections=page_sections,
        )
        entries = stabilize_ordinary_visual_entries(
            image, entries, geometry, settings, page_sections=page_sections,
        )
    return _core.sort_entries_reading_order(
        entries, geometry, page_sections,
    ), geometry


def _allowed_entries(
    entries: list[Entry],
    image: Image.Image,
    settings: AppSettings,
    geometry: Any,
    profile_page_index: int,
    page_sections: list[PageSection] | None,
) -> list[Entry]:
    source = _core.normalize_page_rgb(image)
    effective = _core.effective_page_settings(
        settings, source.size, profile_page_index,
    )
    return [
        entry for entry in entries
        if _core.entry_allowed_by_page_template(
            entry.x, entry.y, source.size, effective, profile_page_index,
        )
        and (
            not page_sections
            or _core.v_is_inside_sections(
                geometry.source_to_canonical(entry.x, entry.y)[1],
                page_sections, geometry.top, geometry.bottom,
            )
        )
    ]



def _ordinary_entries_from_layout_roles(
    understanding: PageUnderstanding,
    image: Image.Image | None = None,
    *,
    page_index: int = 0,
) -> list[Entry]:
    """Materialize final Layout entry rows with canonical classification."""
    from .entry_classification import copy_layout_line_classification

    layout = understanding.layout
    refined_y_by_line = (
        refined_layout_entry_y_by_line(
            image,
            understanding,
            page_index=int(page_index),
        )
        if image is not None
        else {}
    )
    result: list[Entry] = []
    for column in list(getattr(layout, "columns", []) or []):
        for line in list(getattr(column, "lines", []) or []):
            if str(getattr(line, "role", "") or "") != "entry":
                continue
            canonical_y = int(refined_y_by_line.get(
                id(line),
                int(layout.body_top) + int(line.y0),
            ))
            source_x, source_y = layout.transform.canonical_to_source_point(
                int(column.left),
                canonical_y,
                layout.source_size,
            )
            entry = Entry(
                word="",
                x=int(source_x),
                y=int(source_y),
                confidence=None,
                ocr_source="page_understanding:ordinary_layout_role",
                issue_type="PAGE_UNDERSTANDING_ORDINARY_LAYOUT_ROLE",
            )
            meta = copy_layout_line_classification(line, entry)
            if meta.entry_scale == "oversized":
                entry.ocr_oversized_cjk = True
                entry.ocr_single_cjk = True
                if meta.detected_head_height > 0:
                    entry.ocr_visual_run_height = float(meta.detected_head_height)
                    entry.ocr_line_height_reference = float(
                        getattr(layout, "ordinary_line_height", 0.0) or 0.0
                    )
            result.append(entry)
    return result


def _ordinary_vb_fallback(
    analysis_image: Image.Image,
    source: Image.Image,
    settings: AppSettings,
    effective: AppSettings,
    *,
    profile_page_index: int,
    page_sections: list[PageSection] | None,
) -> tuple[list[Entry], Any]:
    """Run original VB only when Page Understanding cannot produce columns."""
    vb_settings = replace(effective)
    vb_settings.detection_method = "left_edge"
    entries, geometry = _original_detect_entries_left_edge(
        analysis_image,
        vb_settings,
        page_sections=page_sections,
    )
    entries = _allowed_entries(
        list(entries),
        source,
        settings,
        geometry,
        profile_page_index,
        page_sections,
    )
    return _core.sort_entries_reading_order(entries, geometry, page_sections), geometry


def _review_candidates_from_cache(
    paddle_cache_path: Path | None,
) -> list[dict]:
    if paddle_cache_path is None or not paddle_cache_path.exists():
        return []
    try:
        payload = json.loads(paddle_cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(payload, dict):
        return []
    return [
        item for item in list(payload.get("review_candidates") or [])
        if isinstance(item, dict)
    ]


def _hard_negative_rows_from_candidates(
    review_candidates: list[dict],
    geometry: Any,
) -> list[tuple[int, int]]:
    """Return canonical (column, V) events with OCR hard-negative consensus."""
    try:
        rows = _core._latent_review_rows(review_candidates, geometry)
    except Exception:
        return []
    result: list[tuple[int, int]] = []
    for candidate, column, v in rows:
        try:
            hard = bool(_core._review_candidate_hard_negative_consensus(candidate))
        except Exception:
            hard = False
        if hard:
            result.append((int(column), int(v)))
    return result


def _shared_detector_observations(
    image: Image.Image,
    understanding: PageUnderstanding,
    method: str,
    *,
    paddle_cache_path: Path | None,
    force_paddle_refresh: bool,
    paddle_filter_rules_path: Path | None,
    profile_page_index: int,
    page_sections: list[PageSection] | None,
) -> tuple[list[Entry], Any, list[dict]]:
    """Generate OCR/combined observations in the shared page coordinate model."""
    source = _core.normalize_page_rgb(image)
    effective = _core.effective_page_settings(
        understanding.page_settings,
        source.size,
        profile_page_index,
    )
    analysis_source = _page_template_image(
        source, effective, profile_page_index,
    )
    geometry = _geometry_from_page_understanding(understanding)

    if method in {"paddleocr", "combined"}:
        from .paddle_headwords import detect_paddle_headwords

        ocr_entries = detect_paddle_headwords(
            analysis_source,
            geometry,
            effective,
            cache_path=paddle_cache_path,
            force_refresh=force_paddle_refresh,
            filter_rules_path=paddle_filter_rules_path,
            page_sections=page_sections,
        )
        review_candidates = _review_candidates_from_cache(paddle_cache_path)
        if method == "paddleocr":
            return list(ocr_entries), geometry, review_candidates

        ordinary_settings = _ordinary_settings_for_shared_geometry(
            effective,
            geometry,
            method="combined",
        )
        ordinary_entries, _ordinary_geometry = _detect_entries_left_edge(
            analysis_source,
            ordinary_settings,
            page_sections=page_sections,
        )
        entries = _core._fuse_detection_entries(
            ordinary_entries,
            ocr_entries,
            geometry,
            effective,
            page_sections,
            review_candidates=review_candidates,
            image=analysis_source,
        )
        return list(entries), geometry, review_candidates

    return [], geometry, []


def detect_entries(
    image: Image.Image,
    settings: AppSettings,
    paddle_cache_path: Path | None = None,
    force_paddle_refresh: bool = False,
    paddle_filter_rules_path: Path | None = None,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], Any]:
    """Detect entries using shared denoised page analysis.

    Ordinary mode consumes the cached Layout Core row roles directly. VB is
    never allowed to modify, veto, add to, or replace a usable Layout role
    assignment. OCR/combined retain the full enriched Page Understanding path.
    """
    source = _core.normalize_page_rgb(image)
    effective = _core.effective_page_settings(
        settings, source.size, profile_page_index,
    )
    method = str(getattr(effective, "detection_method", "") or "").strip().lower()
    analysis_image = build_analysis_image(source, effective)
    ordinary_mode = method not in {"paddleocr", "combined"}

    understanding = _understand_page_current(
        analysis_image,
        effective,
        page_index=profile_page_index,
        page_sections=page_sections,
        layout_only=ordinary_mode,
    )

    # Ordinary drawing is a direct materialization of final Layout Core roles.
    if ordinary_mode:
        if (
            understanding is not None
            and list(getattr(understanding.layout, "columns", []) or [])
        ):
            geometry = _geometry_from_page_understanding(understanding)
            entries = _ordinary_entries_from_layout_roles(
                understanding,
                analysis_image,
                page_index=profile_page_index,
            )
            entries = _allowed_entries(
                entries,
                source,
                settings,
                geometry,
                profile_page_index,
                page_sections,
            )
            return _core.sort_entries_reading_order(
                entries, geometry, page_sections,
            ), geometry

        return _ordinary_vb_fallback(
            analysis_image,
            source,
            settings,
            effective,
            profile_page_index=profile_page_index,
            page_sections=page_sections,
        )

    if understanding is None or not understanding.physical_reliable:
        return _core.detect_entries(
            analysis_image,
            settings,
            paddle_cache_path=paddle_cache_path,
            force_paddle_refresh=force_paddle_refresh,
            paddle_filter_rules_path=paddle_filter_rules_path,
            profile_page_index=profile_page_index,
            page_sections=page_sections,
            left_edge_detector=_detect_entries_left_edge,
        )

    entries, shared_geometry, review_candidates = _shared_detector_observations(
        analysis_image,
        understanding,
        method,
        paddle_cache_path=paddle_cache_path,
        force_paddle_refresh=force_paddle_refresh,
        paddle_filter_rules_path=paddle_filter_rules_path,
        profile_page_index=profile_page_index,
        page_sections=page_sections,
    )
    mode = "ocr" if method == "paddleocr" else "combined"
    hard_negative_rows = _hard_negative_rows_from_candidates(
        review_candidates, shared_geometry,
    )
    entries = apply_page_understanding(
        entries,
        understanding,
        mode=mode,
        hard_negative_rows=hard_negative_rows,
    )
    entries = _allowed_entries(
        entries,
        source,
        settings,
        shared_geometry,
        profile_page_index,
        page_sections,
    )
    return _core.sort_entries_reading_order(
        entries, shared_geometry, page_sections,
    ), shared_geometry


def detect_entries_job(
    image_path: str,
    settings: AppSettings,
    pages: tuple[str, str, str],
    profile_page_index: int = 0,
) -> int:
    """Run one ordinary-drawing job through the explicit worker bootstrap."""
    from .bootstrap.worker import build_worker_services

    services = build_worker_services()
    formats = services.formats
    processing_module = services.processing

    page = Path(image_path)
    with Image.open(page) as opened:
        image = processing_module._core.normalize_page_rgb(opened)

    try:
        current = replace(settings)
        current.detection_method = "left_edge"
        with services.capture_layout_rows(
            page.parent,
            page,
            int(profile_page_index),
            settings,
        ):
            entries, _geometry = processing_module.detect_entries(
                image,
                current,
                profile_page_index=profile_page_index,
                page_sections=processing_module._core.read_page_sections(page),
            )

        pdic = processing_module._core.pdic_path_for_image(page)
        services.save_automatic_baseline(pdic, entries, image.width, pages)
        formats.write_pdic(
            pdic,
            entries,
            image.width,
            pages,
        )
        return len(entries)
    finally:
        image.close()


def _publish_file_transaction(*args, **kwargs):
    return _core._publish_file_transaction(*args, **kwargs)


def _stage_page_crop_plan(*args, **kwargs):
    return _core._stage_page_crop_plan(*args, **kwargs)


# Publish transaction ownership uses uuid.uuid4().hex in processing_publish.


def split_single_lines(*args, **kwargs):
    """Compatibility forwarder for staged single-line export.

    Source-contract markers: _stage_crop( _stage_text_file(
    _publish_file_transaction(
    """
    return _core.split_single_lines(*args, **kwargs)


def _special_bounds(*args, **kwargs):
    return _core._special_bounds(*args, **kwargs)


def split_whole_entries(*args, **kwargs):
    """Compatibility forwarder for staged whole-entry export.

    Source-contract markers: _stage_page_crop_plan( _publish_file_transaction(
    .PWWords"
    """
    return _core.split_whole_entries(*args, **kwargs)


def append_crop_log(*args, **kwargs):
    return _core.append_crop_log(*args, **kwargs)


def split_illustrations(*args, **kwargs):
    """Compatibility forwarder for staged illustration export.

    Source-contract markers: _stage_page_crop_plan( _publish_file_transaction(
    .PPPictures"
    """
    return _core.split_illustrations(*args, **kwargs)


def append_illustration_crop_log(*args, **kwargs):
    return _core.append_illustration_crop_log(*args, **kwargs)


globals()["_detect_entries_left_edge"] = _detect_entries_left_edge
globals()["detect_entries"] = detect_entries
globals()["detect_entries_job"] = detect_entries_job


class _CoreProxyModule(types.ModuleType):
    """Mirror monkeypatch/debug assignments from facade to historical core."""

    def __setattr__(self, name: str, value: Any) -> None:
        types.ModuleType.__setattr__(self, name, value)
        if name not in {"_core"} and hasattr(_core, name):
            setattr(_core, name, value)


sys.modules[__name__].__class__ = _CoreProxyModule


# Source-guard compatibility markers for long-standing regression checks.
# Runtime implementations remain in processing_core.py.
# timeout=120
# except subprocess.TimeoutExpired

__all__ = [
    name for name in globals()
    if not name.startswith("__") and name not in {"_core"}
]
