"""Editing tests for vertices added to saved automatic PPP rectangles."""
from types import SimpleNamespace

from picture_capture.illustration_polygon_edit import nearest_polygon_segment


def test_rectangle_top_edge_inserts_between_original_corners():
    shape = SimpleNamespace(points=[(10, 10), (110, 10), (110, 80), (10, 80)])
    assert nearest_polygon_segment([shape], 56, 13) == (0, 1, (56, 10))
    region, index, point = nearest_polygon_segment([shape], 56, 13)
    shape.points.insert(index, point)
    assert len(shape.points) == 5
    assert shape.points[1] == (56, 10)


def test_polygon_closing_edge_and_diagonal_are_supported():
    triangle = SimpleNamespace(points=[(10, 10), (110, 10), (110, 110)])
    assert nearest_polygon_segment([triangle], 60, 60) == (0, 3, (60, 60))
    assert nearest_polygon_segment([triangle], 110, 55) == (0, 2, (110, 55))


def test_corner_click_does_not_create_duplicate_vertex():
    rectangle = SimpleNamespace(points=[(10, 10), (110, 10), (110, 80), (10, 80)])
    assert nearest_polygon_segment([rectangle], 10, 10) is None


def test_other_polygons_outside_hit_radius_untouched():
    shapes = [
        SimpleNamespace(points=[(0, 0), (30, 0), (30, 30), (0, 30)]),
        SimpleNamespace(points=[(100, 100), (200, 100), (200, 200), (100, 200)]),
    ]
    assert nearest_polygon_segment(shapes, 150, 102, radius_screen=6) == (1, 1, (150, 100))
    assert nearest_polygon_segment(shapes, 60, 60, radius_screen=6) is None
