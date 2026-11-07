"""Implementation owner for historical detect_illustrations_to_ppp workflow.

Core supplies current collaborators per call and preserves public signatures.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from pathlib import Path
    from ..models import AppSettings, PolygonRegion


def detect_illustrations_to_ppp_impl(
    image_path: Path, settings: AppSettings, *, profile_page_index: int = 0,
    detected_regions: list[PolygonRegion] | None = None,
    deps: dict[str, Any],
) -> dict[str, int]:
    """Detect illustrations and safely update one page's PPP file.

    Manual polygons are never overwritten.  Re-running detection replaces only
    previous AUTO polygons, making the operation idempotent and safe to tune.
    """
    Path = deps["Path"]
    ppp_read_path_for_image = deps["ppp_read_path_for_image"]
    ppp_write_path_for_image = deps["ppp_write_path_for_image"]
    read_ppp = deps["read_ppp"]
    is_auto_illustration_region = deps["is_auto_illustration_region"]
    detect_illustration_regions = deps["detect_illustration_regions"]
    _polygon_bbox = deps["_polygon_bbox"]
    _overlap_fraction = deps["_overlap_fraction"]
    image_path = Path(image_path)
    read_path = ppp_read_path_for_image(image_path)
    write_path = ppp_write_path_for_image(image_path)
    existing = read_ppp(read_path)
    manual = [r for r in existing if not is_auto_illustration_region(r)]
    detected = (
        list(detected_regions) if detected_regions is not None else
        detect_illustration_regions(
            image_path, settings, profile_page_index=profile_page_index,
        )
    )
    manual_boxes = [b for r in manual if (b := _polygon_bbox(r)) is not None]
    accepted: list[PolygonRegion] = []
    for region in detected:
        box = _polygon_bbox(region)
        if box is None:
            continue
        if any(_overlap_fraction(box, mb) >= 0.25 for mb in manual_boxes):
            continue
        accepted.append(region)
    from .labels import write_ordered_auto_ppp
    write_ordered_auto_ppp(write_path, manual, accepted, image_path, settings, profile_page_index)
    return {"manual": len(manual), "auto": len(accepted), "total": len(manual) + len(accepted)}
