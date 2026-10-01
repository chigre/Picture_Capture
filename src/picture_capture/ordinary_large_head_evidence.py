from __future__ import annotations

"""OCR-independent oversized headword evidence for ordinary drawing.

This module intentionally does not infer indentation semantics.  It finds
oversized leading display glyphs from physical ink geometry and emits entry
boundaries that can be OR-fused with Layout-role and symbol-template evidence.
"""

from typing import Any

import numpy as np
from PIL import Image

from .models import AppSettings, Entry
from .ordinary_cjk_large_heads import _candidate_boxes
from .ordinary_visual import _otsu


def detect_ordinary_large_head_entries(
    image: Image.Image,
    understanding: Any,
    settings: AppSettings,
) -> list[Entry]:
    """Detect oversized display heads without depending on indent polarity."""
    if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
        return []

    layout = understanding.layout
    canonical = layout.transform.canonical_image_for_analysis(image.convert("RGB"))
    gray_page = np.asarray(canonical.convert("L"), dtype=np.uint8)
    line_height = max(8.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    found: list[Entry] = []

    for column in list(getattr(layout, "columns", []) or []):
        left = max(0, int(column.left))
        right = min(gray_page.shape[1], int(column.right))
        top = max(0, int(layout.body_top))
        bottom = min(gray_page.shape[0], int(layout.body_bottom))
        if right <= left or bottom <= top:
            continue

        gray = gray_page[top:bottom, left:right]
        if gray.size == 0:
            continue
        ink = gray <= _otsu(gray)
        for x0, y0, x1, y1 in _candidate_boxes(ink, int(round(line_height))):
            height = float(y1 - y0)
            width = float(x1 - x0)
            if height < line_height * 1.38:
                continue
            # Display heads may be centered within a column (common in CJK
            # dictionaries), so do not require the glyph to sit on the normal
            # line-start lane.  Instead reject implausibly wide banners/rules.
            if width > line_height * 3.8:
                continue

            canonical_y = top + int(y0)
            source_x, source_y = layout.transform.canonical_to_source_point(
                int(column.left),
                canonical_y,
                layout.source_size,
            )
            found.append(Entry(
                word="",
                x=int(source_x),
                y=int(source_y),
                confidence=min(0.995, max(0.90, height / max(1.0, line_height * 2.5))),
                ocr_source="ordinary_large_head_evidence",
                issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
                ocr_visual_run_height=height,
                ocr_line_height_reference=line_height,
                ocr_leading_height_ratio=height / max(1.0, line_height),
                ocr_single_cjk=True,
                ocr_oversized_cjk=True,
            ))

    # One oversized connected object can overlap more than one logical row.
    # Collapse detections within one ordinary row-height so a two-row display
    # head creates one entry boundary, not two.
    found.sort(key=lambda item: (item.x, item.y))
    deduped: list[Entry] = []
    tolerance = max(4, round(line_height * 0.80))
    for entry in found:
        if any(abs(entry.x - prior.x) <= tolerance and abs(entry.y - prior.y) <= tolerance for prior in deduped):
            continue
        deduped.append(entry)
    return deduped
