from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from PIL import Image, ImageOps

from .coordinate_space import SOURCE_COORDINATE_SPACE
from .layout_transform import LayoutTransform
from .project_storage import page_sections_path_for_image


PAGE_SECTIONS_FORMAT = "picture-capture-page-sections-v2"
PAGE_SECTIONS_COORDINATE_SPACE = SOURCE_COORDINATE_SPACE


@dataclass(frozen=True, slots=True)
class PageSection:
    """Runtime reading interval on temporary canonical V.

    Persisted SECTION geometry uses original-image X/Y boundary segments only.
    """

    top_v: int
    bottom_v: int


@dataclass(frozen=True, slots=True)
class ReadingLane:
    section_index: int
    column_index: int
    top_v: int
    bottom_v: int


def normalize_page_sections(
    sections: list[PageSection] | tuple[PageSection, ...] | None,
    top_v: int,
    bottom_v: int,
) -> list[PageSection]:
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


def _point(value: object) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None


def _segment_v(
    value: object,
    transform: LayoutTransform,
    source_size: tuple[int, int],
) -> int | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    start = _point(value[0])
    end = _point(value[1])
    if start is None or end is None:
        return None
    c0, c1 = transform.source_segment_to_canonical(start, end, source_size)
    if int(c0[1]) != int(c1[1]):
        return None
    return int(c0[1])


def read_page_sections(image_path: Path) -> list[PageSection]:
    image_path = Path(image_path)
    path = page_sections_path_for_image(image_path)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(payload, dict):
        return []
    rows = payload.get("sections")
    if not isinstance(rows, list):
        return []

    coordinate_space = str(payload.get("coordinate_space") or "")
    sections: list[PageSection] = []

    if coordinate_space != SOURCE_COORDINATE_SPACE:
        return []

    try:
        source_size = (
            int(payload.get("source_width") or 0),
            int(payload.get("source_height") or 0),
        )
        if source_size[0] <= 0 or source_size[1] <= 0:
            with Image.open(image_path) as opened:
                source_size = ImageOps.exif_transpose(opened).size
        transform = LayoutTransform(
            str(payload.get("layout_transform_internal") or "identity")
        )
    except Exception:
        return []
    for row in rows:
        if not isinstance(row, dict):
            continue
        top = _segment_v(row.get("top_source_segment_xyxy"), transform, source_size)
        bottom = _segment_v(row.get("bottom_source_segment_xyxy"), transform, source_size)
        if top is not None and bottom is not None and bottom > top:
            sections.append(PageSection(top, bottom))


    sections.sort(key=lambda item: (item.top_v, item.bottom_v))
    if any(current.top_v < previous.bottom_v for previous, current in zip(sections, sections[1:])):
        return []
    return sections


def write_page_sections(
    image_path: Path,
    sections: list[PageSection] | tuple[PageSection, ...],
    *,
    canonical_width: int | None = None,
    canonical_height: int | None = None,
    layout_transform: str = "identity",
) -> Path:
    """Persist SECTION boundaries as original-image X/Y line segments."""
    image_path = Path(image_path)
    path = page_sections_path_for_image(image_path)
    rows = [
        PageSection(int(section.top_v), int(section.bottom_v))
        for section in sorted(sections, key=lambda item: (int(item.top_v), int(item.bottom_v)))
        if int(section.bottom_v) > int(section.top_v)
    ]
    if any(current.top_v < previous.bottom_v for previous, current in zip(rows, rows[1:])):
        raise ValueError("SECTION 区域不能互相重叠")
    if not rows:
        path.unlink(missing_ok=True)
        return path

    transform = LayoutTransform(str(layout_transform or "identity"))
    try:
        with Image.open(image_path) as opened:
            source_size = ImageOps.exif_transpose(opened).size
    except Exception:
        cw = max(1, int(canonical_width or 1))
        ch = max(1, int(canonical_height or 1))
        source_size = (ch, cw) if transform.kind.startswith("rotate_") else (cw, ch)
    cw, _ch = transform.canonical_size(source_size)

    def source_segment(v: int) -> list[list[int]]:
        start, end = transform.canonical_segment_to_source(
            (0, int(v)), (max(0, cw - 1), int(v)), source_size,
        )
        return [[int(start[0]), int(start[1])], [int(end[0]), int(end[1])]]

    payload = {
        "format": PAGE_SECTIONS_FORMAT,
        "version": 2,
        "coordinate_space": SOURCE_COORDINATE_SPACE,
        "source_width": int(source_size[0]),
        "source_height": int(source_size[1]),
        "layout_transform_internal": transform.kind,
        "sections": [
            {
                "index": index + 1,
                "top_source_segment_xyxy": source_segment(section.top_v),
                "bottom_source_segment_xyxy": source_segment(section.bottom_v),
            }
            for index, section in enumerate(rows)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return path
