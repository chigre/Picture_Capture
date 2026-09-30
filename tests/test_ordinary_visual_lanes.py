from __future__ import annotations

from PIL import Image, ImageDraw

from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_visual import recover_ordinary_visual_entries
from picture_capture.processing import derive_nominal_geometry


def _cjk_settings(**overrides) -> AppSettings:
    values = dict(
        columns=1,
        manual_x=20,
        column_width=360,
        gutter=0,
        start_y=0,
        character_height=24,
        row_padding=1,
        follow_column_deformation=False,
        layout_transform="identity",
        ocr_language="chi_sim",
        paddle_language="ch",
        dictionary_profile_id="cjk_visual",
        profile_cjk_allow_single_headword=True,
        profile_cjk_allow_bracketed_headword=True,
    )
    values.update(overrides)
    return AppSettings(**values)


def _draw_body_line(draw: ImageDraw.ImageDraw, y: int) -> None:
    for x in range(20, 300, 26):
        draw.rectangle((x, y, x + 13, y + 17), fill="black")


def _draw_bracket_entry(
    draw: ImageDraw.ImageDraw,
    y: int,
    *,
    number_prefix: bool = False,
) -> None:
    bracket_x = 75
    if number_prefix:
        draw.rectangle((64, y + 2, 69, y + 9), fill="black")
    draw.line((bracket_x + 8, y, bracket_x + 2, y), fill="black", width=3)
    draw.line((bracket_x + 2, y, bracket_x + 2, y + 18), fill="black", width=3)
    draw.line((bracket_x + 2, y + 18, bracket_x + 8, y + 18), fill="black", width=3)
    for x in (90, 116, 142, 168):
        draw.rectangle((x, y + 1, x + 14, y + 17), fill="black")


def test_visual_lane_recovers_repeated_indented_entries_without_ocr():
    image = Image.new("RGB", (420, 620), "white")
    draw = ImageDraw.Draw(image)
    for y in (35, 70, 105, 140, 205, 240, 305, 340, 405, 440, 505, 540):
        _draw_body_line(draw, y)
    for y in (170, 270, 370, 470):
        _draw_bracket_entry(draw, y)

    settings = _cjk_settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = recover_ordinary_visual_entries(
        image, [], geometry, settings,
    )

    lane_entries = [
        entry for entry in entries
        if entry.ocr_source == "ordinary_visual_lane"
    ]
    assert len(lane_entries) == 4
    assert all(
        "ORDINARY_INDENTED_ENTRY_LANE" in entry.issue_type
        for entry in lane_entries
    )
    assert [entry.y for entry in lane_entries] == sorted(entry.y for entry in lane_entries)


def test_visual_lane_accepts_numbered_variant_only_after_lane_is_proven():
    image = Image.new("RGB", (420, 620), "white")
    draw = ImageDraw.Draw(image)
    for y in (35, 70, 105, 140, 205, 240, 305, 340, 405, 440, 505, 540):
        _draw_body_line(draw, y)
    _draw_bracket_entry(draw, 170, number_prefix=True)
    for y in (270, 370, 470):
        _draw_bracket_entry(draw, y)

    settings = _cjk_settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = recover_ordinary_visual_entries(
        image, [], geometry, settings,
    )
    lane_entries = [
        entry for entry in entries
        if entry.ocr_source == "ordinary_visual_lane"
    ]
    assert len(lane_entries) == 4


def test_visual_lane_requires_repeated_structural_support():
    image = Image.new("RGB", (420, 420), "white")
    draw = ImageDraw.Draw(image)
    for y in (35, 70, 105, 140, 205, 240, 305, 340):
        _draw_body_line(draw, y)
    _draw_bracket_entry(draw, 170)
    _draw_bracket_entry(draw, 270)

    settings = _cjk_settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = recover_ordinary_visual_entries(
        image, [], geometry, settings,
    )
    assert not any(
        entry.ocr_source == "ordinary_visual_lane"
        for entry in entries
    )


def test_visual_lane_does_not_duplicate_existing_marker():
    image = Image.new("RGB", (420, 620), "white")
    draw = ImageDraw.Draw(image)
    for y in (35, 70, 105, 140, 205, 240, 305, 340, 405, 440, 505, 540):
        _draw_body_line(draw, y)
    for y in (170, 270, 370, 470):
        _draw_bracket_entry(draw, y)

    settings = _cjk_settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    baseline = recover_ordinary_visual_entries(
        image, [], geometry, settings,
    )
    first = min(
        (entry for entry in baseline if entry.ocr_source == "ordinary_visual_lane"),
        key=lambda entry: entry.y,
    )
    existing = [Entry(word="", x=20, y=first.y)]
    entries = recover_ordinary_visual_entries(
        image, existing, geometry, settings,
    )
    assert len([
        entry for entry in entries
        if abs(entry.y - first.y) <= 8
    ]) == 1


def test_oversized_component_recovers_display_headword_without_ocr():
    image = Image.new("RGB", (420, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 70, 68, 118), fill="black")
    draw.rectangle((31, 81, 56, 105), fill="white")
    for y in (160, 200, 240, 280, 320):
        _draw_body_line(draw, y)

    settings = _cjk_settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = recover_ordinary_visual_entries(
        image, [], geometry, settings,
    )
    display = [
        entry for entry in entries
        if entry.ocr_source == "ordinary_visual_head"
    ]
    assert len(display) == 1
    assert 35 <= display[0].y <= 60
    assert display[0].ocr_oversized_cjk is True
    assert "ORDINARY_OVERSIZED_HEAD_COMPONENT" in display[0].issue_type


def test_normal_body_rows_do_not_become_oversized_heads():
    image = Image.new("RGB", (420, 360), "white")
    draw = ImageDraw.Draw(image)
    for y in (40, 80, 120, 160, 200, 240, 280):
        _draw_body_line(draw, y)

    settings = _cjk_settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = recover_ordinary_visual_entries(
        image, [], geometry, settings,
    )
    assert not any(
        entry.ocr_source == "ordinary_visual_head"
        for entry in entries
    )


def test_visual_recovery_respects_profile_switches():
    image = Image.new("RGB", (420, 620), "white")
    draw = ImageDraw.Draw(image)
    for y in (35, 70, 105, 140, 205, 240, 305, 340, 405, 440, 505, 540):
        _draw_body_line(draw, y)
    for y in (170, 270, 370, 470):
        _draw_bracket_entry(draw, y)
    draw.rectangle((20, 560, 68, 608), fill="black")

    settings = _cjk_settings(
        profile_cjk_allow_single_headword=False,
        profile_cjk_allow_bracketed_headword=False,
    )
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = recover_ordinary_visual_entries(
        image, [], geometry, settings,
    )
    assert entries == []
