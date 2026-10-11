"""Layout regression checks for the specified 280px display menu."""
from pathlib import Path

from picture_capture.ui import workspace_tools
from picture_capture.ui.compact_display_menu import (
    SWATCH_HEIGHT, SWATCH_VERTICAL_PADDING_FRACTION,
)

BASE = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
DISPLAY = BASE / "ui" / "compact_display_menu.py"


def test_pinned_by_default_and_wheel_over_form_controls():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert "TOOL_MENU_WIDTH = 280" in source
    assert "app.workspace_tools_pinned = True" in source
    assert "pin_var = tk.BooleanVar(value=True)" in source
    assert 'header, text="固定", variable=pin_var' in source
    assert 'canvas.yview_scroll(steps, "units")' in source
    assert "def bind_popup_wheel(widget: tk.Misc)" in source
    assert 'widget.bind("<MouseWheel>", scroll_menu_wheel, add="+")' in source
    assert "bind_popup_wheel(popup)" in source
    assert "app.workspace_tools_header = header" in source
    assert "section.winfo_reqheight()" in source
    assert "height = min(available_height, max(115, requested + header_height + 28))" in source
    assert "position_workspace_popup(app)" in source


def test_color_strip_is_vertically_inset_by_quarter_height():
    source = DISPLAY.read_text(encoding="utf-8")
    assert SWATCH_HEIGHT == 24
    assert SWATCH_VERTICAL_PADDING_FRACTION == 0.25
    assert "rely=SWATCH_VERTICAL_PADDING_FRACTION" in source
    assert "relheight=1 - 2 * SWATCH_VERTICAL_PADDING_FRACTION" in source


def test_display_numeric_entries_gain_one_character_without_reflow():
    source = DISPLAY.read_text(encoding="utf-8")
    # The original one-row composition and all declared sizes remain intact;
    # only the shared Entry renderer gets one extra visible character.
    assert 'row, textvariable=qv[name], width=chars + 1, justify="center",' in source
    assert 'def primary_check(' not in source
    assert 'def detail_line(' not in source
    assert 'row.pack(fill="x", pady=0)' in source


def test_each_compact_display_option_is_in_one_explicit_row():
    source = DISPLAY.read_text(encoding="utf-8")
    assert "def number_line(" not in source
    for caption, parts in (
        ("显示区块", ('swatch(row, "page_section_color")',
                    'value(row, "宽:", "page_section_width", 2)')),
        ("栏左垂线", ('swatch(row, "guide_color")',
                     'value(row, "宽:", "guide_width", 2)',
                     'value(row, "透%:", "guide_opacity", 3)')),
        ("词头横线", ('swatch(row, "headword_marker_color")',
                     'value(row, "宽:", "marker_height", 2)',
                     'value(row, "透%:", "headword_marker_opacity", 3)')),
        ("插图形状:线", ('swatch(row, "illustration_outline_color")',
                      'value(row, "宽:", "illustration_outline_width", 2)',
                      'swatch(row, "illustration_fill_color")',
                      'value(row, "透%:", "illustration_fill_opacity", 3)')),
        ("插图标签:线", ('swatch(row, "illustration_label_border_color")',
                      'value(row, "宽:", "illustration_label_border_width", 2)',
                      'swatch(row, "illustration_label_fill_color")')),
        ("词头标签", ('swatch(row, "main_entry_default_color")',
                    'check(row, "缩放", qb["main_entry_follow_zoom"])')),
        ("显示Layout", ('label(row, "去噪强度")',)),
    ):
        block = source.split('"' + caption + '"', 1)[1].split("    row = line()", 1)[0]
        for part in parts:
            assert part in block, (caption, part)


def test_display_font_rows_match_two_line_order():
    source = DISPLAY.read_text(encoding="utf-8")
    assert 'family_line("illustration_label_font_family")' in source
    assert 'font_style(line(), "illustration_label_font_size"' in source
    assert 'family_line("main_entry_font_family")' in source
    assert 'font_style(line(), "main_entry_font_size"' in source
    assert 'label(row, "切图预览标签:")' in source
    assert 'check(row, "缩放", qb["crop_preview_follow_zoom"])' in source
    assert 'family_line("crop_preview_font_family")' in source
    assert 'label(row, "字号")' not in source



def test_requested_numeric_defaults_apply_only_to_new_projects():
    from picture_capture.models import AppSettings

    settings = AppSettings()
    assert settings.batch_interval == 3.0
    assert settings.page_section_width == 2
    assert settings.guide_width == 2
    assert settings.guide_opacity == 60.0
    assert settings.marker_height == 5
    assert settings.headword_marker_opacity == 60.0
    assert settings.illustration_outline_width == 2
    assert settings.illustration_fill_opacity == 60.0
    assert settings.illustration_label_border_width == 2
    assert settings.illustration_label_font_size == 16
    assert settings.main_entry_font_size == 16
    assert settings.main_entry_width_chars == 18
    assert settings.main_entry_x_ratio == 0.66
    assert settings.right_ratio == 100
    assert settings.crop_preview_font_size == 16
