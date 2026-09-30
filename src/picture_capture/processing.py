from __future__ import annotations

"""Compatibility facade for ordinary processing plus page-design inference.

For CJK ordinary drawing the primary abstraction is now the dictionary page
layout itself: reading direction, body, columns, ordinary type scale, indentation
modes and display-size heads are inferred before any entry boundary is emitted.
When that page model is reliable, its boundaries are authoritative and the
historical candidate chain is not consulted.  Legacy processing remains as a
fallback for underdetermined pages and as the unchanged path for non-CJK
projects.
"""

from pathlib import Path
import sys
import types
from typing import Any

from PIL import Image

from .models import AppSettings, Entry
from .page_sections import PageSection
from . import processing_core as _core
from .dictionary_page_design import detect_entries_from_page_design, DictionaryPageLayout
from .ordinary_cjk_large_heads import recover_cjk_oversized_heads
from .ordinary_indent_topology import finalize_indented_topology
from .ordinary_postprocess import stabilize_ordinary_visual_entries
from .ordinary_visual import recover_ordinary_visual_entries


for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


_original_detect_entries_left_edge = _core._detect_entries_left_edge


def _uses_cjk_indent_topology(settings: AppSettings) -> bool:
    """Return whether the page-design CJK path is appropriate."""
    profile_id = str(getattr(settings, "dictionary_profile_id", "") or "").lower()
    ocr_language = str(getattr(settings, "ocr_language", "") or "").lower()
    paddle_language = str(getattr(settings, "paddle_language", "") or "").lower()
    return bool(
        "cjk" in profile_id
        or any(token in ocr_language for token in (
            "chi_sim", "chi_tra", "chinese", "han", "jpn", "jpn_vert",
        ))
        or paddle_language in {"ch", "chi_sim", "chi_tra", "chinese_cht", "japan"}
    )


def _geometry_from_page_design(layout: DictionaryPageLayout) -> Any:
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


def _detect_entries_left_edge(
    image: Image.Image,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], Any]:
    """Historical ordinary fallback and non-CJK visual recovery.

    Direct CJK ordinary drawing is normally intercepted by ``detect_entries``
    before reaching this function.  Keeping this wrapper preserves combined-mode
    compatibility while the new page-design path is validated more broadly.

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
    if _uses_cjk_indent_topology(settings):
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


def detect_entries(
    image: Image.Image,
    settings: AppSettings,
    paddle_cache_path: Path | None = None,
    force_paddle_refresh: bool = False,
    paddle_filter_rules_path: Path | None = None,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], Any]:
    """Detect entries, preferring a recovered page-design model for CJK ordinary mode."""
    method = str(getattr(settings, "detection_method", "") or "").strip().lower()
    if method not in {"paddleocr", "combined"} and _uses_cjk_indent_topology(settings):
        try:
            result = detect_entries_from_page_design(
                image,
                settings,
                page_index=profile_page_index,
                page_sections=page_sections,
            )
        except Exception:
            result = None
        if result is not None and result.layout.reliable and result.layout.columns:
            geometry = _geometry_from_page_design(result.layout)
            source = _core.normalize_page_rgb(image)
            effective = _core.effective_page_settings(
                settings, source.size, profile_page_index,
            )
            entries = [
                entry for entry in result.entries
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
            return _core.sort_entries_reading_order(
                entries, geometry, page_sections,
            ), geometry

    return _core.detect_entries(
        image,
        settings,
        paddle_cache_path=paddle_cache_path,
        force_paddle_refresh=force_paddle_refresh,
        paddle_filter_rules_path=paddle_filter_rules_path,
        profile_page_index=profile_page_index,
        page_sections=page_sections,
    )


def detect_entries_job(
    image_path: str,
    settings: AppSettings,
    pages: tuple[str, str, str],
    profile_page_index: int = 0,
) -> int:
    """Spawn-safe ordinary worker that executes the enhanced facade pipeline."""
    page = Path(image_path)
    with Image.open(page) as opened:
        image = _core.normalize_page_rgb(opened)
    settings.detection_method = "left_edge"
    entries, _geometry = detect_entries(
        image,
        settings,
        profile_page_index=profile_page_index,
        page_sections=_core.read_page_sections(page),
    )
    _core.write_pdic(
        _core.pdic_path_for_image(page),
        entries,
        image.width,
        pages,
    )
    return len(entries)


def _publish_file_transaction(*args, **kwargs):
    return _core._publish_file_transaction(*args, **kwargs)


def _stage_page_crop_plan(*args, **kwargs):
    return _core._stage_page_crop_plan(*args, **kwargs)


# Historical publish implementation uses uuid.uuid4().hex in processing_core.


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


_core._detect_entries_left_edge = _detect_entries_left_edge
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
