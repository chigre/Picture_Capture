from __future__ import annotations

"""Ordinary legacy-VB observation and CJK/non-CJK visual recovery.

The historical processing._detect_entries_left_edge is a call-time compatibility
boundary. This module owns the actual detector/postprocessing sequence; its
collaborators are supplied by the facade on each invocation so public
monkeypatches and SECTION ordering remain effective. It never writes PDIC/PPP
or invokes an OCR model.
"""

from typing import Any
from PIL import Image
from ..models import AppSettings, Entry
from ..persistence.page_sections import PageSection


def detect_entries_left_edge_with_recovery(
    image: Image.Image,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
    *,
    original_detector: Any,
    uses_cjk_role_model: Any,
    indent_type_label: Any,
    uses_cjk_indent_topology: Any,
    finalize_indented_topology: Any,
    recover_cjk_oversized_heads: Any,
    recover_ordinary_visual_entries: Any,
    stabilize_ordinary_visual_entries: Any,
    sort_entries_reading_order: Any,
) -> tuple[list[Entry], Any]:
    """Apply legacy VB observations, then profile-specific visual recovery."""
    entries, geometry = original_detector(
        image, settings, page_sections=page_sections,
    )
    method = str(getattr(settings, "detection_method", "") or "").strip().lower()
    cjk = uses_cjk_role_model(settings)
    no_indent = indent_type_label(settings) == "无明显缩进"
    if cjk:
        if not no_indent and uses_cjk_indent_topology(settings):
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
    return sort_entries_reading_order(
        entries, geometry, page_sections,
    ), geometry
