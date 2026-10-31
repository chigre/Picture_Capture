"""Read-only content witness for focused-review crop cache ownership.

Only pages in a requested crop batch are hashed. The witness is volatile;
it is not a source-time OCR attestation, a persisted schema, or an OS CAS.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from ..persistence.project_storage import (
    page_sections_read_path_for_image, pdic_path_for_image,
)

_CHUNK_SIZE = 1024 * 1024


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
    source_pages = sorted({int(target["page_index"]) for target in targets})
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
