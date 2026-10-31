"""Spawn-importable ordinary drawing page job: exactly-once GPU preflight.

Actual image normalization, Profile sections, Layout capture, automatic baseline
and PDIC persistence are implemented here. The public processing facade retains
its historical function identity, signature and call-time patched IO providers.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from PIL import Image
from ..models import AppSettings

def detect_entries_job_impl(
    image_path: str,
    settings: AppSettings,
    pages: tuple[str, str, str],
    profile_page_index: int = 0,
    *,
    prepared_layout: Any | None = None,
    deps: dict[str, Any],
) -> int:
    Path = deps["Path"]
    Image = deps["Image"]
    replace = deps["replace"]
    """Run ordinary drawing with optional isolated, exactly-once GPU preflight.

    Ordinary serial calls have NO injected estimate and keep the old path.
    """
    from contextlib import nullcontext
    from time import perf_counter
    from ..quality.draw_performance_profile import enabled as profile_enabled, record_page, bind_page, unbind_page
    profiling = profile_enabled()
    stages = {}
    total_start = perf_counter()
    tick = total_start
    from ..bootstrap.worker import build_worker_services
    if prepared_layout is not None:
        from ..ordinary.gpu_pipeline import (
            use_prepared_layout, validate_prepared_layout,
            verify_prepared_source,
        )

        verify_prepared_source(image_path, profile_page_index, prepared_layout)
        estimate_context = use_prepared_layout(prepared_layout)
    else:
        estimate_context = nullcontext(None)

    services = build_worker_services()
    if profiling:
        stages["bootstrap"] = perf_counter() - tick
        tick = perf_counter()
    formats = services.formats
    processing_module = services.processing

    page = Path(image_path)
    with Image.open(page) as opened:
        image = processing_module._core.normalize_page_rgb(opened)

    if profiling:
        stages["image_open_normalize"] = perf_counter() - tick
        tick = perf_counter()

    page_binding = bind_page(page) if profiling else None
    try:
        current = replace(settings)
        current.detection_method = "left_edge"
        sections = processing_module._core.read_page_sections(page)
        if profiling:
            stages["page_sections"] = perf_counter() - tick
            tick = perf_counter()
        with estimate_context as preflight_state:
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
                    page_sections=sections,
                    **({"source_image_path": page}
                       if getattr(current, "layout_mask_illustrations", False) else {}),
                )
            if preflight_state is not None:
                # An optional internal fallback must not turn a missing GPU
                # estimate into altered lines or a second Paddle model.
                validate_prepared_layout(preflight_state)
                verify_prepared_source(page, profile_page_index, prepared_layout)

        if profiling:
            stages["detect_entries"] = perf_counter() - tick
            tick = perf_counter()
        pdic = processing_module._core.pdic_path_for_image(page)
        services.save_automatic_baseline(pdic, entries, image.width, pages)
        if profiling:
            stages["automatic_baseline"] = perf_counter() - tick
            tick = perf_counter()
        formats.write_pdic(
            pdic,
            entries,
            image.width,
            pages,
        )
        if profiling:
            stages["pdic_write"] = perf_counter() - tick
            stages["total_page"] = perf_counter() - total_start
            record_page(page, profile_page_index, stages)
        return len(entries)
    finally:
        if page_binding is not None:
            unbind_page(page_binding)
        image.close()
