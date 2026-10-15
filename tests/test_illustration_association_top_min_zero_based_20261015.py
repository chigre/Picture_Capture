"""Topmost polygon vertex, zero-based per-page logical entry IDs.

These cases model the four specific wrong associations seen by the user:
080005 015->013, 080035 001->000, 080063 006->005,
080067 027->023. Original images are not required.
"""
from __future__ import annotations

from picture_capture.illustration_labels import illustration_labels
from picture_capture.models import Entry, PolygonRegion
from picture_capture.page_sections import PageSection
from picture_capture.processing_core import Geometry


def geometry():
    return Geometry(
        column_starts=[0, 200], column_widths=[190, 190],
        top=0, bottom=950, column_paths=[],
    )


def entries_ascending(count: int, start: int = 10, step: int = 12):
    # Insert backwards deliberately. Association must use logical
    # reading order, independent of PDIC insertion/list order.
    return [Entry(f"word{i}", 15, start + i * step) for i in reversed(range(count))]


def label_for(page: str, points, entries):
    labels = illustration_labels(
        [PolygonRegion("", points)], page, geometry(),
        [PageSection(0, 950)], entries=entries, associate=True,
    )
    return labels[0]


def test_080005_irregular_polygon_global_min_y_links_013_not_015():
    entries = entries_ascending(17, start=10, step=12)
    # Highest vertex is at x=230, y=170, but the leftmost vertex is
    # at y=225. Old left-envelope-first lookup chose a later entry.
    points = [(12, 225), (50, 270), (230, 170), (275, 300), (65, 390)]
    assert label_for("080005", points, entries) == "P_01|080005|013"


def test_080035_first_logical_entry_is_000_not_001():
    entries = [Entry("first", 15, 55), Entry("later", 15, 130)]
    polygon = [(20, 90), (180, 90), (180, 350), (20, 350)]
    assert label_for("080035", polygon, entries) == "P_01|080035|000"


def test_080063_nearest_entry_above_top_is_005_not_006():
    entries = entries_ascending(9, start=40, step=12)
    points = [(18, 161), (75, 130), (115, 103), (175, 210), (80, 220)]
    assert label_for("080063", points, entries) == "P_01|080063|005"


def test_080067_irregular_polygons_use_023_not_027():
    entries = entries_ascending(30, start=10, step=10)
    # The leftmost vertex is y=309, but top of the illustrated body
    # is y=248; it must ignore entries 24..29 within the polygon.
    points = [(10, 310), (80, 270), (215, 248), (280, 350), (265, 440)]
    assert label_for("080067", points, entries) == "P_01|080067|023"


def test_cross_column_figure_uses_left_side_not_top_vertex_column():
    entries = [
        Entry("left above", 20, 75),
        Entry("right above", 225, 95),
        Entry("left below", 20, 170),
    ]
    # Left edge of figure is in column 0, global top vertex in column 1.
    figure = [(160, 160), (240, 125), (260, 205), (165, 240)]
    assert label_for("col", figure, entries) == "P_01|col|000"


def test_section_scope_and_missing_above_never_link_next_section_word():
    entries = [
        Entry("in earlier section", 25, 45),
        Entry("later section", 25, 430),
    ]
    figure = PolygonRegion("", [(10, 410), (130, 410), (140, 510), (10, 510)])
    labels = illustration_labels(
        [figure], "split", geometry(),
        [PageSection(0, 400), PageSection(400, 950)],
        entries=entries, associate=True,
    )
    assert labels == ["P_01|split|xxx"]


def test_each_page_restarts_logical_ids_at_zero():
    words = [Entry("entry", 15, 30)]
    polygon = [(15, 60), (170, 60), (170, 220), (15, 220)]
    assert label_for("page_A", polygon, words) == "P_01|page_A|000"
    assert label_for("page_B", polygon, words) == "P_01|page_B|000"
