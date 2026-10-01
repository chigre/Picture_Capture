from __future__ import annotations

"""OCR-independent visual-symbol evidence for ordinary drawing.

Project Profile may contain multiple real-page samples for structural symbols
such as bracket openers (【) or standalone entry markers (○/◆).  Ordinary
mode must be able to use those samples directly, without OCR.  This module is
intentionally independent from parser/OCR fusion: it only asks whether a
physical Layout row begins with one of the configured visual templates.
"""

from typing import Any

import numpy as np
from PIL import Image

from .models import AppSettings, Entry
from .ordinary_visual import _components, _otsu
from .visual_marker_templates import (
    match_visual_marker_template,
    visual_marker_samples_from_settings,
)


def _enabled(settings: AppSettings) -> bool:
    mode = str(getattr(settings, "profile_symbol_template_mode", "combined") or "combined")
    return bool(
        mode != "off"
        and bool(getattr(settings, "profile_symbol_visual_rescue_enabled", True))
        and visual_marker_samples_from_settings(settings)
    )


def _candidate_components(mask: np.ndarray, line_height: float) -> list[tuple[int, int, int, int, int]]:
    minimum_area = max(2, round(float(line_height) * float(line_height) * 0.006))
    maximum_side = max(12, round(float(line_height) * 2.4))
    result: list[tuple[int, int, int, int, int]] = []
    for x0, y0, x1, y1, area in _components(mask):
        width = int(x1) - int(x0)
        height = int(y1) - int(y0)
        if int(area) < minimum_area:
            continue
        if width < 1 or height < 2:
            continue
        if width > maximum_side or height > maximum_side:
            continue
        result.append((int(x0), int(y0), int(x1), int(y1), int(area)))
    return result


def detect_ordinary_symbol_entries(
    image: Image.Image,
    understanding: Any,
    settings: AppSettings,
) -> list[Entry]:
    """Return entry boundaries whose row start matches a sampled symbol.

    Matching is deliberately restricted to a narrow neighborhood around each
    Layout row start.  A look-alike bracket in the middle of a definition can
    therefore never become an ordinary-mode entry merely because it resembles
    a Profile sample.
    """
    if not _enabled(settings):
        return []

    samples = visual_marker_samples_from_settings(settings)
    if not samples:
        return []
    threshold = float(getattr(settings, "profile_symbol_template_threshold", 0.68) or 0.68)
    threshold = max(0.30, min(0.98, threshold))

    layout = understanding.layout
    canonical = layout.transform.canonical_image_for_analysis(image.convert("RGB"))
    gray_page = np.asarray(canonical.convert("L"), dtype=np.uint8)
    line_height = max(4.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    found: list[Entry] = []

    for column in list(getattr(layout, "columns", []) or []):
        column_left = max(0, int(column.left))
        column_right = min(gray_page.shape[1], int(column.right))
        for line in list(getattr(column, "lines", []) or []):
            canonical_y0 = max(0, int(layout.body_top) + int(line.y0))
            canonical_y1 = min(gray_page.shape[0], int(layout.body_top) + int(line.y1))
            if canonical_y1 <= canonical_y0:
                continue

            first_x = max(0.0, float(getattr(line, "first_x", 0.0) or 0.0))
            start_x = max(column_left, int(round(column_left + first_x - line_height * 0.28)))
            end_x = min(
                column_right,
                max(start_x + 4, int(round(column_left + first_x + line_height * 2.10))),
            )
            if end_x <= start_x:
                continue

            # Give thin/tall punctuation a little vertical breathing room; the
            # template normalizer will trim the actual component afterwards.
            pad_y = max(1, round(line_height * 0.18))
            y0 = max(0, canonical_y0 - pad_y)
            y1 = min(gray_page.shape[0], canonical_y1 + pad_y)
            region = gray_page[y0:y1, start_x:end_x]
            if region.size == 0:
                continue
            ink = region <= _otsu(region)

            best: dict[str, Any] | None = None
            best_box: tuple[int, int, int, int] | None = None
            for x0, yy0, x1, yy1, _area in _candidate_components(ink, line_height):
                # Only the first ~1.2 character widths from the physical line
                # start are structural-marker territory.
                if x0 > line_height * 1.25:
                    continue
                component = ink[yy0:yy1, x0:x1]
                if component.size == 0:
                    continue
                try:
                    match = match_visual_marker_template(
                        component,
                        samples,
                        roles={"bracket_open", "entry_marker"},
                    )
                except (ValueError, TypeError):
                    continue
                if match is None:
                    continue
                score = float(match.get("score", 0.0) or 0.0)
                if best is None or score > float(best.get("score", 0.0) or 0.0):
                    best = match
                    best_box = (x0, yy0, x1, yy1)

            if best is None or best_box is None:
                continue
            score = float(best.get("score", 0.0) or 0.0)
            if score < threshold:
                continue

            source_x, source_y = layout.transform.canonical_to_source_point(
                int(column.left),
                canonical_y0,
                layout.source_size,
            )
            found.append(Entry(
                word="",
                x=int(source_x),
                y=int(source_y),
                confidence=score,
                ocr_source="ordinary_symbol_evidence",
                issue_type=(
                    "ORDINARY_VISUAL_BRACKET_SAMPLE"
                    if str(best.get("role") or "") == "bracket_open"
                    else "ORDINARY_VISUAL_ENTRY_MARKER_SAMPLE"
                ),
            ))

    return found
