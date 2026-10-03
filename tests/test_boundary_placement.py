from __future__ import annotations

from PIL import Image, ImageDraw

from picture_capture.boundary_placement import refine_boundaries_toward_head_top
from picture_capture.dictionary_page_design import (
    ColumnDesign,
    DictionaryPageLayout,
    PageRegion,
    PageRegions,
)
from picture_capture.layout_transform import LayoutTransform
from picture_capture.models import AppSettings, Entry


def _settings() -> AppSettings:
    return AppSettings(
        columns=1,
        start_y=10,
        bottom_y=0,
        crop_to_bottom_y=False,
        character_height=20,
        profile_header_mode="none",
        profile_footer_mode="none",
        profile_side_content_mode="none",
    )


def _layout() -> DictionaryPageLayout:
    body = PageRegion(
        "body",
        (0, 10, 360, 210),
        (0, 10, 360, 210),
        "inferred",
    )
    return DictionaryPageLayout(
        transform=LayoutTransform("identity"),
        source_size=(360, 220),
        canonical_size=(360, 220),
        regions=PageRegions(body=body),
        body_top=10,
        body_bottom=210,
        columns=[ColumnDesign(index=0, left=20, right=320, gutter_after=0)],
        ordinary_line_height=20.0,
        ordinary_line_pitch=50.0,
        ordinary_char_width=18.0,
        ordinary_char_height=20.0,
        indent_type="headword",
        reliable=True,
    )


def _page_with_block(y: int) -> Image.Image:
    image = Image.new("RGB", (360, 220), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, y, 285, y + 12), fill="black")
    return image


def test_first_entry_boundary_moves_from_body_top_toward_headword_top():
    image = _page_with_block(40)
    entry = Entry(
        word="",
        x=20,
        y=10,
        confidence=0.97,
        ocr_source="ordinary_page_design",
        issue_type="ORDINARY_PAGE_DESIGN_ENTRY",
    )

    placed = refine_boundaries_toward_head_top(
        image, _settings(), _layout(), [entry]
    )

    assert len(placed) == 1
    assert placed[0].y > 10
    assert 35 <= placed[0].y <= 38
    assert placed[0].y < 40


def test_interior_boundary_prefers_clean_row_near_current_headword_top():
    image = _page_with_block(100)
    # Simulate the old midpoint placement between the preceding line and the
    # current entry.  The new placement should remain in the same whitespace
    # but sit just above the current headword block.
    entry = Entry(
        word="",
        x=20,
        y=75,
        confidence=0.97,
        ocr_source="ordinary_page_design",
        issue_type="ORDINARY_PAGE_DESIGN_ENTRY",
    )

    placed = refine_boundaries_toward_head_top(
        image, _settings(), _layout(), [entry]
    )

    assert 95 <= placed[0].y <= 98
    assert placed[0].y > 75
    assert placed[0].y < 100


def test_non_page_design_marker_is_not_moved():
    image = _page_with_block(100)
    entry = Entry(
        word="",
        x=20,
        y=75,
        confidence=0.9,
        ocr_source="ordinary_vb",
        issue_type="ORDINARY_SEPARATOR",
    )

    placed = refine_boundaries_toward_head_top(
        image, _settings(), _layout(), [entry]
    )

    assert placed[0].x == 20
    assert placed[0].y == 75
