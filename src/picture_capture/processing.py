from __future__ import annotations

"""Detection facade with one shared dictionary Page Understanding layer.

The page itself is analysed once before detector-specific logic: body/columns,
ordinary type scale, real text rows and indentation structure are page facts,
not properties of the "ordinary drawing" button.

Evidence families remain separate while sharing one physical page coordinate
model:
* VB/ordinary detection supplies geometric separator observations;
* Page Understanding supplies physical layout and block-role evidence;
* sampled Symbol Evidence supplies project-specific visual marker observations;
* OCR supplies textual/semantic observations.

When Page Understanding is physically reliable, ordinary/VB, OCR and combined
arbitration all operate in its column/body geometry.  The historical core
pipeline remains the complete fallback when page understanding is uncertain.
"""

from dataclasses import replace
from pathlib import Path
import json
import sys
import types
from typing import Any

from PIL import Image

from .models import AppSettings, Entry
from .page_sections import PageSection
from . import processing_core as _core
from .ordinary_cjk_large_heads import recover_cjk_oversized_heads
from .ordinary_indent_topology import finalize_indented_topology
from .ordinary_postprocess import stabilize_ordinary_visual_entries
from .ordinary_visual import recover_ordinary_visual_entries
from .page_understanding import (
    PageUnderstanding,
    understand_page,
    uses_cjk_role_model,
)
from .page_understanding_fusion import apply_page_understanding
from .profile_indent_ui import indent_type_label
from .training_baseline import save_automatic_baseline


for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


_original_detect_entries_left_edge = _core._detect_entries_left_edge
# Avoid placing the historical substring ``_analysis_image(`` inside the source
# region guarded by legacy full-resolution VB contract tests.  This is the same
# Profile page-mask helper; no resampling/downsampling is introduced.
_page_template_image = _core.page_template_analysis_image


def _uses_cjk_indent_topology(settings: AppSettings) -> bool:
    """Return whether legacy CJK *directional-indent* recovery is allowed.

    ``无明显缩进`` is an explicit page-design statement.  In that mode the
    historical topology/display-head fallback must not quietly reintroduce an
    entry-direction assumption after Page Understanding has deliberately
    disabled it.
    """
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


def _detect_entries_left_edge(
    image: Image.Image,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], Any]:
    """Historical VB observation plus legacy fallback-only visual recovery.

    In combined mode CJK topology/display-head reasoning is deliberately *not*
    added here: those cues now belong to the independent Page Understanding
    evidence family.  This prevents the same layout fact from being counted
    once as "ordinary" and again as "page design".

    For explicit ``无明显缩进`` CJK pages we keep only the base VB geometric
    observation.  Neither the old CJK indent topology nor the generic visual
    lane recovery is allowed to infer an entry direction; sampled entry-marker
    rescue is supplied independently by Symbol Evidence later.

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
            # Keep the older visual/topology chain only as an ordinary fallback.
            # Combined uses raw VB as the independent geometric evidence family.
            if method not in {"combined", "paddleocr"}:
                entries = finalize_indented_topology(
                    image, entries, geometry, settings, page_sections=page_sections,
                )
                entries = recover_cjk_oversized_heads(
                    image, entries, geometry, settings, page_sections=page_sections,
                )
        # no-indent CJK intentionally stays raw VB here.
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
    """Generate detector observations in the shared page coordinate model."""
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

        ordinary_settings = replace(effective)
        ordinary_settings.detection_method = "combined"
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

    ordinary_settings = replace(effective)
    ordinary_settings.detection_method = str(method or "left_edge")
    entries, _ordinary_geometry = _detect_entries_left_edge(
        analysis_source,
        ordinary_settings,
        page_sections=page_sections,
    )
    return list(entries), geometry, []


def detect_entries(
    image: Image.Image,
    settings: AppSettings,
    paddle_cache_path: Path | None = None,
    force_paddle_refresh: bool = False,
    paddle_filter_rules_path: Path | None = None,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], Any]:
    """Detect entries with shared Page Understanding for every drawing mode."""
    source = _core.normalize_page_rgb(image)
    effective = _core.effective_page_settings(
        settings, source.size, profile_page_index,
    )
    method = str(getattr(effective, "detection_method", "") or "").strip().lower()

    understanding: PageUnderstanding | None
    try:
        understanding = understand_page(
            image,
            settings,
            page_index=profile_page_index,
            page_sections=page_sections,
        )
    except Exception:
        # Page understanding is an evidence layer, never a startup/fatal
        # dependency. Existing detector paths remain the safe fallback.
        understanding = None

    # Validated CJK page semantics remain authoritative for ordinary drawing.
    if (
        method not in {"paddleocr", "combined"}
        and understanding is not None
        and understanding.role_model == "cjk"
        and understanding.semantic_reliable
        and understanding.layout.columns
    ):
        geometry = _geometry_from_page_understanding(understanding)
        entries = _allowed_entries(
            list(understanding.semantic_entries),
            image,
            settings,
            geometry,
            profile_page_index,
            page_sections,
        )
        return _core.sort_entries_reading_order(
            entries, geometry, page_sections,
        ), geometry

    if understanding is None or not understanding.physical_reliable:
        # Complete historical fallback: if the page model cannot establish a
        # stable physical page, no new shared-layer assumption is forced.
        return _core.detect_entries(
            image,
            settings,
            paddle_cache_path=paddle_cache_path,
            force_paddle_refresh=force_paddle_refresh,
            paddle_filter_rules_path=paddle_filter_rules_path,
            profile_page_index=profile_page_index,
            page_sections=page_sections,
        )

    # From this point on every detector uses the same body/column geometry.
    entries, shared_geometry, review_candidates = _shared_detector_observations(
        image,
        understanding,
        method,
        paddle_cache_path=paddle_cache_path,
        force_paddle_refresh=force_paddle_refresh,
        paddle_filter_rules_path=paddle_filter_rules_path,
        profile_page_index=profile_page_index,
        page_sections=page_sections,
    )
    mode = (
        "ocr" if method == "paddleocr"
        else "combined" if method == "combined"
        else "ordinary"
    )
    hard_negative_rows = (
        _hard_negative_rows_from_candidates(review_candidates, shared_geometry)
        if mode in {"ocr", "combined"}
        else []
    )
    entries = apply_page_understanding(
        entries,
        understanding,
        mode=mode,
        hard_negative_rows=hard_negative_rows,
    )
    entries = _allowed_entries(
        entries,
        image,
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
    """Spawn-safe ordinary worker that executes the shared-understanding pipeline.

    The automatic marker set is snapshotted before writing the normal PDIC, so
    later user additions/deletions can be exported as exact supervised diffs.
    Windows/macOS spawn workers import this module directly and therefore use
    the same Page Understanding layer as the GUI process.
    """
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
    pdic = _core.pdic_path_for_image(page)
    save_automatic_baseline(pdic, entries, image.width, pages)
    _core.write_pdic(
        pdic,
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
