"""Validated LayoutRows physical geometry reuse for explicit PDIC Y refinement.

Only fields unambiguously represented by the cache may be reused. No semantic
row labels, estimated gutters, or Project setting changes are manufactured.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any


# Only physical scalars consumed by Y refinement/its column geometry.
# Row padding and unrelated Auto Layout switches are not a reason to load GPU.
REFINEMENT_GEOMETRY_FIELDS = frozenset({
    "columns", "start_y", "manual_x", "column_width", "gutter",
    "character_height",
})


def requested_refinement_fields(settings: Any) -> set[str]:
    """Resolve the *small* set of per-page fields useful to Y refinement."""
    if not bool(getattr(settings, "ordinary_auto_layout", False)):
        return set()
    from ..design.layout_policy import AUTO_LAYOUT_FIELDS

    return {
        field for field, switch in AUTO_LAYOUT_FIELDS
        if field in REFINEMENT_GEOMETRY_FIELDS
        and bool(getattr(settings, switch, False))
    }


def cached_refinement_settings(page: Path, source_size: tuple[int, int],
                               settings: Any, page_index: int):
    """Return selected physical fields and evidence, or None for full detection.

    Read available physical measurements straight from this page's JSON.
    Settings fingerprints include unrelated UI switches and are not a valid
    reason to rerun the heavyweight detector for explicit Y refinement.
    Missing physical fields still fall back safely.
    """
    import json
    from ..layout.rows_cache import (
        layout_rows_cache_path, CACHE_FORMAT, CACHE_ALGORITHM_VERSION,
        _same_image_fingerprint, _layout_from_payload,
    )

    requested = requested_refinement_fields(settings)
    if not requested:
        return None
    page = Path(page)
    try:
        payload = json.loads(layout_rows_cache_path(page.parent, page).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if (payload.get("format") != CACHE_FORMAT
            or payload.get("algorithm_version") != CACHE_ALGORITHM_VERSION
            or payload.get("page_index") != int(page_index)
            or not _same_image_fingerprint(payload, page, source_size)):
        return None
    # Reuse the exact saved physical rows; the global settings fingerprint is
    # deliberately irrelevant to this read-only geometry lookup.
    layout = _layout_from_payload(payload)
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

def refinement_cache_miss_reason(page: Path, source_size: tuple[int, int],
                                 settings: Any, page_index: int) -> str:
    """Explain why an existing JSON cannot safely replace fresh detection."""
    import json
    from ..layout.rows_cache import (
        layout_rows_cache_path, CACHE_FORMAT, CACHE_ALGORITHM_VERSION,
        _same_image_fingerprint,
    )
    path = layout_rows_cache_path(Path(page).parent, Path(page))
    if not path.is_file():
        return "layoutrows_missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return "layoutrows_invalid_json"
    if not isinstance(payload, dict):
        return "layoutrows_invalid_payload"
    if (payload.get("format") != CACHE_FORMAT
            or payload.get("algorithm_version") != CACHE_ALGORITHM_VERSION):
        return "layoutrows_wrong_format"
    if payload.get("page_index") != int(page_index):
        return "layoutrows_page_index_mismatch"
    if not _same_image_fingerprint(payload, Path(page), source_size):
        return "layoutrows_image_changed"
    if not requested_refinement_fields(settings):
        return "layoutrows_no_required_fields"
    return "layoutrows_geometry_insufficient"

