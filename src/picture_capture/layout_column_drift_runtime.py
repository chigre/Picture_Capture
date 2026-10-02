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

Important ownership rule: this module owns *indent remeasurement only*.  It must
never replace the universal large-head detector.  Large-head detection has its
own stricter row-front/oversized authorization runtime; replacing that callable
here used to silently disable those guards in the real GUI/spawn import order.
The helper ``_analysis_left_for_column`` remains public so the strict large-head
detector can reuse exactly the same left safety band without changing ownership.
"""

from typing import Any, Callable

import numpy as np
from PIL import Image, ImageOps


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
    columns = list(getattr(layout, "columns", []) or [])

    for position, column in enumerate(columns):
        column_index = int(getattr(column, "index", position) or position)
        semantic_left = int(getattr(column, "left", 0) or 0)
        semantic_right = int(getattr(column, "right", semantic_left + 1) or semantic_left + 1)
        column_width = max(1, semantic_right - semantic_left)
        analysis_left = _analysis_left_for_column(columns, position, reference)
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
    source, canonical, _transform, effective = base._analysis_page(
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
        try:
            source.close()
        except Exception:
            pass

    if counts:
        detail = ",".join(
            f"C{index + 1}:{count}" for index, count in sorted(counts.items())
        )
        layout.reason += f"; unclipped_first_x={detail}"
    return layout, page_settings, applied


def install_layout_column_drift_runtime() -> None:
    """Install unclipped indent measurement without touching evidence detectors."""
    from . import dictionary_page_layout_policy as policy

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
    policy._column_drift_runtime_installed = True


__all__ = [
    "_analysis_left_for_column",
    "_left_safety",
    "install_layout_column_drift_runtime",
    "remeasure_layout_indents_from_ink",
]
