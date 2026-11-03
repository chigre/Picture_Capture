"""Read-only content witness for focused-review crop cache ownership.

Only pages in a requested crop batch are hashed. The witness is volatile;
it is not a source-time OCR attestation, a persisted schema, or an OS CAS.
"""
from __future__ import annotations

from hashlib import sha256
from operator import index as exact_index
from pathlib import Path

from ..persistence.project_storage import (
    page_sections_read_path_for_image, pdic_path_for_image,
)

_CHUNK_SIZE = 1024 * 1024


def _source_page_index(value: object) -> int:
    """Require genuine integer page identity, without int() truncation."""
    if isinstance(value, bool):
        raise ValueError("focused crop page index must be an integer")
    try:
        return exact_index(value)
    except TypeError as exc:
        raise ValueError("focused crop page index must be an integer") from exc


def _file_witness(path: Path, *, optional: bool) -> tuple[str, str, str]:
    """Include exact content and resolved path; distinguish absent sidecars."""
    path = Path(path)
    try:
        digest = sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
    except FileNotFoundError:
        if not optional:
            raise
        return ("absent", str(path.resolve()), "")
    return ("present", str(path.resolve()), digest.hexdigest())


def focused_crop_source_witness(
    pages: list[Path], targets: list[dict],
) -> tuple[str, tuple]:
    """Pin each referenced image, PDIC and active SECTION sidecar by bytes.

    Managed/legacy SECTION path changes and absent-to-present transitions
    invalidate a crop. PDIC is required for any selected text source row.
    Do not hash unrelated pages or OCR caches for a normal crop.
    """
    source_pages = sorted({_source_page_index(target["page_index"]) for target in targets})
    rows = []
    for page_index in source_pages:
        if not 0 <= page_index < len(pages):
            raise ValueError("focused crop page index out of range")
        page = Path(pages[page_index])
        rows.append((
            page_index,
            _file_witness(page, optional=False),
            _file_witness(pdic_path_for_image(page), optional=False),
            _file_witness(page_sections_read_path_for_image(page), optional=True),
        ))
    return ("focused-crop-source-v1", tuple(rows))


def focused_save_source_from_crop_witness(
    crop_witness: tuple, page_index: int,
) -> tuple | None:
    """Bind an accepted crop's image/SECTION to each human edit.

    PDIC bytes are deliberately omitted: a valid human edit changes PDIC.
    Source provenance is captured during verified crop display, not at save.
    """
    try:
        if crop_witness[0] != "focused-crop-source-v1":
            return None
        owner_index = _source_page_index(page_index)
        matches = [
            row for row in crop_witness[1]
            if row[0] == owner_index
        ]
        if len(matches) != 1:
            return None
        row = matches[0]
        return ("focused-save-source-v1", row[1], row[3])
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def focused_save_source_witness(page: Path) -> tuple:
    """Current image/SECTION byte identity; no new source witness is stored."""
    page = Path(page)
    return (
        "focused-save-source-v1",
        _file_witness(page, optional=False),
        _file_witness(page_sections_read_path_for_image(page), optional=True),
    )


def verify_focused_save_source(page: Path, expected: tuple | None) -> None:
    """Fail closed if the displayed image/SECTION source cannot be proven."""
    if (
        not isinstance(expected, tuple) or len(expected) != 3
        or expected[0] != "focused-save-source-v1"
    ):
        raise RuntimeError("筛选校对缺少有效的原图与 SECTION 来源证明，拒绝保存")
    try:
        current = focused_save_source_witness(page)
    except (OSError, ValueError) as exc:
        raise RuntimeError("筛选校对原图或 SECTION 来源无法核验，拒绝保存") from exc
    if current != expected:
        raise RuntimeError("筛选校对原图或 SECTION 来源已变化，拒绝保存")


def focused_scan_source_witness(
    page: Path, pdic_path: Path, ocr_cache_path: Path,
) -> tuple:
    """Pin the exact inputs consumed by one focused-filter page scan.

    PDIC is required; OCR cache and SECTION are optional but their absence,
    resolved path and bytes are part of the witness. The page pixels are not
    read by the scan and therefore are intentionally not included.
    """
    return (
        "focused-scan-source-v1",
        _file_witness(Path(pdic_path), optional=False),
        _file_witness(Path(ocr_cache_path), optional=True),
        _file_witness(page_sections_read_path_for_image(Path(page)), optional=True),
    )


def verify_focused_scan_source(
    page: Path, pdic_path: Path, ocr_cache_path: Path, expected: tuple | None,
) -> None:
    """Reject a scan whose PDIC/OCR/SECTION inputs no longer match its read."""
    if (
        not isinstance(expected, tuple) or len(expected) != 4
        or expected[0] != "focused-scan-source-v1"
    ):
        raise RuntimeError("重点筛选缺少有效的数据来源证明，拒绝发布结果")
    try:
        current = focused_scan_source_witness(page, pdic_path, ocr_cache_path)
    except (OSError, ValueError) as exc:
        raise RuntimeError("重点筛选的数据来源无法核验，拒绝发布结果") from exc
    if current != expected:
        raise RuntimeError("重点筛选期间 PDIC、OCR 缓存或 SECTION 来源已变化，拒绝发布结果")
