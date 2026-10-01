from __future__ import annotations

"""Spawn-safe ordinary drawing worker with Layout roles as the source of truth.

``ProcessPoolExecutor`` workers on Windows/macOS import modules afresh, so they
must install the same physical-indent Layout runtime used by the GUI before
running Page Understanding.  Otherwise the visible Layout roles and ordinary
worker roles can diverge even when both call ``understand_page``.
"""

from pathlib import Path

from PIL import Image

from . import dictionary_page_design, processing
from .dictionary_page_design_refined import detect_entries_from_page_design
from .layout_line_start_refinement import install_robust_line_starts
from .layout_physical_indent import install_physical_indent_inference
from .ordinary_layout_primary import build_ordinary_layout_primary
from .training_baseline import save_automatic_baseline


def _prepare_layout_role_runtime() -> None:
    """Install the exact Layout-role implementation used by the GUI process."""
    dictionary_page_design.detect_entries_from_page_design = (
        detect_entries_from_page_design
    )
    install_robust_line_starts()
    install_physical_indent_inference()


def detect_entries_job(
    image_path: str,
    settings,
    pages: tuple[str, str, str],
    profile_page_index: int = 0,
) -> int:
    """Run ordinary drawing through final physical-indent Layout roles."""
    _prepare_layout_role_runtime()

    page = Path(image_path)
    with Image.open(page) as opened:
        image = processing._core.normalize_page_rgb(opened)

    settings.detection_method = "left_edge"

    # Build the route inside the worker process itself.  Do not depend on the
    # launcher-time wrapper in the GUI process: spawn workers do not inherit it.
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
