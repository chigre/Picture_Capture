"""Stable illustration labels and explicit nearest-above PDIC association.

PPP polygons stay in source-pixel coordinates.  Numbering is derived from the
same canonical SECTION → column → Y → X reading order as PDIC, rather than
from list insertion or auto-detection sequence.  Labels retain a trailing
|AUTO_nn provenance token so detection can still replace only auto figures.
"""
from __future__ import annotations

import re
from typing import Sequence

from .models import Entry, PolygonRegion
from .page_sections import PageSection, normalize_page_sections, section_index_for_v

LABEL_PATTERN = re.compile(r"^P_(\d+)\|([^|]+)\|(xxx|\d{3})(?:\|.*)?$", re.I)
AUTO_PATTERN = re.compile(r"(?:^|\|)(AUTO_\d+)(?=\||$)", re.I)
ASSOCIATION_UNKNOWN = "xxx"


def label_text(value: str) -> str:
    """Display only the three contractual fields, never AUTO metadata."""
    text = str(value or "").strip()
    matched = LABEL_PATTERN.match(text)
    if matched:
        return f"P_{int(matched.group(1)):02d}|{matched.group(2)}|{matched.group(3)}"
    return text


def _origin_token(value: str) -> str:
    match = AUTO_PATTERN.search(str(value or ""))
    return f"|{match.group(1)}" if match else ""


def _existing_link(value: str) -> str:
    match = LABEL_PATTERN.match(str(value or "").strip())
    return match.group(3) if match else ASSOCIATION_UNKNOWN


def _region_top_coordinates(region: PolygonRegion, geometry) -> list[tuple[int, int]]:
    return [
        geometry.source_to_canonical(int(x), int(y))
        for x, y in region.points
    ]


def _upper_anchor_samples(points: list[tuple[int, int]]) -> tuple[int, int, int]:
    """Upper envelope at left/mid/right; prioritize left, then mid, then right.

    The nearest top polygon vertices supply the boundary Y. For polygons whose
    top edge is sloped the midpoint is linearly interpolated, not the lowest
    vertex (which may be on the figure's bottom border).
    """
    left = min(u for u, _ in points)
    right = max(u for u, _ in points)
    top_points = sorted(points, key=lambda p: (p[0], p[1]))
    left_v = min(v for u, v in points if u == left)
    right_v = min(v for u, v in points if u == right)
    if right == left:
        return left_v, left_v, right_v
    mid = (left + right) / 2.0
    candidates: list[float] = []
    for u0, v0 in points:
        for u1, v1 in points:
            if u0 == u1 or not min(u0, u1) <= mid <= max(u0, u1):
                continue
            v_mid = v0 + (v1 - v0) * (mid - u0) / (u1 - u0)
            candidates.append(v_mid)
    middle_v = round(min(candidates)) if candidates else min(left_v, right_v)
    return left_v, middle_v, right_v


def _region_key(region: PolygonRegion, geometry, sections) -> tuple[int, int, int, int]:
    from .processing_core import column_index_for_click

    points = _region_top_coordinates(region, geometry)
    if not points:
        # Malformed historical PPP rows must not crash the entire GUI.
        # Keep them last and unassociated; normal editing can repair them.
        return (len(sections), len(geometry.column_starts), 10**12, 10**12)
    left = min(points, key=lambda p: (p[0], p[1]))
    left_source = min(region.points, key=lambda p: geometry.source_to_canonical(*p))
    column = column_index_for_click(int(left_source[0]), geometry, int(left_source[1]))
    top_v = min(v for _, v in points)
    section = section_index_for_v(top_v, sections, geometry.top, geometry.bottom)
    return (section, column, top_v, left[0])


def _nearest_above_entry(
    region: PolygonRegion, entries: Sequence[Entry], geometry, sections,
) -> int | None:
    from .processing_core import column_index_for_click, sort_entries_reading_order

    if not entries:
        return None
    points = _region_top_coordinates(region, geometry)
    if not points:
        return None
    first = min(region.points, key=lambda p: geometry.source_to_canonical(*p))
    column = column_index_for_click(int(first[0]), geometry, int(first[1]))
    section = section_index_for_v(min(v for _, v in points), sections, geometry.top, geometry.bottom)
    sorted_entries = sort_entries_reading_order(list(entries), geometry, sections)
    candidates: list[tuple[int, int, int, int]] = []
    for ordinal, entry in enumerate(sorted_entries, 1):
        u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        if column_index_for_click(entry.x, geometry, entry.y) != column:
            continue
        entry_section = section_index_for_v(v, sections, geometry.top, geometry.bottom)
        if entry_section != section:
            continue
        candidates.append((ordinal, u, v, entry_section))
    # Top-edge anchor priority is intentional: left-upper Y first, then
    # midpoint, then right-upper. At each anchor the closest PDIC above wins.
    for anchor_v in _upper_anchor_samples(points):
        above = [item for item in candidates if item[2] < anchor_v]
        if above:
            ordinal, _u, _v, _section = min(
                above, key=lambda item: (anchor_v - item[2], item[0]),
            )
            return ordinal
    return None


def illustration_labels(
    regions: Sequence[PolygonRegion], page_stem: str, geometry,
    page_sections: Sequence[PageSection] | None = None,
    *, entries: Sequence[Entry] = (), associate: bool = False,
) -> list[str]:
    """Return the target labels indexed by original polygon identity/order.

    No mutation or disk I/O. Callers write a cloned candidate PPP atomically,
    then publish new labels to the live objects only after successful write.
    """
    sections = normalize_page_sections(page_sections, geometry.top, geometry.bottom)
    keyed = sorted(
        enumerate(regions),
        key=lambda item: (*_region_key(item[1], geometry, sections), item[0]),
    )
    result = [""] * len(regions)
    for ordinal, (index, region) in enumerate(keyed, 1):
        if associate:
            entry_index = _nearest_above_entry(region, entries, geometry, sections)
            link = f"{entry_index:03d}" if entry_index is not None else ASSOCIATION_UNKNOWN
        else:
            link = _existing_link(region.label)
        result[index] = (
            f"P_{ordinal:02d}|{page_stem}|{link}{_origin_token(region.label)}"
        )
    return result


def user_edited_link(original: str, typed: str) -> str:
    """Allow edits to the association code only, never the generated id/page.

    The canonical number and page stem always come from the polygon order and
    current page, not from stale entry text. Keep AUTO provenance on disk.
    """
    text = label_text(typed)
    match = LABEL_PATTERN.match(text)
    if not match:
        raise ValueError("插图标签格式应为 P_01|页面名称|xxx 或 P_01|页面名称|003")
    old = LABEL_PATTERN.match(original)
    if old is None:
        raise ValueError("插图编号未初始化，请重新打开本页")
    return f"P_{int(old.group(1)):02d}|{old.group(2)}|{match.group(3)}{_origin_token(original)}"


def write_ordered_auto_ppp(
    write_path, manual: Sequence[PolygonRegion], accepted: Sequence[PolygonRegion],
    image_path, settings, profile_page_index: int,
) -> bool:
    """Batch detector commits correctly numbered manual and AUTO regions.

    The detector has already rejected overlaps. Reuse per-page Profile and
    SECTION geometry, preserving AUTO tokens on disk for future redetection.
    """
    from pathlib import Path
    from PIL import Image, ImageOps
    from .formats import write_ppp
    from .processing_core import derive_nominal_geometry
    from .profile_semantics import effective_page_settings
    from .page_sections import read_page_sections

    source = Path(image_path)
    with Image.open(source) as opened:
        size = ImageOps.exif_transpose(opened).size
    effective = effective_page_settings(settings, size, profile_page_index)
    geometry = derive_nominal_geometry(size[0], size[1], effective)
    regions = [
        PolygonRegion(region.label, list(region.points))
        for region in list(manual) + list(accepted)
    ]
    for index in range(len(manual), len(regions)):
        regions[index].label = (
            f"{source.stem}|AUTO_{index - len(manual) + 1:02d}|1|{source.stem}|"
        )
    names = illustration_labels(regions, source.stem, geometry, read_page_sections(source))
    for region, label in zip(regions, names):
        region.label = label
    return write_ppp(write_path, regions, source.stem)


__all__ = [
    "illustration_labels", "label_text", "user_edited_link",
    "write_ordered_auto_ppp",
]
