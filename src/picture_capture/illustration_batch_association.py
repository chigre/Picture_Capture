"""Source-validated, page-local PPP illustration association for batch jobs.

This module never touches Tk or mutable live canvas objects. A page without
an existing PPP is always skipped; the worker must not synthesize empty PPP.
Each page's Profile geometry and SECTIONs determine the same reading order
used by the foreground editor. The only output is that page's PPP file.
"""
from __future__ import annotations

from hashlib import sha256
from glob import escape
from pathlib import Path
from PIL import Image

from .formats import pdic_path, read_pdic, read_ppp, write_ppp
from .text_encoding import read_text_detected
from .illustration_labels import illustration_labels
from .models import AppSettings, PolygonRegion
from .page_sections import read_page_sections
from .processing_core import derive_geometry
from .profile_semantics import effective_page_settings, page_template_analysis_image
from .project_storage import ppp_read_path_for_image
from .image_utils import normalize_page_rgb


def _file_ticket(path: Path) -> tuple[int, int, str]:
    """Optimistic source guard: reject changed inputs before replacing PPP."""
    stat = path.stat()
    return (int(stat.st_size), int(stat.st_mtime_ns), sha256(path.read_bytes()).hexdigest())


def associate_existing_ppp_page(
    image_path: Path, settings: AppSettings, page_index: int,
    previous_image_path: Path | None = None,
) -> dict:
    """Associate one existing PPP, atomically writing changed PPP labels only.

    PDIC and SECTION are read-only. The source/target PPP and PDIC are checked
    immediately before commit, so a concurrent external edit is reported
    instead of deliberately overwriting stale data. Multi-file atomicity or
    Undo/Redo is *not* claimed.
    """
    page = Path(image_path)
    source_ppp = ppp_read_path_for_image(page)
    if not source_ppp.is_file():
        return {"status": "skipped_no_ppp", "page_index": page_index, "page": page.name}
    # On case-sensitive filesystems a page may have both .ppp and .PPP,
    # holding DIFFERENT manually edited polygons. Never silently choose one.
    # On Windows/macOS case-insensitive volumes the directory exposes only
    # one actual entry even if two differently-cased lookups both succeed.
    alternatives = [
        sibling for sibling in source_ppp.parent.glob(f"{escape(page.stem)}.*")
        if sibling.is_file() and sibling.suffix.casefold() == ".ppp"
        and sibling.stem.casefold() == page.stem.casefold()
    ]
    if len(alternatives) > 1:
        return {
            "status": "skipped_ambiguous_ppp",
            "page_index": page_index, "page": page.name,
        }
    original_ticket = _file_ticket(source_ppp)
    regions = read_ppp(source_ppp)
    if not regions:
        return {"status": "skipped_empty_ppp", "page_index": page_index, "page": page.name}
    # The permissive historical reader silently ignores malformed records.
    # Refuse to rewrite a partly parsed human PPP or we could erase shapes.
    record_count = sum(
        bool(line.strip()) for line in read_text_detected(source_ppp)[0].splitlines()
    )
    if len(regions) != record_count or any(len(region.points) < 3 for region in regions):
        return {"status": "skipped_invalid_ppp", "page_index": page_index, "page": page.name}
    source_pdic = pdic_path(page)
    if not source_pdic.is_file():
        return {"status": "skipped_no_pdic", "page_index": page_index, "page": page.name}
    pdic_ticket = _file_ticket(source_pdic)
    entries = read_pdic(source_pdic)
    if not entries:
        return {"status": "skipped_no_pdic", "page_index": page_index, "page": page.name}

    previous_ref = None
    previous_pdic = None
    previous_ticket = None
    if previous_image_path is not None:
        previous_image = Path(previous_image_path)
        previous_pdic = pdic_path(previous_image)
        if previous_pdic.is_file():
            previous_ticket = _file_ticket(previous_pdic)
            previous_entries = read_pdic(previous_pdic)
            if previous_entries and len(previous_entries) <= 1000:
                previous_ref = (previous_image.stem, len(previous_entries) - 1)

    with Image.open(page) as opened:
        image = normalize_page_rgb(opened)
    try:
        effective = effective_page_settings(settings, image.size, int(page_index))
        display = page_template_analysis_image(image, effective, int(page_index))
        geometry = derive_geometry(display, effective)
        sections = read_page_sections(page)
        new_labels = illustration_labels(
            regions, page.stem, geometry, sections,
            entries=entries, associate=True,
            previous_entry_ref=previous_ref,
        )
    finally:
        image.close()

    # Create new objects: the loaded source list is never modified in place.
    proposed = [
        PolygonRegion(label, list(region.points))
        for region, label in zip(regions, new_labels)
    ]
    changed = any(region.label != label for region, label in zip(regions, new_labels))
    if _file_ticket(source_ppp) != original_ticket or _file_ticket(source_pdic) != pdic_ticket:
        raise RuntimeError(f"{page.name}: PPP/PDIC changed concurrently; association not saved")
    if previous_ticket is not None and _file_ticket(previous_pdic) != previous_ticket:
        raise RuntimeError(f"{page.name}: previous PDIC changed concurrently; association not saved")

    if changed:
        # Use the REAL existing file, including historic uppercase .PPP case.
        # Writing a lower-case sibling on case-sensitive filesystems would
        # create a second conflicting source of truth for the same page.
        output = source_ppp
        if _file_ticket(source_ppp) != original_ticket:
            raise RuntimeError(f"{page.name}: PPP changed concurrently; association not saved")
        if _file_ticket(source_pdic) != pdic_ticket:
            raise RuntimeError(f"{page.name}: PDIC changed concurrently; association not saved")
        if previous_ticket is not None and _file_ticket(previous_pdic) != previous_ticket:
            raise RuntimeError(f"{page.name}: previous PDIC changed concurrently; association not saved")
        write_ppp(output, proposed, page.stem)
        persisted = read_ppp(output)
        if [(r.label, r.points) for r in persisted] != [
            (r.label, r.points) for r in proposed
        ]:
            raise RuntimeError(f"{page.name}: PPP write verification failed")
    return {
        "status": "changed" if changed else "unchanged",
        "page_index": int(page_index),
        "page": page.name,
        "figures": len(regions),
        "linked": sum(label.split("|")[2] != "xxx" for label in new_labels),
    }


def associate_existing_ppp_job(
    image_path: str, settings: AppSettings, page_index: int,
    previous_image_path: str | None = None,
) -> dict:
    """Catch a single page failure so other selected PPP pages still proceed."""
    try:
        return associate_existing_ppp_page(
            Path(image_path), settings, page_index,
            Path(previous_image_path) if previous_image_path is not None else None,
        )
    except Exception as exc:
        return {
            "status": "failed", "page_index": int(page_index),
            "page": Path(image_path).name,
            "error": f"{type(exc).__name__}: {exc}",
        }


__all__ = ["associate_existing_ppp_page", "associate_existing_ppp_job"]
