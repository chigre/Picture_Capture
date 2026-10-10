"""Insert editable vertices on any edge of a saved PPP polygon."""
from __future__ import annotations

from collections.abc import Sequence


def nearest_polygon_segment(
    polygons: Sequence[object], x: float, y: float, *,
    view_scale: float = 1.0, radius_screen: float = 10.0,
) -> tuple[int, int, tuple[int, int]] | None:
    """Return (region index, following vertex index, projected source point).

    The closing edge between the final and first points is supported.
    Points close to existing vertices are left to the vertex-drag handler.
    """
    tolerance2 = (radius_screen / max(float(view_scale), 1e-6)) ** 2
    best = None
    for region_index, region in enumerate(polygons):
        points = region.points
        if len(points) < 3:
            continue
        for i, (ax, ay) in enumerate(points):
            bx, by = points[(i + 1) % len(points)]
            dx, dy = bx - ax, by - ay
            length2 = dx * dx + dy * dy
            if not length2:
                continue
            fraction = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2))
            # Prevent inserting duplicate points at/very near corners.
            if fraction < .05 or fraction > .95:
                continue
            px, py = ax + fraction * dx, ay + fraction * dy
            d2 = (x - px) ** 2 + (y - py) ** 2
            if d2 <= tolerance2:
                tolerance2 = d2
                best = (region_index, i + 1, (round(px), round(py)))
    return best
