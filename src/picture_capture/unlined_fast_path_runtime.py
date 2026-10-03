from __future__ import annotations

"""Fast-path adapter for 【未画线行导出】.

The historical exporter called the complete Layout Core on every selected page.
That was correct but unnecessarily expensive for QA because the exporter only
needs physical rows, not entry/body semantics.  This runtime swaps the one-page
worker for a version that resolves physical rows in this order:

1. persisted ``data/LayoutRows/<page>.json``;
2. Profile-geometry projection recovery (no Paddle, symbol or large-head work);
3. full reliable Layout Core only when the fast physical geometry is implausible.

The existing PDIC matching, near-blank filter, white-border handling and output
format remain unchanged.
"""

from pathlib import Path
from typing import Any

from PIL import Image

from . import formats
from .image_utils import normalize_page_rgb
from .layout_rows_cache import resolve_physical_rows_layout
from .page_sections import read_page_sections
from .project_storage import qt_root


def export_unlined_page_job_fast(
    project_root: str | Path,
    image_path: str | Path,
    page_index: int,
    settings: Any,
    merge_by_page: bool,
    filter_enabled: bool,
    filter_blank: bool,
    blank_ink_percent: float,
):
    """Spawn-safe one-page exporter using physical-row cache/projection first."""
    from .unlined_line_export import (
        OUTPUT_DIRNAME,
        UnlinedPageResult,
        _save_unlined_rows,
        unlined_rows_from_layout,
    )

    root = Path(project_root)
    page = Path(image_path)
    output_dir = qt_root(root) / OUTPUT_DIRNAME
    entries = formats.read_pdic(formats.pdic_path(page))
    sections = read_page_sections(page)

    with Image.open(page) as opened:
        source = normalize_page_rgb(opened)
    try:
        layout, _source = resolve_physical_rows_layout(
            root,
            page,
            source,
            settings,
            page_index=int(page_index),
        )
        if layout is None:
            return UnlinedPageResult(
                int(page_index), page.name, 0, 0, 0, 0, 0, 0, False, False
            )

        rows, layout_rows, lined_rows = unlined_rows_from_layout(
            layout,
            entries,
            sections,
        )
        exported, blanks, filtered_out, merged = _save_unlined_rows(
            source,
            page,
            rows,
            output_dir,
            merge_by_page=bool(merge_by_page),
            filter_enabled=bool(filter_enabled),
            filter_blank=bool(filter_blank),
            blank_ink_percent=float(blank_ink_percent),
        )
        return UnlinedPageResult(
            int(page_index),
            page.name,
            int(layout_rows),
            int(lined_rows),
            len(rows),
            int(exported),
            int(blanks),
            int(filtered_out),
            bool(merged),
            True,
        )
    finally:
        source.close()


def install_unlined_fast_path() -> None:
    """Replace only the one-page worker; keep all existing batch/UI behavior."""
    from . import unlined_line_export as exporter

    if bool(getattr(exporter, "_physical_rows_fast_path_installed", False)):
        return
    exporter.export_unlined_page_job = export_unlined_page_job_fast
    exporter._physical_rows_fast_path_installed = True


__all__ = ["export_unlined_page_job_fast", "install_unlined_fast_path"]
