"""Strict source-coordinate ownership of focused review and main canvas rows.

These are read-only association helpers; they never normalize or mutate an
Entry, queue an edit, save PDIC, import Tk or infer nearest-row identity.
Unverifiable/duplicate owners are excluded instead of choosing by list order.
"""
from __future__ import annotations

from typing import Any, Iterable

from .focused_crop_source_fingerprint import _source_page_index
from .focused_pdic_updates import _exact_page_coordinate


def unique_focused_visible_targets(
    rows: Iterable[dict[str, Any]],
) -> dict[tuple[int, int, int], dict[str, Any]]:
    """Only genuine and unique page/XY points can own a Tk save callback."""
    by_point: dict[tuple[int, int, int], dict[str, Any]] = {}
    duplicates: set[tuple[int, int, int]] = set()
    for row in rows:
        try:
            point = (
                _source_page_index(row["page_index"]),
                _exact_page_coordinate(row["x"]),
                _exact_page_coordinate(row["y"]),
            )
        except (KeyError, TypeError, ValueError, RuntimeError, OverflowError):
            continue
        if point in by_point:
            duplicates.add(point)
        else:
            by_point[point] = row
    for point in duplicates:
        by_point.pop(point, None)
    return by_point


def unique_canvas_source_entries(entries: Iterable[Any]) -> dict[tuple[int, int], Any]:
    """A saved marker cannot be reconciled into ambiguous/aliased Entry XY."""
    by_point: dict[tuple[int, int], Any] = {}
    duplicates: set[tuple[int, int]] = set()
    for entry in entries:
        try:
            point = (
                _exact_page_coordinate(entry.x),
                _exact_page_coordinate(entry.y),
            )
        except (AttributeError, TypeError, ValueError, RuntimeError, OverflowError):
            continue
        if point in by_point:
            duplicates.add(point)
        else:
            by_point[point] = entry
    for point in duplicates:
        by_point.pop(point, None)
    return by_point
