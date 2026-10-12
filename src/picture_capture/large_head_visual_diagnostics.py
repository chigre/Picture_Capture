"""Read-only oversized-CJK candidate diagnostics for the GUI.

Runs the exact existing detector with its optional trace, then inspects the
same canonical Layout roles and final ordinary auto-output. Nothing is
persisted and no PDIC, project settings, or entry lists are changed.

Final separator association is by nearby X/Y and is labeled as proximity,
not a claim that one detector alone caused the line.
"""
from __future__ import annotations

from typing import Any

from PIL import Image

from .image_utils import build_analysis_image
from .models import AppSettings
from .layout_core_understanding import understand_layout_core
from .profile_semantics import effective_page_settings


def _nearest_layout_row(
    layout: Any, item: dict[str, Any],
) -> tuple[str, str]:
    from .entry_classification import get_layout_line_classification

    index = int(item["column"])
    columns = list(getattr(layout, "columns", ()) or ())
    if not 0 <= index < len(columns):
        return "unmapped", "unknown"
    column = columns[index]
    top = int(item["canonical_box"][1])
    lines = list(getattr(column, "lines", ()) or ())
    if not lines:
        return "unmapped", "unknown"
    nearest = min(
        lines, key=lambda line: abs(
            int(layout.body_top) + int(line.y0) - top,
        ),
    )
    distance = abs(int(layout.body_top) + int(nearest.y0) - top)
    reference = float(item["reference_height"])
    if distance > max(7.0, reference * .75):
        return "unmapped", "unknown"
    return (
        str(getattr(nearest, "role", "unknown") or "unknown"),
        str(get_layout_line_classification(nearest).entry_source),
    )


def _diagnostic_settings(effective: AppSettings) -> dict[str, Any]:
    """Parameters sufficient to compare two page diagnostics, not all settings."""
    names = (
        "detection_method", "ocr_language", "paddle_language",
        "dictionary_profile_id", "character_height", "row_padding",
        "layout_columns_policy", "ordinary_auto_columns",
        "ordinary_auto_start_y", "ordinary_auto_manual_x",
        "ordinary_auto_column_width", "ordinary_auto_gutter",
        "ordinary_auto_character_height", "ordinary_auto_row_padding",
        "profile_cjk_allow_single_headword",
        "profile_cjk_allow_bracketed_headword",
        "layout_mask_illustrations",
        "ordinary_indent_type",
    )
    result = {}
    for name in names:
        if hasattr(effective, name):
            value = getattr(effective, name)
            if isinstance(value, (str, int, float, bool, type(None))):
                result[name] = value
    return result


def _diagnostic_layout(layout: Any) -> dict[str, Any]:
    """Serialize physical row evidence from the SAME traced Layout run."""
    from .entry_classification import get_layout_line_classification
    from .layout_physical_indent import normalized_physical_indents

    rows: list[dict[str, Any]] = []
    for col_index, column in enumerate(list(getattr(layout, "columns", ()) or ())):
        actual_lines = sorted(
            list(getattr(column, "lines", ()) or ()),
            key=lambda item: (int(item.y0), int(item.y1)),
        )
        corrected = normalized_physical_indents(actual_lines)
        for row_index, line in enumerate(actual_lines):
            cy0 = int(layout.body_top) + int(line.y0)
            cy1 = int(layout.body_top) + int(line.y1)
            sx, sy = layout.transform.canonical_to_source_point(
                int(column.left), cy0, layout.source_size,
            )
            sx1, sy1 = layout.transform.canonical_to_source_point(
                int(column.left), cy1, layout.source_size,
            )
            meta = get_layout_line_classification(line)
            rows.append({
                "id": f"C{col_index+1:02d}-R{row_index+1:03d}",
                "column": col_index,
                "canonical_y0": cy0, "canonical_y1": cy1,
                "source_x": int(sx), "source_y": int(sy),
                "source_x1": int(sx1), "source_y1": int(sy1),
                "role": str(getattr(line, "role", "unknown") or "unknown"),
                "entry_source": str(meta.entry_source),
                "first_x": float(getattr(line, "first_x", 0) or 0),
                "corrected_first_x": round(float(
                    corrected.get(id(line), getattr(line, "first_x", 0) or 0)
                ), 3),
            })
    return {
        "physical_rows": rows,
        "body_top": int(layout.body_top),
        "body_bottom": int(layout.body_bottom),
        "ordinary_line_height": float(layout.ordinary_line_height),
        "ordinary_line_pitch": float(getattr(layout, "ordinary_line_pitch", 0) or 0),
        "indent_type": str(getattr(layout, "indent_type", "")),
        "transform": str(getattr(layout.transform, "kind", "")),
        "reason": str(getattr(layout, "reason", "")),
        "columns": [{
            "index": i, "left": int(col.left), "right": int(col.right),
            "physical_lines": len(getattr(col, "lines", ()) or ()),
            "entry_rows": sum(str(getattr(row, "role", "")) == "entry"
                              for row in getattr(col, "lines", ()) or ()),
            "body_rows": sum(str(getattr(row, "role", "")) == "body"
                             for row in getattr(col, "lines", ()) or ()),
            "body_mode": (
                {"center": float(col.body_mode.center),
                 "support": int(getattr(col.body_mode, "support", 0) or 0)}
                if getattr(col, "body_mode", None) is not None else None
            ),
            "entry_modes": [{
                "center": float(mode.center),
                "support": int(getattr(mode, "support", 0) or 0),
            } for mode in getattr(col, "entry_modes", ()) or ()],
        } for i, col in enumerate(getattr(layout, "columns", ()) or ())],
    }


def build_large_head_diagnostics(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
    page_sections: list[Any] | None = None,
) -> dict[str, Any]:
    """Return diagnostic data from the *real*, unmodified CJK detection code."""
    from . import processing
    from .ordinary_large_head_evidence import _uses_cjk_large_heads

    result: dict[str, Any] = {
        "enabled": False, "candidates": [], "final_lines": [],
        "summary": {}, "ordinary_mode": False,
        "message": "",
    }
    source = processing._core.normalize_page_rgb(image)
    try:
        # Stable content fingerprint prevents accidental comparisons of
        # distinct scanned pages that happen to have identical pixel sizes.
        from hashlib import sha256
        result["image_sha256"] = sha256(source.tobytes()).hexdigest()
        effective = effective_page_settings(
            settings, source.size, int(page_index),
        )
        large_head_enabled = bool(_uses_cjk_large_heads(effective))
        ordinary_mode = str(getattr(
            effective, "detection_method", "",
        ) or "").lower() not in {"paddleocr", "combined"}
        result["ordinary_mode"] = ordinary_mode
        analysis = build_analysis_image(source, effective)
        try:
            # Reproduce the exact masked input used by normal Layout. The
            # independent diagnostic Layout runs the production detector once
            # at its real pre-fusion stage; it does NOT consult or overwrite
            # the normal shared Layout cache.
            candidate_image = analysis
            if bool(getattr(effective, "layout_mask_illustrations", False)):
                from .layout_illustration_mask import mask_large_illustrations_for_layout
                candidate_image, _stats = mask_large_illustrations_for_layout(
                    analysis, effective, profile_page_index=int(page_index),
                )
            try:
                trace: list[dict[str, Any]] = []
                fusion_context: dict[str, Any] = {}
                understanding = understand_layout_core(
                    candidate_image, effective,
                    page_index=int(page_index),
                    large_head_diagnostics=trace,
                    large_head_debug_context=fusion_context,
                )
            finally:
                if candidate_image is not analysis:
                    candidate_image.close()

            result["effective_settings"] = _diagnostic_settings(effective)
            result["layout_snapshot"] = _diagnostic_layout(understanding.layout)
            result["layout_role_transitions"] = fusion_context.get("role_transitions", [])
            result["layout_role_stage_counts"] = fusion_context.get("role_counts", {})
            result["fusion_promotion_counts"] = fusion_context.get("promotion_counts", {})

            for item in trace:
                item["layout_role"], item["layout_source"] = _nearest_layout_row(
                    understanding.layout, item,
                )

            final_entries: list[Any] = []
            if ordinary_mode:
                # Only an in-memory computation of automatic candidates. Unlike
                # the user's saved PDIC lines this is the actual pipeline output.
                pipeline_trace: dict[str, Any] = {}
                final_entries, _geometry = processing.detect_entries(
                    image, settings, profile_page_index=int(page_index),
                    page_sections=page_sections,
                    debug_trace=pipeline_trace,
                )
                result["ordinary_pipeline_stages"] = pipeline_trace.get("stages", [])
            result["final_lines"] = [{
                "x": int(entry.x), "y": int(entry.y),
                "source": str(getattr(entry, "ocr_source", "") or ""),
                "oversized": bool(getattr(entry, "ocr_oversized_cjk", False)),
            } for entry in final_entries]
            from .ordinary_unified_diagnostics import (
                SCHEMA, compose_ordinary_evidence_report,
            )
            unified = compose_ordinary_evidence_report(
                result["layout_snapshot"],
                trace,
                result.get("ordinary_pipeline_stages", []),
                result["layout_role_transitions"],
                result["final_lines"],
            )
            result["schema"] = SCHEMA
            result["unified_report"] = unified
            result["review_queue"] = unified["review_queue"]
            result["candidate_registry"] = unified["registry"]
            result["summary_unified"] = unified["summary"]
            result["large_head_detector_enabled"] = large_head_enabled

            for item in trace:
                index = int(item["column"])
                cols = understanding.layout.columns
                if not 0 <= index < len(cols):
                    item["nearby_final_lines"] = []
                    continue
                source_x, source_y = understanding.layout.transform.canonical_to_source_point(
                    int(cols[index].left), int(item["canonical_box"][1]),
                    understanding.layout.source_size,
                )
                ref = max(8.0, float(item["reference_height"]))
                threshold = max(10.0, min(ref * 1.3,
                    float(getattr(understanding.layout, "ordinary_line_pitch", ref * 1.4)) * .9,
                ))
                item["nearby_final_lines"] = [
                    {"x": line["x"], "y": line["y"], "source": line["source"]}
                    for line in result["final_lines"]
                    if abs(line["x"] - source_x) <= max(12.0, ref * .80)
                    and abs(line["y"] - source_y) <= threshold
                ]

            result["candidates"] = trace
            result["enabled"] = True
            statuses = ("accepted", "rejected_weak", "rejected_row_front",
                        "size_or_density", "group_too_tall", "split_parent")
            result["summary"] = {
                key: sum(1 for row in trace if row["status"] == key)
                for key in statuses
            }
            result["summary"]["detector_output"] = sum(
                bool(row.get("detector_output")) for row in trace
            )
            result["message"] = (
                "蓝线表示附近最终自动线；关联仅按位置，不代表因果。"
                if ordinary_mode else
                "当前不是普通画线模式，仅提供 Layout 和大字候选证据。"
            )
            return result
        finally:
            analysis.close()
    finally:
        if source is not image:
            source.close()


__all__ = ["build_large_head_diagnostics"]
