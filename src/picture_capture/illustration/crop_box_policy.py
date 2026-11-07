"""Implementation owner for historical illustration_polygon_box workflow.

Core supplies current collaborators per call and preserves public signatures.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import Image
    from ..models import PolygonRegion


def illustration_polygon_box_impl(
    image: Image.Image,
    region: PolygonRegion,
    *,
    top: int = 0,
    bottom: int | None = None,
    margin_px: int = 0,
    deps: dict[str, Any],
) -> tuple[int, int, int, int] | None:
    """Return the effective illustration crop box after page-boundary clipping."""
    clamp_box = deps["clamp_box"]
    if len(region.points) < 3:
        return None
    bottom = image.height if bottom is None else max(1, min(image.height, int(bottom)))
    xs = [point[0] for point in region.points]
    ys = [point[1] for point in region.points]
    raw = (
        min(xs) - margin_px,
        min(ys) - margin_px,
        max(xs) + 1 + margin_px,
        max(ys) + 1 + margin_px,
    )
    box = clamp_box(raw, image)
    clipped = (box[0], max(box[1], int(top)), box[2], min(box[3], int(bottom)))
    if clipped[2] - clipped[0] <= 1 or clipped[3] - clipped[1] <= 1:
        return None
    return clipped
