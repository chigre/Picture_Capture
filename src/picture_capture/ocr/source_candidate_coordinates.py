"""Source-image coordinate translation for OCR candidate diagnostics.

The source-only serialization projection remains separately owned by
source_coordinate_persistence; this stage attaches the source coordinates.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..processing_core import Geometry


def attach_source_candidate_coordinates(
    diagnostics: list[dict[str, Any]],
    geometry: "Geometry",
    column: int,
) -> None:
    """Attach original-image X/Y while keeping reading-axis values private."""
    for item in diagnostics:
        if "meta" in item:
            meta = item.get("meta") or {}
            meta["coordinate_space"] = "source_image_pixels"
            if meta.get("_header_cutoff_axis_v") is not None:
                try:
                    axis_v = int(meta["_header_cutoff_axis_v"])
                    axis_u = int(geometry.x_at(column, axis_v))
                    sx, sy = geometry.canonical_to_source(axis_u, axis_v)
                    meta["header_cutoff_source_x"] = int(sx)
                    meta["header_cutoff_source_y"] = int(sy)
                except (TypeError, ValueError):
                    pass
            continue

        # Low-level filtering works on a temporary transformed reading axis.
        # Keep that fact private; every public/cache coordinate is source X/Y.
        try:
            axis_v = int(item.get("_axis_v", item.get("_axis_v", item.get("source_y", 0))))
        except (TypeError, ValueError):
            axis_v = 0
        try:
            coarse_axis_v = int(item.get("_coarse_axis_v", item.get("coarse_canonical_v", item.get("coarse_source_y", axis_v))))
        except (TypeError, ValueError):
            coarse_axis_v = axis_v
        try:
            anchor_axis_v = int(item.get("_anchor_axis_v", item.get("anchor_canonical_v", item.get("anchor_source_y", coarse_axis_v))))
        except (TypeError, ValueError):
            anchor_axis_v = coarse_axis_v

        axis_u = int(geometry.x_at(column, axis_v))
        source_x, source_y = geometry.canonical_to_source(axis_u, axis_v)
        coarse_axis_u = int(geometry.x_at(column, coarse_axis_v))
        coarse_source_x, coarse_source_y = geometry.canonical_to_source(
            coarse_axis_u, coarse_axis_v
        )
        anchor_axis_u = int(geometry.x_at(column, anchor_axis_v))
        anchor_source_x, anchor_source_y = geometry.canonical_to_source(
            anchor_axis_u, anchor_axis_v
        )

        item["_axis_v"] = axis_v
        item["_coarse_axis_v"] = coarse_axis_v
        item["_anchor_axis_v"] = anchor_axis_v
        for key in ("canonical_u", "canonical_v", "coarse_canonical_v", "anchor_canonical_v", "canonical_coordinate_space"):
            item.pop(key, None)
        item["coordinate_space"] = "source_image_pixels"
        item["source_x"] = int(source_x)
        item["source_y"] = int(source_y)
        item["coarse_source_x"] = int(coarse_source_x)
        item["coarse_source_y"] = int(coarse_source_y)
        item["anchor_source_x"] = int(anchor_source_x)
        item["anchor_source_y"] = int(anchor_source_y)

ndef candidate_axis_v(candidate: dict[str, Any] | None) -> int | None:
    if not candidate:
        return None
    value = candidate.get("_axis_v", candidate.get("source_y"))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
