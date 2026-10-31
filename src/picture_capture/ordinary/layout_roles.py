"""Ordinary Layout-role Entry materialization and emergency VB fallback.

This module owns both real algorithms. The processing facade forwards live
patchable dependencies at each call; neither OCR nor sidecar formats change.
"""
from __future__ import annotations

from typing import Any

from PIL import Image

from ..layout.page_understanding import PageUnderstanding
from ..models import AppSettings, Entry
from ..persistence.page_sections import PageSection


def materialize_layout_role_entries(
    understanding: PageUnderstanding,
    image: Image.Image | None = None,
    *,
    page_index: int = 0,
    diagnostics: list[dict[str, Any]] | None = None,
    refine_entry_y: Any,
    entry_type: Any,
) -> list[Entry]:
    """Materialize final Layout entry rows with canonical classification."""
    from ..proofreading.classification import copy_layout_line_classification

    layout = understanding.layout
    refined_y_by_line = (
        refine_entry_y(
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
            entry = entry_type(
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


def ordinary_vb_fallback(
    analysis_image: Image.Image,
    source: Image.Image,
    settings: AppSettings,
    effective: AppSettings,
    *,
    profile_page_index: int,
    page_sections: list[PageSection] | None,
    left_edge_detector: Any,
    allowed_entries: Any,
    sort_entries_reading_order: Any,
    replace_settings: Any,
) -> tuple[list[Entry], Any]:
    """Run original VB only when Page Understanding cannot produce columns."""
    vb_settings = replace_settings(effective)
    vb_settings.detection_method = "left_edge"
    entries, geometry = left_edge_detector(
        analysis_image,
        vb_settings,
        page_sections=page_sections,
    )
    entries = allowed_entries(
        list(entries),
        source,
        settings,
        geometry,
        profile_page_index,
        page_sections,
    )
    return sort_entries_reading_order(entries, geometry, page_sections), geometry
