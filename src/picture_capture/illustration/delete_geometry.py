"""Choose a visible center inside a PPP illustration polygon."""
from __future__ import annotations


def _inside(x: float, y: float, pts) -> bool:
    odd = False
    for a, b in zip(pts, pts[1:] + pts[:1]):
        x1, y1 = a
        x2, y2 = b
        if (y1 > y) != (y2 > y):
            cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < cross:
                odd = not odd
    return odd


def interior_polygon_center(points) -> tuple[float, float]:
    """Area centroid when inside; otherwise choose an interior central point."""
    pts = [(float(x), float(y)) for x, y in points]
    if not pts:
        return 0., 0.
    if len(pts) < 3:
        return (sum(x for x, _ in pts) / len(pts),
                sum(y for _, y in pts) / len(pts))
    area2 = cx = cy = 0.
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        cross = x1 * y2 - x2 * y1
        area2 += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(area2) > 1e-9:
        center = (cx / (3 * area2), cy / (3 * area2))
        if _inside(*center, pts):
            return center
    # Concave polygons can have a centroid outside; sample near geometric
    # center and choose an interior point with good clearance from edges.
    min_x, max_x = min(x for x, _ in pts), max(x for x, _ in pts)
    min_y, max_y = min(y for _, y in pts), max(y for _, y in pts)
    mid = ((min_x + max_x) / 2, (min_y + max_y) / 2)
    best = None
    for iy in range(1, 22):
        y = min_y + (max_y - min_y) * iy / 22
        for ix in range(1, 22):
            x = min_x + (max_x - min_x) * ix / 22
            if not _inside(x, y, pts):
                continue
            score = -((x - mid[0]) ** 2 + (y - mid[1]) ** 2)
            if best is None or score > best[0]:
                best = (score, x, y)
    return (best[1], best[2]) if best else pts[0]
