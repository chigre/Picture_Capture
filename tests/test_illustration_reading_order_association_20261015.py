"""Reading-order illustration IDs and associated PDIC ordinal: synthetic pages."""
from __future__ import annotations

from picture_capture.illustration_labels import (
    illustration_labels, label_text, user_edited_link,
)
from picture_capture.models import Entry, PolygonRegion
from picture_capture.page_sections import PageSection
from picture_capture.processing_core import Geometry


def geo():
    return Geometry(
        column_starts=[0, 110], column_widths=[100, 100],
        top=0, bottom=800, column_paths=[],
    )


def fig(x1: int, y1: int, x2: int, y2: int, label: str = ""):
    return PolygonRegion(label, [(x1, y1), (x2, y1), (x2, y2), (x1, y2)])


def test_manual_and_auto_numbering_uses_section_column_y_not_insertion():
    shapes = [
        fig(115, 170, 180, 200, "080101|AUTO_03|1|080101|"),
        fig(20, 520, 90, 590, "手工旧名"),
        fig(5, 280, 90, 330, ""),
        fig(5, 90, 90, 110, "080101|AUTO_01|1|080101|"),
    ]
    labels = illustration_labels(
        shapes, "080101", geo(), [PageSection(0, 400), PageSection(400, 800)],
    )
    assert labels[3] == "P_01|080101|xxx|AUTO_01"
    assert labels[2] == "P_02|080101|xxx"
    assert labels[0] == "P_03|080101|xxx|AUTO_03"
    assert labels[1] == "P_04|080101|xxx"
    assert label_text(labels[0]) == "P_03|080101|xxx"
    assert all(shape.label == old for shape, old in zip(
        shapes, ["080101|AUTO_03|1|080101|", "手工旧名", "",
                 "080101|AUTO_01|1|080101|"],
    ))


def test_add_and_delete_renumbers_every_survivor_without_mutating_user_shapes():
    a, b, c = (
        fig(5, 100, 80, 140), fig(5, 220, 80, 270),
        fig(115, 120, 180, 170),
    )
    originals = [b, c, a]
    before = illustration_labels(originals, "page", geo())
    assert before == [
        "P_02|page|xxx", "P_03|page|xxx", "P_01|page|xxx",
    ]
    added = fig(5, 180, 80, 200)
    with_addition = illustration_labels(originals + [added], "page", geo())
    assert with_addition == [
        "P_03|page|xxx", "P_04|page|xxx",
        "P_01|page|xxx", "P_02|page|xxx",
    ]
    after_delete = illustration_labels([c, a, added], "page", geo())
    assert after_delete == [
        "P_03|page|xxx", "P_01|page|xxx", "P_02|page|xxx",
    ]
    assert all(not shape.label for shape in (a, b, c, added))


def test_link_within_column_same_section_to_closest_headword_above():
    entries = [
        Entry("right", 120, 110),
        Entry("left near", 15, 240),
        Entry("section 2", 15, 450),
        Entry("left far", 12, 70),
        Entry("right below", 120, 300),
    ]
    regions = [
        fig(115, 170, 185, 230),
        fig(5, 270, 210, 335),  # Spans both columns => left.
        fig(5, 500, 190, 570),  # New SECTION => left section2.
    ]
    labels = illustration_labels(
        regions, "080999", geo(), [PageSection(0, 400), PageSection(400, 800)],
        entries=entries, associate=True,
    )
    # Canonical PDIC indices begin at zero on EVERY page:
    # left far=0, left near=1, right=2, right below=3, section2 left=4.
    assert labels == [
        "P_02|080999|002",
        "P_01|080999|001",
        "P_03|080999|004",
    ]


def test_no_entry_above_same_lane_never_fabricates_index():
    regions = [fig(5, 60, 70, 120)]
    entries = [Entry("too low", 12, 80), Entry("different column", 110, 10)]
    labels = illustration_labels(regions, "000001", geo(), entries=entries, associate=True)
    assert labels == ["P_01|000001|xxx"]


def test_existing_link_survives_only_reading_reindex_not_auto_legacy_field():
    regions = [
        fig(115, 100, 170, 140, "P_22|page|004|AUTO_04"),
        fig(5, 110, 70, 170, "page|AUTO_07|1|page|"),
    ]
    assert illustration_labels(regions, "page", geo()) == [
        "P_02|page|004|AUTO_04", "P_01|page|xxx|AUTO_07",
    ]


def test_editing_only_changes_link_not_number_page_or_source():
    original = "P_05|080012|xxx|AUTO_02"
    assert user_edited_link(original, "P_88|forged|006") == (
        "P_05|080012|006|AUTO_02"
    )
    import pytest
    with pytest.raises(ValueError):
        user_edited_link(original, "wrong")
    with pytest.raises(ValueError):
        user_edited_link("original fish caption", "P_01|page|006")


def test_background_automatic_detection_persists_reading_order_and_auto_origin(tmp_path):
    from PIL import Image
    from picture_capture.formats import read_ppp, write_ppp
    from picture_capture.illustration_detection import is_auto_illustration_region
    from picture_capture.models import AppSettings
    from picture_capture.processing_core import detect_illustrations_to_ppp
    page = tmp_path / "scan.png"
    Image.new("RGB", (240, 420), "white").save(page)
    manual = fig(5, 220, 70, 270, "custom-manual-region")
    write_ppp(page.with_suffix(".ppp"), [manual], page.stem)
    result = detect_illustrations_to_ppp(
        page,
        AppSettings(columns=2, manual_x=0, column_width=100, gutter=10, start_y=0),
        detected_regions=[
            fig(118, 110, 205, 180), fig(8, 70, 75, 120),
        ],
    )
    assert result == {"manual": 1, "auto": 2, "total": 3}
    saved = read_ppp(page.with_suffix(".ppp"))
    assert len(saved) == 3
    assert [shape.label.split("|")[0] for shape in saved] == ["P_02", "P_03", "P_01"]
    assert [is_auto_illustration_region(region) for region in saved] == [
        False, True, True,
    ]
    # Redetection replaces ONLY the previous AUTO shapes, never manual PPP.
    second = detect_illustrations_to_ppp(
        page,
        AppSettings(columns=2, manual_x=0, column_width=100, gutter=10, start_y=0),
        detected_regions=[fig(115, 330, 210, 385)],
    )
    assert second == {"manual": 1, "auto": 1, "total": 2}
    saved_again = read_ppp(page.with_suffix(".ppp"))
    assert saved_again[0].points == manual.points
    assert not is_auto_illustration_region(saved_again[0])
    assert is_auto_illustration_region(saved_again[1])
    assert [r.label.split("|")[0] for r in saved_again] == ["P_01", "P_02"]


def test_empty_or_malformed_ppp_polygon_does_not_make_redraw_crash():
    from picture_capture.illustration_labels import illustration_labels
    regions = [PolygonRegion("old", []), fig(5, 100, 70, 120)]
    labels = illustration_labels(regions, "page", geo())
    assert labels[1].startswith("P_01|page|")
    assert labels[0].startswith("P_02|page|")
