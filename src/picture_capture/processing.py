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

from .facade_compat import install_core_assignment_mirror, publish_core_namespace
from .image_utils import build_analysis_image
from .models import AppSettings, Entry
from .page_sections import PageSection
from . import processing_core as _core
from .ordinary_cjk_large_heads import recover_cjk_oversized_heads
from .ordinary_indent_topology import finalize_indented_topology
from .ordinary_postprocess import stabilize_ordinary_visual_entries
from .ordinary_visual import recover_ordinary_visual_entries
from .page_understanding import PageUnderstanding, uses_cjk_role_model, uses_cjk_script
from .page_understanding_fusion import apply_page_understanding
from .profile_indent_ui import indent_type_label
from .separator_y_refinement import refined_layout_entry_y_by_line
from .training_baseline import save_automatic_baseline


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
    from .layout_line_start_refinement import install_robust_line_starts
    from .layout_physical_indent import install_physical_indent_inference

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
    """Resolve Page Understanding with optional static illustration masking."""
    analysis_image = image
    mask_stats = None
    append_reason = None
    mask_candidates: list[dict[str, Any]] | None = (
        [] if layout_trace is not None else None
    )
    masking_enabled = bool(getattr(settings, "layout_mask_illustrations", False))
    mask_error = None
    if masking_enabled:
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
                **({"source_image_path": source_image_path}
                   if source_image_path is not None else {}),
                **({"candidate_debug": mask_candidates}
                   if mask_candidates is not None else {}),
            )
        except Exception as exc:
            if bool(getattr(settings, "layout_mask_illustrations_use_existing", False)):
                raise
            analysis_image = image
            mask_stats = IllustrationMaskStats()
            mask_error = f"{type(exc).__name__}: {exc}"

    if layout_trace is not None:
        # A disabled/no-candidates/no-mask/failure result is still an explicit
        # stage: the user must not infer that masking was skipped silently.
        stats = mask_stats
        layout_trace.add_note(
            "illustration_mask", "Layout 前插图区域检测／白化",
            ("启用后先筛选自动插图候选，只有安全通过的多边形才填白。"
             if masking_enabled else "当前项目已关闭 Layout 前插图掩膜。"),
            details={
                "enabled": masking_enabled,
                "detected": int(stats.detected) if stats else 0,
                "masked": int(stats.masked) if stats else 0,
                "rejected_small": int(stats.rejected_small) if stats else 0,
                "rejected_headlike": int(stats.rejected_headlike) if stats else 0,
                "failure_fallback_to_unmasked": mask_error,
            },
            candidates=mask_candidates,
        )
        if replay_preview is not None and masking_enabled:
            replay_preview("illustration_mask", analysis_image)

    try:
        # Both the layout-only and enriched Page Understanding branches use
        # explicit Physical Layout composition. Legacy installer preparation is
        # no longer part of the normal detection path.
        if layout_only:
            from .layout_core_understanding import understand_layout_core

            understanding = understand_layout_core(
                analysis_image,
                settings,
                page_index=page_index,
                **({"trace": layout_trace} if layout_trace is not None else {}),
            )
        else:
            from .layout_composition import understand_composed_page

            understanding = understand_composed_page(
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
    # All private call sites pass detect_entries()' already-normalized source.
    # This filter only needs page size, so a second full-page RGB copy is waste.
    source_size = tuple(image.size)
    effective = _core.effective_page_settings(
        settings, source_size, profile_page_index,
    )
    return [
        entry for entry in entries
        if _core.entry_allowed_by_page_template(
            entry.x, entry.y, source_size, effective, profile_page_index,
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
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[Entry]:
    """Materialize final Layout entry rows with canonical classification."""
    from .entry_classification import copy_layout_line_classification

    layout = understanding.layout
    refined_y_by_line = (
        refined_layout_entry_y_by_line(
            image,
            understanding,
            page_index=int(page_index),
            diagnostics=diagnostics,
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


def _record_ordinary_debug_stage(
    trace: dict[str, Any] | None,
    stage: str,
    entries: list[Entry],
    **details: Any,
) -> None:
    """Snapshot each materialized marker at the actual production seam.

    Enabled ONLY for a user-initiated read-only diagnostic run. Never writes
    project files, mutates role objects or changes detection decisions.
    """
    if trace is None:
        return
    rows = [{
        "x": int(item.x), "y": int(item.y),
        "source": str(getattr(item, "ocr_source", "") or ""),
        "issue_type": str(getattr(item, "issue_type", "") or ""),
        "oversized": bool(getattr(item, "ocr_oversized_cjk", False)),
    } for item in entries]
    stages = trace.setdefault("stages", [])
    current_keys = {(item["x"], item["y"]) for item in rows}
    previous = stages[-1]["entries"] if stages else []
    previous_keys = {(item["x"], item["y"]) for item in previous}
    stages.append({
        "stage": stage, "count": len(rows), "entries": rows,
        "added": [item for item in rows
                  if (item["x"], item["y"]) not in previous_keys],
        "removed": [item for item in previous
                    if (item["x"], item["y"]) not in current_keys],
        **details,
    })
    replay_trace = trace.get("_layout_replay_trace")
    if replay_trace is not None:
        from .ordinary_unified_diagnostics import STAGE_DESCRIPTIONS
        replay_trace.add_entries(
            stages[-1], description=STAGE_DESCRIPTIONS.get(stage, stage),
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
    """Detect entries using shared denoised page analysis.

    Ordinary mode consumes the cached Layout Core row roles directly. VB is
    never allowed to modify, veto, add to, or replace a usable Layout role
    assignment. OCR/combined retain the full enriched Page Understanding path.
    """
    from time import perf_counter as _pc
    from .draw_performance_profile import enabled as _profile_on
    _timing = _profile_on() and str(getattr(settings, "detection_method", "")).lower() == "left_edge"
    _nested = {}
    _tick = _pc() if _timing else 0.0
    def _mark(name):
        nonlocal _tick
        if _timing:
            now = _pc()
            _nested[name] = _nested.get(name, 0.0) + now - _tick
            _tick = now
    source = _core.normalize_page_rgb(image)
    effective = _core.effective_page_settings(
        settings, source.size, profile_page_index,
    )
    method = str(getattr(effective, "detection_method", "") or "").strip().lower()
    analysis_image = build_analysis_image(source, effective)
    ordinary_mode = method not in {"paddleocr", "combined"}
    replay_trace = debug_trace.get("_layout_replay_trace") if debug_trace else None
    replay_preview = debug_trace.get("_layout_replay_preview") if debug_trace else None
    if replay_trace is not None:
        replay_trace.add_note(
            "image_preparation", "共享分析图与去噪",
            "按当前页实际有效 Profile 生成共享分析图；以下插图掩膜发生在 Layout 前。",
            details={
                "source_size": list(source.size),
                "denoise": dict(analysis_image.info.get("analysis_denoise_profile") or {}),
                "effective_detection_method": method,
            },
        )
        if replay_preview is not None:
            replay_preview("image_preparation", analysis_image)

    _mark("inner_image_prepare")
    understanding = _understand_page_current(
        analysis_image,
        effective,
        page_index=profile_page_index,
        page_sections=page_sections,
        layout_only=ordinary_mode,
        source_image_path=source_image_path,
        layout_trace=replay_trace if ordinary_mode else None,
        replay_preview=replay_preview if ordinary_mode else None,
    )

    _mark("inner_page_understanding")
    # Ordinary drawing is a direct materialization of final Layout Core roles.
    if ordinary_mode:
        if (
            understanding is not None
            and list(getattr(understanding.layout, "columns", []) or [])
        ):
            geometry = _geometry_from_page_understanding(understanding)
            y_refine_diagnostics = [] if replay_trace is not None else None
            entries = _ordinary_entries_from_layout_roles(
                understanding,
                analysis_image,
                page_index=profile_page_index,
                diagnostics=y_refine_diagnostics,
            )
            if replay_trace is not None:
                replay_trace.add_note(
                    "separator_y_per_line",
                    "横线 Y 精修诊断（逐条）",
                    "记录普通画线 Layout 词条初始 Y、墨迹谷结果、位移限制、"
                    "真实左右栏 ROI 与异常。此阶段只读，后续修正可能继续改变坐标。",
                    details={
                        "count": len(y_refine_diagnostics),
                        "errors": sum(bool(x.get("error")) for x in y_refine_diagnostics),
                        "lines": y_refine_diagnostics,
                    },
                    candidates=[
                        {"status": "refined" if not x.get("error") else "error",
                         "column": x.get("column"), "reason": x.get("reason"),
                         "source_box": [x.get("roi_x0"), x.get("clamped_y"),
                                        x.get("roi_x1"), x.get("clamped_y")],
                         "coarse_y": x.get("coarse_y"),
                         "raw_refined_y": x.get("raw_refined_y"),
                         "clamped_y": x.get("clamped_y"),
                         "shift": x.get("shift"),
                         "roi_x0": x.get("roi_x0"), "roi_x1": x.get("roi_x1"),
                         "search_top": x.get("search_top"),
                         "search_bottom": x.get("search_bottom"),
                         "clamped": x.get("clamped"),
                         "error": x.get("error")}
                        for x in y_refine_diagnostics if x.get("column")
                    ],
                )
            _record_ordinary_debug_stage(
                debug_trace, "layout_role_materialization", entries,
            )
            _mark("inner_role_materialization")
            # Large ideographs may generate several spurious Layout entry
            # rows inside one glyph; veto only image-confirmed duplicates.
            if uses_cjk_role_model(effective) and str(getattr(understanding.layout.transform, "kind", "identity")) == "identity":
                from .ordinary_oversized_head_guard import suppress_oversized_head_fragment_entries
                columns = understanding.layout.columns
                entries = suppress_oversized_head_fragment_entries(
                    entries, analysis_image,
                    [int(column.left) for column in columns],
                    [int(column.right - column.left) for column in columns],
                    float(understanding.layout.ordinary_line_height),
                )
                _record_ordinary_debug_stage(
                    debug_trace, "oversized_fragment_veto", entries,
                )
            # This is an EARLY correction of EXISTING Layout candidates,
            # not a final global Y adjustment. Bracket recovery will inspect
            # actual print gaps and may add independently anchored separators;
            # shifting those late-added positions by this offset is unsafe.
            # A coherent page shift is supported only by real ink gaps.
            _visual_y_shift = 0
            if (
                uses_cjk_role_model(effective)
                and str(getattr(understanding.layout.transform, "kind", "identity")) == "identity"
            ):
                from .ordinary_crossing_separator import adjust_page_coherent_crossing_separators
                entries, _visual_y_shift = adjust_page_coherent_crossing_separators(
                    entries, analysis_image,
                    float(understanding.layout.ordinary_line_height),
                )
                _record_ordinary_debug_stage(
                    debug_trace, "coherent_separator_y_refinement", entries,
                    shift=_visual_y_shift,
                    scope="已有 Layout 候选（【】恢复之前）；并非最终全部画线",
                    rationale="先纠正穿过大字的初始线，供后续【】匹配去重",
                )
            if (
                uses_cjk_script(effective)
                and bool(getattr(effective, "profile_cjk_allow_bracketed_headword", True))
            ):
                from .ordinary_bracket_pair import recover_bracketed_ordinary_entries
                layout = understanding.layout
                rotated = str(getattr(layout.transform, "kind", "identity")) != "identity"
                bracket_image = (
                    layout.transform.canonical_image_for_analysis(analysis_image)
                    if rotated else analysis_image
                )
                bracket_visual_candidates: list[dict[str, Any]] | None = (
                    [] if replay_trace is not None else None
                )
                try:
                    entries = recover_bracketed_ordinary_entries(
                        entries, bracket_image, layout.columns,
                        int(layout.body_top), int(layout.body_bottom),
                        float(layout.ordinary_line_height),
                        transform=layout.transform, source_size=layout.source_size,
                        **({"candidate_debug": bracket_visual_candidates}
                           if bracket_visual_candidates is not None else {}),
                    )
                finally:
                    if rotated:
                        bracket_image.close()
                _record_ordinary_debug_stage(
                    debug_trace, "bracketed_headword_recovery", entries,
                    **({"candidates": bracket_visual_candidates}
                       if bracket_visual_candidates is not None else {}),
                )
            elif replay_trace is not None:
                replay_trace.add_note(
                    "bracketed_headword_not_run", "【】词头恢复：本页未执行",
                    "实际普通画线流程跳过了此步骤：当前页面不是 CJK 脚本，"
                    "或 Profile 的【】词头恢复开关未开启。"
                    "这不代表检测到候选后被拒绝。",
                    details={
                        "cjk_script": bool(uses_cjk_script(effective)),
                        "profile_cjk_allow_bracketed_headword": bool(
                            getattr(effective, "profile_cjk_allow_bracketed_headword", True)
                        ),
                    },
                )
            # Keep proven lemma-indentation evidence from a second physical
            # analyzer when the primary normalization lost an entire column.
            if not uses_cjk_role_model(effective):
                from .ordinary_independent_indent_rescue import recover_depleted_indent_columns
                entries = recover_depleted_indent_columns(
                    analysis_image, effective, understanding, entries,
                    page_index=profile_page_index,
                )
            _mark("inner_entry_recovery")
            entries = _allowed_entries(
                entries,
                source,
                settings,
                geometry,
                profile_page_index,
                page_sections,
            )
            _record_ordinary_debug_stage(
                debug_trace, "page_template_section_filter", entries,
            )
            # The final separator Y differs from the raw physical LayoutLine.y0.
            # Check an anomalous CJK page at its *actual* emitted coordinates;
            # the earlier indent-mode detector cannot independently veto itself.
            from .ordinary_final_visual_consistency import correct_anomalous_final_ordinary_entries
            entries, last_mile = correct_anomalous_final_ordinary_entries(
                analysis_image, effective, understanding.layout, entries,
            )
            _record_ordinary_debug_stage(
                debug_trace, "anomalous_final_visual_consistency", entries,
                stats=dict(last_mile),
            )
            from .ordinary_final_visual_consistency import suppress_proven_bracket_body_continuations
            entries, bracket_body_removed = suppress_proven_bracket_body_continuations(
                analysis_image, effective, understanding.layout, entries,
            )
            _record_ordinary_debug_stage(
                debug_trace, "proven_bracket_body_continuation", entries,
                removed_details=bracket_body_removed,
            )
            if bracket_body_removed:
                understanding.layout.reason += (
                    f"; bracket_body_continuations_removed={len(bracket_body_removed)}"
                )
            from .ordinary_final_visual_consistency import suppress_blank_layout_rows_before_proven_head
            entries, removed_blank = suppress_blank_layout_rows_before_proven_head(
                analysis_image, effective, understanding.layout, entries,
            )
            _record_ordinary_debug_stage(
                debug_trace, "blank_before_proven_head", entries,
                removed_blank=int(removed_blank),
            )
            if removed_blank:
                understanding.layout.reason += (
                    f"; final_blank_before_proven={removed_blank}"
                )
            if last_mile["repaired_columns"]:
                understanding.layout.reason += (
                    f"; final_visual_repaired={last_mile['repaired_columns']}"
                    f" final_visual_rejected={last_mile['removed_false_entries']}"
                    f" final_visual_glyph_fragments={last_mile['removed_glyph_fragments']}"
                    f" final_visual_heads_added={last_mile['added_verified_heads']}"
                )
            # All candidate additions, source upgrades, vetoes and Y
            # refinements are complete at this point. Final reading-order
            # sorting does NOT move Y. Recording this boundary is important:
            # the early coherent adjustment cannot safely be applied to
            # bracket separators located independently from print gaps.
            _record_ordinary_debug_stage(
                debug_trace, "final_y_coordinates_locked", entries,
                move_y=False,
                layout_initial_page_shift=int(_visual_y_shift),
                scope="最终剩余全部候选，含后续【】及大字头来源；只读核对",
                rationale="后续仅排序，不再对所有来源执行统一 Y 平移",
            )
            _mark("inner_final_filter_and_corrections")
            sorted_entries = _core.sort_entries_reading_order(
                entries, geometry, page_sections,
            )
            _record_ordinary_debug_stage(
                debug_trace, "final_reading_order", sorted_entries,
            )
            _mark("inner_sort")
            if _timing:
                from .draw_performance_profile import record_page
                record_page("<substage>", profile_page_index, _nested,
                            stage_group="detect_entries_inner")
            return sorted_entries, geometry

        if replay_trace is not None:
            replay_trace.add_note(
                "vb_fallback", "Layout 物理行不可用：使用 VB 备用通道",
                "该页未产生可用 Layout 列，实际画线走 VB 备用路径，"
                "不是正常 Layout Core／【】恢复阶段。",
            )
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
    *,
    prepared_layout: Any | None = None,
) -> int:
    """Run ordinary drawing with optional isolated, exactly-once GPU preflight.

    Ordinary serial calls have NO injected estimate and keep the old path.
    """
    from contextlib import nullcontext
    from time import perf_counter
    from .draw_performance_profile import enabled as profile_enabled, record_page, bind_page, unbind_page
    profiling = profile_enabled()
    stages = {}
    total_start = perf_counter()
    tick = total_start
    from .bootstrap.worker import build_worker_services
    if prepared_layout is not None:
        from .ordinary_gpu_pipeline import (
            use_prepared_layout, validate_prepared_layout,
            verify_prepared_source,
        )

        verify_prepared_source(image_path, profile_page_index, prepared_layout)
        estimate_context = use_prepared_layout(prepared_layout)
    else:
        estimate_context = nullcontext(None)

    services = build_worker_services()
    if profiling:
        stages["bootstrap"] = perf_counter() - tick
        tick = perf_counter()
    formats = services.formats
    processing_module = services.processing

    page = Path(image_path)
    with Image.open(page) as opened:
        image = processing_module._core.normalize_page_rgb(opened)

    if profiling:
        stages["image_open_normalize"] = perf_counter() - tick
        tick = perf_counter()

    page_binding = bind_page(page) if profiling else None
    try:
        current = replace(settings)
        current.detection_method = "left_edge"
        sections = processing_module._core.read_page_sections(page)
        if profiling:
            stages["page_sections"] = perf_counter() - tick
            tick = perf_counter()
        with estimate_context as preflight_state:
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
                    page_sections=sections,
                    **({"source_image_path": page}
                       if getattr(current, "layout_mask_illustrations", False) else {}),
                )
            if preflight_state is not None:
                # An optional internal fallback must not turn a missing GPU
                # estimate into altered lines or a second Paddle model.
                validate_prepared_layout(preflight_state)
                verify_prepared_source(page, profile_page_index, prepared_layout)

        if profiling:
            stages["detect_entries"] = perf_counter() - tick
            tick = perf_counter()
        pdic = processing_module._core.pdic_path_for_image(page)
        services.save_automatic_baseline(pdic, entries, image.width, pages)
        if profiling:
            stages["automatic_baseline"] = perf_counter() - tick
            tick = perf_counter()
        formats.write_pdic(
            pdic,
            entries,
            image.width,
            pages,
        )
        if profiling:
            stages["pdic_write"] = perf_counter() - tick
            stages["total_page"] = perf_counter() - total_start
            record_page(page, profile_page_index, stages)
        return len(entries)
    finally:
        if page_binding is not None:
            unbind_page(page_binding)
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


install_core_assignment_mirror(__name__, _core)


# Source-guard compatibility markers for long-standing regression checks.
# Runtime implementations remain in processing_core.py.
# timeout=120
# except subprocess.TimeoutExpired

__all__ = [
    name for name in globals()
    if not name.startswith("__") and name not in {"_core"}
]
