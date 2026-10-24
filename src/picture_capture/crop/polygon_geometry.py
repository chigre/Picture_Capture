from __future__ import annotations

"""Pure crop polygon primitives.

Optional call-time callbacks preserve monkeypatch behavior of the historical
processing/processing_core public modules without sharing mutable globals.
"""

def point_in_rect(point: tuple[int, int], box: tuple[int, int, int, int]) -> bool:
    x, y = point
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def point_in_polygon(point: tuple[int, int], points: list[tuple[int, int]]) -> bool:
    x, y = point
    inside = False
    n = len(points)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = points[i]; xj, yj = points[j]
        if ((yi > y) != (yj > y)):
            denom = (yj - yi) or 1e-12
            cross_x = (xj - xi) * (y - yi) / denom + xi
            if x <= cross_x:
                inside = not inside
        j = i
    return inside


def orientation(a, b, c) -> int:
    v = (b[1]-a[1])*(c[0]-b[0]) - (b[0]-a[0])*(c[1]-b[1])
    if abs(v) < 1e-9: return 0
    return 1 if v > 0 else 2


def on_segment(a, b, c) -> bool:
    return min(a[0], c[0]) <= b[0] <= max(a[0], c[0]) and min(a[1], c[1]) <= b[1] <= max(a[1], c[1])


def segments_intersect(p1, q1, p2, q2, *, orientation_fn=None, on_segment_fn=None) -> bool:
    orientation_at = orientation if orientation_fn is None else orientation_fn
    on_segment_at = on_segment if on_segment_fn is None else on_segment_fn
    o1, o2, o3, o4 = (
        orientation_at(p1,q1,p2), orientation_at(p1,q1,q2),
        orientation_at(p2,q2,p1), orientation_at(p2,q2,q1),
    )
    if o1 != o2 and o3 != o4: return True
    if o1 == 0 and on_segment_at(p1,p2,q1): return True
    if o2 == 0 and on_segment_at(p1,q2,q1): return True
    if o3 == 0 and on_segment_at(p2,p1,q2): return True
    if o4 == 0 and on_segment_at(p2,q1,q2): return True
    return False


def polygon_intersects_box(
    points: list[tuple[int, int]],
    box: tuple[int, int, int, int],
    *,
    point_in_rect_fn=None,
    point_in_polygon_fn=None,
    segments_intersect_fn=None,
) -> bool:
    if len(points) < 3:
        return False
    in_rect = point_in_rect if point_in_rect_fn is None else point_in_rect_fn
    in_polygon = point_in_polygon if point_in_polygon_fn is None else point_in_polygon_fn
    intersect = segments_intersect if segments_intersect_fn is None else segments_intersect_fn
    if any(in_rect(p, box) for p in points):
        return True
    corners = [(box[0],box[1]),(box[2],box[1]),(box[2],box[3]),(box[0],box[3])]
    if any(in_polygon(c, points) for c in corners):
        return True
    rect_edges = list(zip(corners, corners[1:]+corners[:1]))
    poly_edges = list(zip(points, points[1:]+points[:1]))
    return any(intersect(a,b,c,d) for a,b in poly_edges for c,d in rect_edges)


def polygon_fully_inside_boxes(
    points: list[tuple[int, int]],
    boxes: list[tuple[int,int,int,int]],
    *,
    point_in_rect_fn=None,
) -> bool:
    in_rect = point_in_rect if point_in_rect_fn is None else point_in_rect_fn
    return bool(points) and all(any(in_rect(point, box) for box in boxes) for point in points)


def box_intersection_area(a: tuple[int,int,int,int], b: tuple[int,int,int,int]) -> int:
    x0,y0=max(a[0],b[0]),max(a[1],b[1]); x1,y1=min(a[2],b[2]),min(a[3],b[3])
    return max(0,x1-x0)*max(0,y1-y0)


__all__ = [
    "point_in_rect", "point_in_polygon", "orientation", "on_segment",
    "segments_intersect", "polygon_intersects_box",
    "polygon_fully_inside_boxes", "box_intersection_area",
]
