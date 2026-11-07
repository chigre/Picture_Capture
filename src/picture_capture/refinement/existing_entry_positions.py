"""Source-coordinate marker Y refinement with optional verified ink-top tracking.

Core implementation is delegated here, with live historical collaborators
injected at invocation and with persisted classes remaining in their owners.
"""
from __future__ import annotations
from PIL import Image
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import Entry, AppSettings
    from ..processing_core import Geometry


def refine_existing_entries_with_geometry_impl(
    entries: list[Entry],
    effective: AppSettings,
    analysis_source: Image.Image,
    geometry: Geometry,
    *,
    align_to_ink_top: bool = False,
    fixed_half_gutter: bool = False,
    deps: dict[str, Any],
) -> tuple[list[Entry], dict[str, int]]:
    """Refine Y without reclassifying Layout rows."""
    _source_px = deps["_source_px"]
    column_index = deps["column_index"]
    replace = deps["replace"]
    np = deps["np"]
    ImageOps = deps["ImageOps"]
    canonical = geometry.transform.canonical_image_for_analysis(analysis_source)
    gray = np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8)

    if align_to_ink_top:
        from .top_edge import refine_existing_marker_to_ink_top
    else:
        from ..paddle_headwords import refine_separator_y

    line_height = max(
        2,
        _source_px(effective.character_height),
    )
    source_pixel_scale = 1.0
    search_ratio = max(0.05, min(0.80, float(effective.paddle_separator_search_ratio)))
    max_delta = (
        max(0, round(line_height * max(0.0, min(1.5, float(effective.separator_y_max_shift_ratio)))))
        if align_to_ink_top
        else max(2, round(line_height * search_ratio))
    )

    refined_entries: list[Entry] = []
    moved = 0
    limited = 0
    unverified = 0
    for entry in entries:
        canonical_u, canonical_v = geometry.source_to_canonical(entry.x, entry.y)
        col = column_index(entry.x, geometry, entry.y)
        column_x = max(0, round(geometry.x_at(col, canonical_v)))
        column_right = min(
            gray.shape[1],
            column_x + max(10, min(int(geometry.column_widths[col]), int(effective.column_width))),
        )
        if align_to_ink_top:
            from .fixed_band import fixed_half_gutter_band
            column_x, column_right = fixed_half_gutter_band(
                geometry, col, int(canonical_v), gray.shape[1],
                int(effective.column_width), int(effective.gutter),
            )
        new_v = int(canonical_v)
        if column_right > column_x:
            if align_to_ink_top:
                candidate_v, _details = refine_existing_marker_to_ink_top(
                    gray, int(canonical_v), line_height, effective,
                    anchor_x=int(canonical_u),
                    column_left=column_x, column_right=column_right,
                    lower_bound=max(0, int(geometry.top)),
                    upper_bound=int(geometry.bottom),
                )
                if not str(_details.get("reason", "")).startswith("verified_whole_column_"):
                    unverified += 1
            else:
                candidate_v, _details = refine_separator_y(
                    gray[:, column_x:column_right],
                    int(canonical_v),
                    line_height,
                    effective,
                    pixel_scale=source_pixel_scale,
                    lower_bound=max(0, int(geometry.top)),
                )
            delta = int(candidate_v) - int(canonical_v)
            if abs(delta) > max_delta:
                limited += 1
                delta = max(-max_delta, min(max_delta, delta))
            new_v = int(canonical_v) + delta

        if new_v != int(canonical_v):
            moved += 1
        new_x, new_y = geometry.canonical_to_source(int(canonical_u), int(new_v))
        refined_entries.append(replace(entry, x=int(new_x), y=int(new_y)))

    return refined_entries, {
        "total": len(entries),
        "moved": moved,
        "limited": limited,
        "max_delta": int(max_delta),
        "unverified": unverified,
    }
