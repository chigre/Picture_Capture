from __future__ import annotations

"""Spawn-safe ordinary drawing worker with the same runtime metadata as the GUI.

The main launcher installs Entry classification by wrapping both Layout-row
materialization and PDIC IO.  A ``multiprocessing`` worker started with the
``spawn`` context imports ``picture_capture.processing`` directly and does not
run the GUI launcher, so those process-local wrappers are otherwise absent.

That mismatch is especially dangerous when ordinary drawing replaces an existing
PDIC: the old EntryClassification sidecar can survive while the marker geometry
changes, and the GUI may later match stale regular/oversized/manual metadata onto
the newly detected markers.

This top-level function is intentionally pickleable.  It bootstraps the same
classification runtime inside each spawned worker before detection and writes the
new PDIC through the classification-aware formats writer.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any

from PIL import Image


def detect_entries_job_with_runtime(
    image_path: str,
    settings: Any,
    pages: tuple[str, str, str],
    profile_page_index: int = 0,
) -> int:
    """Run one ordinary-drawing job with spawn-local runtime installers."""

    from . import formats
    from . import processing as processing_module
    from .entry_classification import install_pdic_classification
    from .entry_classification_runtime import install_processing_entry_classification
    from .training_baseline import save_automatic_baseline

    # Every spawn process has its own module globals.  Reinstall these wrappers
    # here rather than relying on launcher-time monkey patches from the parent.
    install_pdic_classification(formats)
    install_processing_entry_classification(processing_module)

    page = Path(image_path)
    with Image.open(page) as opened:
        image = processing_module._core.normalize_page_rgb(opened)

    try:
        current = replace(settings)
        current.detection_method = "left_edge"
        entries, _geometry = processing_module.detect_entries(
            image,
            current,
            profile_page_index=profile_page_index,
            page_sections=processing_module._core.read_page_sections(page),
        )

        pdic = processing_module._core.pdic_path_for_image(page)
        save_automatic_baseline(pdic, entries, image.width, pages)
        formats.write_pdic(
            pdic,
            entries,
            image.width,
            pages,
        )
        return len(entries)
    finally:
        image.close()


def install_spawn_detection_runtime(processing_module: Any) -> None:
    """Expose the spawn-safe top-level worker before ``app`` imports it."""

    if bool(getattr(processing_module, "_spawn_detection_runtime_installed", False)):
        return
    processing_module.detect_entries_job = detect_entries_job_with_runtime
    processing_module._spawn_detection_runtime_installed = True


__all__ = [
    "detect_entries_job_with_runtime",
    "install_spawn_detection_runtime",
]
