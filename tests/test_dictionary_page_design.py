from __future__ import annotations

from PIL import Image, ImageDraw

from picture_capture.dictionary_page_design import (
    detect_entries_from_page_design,
    infer_dictionary_page_layout,
)
from picture_capture.models import AppSettings
from picture_capture.profile_indent_ui import apply_indent_type_label


def _settings(*, columns: int = 1) -> AppSettings:
    return AppSettings(
        columns=columns,
        layout_columns_policy="fixed",
        layout_column_separator_mode="auto",
        start_y=10,
        bottom_y=0,
        crop_to_bottom_y=False,
        character_height=20,
        dictionary_profile_id="cjk_visual",
        ocr_language="chi_tra",
        paddle_language="chinese_cht",
        detection_method="left_edge",
        profile_header_mode="none",
        profile_footer_mode="none",
        profile_side_content_mode="none",
        profile_cjk_allow_single_headword=True,
        profile_cjk_allow_bracketed_headword=True,
    )


def _draw_line(draw: ImageDraw.ImageDraw, x: int, y: int, width: int = 240, height: int = 11) -> None:
    draw.rectangle((x, y, x + width, y + height), fill="black")


def _single_column_page(*, body_x: int = 20, entry_x: int = 65) -> tuple[Image.Image, list[int], list[int]]:
    image = Image.new("RGB", (360, 520), "white")
    draw = ImageDraw.Draw(image)
    body_rows = [42, 98, 154, 210, 266, 322, 378, 434, 480]
    entry_rows = [70, 182, 294, 406]
    for y in body_rows:
        _draw_line(draw, body_x, y)
    for index, y in enumerate(entry_rows):
        if index % 2:
            # Superscript/number prefix: first ink moves left, but the first
            # full-height structural block remains on the entry indent.
            draw.rectangle((entry_x - 22, y, entry_x - 14, y + 4), fill="black")
        _draw_line(draw, entry_x, y, width=205)
    return image, body_rows, entry_rows


def test_page_design_recovers_body_and_entry_indent_modes_without_ocr():
    image, _body_rows, entry_rows = _single_column_page()
    settings = _settings()

    layout = infer_dictionary_page_layout(image, settings)

    assert layout.reliable
    assert len(layout.columns) == 1
    column = layout.columns[0]
    assert column.body_mode is not None
    assert abs(column.body_mode.center - 0) <= 8 or column.body_mode.support >= 6
    assert column.entry_modes
    assert sum(mode.support for mode in column.entry_modes) >= len(entry_rows) - 1
    assert layout.ordinary_line_height > 6
    assert layout.ordinary_line_pitch > layout.ordinary_line_height

    result = detect_entries_from_page_design(image, settings)
    assert result.layout.reliable
    normal = [entry for entry in result.entries if entry.issue_type == "ORDINARY_PAGE_DESIGN_ENTRY"]
    assert len(normal) >= len(entry_rows) - 1


def test_body_only_continuation_page_is_reliable_zero_not_legacy_fallback():
    image = Image.new("RGB", (360, 420), "white")
    draw = ImageDraw.Draw(image)
    for y in (36, 76, 116, 156, 196, 236, 276, 316, 356):
        _draw_line(draw, 20, y, width=285)

    settings = _settings()
    result = detect_entries_from_page_design(image, settings)

    assert result.layout.reliable
    assert result.layout.columns[0].body_mode is not None
    assert result.layout.columns[0].entry_modes == []
    assert result.entries == []


def test_body_indent_reverses_semantic_roles_not_geometry():
    image, _body_rows, entry_rows = _single_column_page(body_x=70, entry_x=20)
    settings = _settings()
    apply_indent_type_label(settings, "正文缩进")

    layout = infer_dictionary_page_layout(image, settings)

    assert layout.reliable
    assert layout.indent_type == "body"
    column = layout.columns[0]
    assert column.body_mode is not None
    assert column.entry_modes
    assert column.body_mode.center > max(mode.center for mode in column.entry_modes)

    result = detect_entries_from_page_design(image, settings)
    normal = [entry for entry in result.entries if entry.issue_type == "ORDINARY_PAGE_DESIGN_ENTRY"]
    assert len(normal) >= len(entry_rows) - 1


def test_display_size_head_is_typographic_level_not_normal_line_candidate():
    image = Image.new("RGB", (360, 460), "white")
    draw = ImageDraw.Draw(image)
    for y in (80, 122, 164, 206, 248, 330, 372, 414):
        _draw_line(draw, 20, y, width=285)
    # One display-size head at the semantic entry side, with enough whitespace
    # around it that it is a separate visual block.
    draw.rectangle((68, 270, 103, 316), fill="black")

    settings = _settings()
    result = detect_entries_from_page_design(image, settings)

    assert result.layout.reliable
    assert result.layout.has_display_heads
    heads = [entry for entry in result.entries if entry.issue_type == "ORDINARY_PAGE_DESIGN_DISPLAY_HEAD"]
    assert heads
    assert all(entry.ocr_oversized_cjk for entry in heads)


def test_vertical_rule_inside_gutter_does_not_become_column_edge():
    image = Image.new("RGB", (820, 520), "white")
    draw = ImageDraw.Draw(image)
    left_start, right_start = 35, 445
    for y in (42, 84, 126, 168, 210, 252, 294, 336, 378, 420, 462):
        _draw_line(draw, left_start, y, width=300)
        _draw_line(draw, right_start, y, width=300)
    # Decorative divider intentionally sits inside the inter-column whitespace.
    draw.rectangle((397, 18, 400, 500), fill="black")

    settings = _settings(columns=2)
    layout = infer_dictionary_page_layout(image, settings)

    assert len(layout.columns) == 2
    first, second = layout.columns
    assert second.left - first.left > 300
    assert first.gutter_after > 10
    # The rule at x≈398 is not allowed to become the second text-column start.
    assert second.left > 420
