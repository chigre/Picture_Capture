"""SECTION evidence only when original-image coordinates and saved sidecar agree.

Never infer SECTION from a list position or assign a marker in a gap to the
nearest section. The sidecar fingerprint becomes part of each new event.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from .layout_transform import LayoutTransform
from .page_sections import read_page_sections
from .project_storage import page_sections_read_path_for_image
from .proofreading_events import sha256_file


def section_snapshot_for_source_point(
    image_path: Path, x: int, y: int,
) -> tuple[str, str] | None:
    image_path = Path(image_path)
    sidecar = page_sections_read_path_for_image(image_path)
    if not sidecar.is_file():
        return None
    try:
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        kind = raw.get("layout_transform_internal")
        if not isinstance(kind, str) or not kind:
            return None
        transform = LayoutTransform(kind)
        sections = read_page_sections(image_path)
        if not sections or len(sections) != len(raw.get("sections", [])):
            return None
        # Read header/EXIF only; fully transposing a large scanned page here
        # would decode its pixels during every single proofreading action.
        with Image.open(image_path) as opened:
            raw_width, raw_height = opened.size
            orientation = int(opened.getexif().get(274, 1) or 1)
            size = (
                (raw_height, raw_width)
                if orientation in (5, 6, 7, 8)
                else (raw_width, raw_height)
            )
        if size != (int(raw.get("source_width", -1)), int(raw.get("source_height", -1))):
            return None
        x, y = int(x), int(y)
        if not (0 <= x < size[0] and 0 <= y < size[1]):
            return None
        _, v = transform.source_to_canonical_point(x, y, size)
        indices = [
            i + 1
            for i, section in enumerate(sections)
            if section.top_v <= v < section.bottom_v
        ]
        digest = sha256_file(sidecar)
        if len(indices) != 1 or digest is None:
            return None
        return f"section:{indices[0]}", digest
    except (OSError, ValueError, TypeError, KeyError):
        return None


def section_fields_for_event(
    image_path: Path, *, before_xy: tuple[int, int] | None = None,
    after_xy: tuple[int, int] | None = None,
) -> dict[str, str | None]:
    """Cross-section moves remain unassigned instead of inventing a section."""
    points = [p for p in (before_xy, after_xy) if p is not None]
    identities = [section_snapshot_for_source_point(image_path, *p) for p in points]
    result: tuple[str, str] | None = (
        identities[0] if identities and all(x == identities[0] for x in identities) else None
    )
    return {
        "section_id": result[0] if result else None,
        "section_snapshot_sha256": result[1] if result else None,
    }
