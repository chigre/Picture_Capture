"""Validated LayoutRows physical geometry reuse for explicit PDIC Y refinement.

Only fields unambiguously represented by the cache may be reused. No semantic
row labels, estimated gutters, or Project setting changes are manufactured.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any


def cached_refinement_settings(page: Path, source_size: tuple[int, int],
                               settings: Any, page_index: int):
    """Return selected physical fields and evidence, or None for full detection.

    Cache validation checks scan identity, settings fingerprint, page index and
    reliable row content. If any requested field cannot be reconstructed, fall
    back to the existing authoritative estimator for ALL fields.
    """
    from .dictionary_page_layout_policy import AUTO_LAYOUT_FIELDS
    from .layout_rows_cache import load_layout_rows_cache

    requested = {
        field for field, switch in AUTO_LAYOUT_FIELDS
        if bool(getattr(settings, switch, False))
    }
    if not requested or not requested <= {
        "columns", "start_y", "manual_x", "column_width",
        "gutter", "character_height",
    }:
        return None
    page = Path(page)
    layout = load_layout_rows_cache(
        page.parent, page, int(page_index), settings, source_size=source_size,
    )
    if layout is None:
        return None
    columns = sorted(layout.columns, key=lambda column: int(column.index))
    if not columns or [int(column.index) for column in columns] != list(range(len(columns))):
        return None
    # The JSON records canonical column rectangles. Reuse only exact identity
    # pixel space: rotated/transformed measurements are not direct source X/Y.
    if (str(getattr(layout.transform, "kind", "")) != "identity"
            or tuple(layout.canonical_size) != tuple(source_size)):
        return None
    starts = [int(column.left) for column in columns]
    widths = [int(column.right) - int(column.left) for column in columns]
    if any(width <= 0 for width in widths):
        return None
    available = {
        "columns": len(columns),
        "start_y": int(layout.body_top),
        "manual_x": starts[0],
        "character_height": round(float(layout.ordinary_line_height)),
    }
    if len(set(widths)) == 1:
        available["column_width"] = widths[0]
    if len(columns) > 1 and len(set(widths)) == 1:
        gaps = [
            starts[i + 1] - int(columns[i].right)
            for i in range(len(columns) - 1)
        ]
        if gaps and len(set(gaps)) == 1 and gaps[0] >= 0:
            available["gutter"] = gaps[0]
    if not requested <= available.keys():
        return None
    result = replace(settings)
    applied = {}
    for field in requested:
        value = int(available[field])
        setattr(result, field, value)
        applied[field] = value
    result.manual_columns = False
    return result, applied
