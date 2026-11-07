"""Canonical page detection orchestration: ordinary Layout roles and OCR/combined.

This module owns the actual detector branching and evidence recovery algorithm.
The stable public processing.detect_entries entry injects current module globals
per invocation to preserve long-standing runtime monkeypatch seams. No implicit
Paddle/GPU construction occurs during import.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from PIL import Image
from ..models import AppSettings, Entry
from ..persistence.page_sections import PageSection

def detect_entries_impl(
    image: Image.Image,
    settings: AppSettings,
    paddle_cache_path: Path | None = None,
    force_paddle_refresh: bool = False,
    paddle_filter_rules_path: Path | None = None,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    debug_trace: dict[str, Any] | None = None,
    source_image_path: Path | None = None,
    *, deps: dict[str, Any],
) -> tuple[list[Entry], Any]:
    _core = deps["_core"]
    build_analysis_image = deps["build_analysis_image"]
    _understand_page_current = deps["_understand_page_current"]
    _geometry_from_page_understanding = deps["_geometry_from_page_understanding"]
    _ordinary_entries_from_layout_roles = deps["_ordinary_entries_from_layout_roles"]
    _record_ordinary_debug_stage = deps["_record_ordinary_debug_stage"]
    uses_cjk_role_model = deps["uses_cjk_role_model"]
    uses_cjk_script = deps["uses_cjk_script"]
    _allowed_entries = deps["_allowed_entries"]
    _ordinary_vb_fallback = deps["_ordinary_vb_fallback"]
    _detect_entries_left_edge = deps["_detect_entries_left_edge"]
    _shared_detector_observations = deps["_shared_detector_observations"]
    _hard_negative_rows_from_candidates = deps["_hard_negative_rows_from_candidates"]
    apply_page_understanding = deps["apply_page_understanding"]
    """Detect entries using shared denoised page analysis.

    Ordinary mode consumes the cached Layout Core row roles directly. VB is
    never allowed to modify, veto, add to, or replace a usable Layout role
    assignment. OCR/combined retain the full enriched Page Understanding path.
    """
    from time import perf_counter as _pc
    from ..quality.draw_performance_profile import enabled as _profile_on
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
                from ..ordinary.oversized_head_guard import suppress_oversized_head_fragment_entries
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
                from ..ordinary.crossing_separator import adjust_page_coherent_crossing_separators
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
                from ..ordinary.bracket_pair import recover_bracketed_ordinary_entries
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
                from ..ordinary.independent_indent_rescue import recover_depleted_indent_columns
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
            from ..ordinary.final_visual_consistency import correct_anomalous_final_ordinary_entries
            entries, last_mile = correct_anomalous_final_ordinary_entries(
                analysis_image, effective, understanding.layout, entries,
            )
            _record_ordinary_debug_stage(
                debug_trace, "anomalous_final_visual_consistency", entries,
                stats=dict(last_mile),
            )
            from ..ordinary.final_visual_consistency import suppress_proven_bracket_body_continuations
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
            from ..ordinary.final_visual_consistency import suppress_blank_layout_rows_before_proven_head
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
                from ..quality.draw_performance_profile import record_page
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
