from __future__ import annotations

"""Conservative Y-placement refinement for page-design entry boundaries.

Entry detection and boundary placement are intentionally separate concerns.
The page-design model decides *whether* a visual block is an entry; this module
only moves an already accepted marker within the same inter-line whitespace so
that the horizontal line sits close to the top of the current headword block.

The refiner never creates or removes markers.  It only moves a marker downward
when it can see the next real ink block below it.  The final row is selected in
a narrow white-band window immediately above that block, preferring the cleanest
row and, among equally clean rows, the row closest to the headword.
"""

from typing import Iterable

import numpy as np
from PIL import Image, ImageOps

from .dictionary_page_design import DictionaryPageLayout, _leading_width
from .image_utils import normalize_page_rgb
from .layout_detection import analysis_ink_mask
from .models import AppSettings, Entry
from .profile_semantics import effective_page_settings


def _runs(active: np.ndarray) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(np.asarray(active, dtype=bool)):
        if value and start is None:
            start = index
        elif not value and start is not None:
            result.append((start, index))
            start = None
    if start is not None:
        result.append((start, len(active)))
    return result


def _next_block_top(
    page_ink: np.ndarray,
    *,
    column_left: int,
    column_right: int,
    marker_v: int,
    search_bottom: int,
    reference: float,
) -> int | None:
    """Return the top of the first substantial text/display block below marker."""
    x0 = max(0, int(column_left))
    x1 = min(
        page_ink.shape[1],
        x0 + _leading_width(max(1, int(column_right) - x0), reference),
    )
    y0 = max(0, int(marker_v) + 1)
    y1 = min(page_ink.shape[0], max(y0 + 1, int(search_bottom)))
    if x1 <= x0 or y1 <= y0:
        return None

    strip = page_ink[y0:y1, x0:x1]
    threshold = max(2, round(strip.shape[1] * 0.003))
    active = strip.sum(axis=1) >= threshold

    # Bridge only tiny anti-alias / radical gaps inside one printed line.  The
    # radius is deliberately much smaller than a true inter-line whitespace.
    bridge = max(1, round(reference * 0.06))
    if bridge > 0 and active.size:
        filled = active.copy()
        false_runs = _runs(~active)
        for a, b in false_runs:
            if a > 0 and b < len(active) and b - a <= bridge:
                filled[a:b] = True
        active = filled

    for start, end in _runs(active):
        height = end - start
        # Small superscript prefixes may appear above a headword, but the full
        # entry line or display head is substantially taller than this floor.
        if height < max(2, round(reference * 0.20)):
            continue
        return y0 + int(start)
    return None


def _closest_clean_row(
    page_ink: np.ndarray,
    *,
    column_left: int,
    column_right: int,
    old_v: int,
    head_top: int,
    reference: float,
) -> int | None:
    """Pick a clean horizontal row close to head_top but safely above the ink."""
    min_clearance = max(2, round(reference * 0.075))
    max_retreat = max(min_clearance + 2, round(reference * 0.28))
    upper = int(head_top) - min_clearance
    lower = max(int(old_v), int(head_top) - max_retreat)
    if upper <= lower:
        return None

    x0 = max(0, int(column_left))
    x1 = min(page_ink.shape[1], max(x0 + 1, int(column_right)))
    if x1 <= x0:
        return None

    # Score a three-row band because the rendered boundary has thickness and a
    # single perfectly blank raster row between glyph pixels can be misleading.
    candidates: list[tuple[int, int]] = []
    for y in range(lower, upper + 1):
        ya = max(0, y - 1)
        yb = min(page_ink.shape[0], y + 2)
        score = int(page_ink[ya:yb, x0:x1].sum())
        candidates.append((score, y))
    if not candidates:
        return None

    minimum = min(score for score, _y in candidates)
    # A "clean" band may still contain a few scan specks.  Reject the move if
    # even the best local band has too much ink, because the existing midpoint
    # boundary is safer than crossing printed content.
    blank_limit = max(3, round((x1 - x0) * 3 * 0.012))
    if minimum > blank_limit:
        return None

    near_minimum = minimum + max(1, round((x1 - x0) * 3 * 0.0015))
    # Larger y means visually closer to the current headword top.
    return max(y for score, y in candidates if score <= near_minimum)


def refine_boundaries_toward_head_top(
    image: Image.Image,
    settings: AppSettings,
    layout: DictionaryPageLayout,
    entries: Iterable[Entry],
    *,
    page_index: int = 0,
) -> list[Entry]:
    """Move accepted page-design markers toward the next block top, never upward."""
    result = list(entries)
    if not result or not layout.columns:
        return result

    source = normalize_page_rgb(image)
    effective = effective_page_settings(settings, source.size, page_index)
    canonical = layout.transform.canonical_image_for_analysis(source)
    page_ink = analysis_ink_mask(
        np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8), effective
    )
    reference = max(1.0, float(layout.ordinary_line_height))
    search_span = max(
        round(reference * 1.85),
        round(max(reference, float(layout.ordinary_line_pitch)) * 1.15),
    )

    for entry in result:
        # This placement rule belongs only to the authoritative page-design path.
        if str(getattr(entry, "ocr_source", "") or "") != "ordinary_page_design":
            continue
        u, v = layout.transform.source_to_canonical_point(
            int(entry.x), int(entry.y), layout.source_size,
        )
        column = min(
            layout.columns,
            key=lambda item: abs(int(item.left) - int(u)),
        )
        search_bottom = min(
            int(layout.body_bottom),
            int(v) + search_span,
        )
        head_top = _next_block_top(
            page_ink,
            column_left=int(column.left),
            column_right=int(column.right),
            marker_v=int(v),
            search_bottom=search_bottom,
            reference=reference,
        )
        if head_top is None or head_top <= int(v) + 1:
            continue

        refined_v = _closest_clean_row(
            page_ink,
            column_left=int(column.left),
            column_right=int(column.right),
            old_v=int(v),
            head_top=int(head_top),
            reference=reference,
        )
        if refined_v is None or refined_v <= int(v):
            continue

        # Keep the semantic boundary inside the logical body even though the
        # typography guard-band detector may have looked slightly outside it.
        refined_v = max(
            int(layout.body_top),
            min(int(layout.body_bottom) - 1, int(refined_v)),
        )
        refined_x, refined_y = layout.transform.canonical_to_source_point(
            int(column.left), int(refined_v), layout.source_size,
        )
        entry.x = int(refined_x)
        entry.y = int(refined_y)

    return result
