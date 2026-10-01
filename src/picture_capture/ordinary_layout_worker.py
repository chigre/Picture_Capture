from __future__ import annotations

"""Spawn-safe ordinary drawing worker with Layout roles as the source of truth.

The GUI process installs a Layout-first detector wrapper at startup, but
``ProcessPoolExecutor`` workers on Windows/macOS import modules afresh and do
not execute that launcher-time monkey patch.  This module is itself the process
target, so every spawned worker constructs the same Layout-first detector before
running ordinary drawing.
"""

from pathlib import Path

from PIL import Image

from . import processing
from .ordinary_layout_primary import build_ordinary_layout_primary
from .training_baseline import save_automatic_baseline


def detect_entries_job(
    image_path: str,
    settings,
    pages: tuple[str, str, str],
    profile_page_index: int = 0,
) -> int:
    """Run ordinary drawing through final Page Understanding Layout roles."""
    page = Path(image_path)
    with Image.open(page) as opened:
        image = processing._core.normalize_page_rgb(opened)

    settings.detection_method = "left_edge"

    # Build the route inside the worker process itself.  Do not depend on the
    # launcher-time patch in the GUI process: spawn workers do not inherit it.
    detect_layout_primary = build_ordinary_layout_primary(
        processing,
        processing.detect_entries,
    )
    entries, _geometry = detect_layout_primary(
        image,
        settings,
        profile_page_index=profile_page_index,
        page_sections=processing._core.read_page_sections(page),
    )

    pdic = processing._core.pdic_path_for_image(page)
    save_automatic_baseline(pdic, entries, image.width, pages)
    processing._core.write_pdic(
        pdic,
        entries,
        image.width,
        pages,
    )
    return len(entries)
