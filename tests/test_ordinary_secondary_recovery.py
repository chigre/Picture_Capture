from __future__ import annotations

from PIL import Image, ImageDraw

from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_secondary_recovery import recover_proven_secondary_lane_variants
from picture_capture.processing import derive_nominal_geometry


def _settings() -> AppSettings:
    return AppSettings(
        columns=1,
        manual_x=0,
        column_width=320,
        gutter=0,
        start_y=10,
        bottom_y=330,
        crop_to_bottom_y=True,
        character_height=20,
        row_padding=0,
        follow_column_deformation=False,
        dictionary_profile_id="cjk_visual",
        ocr_language="chi_tra",
        paddle_language="chinese_cht",
        profile_cjk_allow_bracketed_headword=True,
        profile_cjk_allow_single_headword=True,
    )


def _draw_body_lane(draw: ImageDraw.ImageDraw) -> None:
    # Keep ordinary body rows separate from the indented entry rows so the
    # first-ink lane learned by the visual detector is unambiguous.
    for y in (40, 58, 98, 116, 136, 174, 192, 212, 250, 306):
        draw.rectangle((4, y, 250, y + 10), fill="black")


def _proven_entries(geometry) -> list[Entry]:
    x = int(geometry.column_starts[0])
    return [
        Entry(word="", x=x, y=77, confidence=0.96, ocr_source="ordinary_visual_lane"),
        Entry(word="", x=x, y=153, confidence=0.96, ocr_source="ordinary_visual_lane"),
        Entry(word="", x=x, y=229, confidence=0.96, ocr_source="ordinary_visual_lane"),
    ]


def test_proven_lane_recovers_numbered_variant_shifted_right():
    image = Image.new("RGB", (340, 340), "white")
    draw = ImageDraw.Draw(image)
    _draw_body_lane(draw)

    # Three already-proven bracketed entries start around x=42.
    for y in (78, 154, 230):
        draw.rectangle((42, y, 50, y + 10), fill="black")
        draw.rectangle((56, y, 160, y + 9), fill="black")
    # A numbered/superscript variant shifts the first visible ink to the right.
    draw.rectangle((60, 268, 68, 278), fill="black")
    draw.rectangle((74, 268, 170, 277), fill="black")

    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = _proven_entries(geometry)

    result = recover_proven_secondary_lane_variants(
        image, entries, geometry, settings,
    )

    variants = [
        entry for entry in result
        if "ORDINARY_PROVEN_INDENT_VARIANT" in str(entry.issue_type or "")
    ]
    assert len(variants) == 1
    assert 265 <= variants[0].y <= 267


def test_left_shifted_wrapped_definition_rows_are_not_recovered():
    image = Image.new("RGB", (340, 340), "white")
    draw = ImageDraw.Draw(image)
    _draw_body_lane(draw)

    for y in (78, 154, 230):
        draw.rectangle((42, y, 50, y + 10), fill="black")
        draw.rectangle((56, y, 160, y + 9), fill="black")

    # Dense CJK definitions/quotes can begin left of the bracketed-headword lane
    # and still have clean whitespace above every text line. These were the rows
    # that produced the repeated false boundaries seen in the real dictionary.
    for y in (268, 286):
        draw.rectangle((20, y, 245, y + 10), fill="black")

    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = _proven_entries(geometry)

    result = recover_proven_secondary_lane_variants(
        image, entries, geometry, settings,
    )

    variants = [
        entry for entry in result
        if "ORDINARY_PROVEN_INDENT_VARIANT" in str(entry.issue_type or "")
    ]
    assert variants == []


def test_unproven_page_does_not_recover_arbitrary_indentation():
    image = Image.new("RGB", (340, 260), "white")
    draw = ImageDraw.Draw(image)
    for y in (40, 78, 116, 154, 192):
        draw.rectangle((4, y, 250, y + 10), fill="black")
    draw.rectangle((60, 154, 170, 164), fill="black")

    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    x = int(geometry.column_starts[0])
    entries = [
        Entry(word="", x=x, y=77, confidence=0.96, ocr_source="ordinary_visual_lane"),
        Entry(word="", x=x, y=115, confidence=0.96, ocr_source="ordinary_visual_lane"),
    ]

    result = recover_proven_secondary_lane_variants(
        image, entries, geometry, settings,
    )

    assert len(result) == len(entries)
