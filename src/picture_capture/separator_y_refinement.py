from __future__ import annotations

"""Shared separator-Y refinement for every drawing source.

Y refinement is a rendering/geometry operation, not a Layout or OCR decision.
Callers first decide *which* separator candidates exist (Layout roles, OCR,
manual/PDIC markers, historical VB fallback), then this module may move each
candidate a small distance to a safer local inter-line boundary.  It never adds,
removes, accepts, rejects, or reclassifies entries.

The public settings contract is now neutral and shared:
``separator_y_refine_enabled``, ``separator_y_search_ratio``,
``separator_y_band_radius``, ``separator_y_safety_px``,
``separator_y_roi_width_ratio`` and ``separator_y_column_margin``.
Historical ``paddle_*`` storage slots are exposed through static AppSettings
aliases, so old projects and the mature numerical engine keep working without
leaking OCR-specific naming into new code.
"""

from typing import Any

import numpy as np
from PIL import Image, ImageOps

from .models import AppSettings

# Capture the mature engine before compatibility facades redirect their public
# ``refine_separator_y`` symbol back to this module. This prevents recursion.
from . import paddle_headwords_core as _paddle_core

_ENGINE_REFINE_SEPARATOR_Y = _paddle_core.refine_separator_y


def refine_separator_y(
    gray: np.ndarray,
    coarse_y: int,
    line_height: int | float,
    settings: AppSettings,
    *args: Any,
    **kwargs: Any,
) -> tuple[int, dict[str, Any]]:
    """Refine one existing separator candidate without changing its semantics."""
    if not bool(getattr(settings, "separator_y_refine_enabled", True)):
        return int(coarse_y), {
            "refiner": "shared_separator_y",
            "enabled": False,
        }

    refined_y, details = _ENGINE_REFINE_SEPARATOR_Y(
        gray,
        int(coarse_y),
        max(2, int(round(float(line_height or 0)))),
        settings,
        *args,
        **kwargs,
    )
    payload = dict(details or {})
    payload.setdefault("refiner", "shared_separator_y")
    payload.setdefault("enabled", True)
    payload.setdefault(
        "search_ratio",
        float(getattr(settings, "separator_y_search_ratio", 0.30) or 0.30),
    )
    payload.setdefault(
        "band_radius",
        int(getattr(settings, "separator_y_band_radius", 2) or 2),
    )
    payload.setdefault(
        "safety_px",
        int(getattr(settings, "separator_y_safety_px", 2) or 0),
    )
    payload.setdefault(
        "roi_width_ratio",
        float(getattr(settings, "separator_y_roi_width_ratio", 60.0) or 60.0),
    )
    return int(refined_y), payload


def refined_layout_entry_y_by_line(
    image: Image.Image,
    understanding: Any,
    *,
    page_index: int = 0,
) -> dict[int, int]:
    """Apply the shared refiner to rows already classified as Layout entries.

    Layout remains authoritative for entry/body membership. This adapter only
    supplies the common Y refiner with each entry row's coarse Y and column ROI.
    """
    try:
        from . import dictionary_page_design as page_design

        layout = understanding.layout
        settings = understanding.page_settings
        _source, canonical, _transform, effective = page_design._analysis_page(
            image,
            settings,
            int(page_index),
        )
        gray = np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8)
    except Exception:
        return {}

    line_height = max(
        2,
        int(round(float(
            getattr(layout, "ordinary_line_height", 0.0)
            or getattr(effective, "character_height", 0)
            or 2
        ))),
    )
    height, width = gray.shape[:2]
    result: dict[int, int] = {}

    for column in list(getattr(layout, "columns", []) or []):
        left = max(0, min(width - 1, int(getattr(column, "left", 0) or 0)))
        right = max(left + 1, min(width, int(getattr(column, "right", width) or width)))
        if right - left < 4:
            continue
        band = gray[:, left:right]
        for line in list(getattr(column, "lines", []) or []):
            if str(getattr(line, "role", "") or "") != "entry":
                continue
            coarse = int(getattr(layout, "body_top", 0) or 0) + int(
                getattr(line, "y0", 0) or 0
            )
            coarse = max(0, min(height - 1, coarse))
            try:
                refined, _details = refine_separator_y(
                    band,
                    coarse,
                    line_height,
                    effective,
                    pixel_scale=1.0,
                )
            except Exception:
                refined = coarse

            # The shared engine already has its own safety controls. Retain an
            # adapter-level guard as well so a Layout entry can never jump to a
            # neighboring row because of an unusual scan artifact.
            max_move = max(3, int(round(line_height * 0.45)))
            refined = max(coarse - max_move, min(coarse + max_move, int(refined)))
            result[id(line)] = max(0, min(height - 1, int(refined)))

    return result


__all__ = ["refine_separator_y", "refined_layout_entry_y_by_line"]
