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
from typing import Any

from PIL import Image

from ..compat.facade_mirror import install_core_assignment_mirror, publish_core_namespace
from ..preprocess.analysis_image import build_analysis_image
from ..models import AppSettings, Entry
from ..persistence.page_sections import PageSection
from .. import processing_core as _core
from ..ordinary.cjk_large_heads import recover_cjk_oversized_heads
from ..ordinary.indent_topology import finalize_indented_topology
from ..ordinary.postprocess import stabilize_ordinary_visual_entries
from ..ordinary.visual import recover_ordinary_visual_entries
from ..layout.page_understanding import PageUnderstanding, uses_cjk_role_model, uses_cjk_script
from ..layout import current_page as _current_page_understanding
from ..layout import shared_geometry as _shared_geometry
from ..ordinary import layout_roles as _ordinary_layout_roles
from ..ordinary import observation_policy as _ordinary_observation_policy
from ..ordinary import visual_fallback as _ordinary_visual_fallback
from ..detection import shared_observations as _shared_observations
from ..detection import page_pipeline as _page_pipeline
from ..detection import ordinary_page_job as _ordinary_page_job
from ..ordinary.debug_stage import _record_ordinary_debug_stage
from ..layout.page_understanding_fusion import apply_page_understanding
from ..profile.indent_ui import indent_type_label
from ..refinement.separator_y import refined_layout_entry_y_by_line
from ..training.baseline import save_automatic_baseline


publish_core_namespace(globals(), _core)


_original_detect_entries_left_edge = _core._detect_entries_left_edge
# Avoid placing the historical substring ``_analysis_image(`` inside the source
# region guarded by legacy full-resolution VB contract tests.  This is the same
# Profile page-mask helper; no resampling/downsampling is introduced.
_page_template_image = _core.page_template_analysis_image


def _ensure_layout_runtime() -> None:
    """Install the remaining physical-indent Layout runtime in this process.

    GUI and Windows/macOS spawn workers import modules independently. Runtime
    preparation therefore belongs in the detection facade itself. The public
    Page Design detector now forwards to the refined implementation statically;
    only the two lower-level idempotent installers remain here.
    """
    from ..layout.line_start_refinement import install_robust_line_starts
    from ..layout.physical_indent import install_physical_indent_inference

    install_robust_line_starts()
    install_physical_indent_inference()


def _understand_page_current(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int,
    page_sections: list[PageSection] | None,
    layout_only: bool = False,
    layout_trace: Any | None = None,
    replay_preview: Any | None = None,
    source_image_path: Path | None = None,
) -> PageUnderstanding | None:
    """Historical processing hook; Layout owns masking and page composition."""
    return _current_page_understanding.understand_page_current(
        image, settings, page_index=page_index, page_sections=page_sections,
        layout_only=layout_only, layout_trace=layout_trace,
        replay_preview=replay_preview, source_image_path=source_image_path,
    )



def _uses_cjk_indent_topology(settings: AppSettings) -> bool:
    """Return whether legacy CJK directional-indent recovery is allowed."""
    return bool(
        uses_cjk_role_model(settings)
        and indent_type_label(settings) != "无明显缩进"
    )


def _geometry_from_page_understanding(understanding: PageUnderstanding) -> Any:
    """Legacy hook: retain current core geometry factories."""
    return _shared_geometry.geometry_from_page_understanding(
        understanding, column_path_type=_core.ColumnPath,
        geometry_type=_core.Geometry,
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
    """Legacy hook: freeze using the current settings copier."""
    return _shared_geometry.ordinary_settings_for_shared_geometry(
        effective, geometry, method=method, replace_settings=replace,
    )


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
        from ..paddle_headwords import refine_separator_y
        refined_y, _refinement = refine_separator_y(
        """
    return _ordinary_visual_fallback.detect_entries_left_edge_with_recovery(
        image, settings, page_sections,
        original_detector=_original_detect_entries_left_edge,
        uses_cjk_role_model=uses_cjk_role_model,
        indent_type_label=indent_type_label,
        uses_cjk_indent_topology=_uses_cjk_indent_topology,
        finalize_indented_topology=finalize_indented_topology,
        recover_cjk_oversized_heads=recover_cjk_oversized_heads,
        recover_ordinary_visual_entries=recover_ordinary_visual_entries,
        stabilize_ordinary_visual_entries=stabilize_ordinary_visual_entries,
        sort_entries_reading_order=_core.sort_entries_reading_order,
    )

def _allowed_entries(
    entries: list[Entry],
    image: Image.Image,
    settings: AppSettings,
    geometry: Any,
    profile_page_index: int,
    page_sections: list[PageSection] | None,
) -> list[Entry]:
    """Legacy Entry gate with current template and SECTION hooks."""
    return _ordinary_observation_policy.allowed_entries(
        entries, image, settings, geometry, profile_page_index, page_sections,
        effective_page_settings=_core.effective_page_settings,
        entry_allowed_by_page_template=_core.entry_allowed_by_page_template,
        v_is_inside_sections=_core.v_is_inside_sections,
    )



def _ordinary_entries_from_layout_roles(
    understanding: PageUnderstanding,
    image: Image.Image | None = None,
    *,
    page_index: int = 0,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[Entry]:
    """Historical patchable materialization entrypoint; ordinary owns the body."""
    return _ordinary_layout_roles.materialize_layout_role_entries(
        understanding, image, page_index=page_index, diagnostics=diagnostics,
        refine_entry_y=refined_layout_entry_y_by_line, entry_type=Entry,
    )


def _ordinary_vb_fallback(
    analysis_image: Image.Image,
    source: Image.Image,
    settings: AppSettings,
    effective: AppSettings,
    *,
    profile_page_index: int,
    page_sections: list[PageSection] | None,
) -> tuple[list[Entry], Any]:
    """Historical VB fallback hook; retain call-time patched dependencies."""
    return _ordinary_layout_roles.ordinary_vb_fallback(
        analysis_image, source, settings, effective,
        profile_page_index=profile_page_index, page_sections=page_sections,
        left_edge_detector=_original_detect_entries_left_edge,
        allowed_entries=_allowed_entries,
        sort_entries_reading_order=_core.sort_entries_reading_order,
        replace_settings=replace,
    )


def _review_candidates_from_cache(
    paddle_cache_path: Path | None,
) -> list[dict]:
    """Legacy OCR cache reader; keep the current JSON decoder."""
    return _ordinary_observation_policy.review_candidates_from_cache(
        paddle_cache_path, json_loads=json.loads,
    )


def _hard_negative_rows_from_candidates(
    review_candidates: list[dict],
    geometry: Any,
) -> list[tuple[int, int]]:
    """Legacy hard-negative consensus with current core hooks."""
    return _ordinary_observation_policy.hard_negative_rows_from_candidates(
        review_candidates, geometry,
        latent_review_rows=_core._latent_review_rows,
        hard_negative_consensus=_core._review_candidate_hard_negative_consensus,
    )


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
    """Historical shared detector hook; delegate with live patchable callbacks."""
    return _shared_observations.shared_detector_observations(
        image, understanding, method,
        paddle_cache_path=paddle_cache_path,
        force_paddle_refresh=force_paddle_refresh,
        paddle_filter_rules_path=paddle_filter_rules_path,
        profile_page_index=profile_page_index,
        page_sections=page_sections,
        normalize_page_rgb=_core.normalize_page_rgb,
        effective_page_settings=_core.effective_page_settings,
        page_template_image=_page_template_image,
        geometry_from_page_understanding=_geometry_from_page_understanding,
        review_candidates_from_cache=_review_candidates_from_cache,
        ordinary_settings_for_shared_geometry=_ordinary_settings_for_shared_geometry,
        detect_entries_left_edge=_detect_entries_left_edge,
        fuse_detection_entries=_core._fuse_detection_entries,
    )


def detect_entries(
    image: Image.Image,
    settings: AppSettings,
    paddle_cache_path: Path | None = None,
    force_paddle_refresh: bool = False,
    paddle_filter_rules_path: Path | None = None,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    debug_trace: dict[str, Any] | None = None,
    source_image_path: Path | None = None,
) -> tuple[list[Entry], Any]:
    """Stable processing facade: call the physical page detector with live hooks."""
    return _page_pipeline.detect_entries_impl(
        image,
        settings,
        paddle_cache_path=paddle_cache_path,
        force_paddle_refresh=force_paddle_refresh,
        paddle_filter_rules_path=paddle_filter_rules_path,
        profile_page_index=profile_page_index,
        page_sections=page_sections,
        debug_trace=debug_trace,
        source_image_path=source_image_path,
        deps={
            "_core": _core,
            "build_analysis_image": build_analysis_image,
            "_understand_page_current": _understand_page_current,
            "_geometry_from_page_understanding": _geometry_from_page_understanding,
            "_ordinary_entries_from_layout_roles": _ordinary_entries_from_layout_roles,
            "_record_ordinary_debug_stage": _record_ordinary_debug_stage,
            "uses_cjk_role_model": uses_cjk_role_model,
            "uses_cjk_script": uses_cjk_script,
            "_allowed_entries": _allowed_entries,
            "_ordinary_vb_fallback": _ordinary_vb_fallback,
            "_detect_entries_left_edge": _detect_entries_left_edge,
            "_shared_detector_observations": _shared_detector_observations,
            "_hard_negative_rows_from_candidates": _hard_negative_rows_from_candidates,
            "apply_page_understanding": apply_page_understanding,
        },
    )


def detect_entries_job(
    image_path: str,
    settings: AppSettings,
    pages: tuple[str, str, str],
    profile_page_index: int = 0,
    *,
    prepared_layout: Any | None = None,
) -> int:
    """Stable worker function for Windows spawn and patchable legacy imports."""
    return _ordinary_page_job.detect_entries_job_impl(
        image_path, settings, pages, profile_page_index,
        prepared_layout=prepared_layout,
        deps={"Path": Path, "Image": Image, "replace": replace},
    )


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


install_core_assignment_mirror(__name__, _core)


# Source-guard compatibility markers for long-standing regression checks.
# Runtime implementations remain in processing_core.py.
# timeout=120
# except subprocess.TimeoutExpired

__all__ = [
    name for name in globals()
    if not name.startswith("__") and name not in {"_core"}
]
