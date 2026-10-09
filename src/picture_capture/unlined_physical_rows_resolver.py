from __future__ import annotations

"""Physical-row resolver dedicated to unlined-row QA.

This module is intentionally narrower than PageUnderstanding/Layout Core.  It
never needs entry/body roles, sampled symbols or universal large-head evidence.
Only the final escalation step may invoke the reliable per-page geometry
detector (including Paddle when configured/needed), and even then it stops at
the physical Page Layout policy result.
"""

from pathlib import Path
from typing import Any

from PIL import Image

from .layout_rows_cache import (
    load_layout_rows_cache,
    recover_physical_rows_fast,
    write_layout_rows_cache,
)


def resolve_unlined_physical_rows(
    project_root: Path,
    image_path: Path,
    image: Image.Image,
    settings: Any,
    *,
    page_index: int = 0,
) -> tuple[Any | None, str]:
    """Resolve physical rows: persisted cache -> Profile projection -> detector."""
    cached = load_layout_rows_cache(
        project_root,
        image_path,
        int(page_index),
        settings,
        source_size=tuple(image.size),
    )
    if cached is not None:
        return cached, "cache"

    fast = recover_physical_rows_fast(
        image,
        settings,
        page_index=int(page_index),
    )
    if fast is not None:
        try:
            write_layout_rows_cache(
                project_root,
                image_path,
                int(page_index),
                settings,
                fast,
            )
        except Exception:
            pass
        return fast, "fast_projection"

    # Escalate geometry only through the explicit physical-only policy
    # composition. This independent spawn worker no longer needs to install
    # process-global Layout hooks before the detector can run.
    from .layout_composition import infer_composed_physical_page_layout

    try:
        layout, _page_settings, _applied = infer_composed_physical_page_layout(
            image,
            settings,
            page_index=int(page_index),
        )
    except Exception:
        return None, "physical_detector_error"

    columns = list(getattr(layout, "columns", []) or [])
    populated = sum(bool(list(getattr(column, "lines", []) or [])) for column in columns)
    row_count = sum(len(list(getattr(column, "lines", []) or [])) for column in columns)
    reliable = bool(
        columns
        and populated >= max(1, len(columns) - 1)
        and row_count >= max(5, 3 * len(columns))
        and float(getattr(layout, "ordinary_line_height", 0.0) or 0.0) >= 4.0
    )
    if not reliable:
        return None, "physical_detector_unreliable"

    try:
        write_layout_rows_cache(
            project_root,
            image_path,
            int(page_index),
            settings,
            layout,
        )
    except Exception:
        pass
    return layout, "physical_detector"


__all__ = ["resolve_unlined_physical_rows"]
