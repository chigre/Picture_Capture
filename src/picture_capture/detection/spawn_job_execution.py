"""Spawn-safe one-page ordinary marker detection and PDIC writer.

Historical processing_core entrypoints supply the live callbacks and preserve
serializable model identity, pixel coordinates and output file contracts.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import AppSettings


def detect_entries_job_impl(
    image_path: str,
    settings: AppSettings,
    pages: tuple[str, str, str],
    profile_page_index: int = 0,
    *, deps: dict[str, Any],
) -> int:
    """Spawn-safe ordinary-line detection job that commits one PDIC page."""
    Path = deps["Path"]
    Image = deps["Image"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    detect_entries = deps["detect_entries"]
    read_page_sections = deps["read_page_sections"]
    write_pdic = deps["write_pdic"]
    pdic_path_for_image = deps["pdic_path_for_image"]
    page = Path(image_path)
    with Image.open(page) as opened:
        image = normalize_page_rgb(opened)
    settings.detection_method = "left_edge"
    entries, _geometry = detect_entries(
        image, settings, profile_page_index=profile_page_index,
        page_sections=read_page_sections(page),
    )
    write_pdic(pdic_path_for_image(page), entries, image.width, pages)
    return len(entries)
