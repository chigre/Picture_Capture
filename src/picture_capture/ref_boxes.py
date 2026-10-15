"""Standalone, lossless REF rectangles in nine-column tab-separated .rbox.

These are page-local annotations. They NEVER mutate PDIC, PPP, SECTION or
Profile. Text uses RFC4180-style TSV quoting, including tabs and newlines.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from io import StringIO
from pathlib import Path
import csv
import re

from PIL import Image

from .formats import write_text_atomic
from .project_storage import is_managed_project, storage_root


# Seven-field files remain readable without mutation; every successful edit
# publishes this nine-field format. Percentages intentionally use page WIDTH
# as the denominator for both dimensions, matching PDIC X% and Y%.
LEGACY_COLUMNS = ("id", "x", "y", "w", "h", "entry_index", "text")
COLUMNS = ("id", "x", "y", "w", "h", "w.ww%", "h.hh%", "entry_index", "text")
_PERCENT_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]{2}%$")


def _source_image_width(image_path: Path) -> int:
    """Displayed original image width, accounting for EXIF 90° rotations."""
    with Image.open(image_path) as image:
        width, height = image.size
        try:
            orientation = int(image.getexif().get(274, 1))
        except (TypeError, ValueError, OverflowError):
            orientation = 1
        width = height if orientation in (5, 6, 7, 8) else width
    if width <= 0:
        raise ValueError("REF source image has no valid width")
    return width


def _percent(pixels: int, image_width: int) -> str:
    # Use the same denominator and 2-digit precision as write_pdic().
    return f"{pixels / image_width * 100:.2f}%"


def _verify_percent(saved: str, pixels: int, image_width: int) -> None:
    if _PERCENT_PATTERN.fullmatch(saved) is None:
        raise ValueError("REF percentage must have two decimal places and %")
    if saved != _percent(pixels, image_width):
        raise ValueError("REF percentage does not match source-image width")



@dataclass(frozen=True, slots=True)
class RefBox:
    id: int
    x: int
    y: int
    w: int
    h: int
    entry_index: int | None
    text: str = ""


def ref_box_root(project_root: Path) -> Path:
    root = Path(project_root)
    base = storage_root(root) if is_managed_project(root) else root
    return base / "data" / "ref_box"


def ref_box_path(image_path: Path) -> Path:
    page = Path(image_path)
    return ref_box_root(page.parent) / f"{page.stem}.rbox"


def ref_sample_root(project_root: Path) -> Path:
    return ref_box_root(project_root) / "samples"


def ref_box_ticket(image_path: Path) -> str | None:
    path = ref_box_path(image_path)
    try:
        return sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def validate_ref_boxes(boxes: list[RefBox] | tuple[RefBox, ...]) -> None:
    ids: set[int] = set()
    for box in boxes:
        if not isinstance(box, RefBox):
            raise ValueError("REF box record has invalid type")
        if (not isinstance(box.id, int) or isinstance(box.id, bool)
                or box.id <= 0 or box.id in ids):
            raise ValueError("REF ID must be unique and positive")
        ids.add(box.id)
        if not all(isinstance(v, int) and not isinstance(v, bool)
                   for v in (box.x, box.y, box.w, box.h)):
            raise ValueError("REF coordinates must be integer source pixels")
        if box.x < 0 or box.y < 0 or box.w <= 0 or box.h <= 0:
            raise ValueError("REF rectangle lies outside positive source coordinates")
        if box.entry_index is not None and (
            not isinstance(box.entry_index, int) or isinstance(box.entry_index, bool)
            or box.entry_index < 0
        ):
            raise ValueError("REF entry_index must be a nonnegative zero-based ordinal")
        if not isinstance(box.text, str) or "\0" in box.text:
            raise ValueError("REF text contains unsupported characters")


def _serialize(boxes: list[RefBox] | tuple[RefBox, ...], image_width: int) -> str:
    validate_ref_boxes(boxes)
    if image_width <= 0:
        raise ValueError("REF source image width must be positive")
    stream = StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(COLUMNS)
    for box in boxes:
        writer.writerow((
            box.id, box.x, box.y, box.w, box.h,
            _percent(box.w, image_width), _percent(box.h, image_width),
            "" if box.entry_index is None else box.entry_index, box.text,
        ))
    return stream.getvalue()


def read_ref_boxes(image_path: Path) -> list[RefBox]:
    path = ref_box_path(image_path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return []
    try:
        reader = csv.reader(StringIO(text, newline=""), delimiter="\t", strict=True)
        header = tuple(next(reader, ()))
        if header not in (COLUMNS, LEGACY_COLUMNS):
            raise ValueError("REF file has unexpected columns")
        is_nine_column = header == COLUMNS
        results: list[RefBox] = []
        image_width = _source_image_width(image_path) if is_nine_column else None
        for row in reader:
            if len(row) != len(header):
                raise ValueError("REF record has wrong column count")
            box = RefBox(
                id=int(row[0]), x=int(row[1]), y=int(row[2]),
                w=int(row[3]), h=int(row[4]),
                entry_index=int(row[7 if is_nine_column else 5])
                    if row[7 if is_nine_column else 5] != "" else None,
                text=row[8 if is_nine_column else 6],
            )
            if image_width is not None:
                _verify_percent(row[5], box.w, image_width)
                _verify_percent(row[6], box.h, image_width)
            results.append(box)
        validate_ref_boxes(results)
        return results
    except (ValueError, csv.Error) as exc:
        raise ValueError(f"{path.name}: invalid REF file; no changes were made") from exc


def write_ref_boxes(image_path: Path, boxes: list[RefBox] | tuple[RefBox, ...],
                    *, expected_ticket: str | None) -> str:
    """Disk-first single-file atomic commit; never publish stale UI state.

    A hash must be supplied from the last successful read (None means absent).
    If the on-disk file differs, raise without overwriting external edits.
    """
    # Validate first, before reading the image or attempting any disk write.
    validate_ref_boxes(boxes)
    image_width = _source_image_width(image_path)
    payload = _serialize(boxes, image_width)
    target = ref_box_path(image_path)
    if ref_box_ticket(image_path) != expected_ticket:
        raise RuntimeError("REF file changed outside the editor; reload the page")
    # Existing manually edited records must never be silently replaced if
    # their structure is corrupt, even when the caller knows their hash.
    if target.is_file():
        read_ref_boxes(image_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # A second check after mkdir narrows (but does not eliminate) race windows.
    if ref_box_ticket(image_path) != expected_ticket:
        raise RuntimeError("REF file changed before publication")
    write_text_atomic(target, payload)
    persisted = read_ref_boxes(image_path)
    if persisted != list(boxes):
        raise RuntimeError("REF write could not be verified; reload before editing")
    return ref_box_ticket(image_path) or sha256(payload.encode("utf-8")).hexdigest()


def next_ref_id(boxes: list[RefBox] | tuple[RefBox, ...]) -> int:
    return max((b.id for b in boxes), default=0) + 1


def box_intersection_fraction(a: RefBox, b: RefBox) -> float:
    left, top = max(a.x, b.x), max(a.y, b.y)
    right, bottom = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    intersection = max(0, right - left) * max(0, bottom - top)
    return intersection / max(1, min(a.w * a.h, b.w * b.h))


def reindex_ref_box(box: RefBox, entry_index: int | None) -> RefBox:
    return replace(box, entry_index=entry_index)


__all__ = [
    "RefBox", "COLUMNS", "LEGACY_COLUMNS", "ref_box_root", "ref_box_path", "ref_sample_root",
    "read_ref_boxes", "write_ref_boxes", "ref_box_ticket",
    "next_ref_id", "box_intersection_fraction", "validate_ref_boxes",
]
