from __future__ import annotations

"""Preserve physical indents when a scanned column drifts across Y.

Project/Profile geometry owns the *semantic* column-left boundary.  Real scans,
however, can lean or curve slightly so lower rows may extend left of that fixed
boundary.  The historical Page Layout strip started exactly at ``column.left``;
once a row crossed that edge its leading ink was clipped and ``first_x`` became
0.  A later slant correction cannot recover pixels that were never observed.

This runtime keeps the configured column geometry unchanged but re-measures each
recovered row in a wider analysis window that extends to the left.  The measured
``first_x`` remains expressed relative to the original semantic ``column.left``
and is therefore allowed to be negative before common-drift normalization.

The same left safety band is used by universal oversized-head evidence so a
large CJK display head is not clipped before duplicate-entry suppression.
"""

from typing import Any, Callable

import numpy as np
from PIL import Image, ImageOps


def _left_safety(reference: float, column_width: int) -> int:
    """Return a conservative analysis-only margin left of the semantic column."""
    ref = max(6.0, float(reference))
    width = max(1, int(column_width))
    return max(12, min(round(ref * 1.75), round(width * 0.14), 96))


def remeasure_layout_indents_from_ink(
    layout: Any,
    page_ink: np.ndarray,
) -> dict[int, int]:
    """Re-measure recovered rows without clipping ink left of ``column.left``.

    Returns a per-column count of rows whose first-X measurement was updated.
    Geometry is never moved.  ``line.first_x`` remains in local column
    coordinates, so values may be negative when the physical scan drifts left of
    the project/Profile origin.
    """
    from . import dictionary_page_design as base
    from .layout_physical_indent import _credible_first_ink_x

    if page_ink.ndim != 2 or page_ink.size == 0:
        return {}

    reference = max(
        6.0,
        float(getattr(layout, "ordinary_line_height", 1.0) or 1.0),
    )
    body_top = int(getattr(layout, "body_top", 0) or 0)
    height, width = page_ink.shape
    updated: dict[int, int] = {}

    for column in list(getattr(layout, "columns", []) or []):
        column_index = int(getattr(column, "index", 0) or 0)
        semantic_left = int(getattr(column, "left", 0) or 0)
        semantic_right = int(getattr(column, "right", semantic_left + 1) or semantic_left + 1)
        column_width = max(1, semantic_right - semantic_left)
        safety = _left_safety(reference, column_width)
        analysis_left = max(0, semantic_left - safety)
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
            # Runtime installers already replace these with the physical-indent
            # implementations. Rebuild modes and roles from the unclipped values.
            column.indent_modes = base._indent_modes(column.lines, reference)
            base._assign_indent_semantics(
                column,
                str(getattr(layout, "indent_type", "body") or "body"),
                reference,
            )
            updated[column_index] = count

    return updated


def _remeasure_policy_layout(
    original: Callable[..., Any],
    image: Image.Image,
    settings: Any,
    *,
    page_index: int = 0,
) -> tuple[Any, Any, dict[str, int]]:
    from . import dictionary_page_design as base
    from .layout_detection import analysis_ink_mask

    layout, page_settings, applied = original(
        image,
        settings,
        page_index=page_index,
    )
    _source, canonical, _transform, effective = base._analysis_page(
        image,
        page_settings,
        int(page_index),
    )
    try:
        page_ink = analysis_ink_mask(
            np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8),
            effective,
        )
        counts = remeasure_layout_indents_from_ink(layout, page_ink)
    finally:
        try:
            canonical.close()
        except Exception:
            pass

    if counts:
        detail = ",".join(
            f"C{index + 1}:{count}" for index, count in sorted(counts.items())
        )
        layout.reason += f"; unclipped_first_x={detail}"
    return layout, page_settings, applied


def _detect_large_heads_with_left_safety(
    image: Image.Image,
    understanding: Any,
    settings: Any,
) -> list[Any]:
    """Universal large-head detector with the same unclipped leading window."""
    from .models import Entry
    from .ordinary_large_head_evidence import (
        _candidate_boxes,
        _otsu,
        _uses_cjk_large_heads,
    )

    if not _uses_cjk_large_heads(settings):
        return []

    layout = understanding.layout
    canonical = layout.transform.canonical_image_for_analysis(image.convert("RGB"))
    try:
        gray_page = np.asarray(canonical.convert("L"), dtype=np.uint8)
        reference = max(
            8.0,
            float(getattr(layout, "ordinary_line_height", 1.0) or 1.0),
        )
        found: list[Any] = []
        top = max(0, int(getattr(layout, "body_top", 0) or 0))
        bottom = min(
            gray_page.shape[0],
            int(getattr(layout, "body_bottom", gray_page.shape[0]) or gray_page.shape[0]),
        )

        for column in list(getattr(layout, "columns", []) or []):
            semantic_left = max(0, int(getattr(column, "left", 0) or 0))
            semantic_right = min(
                gray_page.shape[1],
                int(getattr(column, "right", semantic_left + 1) or semantic_left + 1),
            )
            safety = _left_safety(reference, max(1, semantic_right - semantic_left))
            analysis_left = max(0, semantic_left - safety)
            if semantic_right <= analysis_left or bottom <= top:
                continue

            gray = gray_page[top:bottom, analysis_left:semantic_right]
            if gray.size == 0:
                continue
            ink = gray <= _otsu(gray)
            for _x0, y0, _x1, y1 in _candidate_boxes(ink, reference):
                height = float(y1 - y0)
                canonical_y = top + int(y0)
                source_x, source_y = layout.transform.canonical_to_source_point(
                    semantic_left,
                    canonical_y,
                    layout.source_size,
                )
                found.append(Entry(
                    word="",
                    x=int(source_x),
                    y=int(source_y),
                    confidence=min(0.995, max(0.90, height / max(1.0, reference * 2.5))),
                    ocr_source="ordinary_large_head_evidence",
                    issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
                    ocr_visual_run_height=height,
                    ocr_line_height_reference=reference,
                    ocr_leading_height_ratio=height / max(1.0, reference),
                    ocr_single_cjk=True,
                    ocr_oversized_cjk=True,
                ))
    finally:
        try:
            canonical.close()
        except Exception:
            pass

    found.sort(key=lambda item: (item.x, item.y))
    deduped: list[Any] = []
    tolerance = max(4, round(reference * 0.80))
    for entry in found:
        if any(
            abs(entry.x - prior.x) <= tolerance
            and abs(entry.y - prior.y) <= tolerance
            for prior in deduped
        ):
            continue
        deduped.append(entry)
    return deduped


def install_layout_column_drift_runtime() -> None:
    """Install unclipped indent + large-head measurement before Layout Core use."""
    from . import dictionary_page_layout_policy as policy
    from . import ordinary_large_head_evidence as large_head

    if bool(getattr(policy, "_column_drift_runtime_installed", False)):
        return

    original = policy.infer_dictionary_page_layout

    def wrapped(
        image: Image.Image,
        settings: Any,
        *,
        page_index: int = 0,
    ) -> tuple[Any, Any, dict[str, int]]:
        return _remeasure_policy_layout(
            original,
            image,
            settings,
            page_index=page_index,
        )

    policy.infer_dictionary_page_layout = wrapped
    large_head.detect_ordinary_large_head_entries = _detect_large_heads_with_left_safety
    policy._column_drift_runtime_installed = True


__all__ = [
    "_left_safety",
    "_detect_large_heads_with_left_safety",
    "install_layout_column_drift_runtime",
    "remeasure_layout_indents_from_ink",
]
