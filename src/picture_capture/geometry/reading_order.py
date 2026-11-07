from __future__ import annotations

"""SECTION-aware column classification and stable dictionary reading order.

Historical processing_core functions inject current facade-patchable operations
at each call; no persisted Entry/Geometry class is moved to this module.
"""

from collections.abc import Callable
from typing import Any, TypeAlias
from ..models import Entry
from ..persistence.page_sections import (
    PageSection, section_index_for_v, normalize_page_sections,
)

# The concrete Geometry class stays in processing_core for pickle and import
# compatibility. Avoid a runtime import cycle in this calculation-only leaf.
Geometry: TypeAlias = Any


def column_index_for_click(x: int, geometry: Geometry, y: int = 0) -> int:
    """Return the visual column containing a manual click.

    Manual drawing must use each column's full horizontal interval, not the
    nearest column start. If the click is genuinely in a gutter or outside all
    columns, choose the interval boundary nearest to the click.
    """
    x, canonical_y = geometry.source_to_canonical(int(x), int(y))
    if not geometry.column_starts:
        return 0
    intervals: list[tuple[int, int]] = []
    for i, nominal_start in enumerate(geometry.column_starts):
        # Use the same Y-dependent path that drawing, OCR and cropping use.
        # The previous nominal-only classifier could assign a marker to the
        # adjacent column after the visible left edge had curved away.
        start = (
            geometry.x_at(i, int(canonical_y))
            if i < len(geometry.column_paths)
            else int(nominal_start)
        )
        width = geometry.column_widths[i] if i < len(geometry.column_widths) else 1
        right = int(start) + max(1, int(width))
        intervals.append((int(start), right))
        if int(start) <= x < right or (i == len(geometry.column_starts) - 1 and x == right):
            return i

    def distance_to_interval(pair: tuple[int, tuple[int, int]]) -> tuple[int, int]:
        i, (left, right) = pair
        if x < left:
            distance = left - x
        elif x > right:
            distance = x - right
        else:
            distance = 0
        return distance, i

    return min(enumerate(intervals), key=distance_to_interval)[0]



def entry_reading_order_key(
    entry: Entry,
    geometry: Geometry,
    page_sections: list[PageSection] | tuple[PageSection, ...] | None = None,
    *,
    column_fn: Callable[[int, Any, int], int] = column_index_for_click,
    section_fn: Callable[..., int] = section_index_for_v,
) -> tuple[int, int, int, int]:
    """Canonical dictionary order: SECTION first, then column, then position."""
    u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
    column = column_fn(int(entry.x), geometry, int(entry.y))
    section = section_fn(v, page_sections, geometry.top, geometry.bottom)
    return (section, column, v, u)


def sort_entries_reading_order(
    entries: list[Entry],
    geometry: Geometry,
    page_sections: list[PageSection] | tuple[PageSection, ...] | None = None,
    *,
    column_fn: Callable[[int, Any, int], int] = column_index_for_click,
    section_fn: Callable[..., int] = section_index_for_v,
    normalize_fn: Callable[..., Any] = normalize_page_sections,
) -> list[Entry]:
    """Return one stable order shared by UI, OCR, filling and cropping."""
    effective = normalize_fn(page_sections, geometry.top, geometry.bottom)

    def key(entry: Entry) -> tuple[int, int, int, int]:
        u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        column = column_fn(int(entry.x), geometry, int(entry.y))
        section = section_fn(v, effective, geometry.top, geometry.bottom)
        return (section, column, v, u)

    return sorted(entries, key=key)


def sort_entries_column_y(
    entries: list[Entry],
    geometry: Geometry,
    page_sections: list[PageSection] | tuple[PageSection, ...] | None = None,
    *,
    column_fn: Callable[[int, Any, int], int] = column_index_for_click,
    section_fn: Callable[..., int] = section_index_for_v,
    normalize_fn: Callable[..., Any] = normalize_page_sections,
) -> list[Entry]:
    """Stable PDIC repair order: SECTION, visual column, then V; never raw X."""
    effective = normalize_fn(page_sections, geometry.top, geometry.bottom)
    return sorted(
        entries,
        key=lambda entry: (
            section_fn(
                geometry.source_to_canonical(int(entry.x), int(entry.y))[1],
                effective, geometry.top, geometry.bottom,
            ),
            column_fn(int(entry.x), geometry, int(entry.y)),
            geometry.source_to_canonical(int(entry.x), int(entry.y))[1],
        ),
    )

