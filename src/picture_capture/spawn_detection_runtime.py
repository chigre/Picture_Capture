from __future__ import annotations

"""Spawn-safe ordinary drawing worker with the same runtime metadata as the GUI.

A ``multiprocessing`` worker started with the ``spawn`` context imports package
modules in a fresh interpreter.  Worker-local runtime preparation therefore goes
through ``bootstrap.build_worker_services`` before ordinary detection runs.

This top-level function remains intentionally pickleable.  It performs one page
job using the dependencies returned by the worker composition root, writes PDIC
through the classification-aware formats writer, and captures the physical
Layout rows used by ordinary drawing into ``data/LayoutRows`` for later QA.
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
    """Run one ordinary-drawing job through the explicit worker bootstrap."""

    from .bootstrap.worker import build_worker_services

    services = build_worker_services()
    formats = services.formats
    processing_module = services.processing

    page = Path(image_path)
    with Image.open(page) as opened:
        image = processing_module._core.normalize_page_rgb(opened)

    try:
        current = replace(settings)
        current.detection_method = "left_edge"
        # The full ordinary Layout result is already being computed here. Capture
        # its physical rows once instead of making post-production rebuild them.
        # Cache validity is keyed by the persisted/project settings rather than
        # the temporary worker-only detection_method override.
        with services.capture_layout_rows(
            page.parent,
            page,
            int(profile_page_index),
            settings,
        ):
            entries, _geometry = processing_module.detect_entries(
                image,
                current,
                profile_page_index=profile_page_index,
                page_sections=processing_module._core.read_page_sections(page),
            )

        pdic = processing_module._core.pdic_path_for_image(page)
        services.save_automatic_baseline(pdic, entries, image.width, pages)
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
