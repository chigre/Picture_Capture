from __future__ import annotations

"""Preserve physical indents when a scanned column drifts across Y.

Project/Profile geometry owns the *semantic* column-left boundary.  Real scans,
however, can lean or curve slightly so lower rows may extend left of that fixed
boundary.  The historical Page Layout strip started exactly at ``column.left``;
once a row crossed that edge its leading ink was clipped and ``first_x`` became
0.  A later slant correction cannot recover pixels that were never observed.

This helper keeps the configured column geometry unchanged but re-measures each
recovered row in a wider analysis window that extends to the left.  The measured
``first_x`` remains expressed relative to the original semantic ``column.left``
and is therefore allowed to be negative before common-drift normalization.

Important ownership rule: this module owns *indent remeasurement only*.  It must
never replace the universal large-head detector.  Large-head detection has its
own stricter row-front/oversized authorization runtime; replacing that callable
here used to silently disable those guards in the real GUI/spawn import order.
The helper ``_analysis_left_for_column`` remains public so the strict large-head
detector can reuse exactly the same left safety band without changing ownership.
"""

from typing import Any

import numpy as np
from PIL import Image, ImageOps

from . import dictionary_page_design as base


def _left_safety(reference: float, column_width: int) -> int:
    """Return a conservative analysis-only margin left of the semantic column."""
    ref = max(6.0, float(reference))
    width = max(1, int(column_width))
    return max(12, min(round(ref * 1.75), round(width * 0.14), 96))


def _analysis_left_for_column(
    columns: list[Any],
    index: int,
    reference: float,
) -> int:
    """Extend left into margin/gutter but never into the previous text column."""
    column = columns[index]
    semantic_left = int(getattr(column, "left", 0) or 0)
    semantic_right = int(getattr(column, "right", semantic_left + 1) or semantic_left + 1)
    safety = _left_safety(reference, max(1, semantic_right - semantic_left))
    candidate = max(0, semantic_left - safety)
    if index <= 0:
        return candidate
    previous_right = int(getattr(columns[index - 1], "right", 0) or 0)
    return max(candidate, previous_right + 1)




def _gutter_divider_right_edge(
    ink: np.ndarray,
    *,
    body_top: int,
    body_bottom: int,
    corridor_left: int,
    corridor_right: int,
    reference: float,
) -> int | None:
    """Find a *slanted* printed divider in the inter-column gutter.

    Whole-page X-column persistence misses diagonal rules (e.g., a rule that
    drifts 7px from page top to bottom). Here we locate an almost-continuous
    single-pixel stroke in successive vertical tiles and require its X position
    to form one coherent track. Only a *gutter*, never legitimate word ink, is
    eligible. Return the right edge of that stroke plus a tiny safety margin.
    """
    if ink.ndim != 2 or ink.size == 0:
        return None
    height, width = ink.shape
    left = max(0, min(width, int(corridor_left)))
    right = max(left, min(width, int(corridor_right)))
    top = max(0, min(height, int(body_top)))
    bottom = max(top, min(height, int(body_bottom)))
    ref = max(6.0, float(reference))
    if right - left < max(8, round(ref * .45)) or bottom - top < ref * 8:
        return None

    tile = max(44, round(ref * 3.0))
    peaks: list[int] = []
    eligible = 0
    for y in range(top, bottom, tile):
        band = ink[y:min(bottom, y + tile), left:right]
        if band.shape[0] < tile * .42:
            continue
        eligible += 1
        density = np.asarray(band, dtype=np.uint8).mean(axis=0)
        peak = int(np.argmax(density))
        if float(density[peak]) >= .50:
            peaks.append(left + peak)
    if eligible < 4 or len(peaks) < max(4, round(eligible * .55)):
        return None
    values = np.asarray(peaks, dtype=float)
    center = float(np.median(values))
    inliers = values[np.abs(values - center) <= max(4.0, ref * .18)]
    if len(inliers) < max(4, round(eligible * .50)):
        return None
    return int(max(inliers)) + max(2, round(ref * .10))

def remeasure_layout_indents_from_ink(
    layout: Any,
    page_ink: np.ndarray,
    *,
    ops: base.LayoutPrimitiveOps | None = None,
    divider_positions: dict[int, int] | None = None,
) -> dict[int, int]:
    """Re-measure recovered rows without clipping ink left of ``column.left``.

    Returns a per-column count of rows whose first-X measurement was updated.
    Geometry is never moved.  ``line.first_x`` remains in local column
    coordinates, so values may be negative when the physical scan drifts left of
    the project/Profile origin.
    """
    from .layout_physical_indent import _credible_first_ink_x

    ops = base.current_layout_ops() if ops is None else ops

    if page_ink.ndim != 2 or page_ink.size == 0:
        return {}

    reference = max(
        6.0,
        float(getattr(layout, "ordinary_line_height", 1.0) or 1.0),
    )
    body_top = int(getattr(layout, "body_top", 0) or 0)
    height, width = page_ink.shape
    updated: dict[int, int] = {}
    columns = list(getattr(layout, "columns", []) or [])

    for position, column in enumerate(columns):
        column_index = int(getattr(column, "index", position) or position)
        semantic_left = int(getattr(column, "left", 0) or 0)
        semantic_right = int(getattr(column, "right", semantic_left + 1) or semantic_left + 1)
        column_width = max(1, semantic_right - semantic_left)
        analysis_left = _analysis_left_for_column(columns, position, reference)
        # The widening needed for tilted text also reaches back into the
        # *printed divider* of a ruled dictionary. An ink stroke stretching
        # most of the page may otherwise become "first_x" on every row,
        # collapsing real entry/body indents to the same negative X lane.
        if position > 0 and analysis_left < semantic_left:
            previous_right = int(columns[position - 1].right)
            rule_right = _gutter_divider_right_edge(
                page_ink,
                body_top=body_top,
                body_bottom=int(getattr(layout, "body_bottom", height)),
                corridor_left=max(analysis_left, previous_right + 1),
                corridor_right=semantic_left - max(2, round(reference * .12)),
                reference=reference,
            )
            if rule_right is not None and rule_right > analysis_left:
                analysis_left = min(semantic_left, rule_right)
                if divider_positions is not None:
                    divider_positions[column_index] = analysis_left
        analysis_right = min(
            width,
            semantic_left + base._leading_width(column_width, reference),
        )
        if analysis_right <= analysis_left:
            continue

        count = 0
        for line in list(getattr(column, "lines", []) or []):
            try:
                y0 = max(0, min(height, body_top + int(getattr(line, "y0"))))
                y1 = max(y0 + 1, min(height, body_top + int(getattr(line, "y1"))))
            except (AttributeError, TypeError, ValueError):
                continue
            row = page_ink[y0:y1, analysis_left:analysis_right]
            local = _credible_first_ink_x(row, reference)
            if local is None:
                continue
            absolute_x = analysis_left + int(local)
            line.first_x = int(absolute_x - semantic_left)
            count += 1

        if count:
            # Composition already provides the physical-indent implementations.
            # Rebuild modes and roles from the unclipped values.
            column.indent_modes = ops.indent_modes(column.lines, reference)
            ops.assign_indent_semantics(
                column,
                str(getattr(layout, "indent_type", "body") or "body"),
                reference,
            )
            updated[column_index] = count

    return updated


def finalize_layout_column_drift(
    image: Image.Image,
    settings: Any,
    layout: Any,
    *,
    page_index: int = 0,
    page_ink: np.ndarray | None = None,
    ops: base.LayoutPrimitiveOps | None = None,
) -> Any:
    """Apply post-policy indent remeasurement, reusing an existing page mask when supplied."""
    explicit_ops = ops is not None
    ops = base.current_layout_ops() if ops is None else ops
    divider_positions: dict[int, int] = {}
    if page_ink is None:
        from .layout_detection import analysis_ink_mask

        source, canonical, _transform, effective = base._analysis_page(
            image,
            settings,
            int(page_index),
        )
        try:
            page_ink = analysis_ink_mask(
                np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8),
                effective,
            )
            counts = remeasure_layout_indents_from_ink(layout, page_ink, divider_positions=divider_positions, **({"ops": ops} if explicit_ops else {}))
        finally:
            try:
                canonical.close()
            except Exception:
                pass
            try:
                source.close()
            except Exception:
                pass
    else:
        counts = remeasure_layout_indents_from_ink(layout, page_ink, divider_positions=divider_positions, **({"ops": ops} if explicit_ops else {}))

    if counts:
        detail = ",".join(
            f"C{index + 1}:{count}" for index, count in sorted(counts.items())
        )
        layout.reason += f"; unclipped_first_x={detail}"
    if divider_positions:
        detail = ",".join(
            f"C{index + 1}:X{right}" for index, right in sorted(divider_positions.items())
        )
        layout.reason += f"; slanted_gutter_rule_guard={detail}"
    return layout


__all__ = [
    "_analysis_left_for_column",
    "_left_safety",
    "finalize_layout_column_drift",
    "remeasure_layout_indents_from_ink",
]
