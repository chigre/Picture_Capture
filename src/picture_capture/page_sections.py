from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from .project_storage import page_sections_path_for_image


PAGE_SECTIONS_FORMAT = "picture-capture-page-sections-v1"
PAGE_SECTIONS_COORDINATE_SPACE = "canonical_full_resolution_pixels"


@dataclass(frozen=True, slots=True)
class PageSection:
    """One page-local reading region expressed on the canonical V axis."""

    top_v: int
    bottom_v: int


@dataclass(frozen=True, slots=True)
class ReadingLane:
    """One continuous SECTION × column lane in dictionary reading order."""

    section_index: int
    column_index: int
    top_v: int
    bottom_v: int


def normalize_page_sections(
    sections: list[PageSection] | tuple[PageSection, ...] | None,
    top_v: int,
    bottom_v: int,
) -> list[PageSection]:
    """Clamp/sort explicit sections; missing sections mean one ordinary page region."""
    top = int(top_v)
    bottom = max(top + 1, int(bottom_v))
    if not sections:
        return [PageSection(top, bottom)]

    normalized: list[PageSection] = []
    for section in sorted(sections, key=lambda item: (int(item.top_v), int(item.bottom_v))):
        start = max(top, min(bottom, int(section.top_v)))
        stop = max(top, min(bottom, int(section.bottom_v)))
        if stop <= start:
            continue
        if normalized and start < normalized[-1].bottom_v:
            start = normalized[-1].bottom_v
        if stop <= start:
            continue
        normalized.append(PageSection(start, stop))
    return normalized or [PageSection(top, bottom)]


def section_index_for_v(
    v: int,
    sections: list[PageSection] | tuple[PageSection, ...] | None,
    top_v: int,
    bottom_v: int,
) -> int:
    """Return the containing SECTION; gap markers attach to the nearest SECTION."""
    effective = normalize_page_sections(sections, top_v, bottom_v)
    value = int(v)
    for index, section in enumerate(effective):
        if section.top_v <= value < section.bottom_v:
            return index
    if value == effective[-1].bottom_v:
        return len(effective) - 1

    def distance(item: tuple[int, PageSection]) -> tuple[int, int]:
        index, section = item
        if value < section.top_v:
            return section.top_v - value, index
        return value - section.bottom_v, index

    return min(enumerate(effective), key=distance)[0]


def v_is_inside_sections(
    v: int,
    sections: list[PageSection] | tuple[PageSection, ...] | None,
    top_v: int,
    bottom_v: int,
) -> bool:
    """True when V is inside a real reading SECTION (ordinary pages always pass)."""
    if not sections:
        return int(top_v) <= int(v) < int(bottom_v)
    value = int(v)
    return any(int(section.top_v) <= value < int(section.bottom_v) for section in sections)


def build_reading_lanes(
    column_count: int,
    top_v: int,
    bottom_v: int,
    sections: list[PageSection] | tuple[PageSection, ...] | None = None,
) -> list[ReadingLane]:
    """Expand page sections into SECTION-major, column-minor reading lanes."""
    count = max(1, int(column_count))
    effective = normalize_page_sections(sections, top_v, bottom_v)
    return [
        ReadingLane(section_index, column_index, section.top_v, section.bottom_v)
        for section_index, section in enumerate(effective)
        for column_index in range(count)
    ]


def reading_lane_index(
    v: int,
    column_index: int,
    column_count: int,
    top_v: int,
    bottom_v: int,
    sections: list[PageSection] | tuple[PageSection, ...] | None = None,
) -> int:
    count = max(1, int(column_count))
    section_index = section_index_for_v(v, sections, top_v, bottom_v)
    column = max(0, min(count - 1, int(column_index)))
    return section_index * count + column


def read_page_sections(image_path: Path) -> list[PageSection]:
    """Read explicit page SECTIONs. Missing/invalid sidecars safely mean one SECTION."""
    path = page_sections_path_for_image(Path(image_path))
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(payload, dict):
        return []
    if payload.get("coordinate_space") not in {None, PAGE_SECTIONS_COORDINATE_SPACE}:
        return []
    rows = payload.get("sections")
    if not isinstance(rows, list):
        return []

    sections: list[PageSection] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            top = int(row.get("top_v"))
            bottom = int(row.get("bottom_v"))
        except (TypeError, ValueError):
            continue
        if bottom > top:
            sections.append(PageSection(top, bottom))
    sections.sort(key=lambda item: (item.top_v, item.bottom_v))
    if any(current.top_v < previous.bottom_v for previous, current in zip(sections, sections[1:])):
        return []
    return sections if len(sections) > 1 else []


def write_page_sections(
    image_path: Path,
    sections: list[PageSection] | tuple[PageSection, ...],
    *,
    canonical_width: int | None = None,
    canonical_height: int | None = None,
    layout_transform: str = "identity",
) -> Path:
    """Persist explicit SECTION bounds atomically; <=1 SECTION restores ordinary mode."""
    path = page_sections_path_for_image(Path(image_path))
    rows = [
        PageSection(int(section.top_v), int(section.bottom_v))
        for section in sorted(sections, key=lambda item: (int(item.top_v), int(item.bottom_v)))
        if int(section.bottom_v) > int(section.top_v)
    ]
    if any(current.top_v < previous.bottom_v for previous, current in zip(rows, rows[1:])):
        raise ValueError("SECTION 区域不能互相重叠")
    if len(rows) <= 1:
        path.unlink(missing_ok=True)
        return path

    payload = {
        "format": PAGE_SECTIONS_FORMAT,
        "version": 1,
        "coordinate_space": PAGE_SECTIONS_COORDINATE_SPACE,
        "layout_transform": str(layout_transform or "identity"),
        "canonical_width": int(canonical_width or 0),
        "canonical_height": int(canonical_height or 0),
        "sections": [
            {"index": index + 1, "top_v": section.top_v, "bottom_v": section.bottom_v}
            for index, section in enumerate(rows)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return path
