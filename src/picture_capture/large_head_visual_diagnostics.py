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
        effective = effective_page_settings(
            settings, source.size, int(page_index),
        )
        if not _uses_cjk_large_heads(effective):
            result["message"] = "此页面未启用 CJK 大字单字检测"
            return result
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
                understanding = understand_layout_core(
                    candidate_image, effective,
                    page_index=int(page_index), large_head_diagnostics=trace,
                )
            finally:
                if candidate_image is not analysis:
                    candidate_image.close()

            for item in trace:
                item["layout_role"], item["layout_source"] = _nearest_layout_row(
                    understanding.layout, item,
                )

            final_entries: list[Any] = []
            if ordinary_mode:
                # Only an in-memory computation of automatic candidates. Unlike
                # the user's saved PDIC lines this is the actual pipeline output.
                final_entries, _geometry = processing.detect_entries(
                    image, settings, profile_page_index=int(page_index),
                    page_sections=page_sections,
                )
            result["final_lines"] = [{
                "x": int(entry.x), "y": int(entry.y),
                "source": str(getattr(entry, "ocr_source", "") or ""),
                "oversized": bool(getattr(entry, "ocr_oversized_cjk", False)),
            } for entry in final_entries]

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
                "当前不是普通画线模式，不显示普通画线最终线。"
            )
            return result
        finally:
            analysis.close()
    finally:
        if source is not image:
            source.close()


__all__ = ["build_large_head_diagnostics"]
