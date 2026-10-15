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


def test_display_numeric_entries_gain_two_characters_without_reflow():
    source = DISPLAY.read_text(encoding="utf-8")
    # The original one-row composition and all declared sizes remain intact;
    # only the shared Entry renderer gains two characters from original.
    assert 'row, textvariable=qv[name], width=chars + 2, justify="center",' in source
    assert 'def primary_check(' not in source
    assert 'def detail_line(' not in source
    assert 'row.pack(fill="x", pady=0)' in source


def test_each_compact_display_option_is_in_one_explicit_row():
    source = DISPLAY.read_text(encoding="utf-8")
    assert "def number_line(" not in source
    for caption, parts in (
        ("显示区块", ('swatch(row, "page_section_color")',
                    'value(row, "宽", "page_section_width", 2)')),
        ("栏左垂线", ('swatch(row, "guide_color")',
                     'value(row, "宽", "guide_width", 2)',
                     'value(row, "透%:", "guide_opacity", 3)')),
        ("词头横线", ('swatch(row, "headword_marker_color")',
                     'value(row, "宽", "marker_height", 2)',
                     'value(row, "透%:", "headword_marker_opacity", 3)')),
        ("插图形状:线", ('swatch(row, "illustration_outline_color")',
                      'value(row, "宽", "illustration_outline_width", 2)',
                      'swatch(row, "illustration_fill_color")',
                      'value(row, "透%:", "illustration_fill_opacity", 3)')),
        ("插图标签:线", ('swatch(row, "illustration_label_border_color")',
                      'value(row, "宽", "illustration_label_border_width", 2)',
                      'swatch(row, "illustration_label_fill_color")')),
        ("词头标签", ('swatch(row, "main_entry_default_color")',
                    'check(row, "缩放", qb["main_entry_follow_zoom"])')),
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


def test_display_integers_and_only_right_ratio_allows_decimals():
    from types import SimpleNamespace
    from picture_capture.app import PictureCaptureApp
    from picture_capture.models import AppSettings

    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    settings = AppSettings()
    errors = []
    app = SimpleNamespace(
        settings=settings,
        _batch_active=False,
        quick_vars={},
        quick_field_casts={},
        _quick_geometry_edit_source={},
        quick_bool_vars={},
        quick_color_vars={},
        image=None,
        lens_mode_var=Value("关闭"),
        hide_var=Value(False),
        polygon_var=Value(False),
        autosave_var=Value(False),
        status_var=Value(""),
        sync_quick_settings=lambda: None,
        redraw=lambda: None,
        show_error=lambda *_args: errors.append(_args),
    )
    integer_fields = (
        "batch_interval", "page_section_width", "guide_width", "guide_opacity",
        "marker_height", "headword_marker_opacity", "illustration_outline_width",
        "illustration_fill_opacity", "illustration_label_border_width",
        "illustration_label_font_size", "main_entry_width_chars",
        "main_entry_font_size", "crop_preview_font_size", "main_entry_x_ratio",
    )
    for name in integer_fields:
        app.quick_vars = {name: Value("7.5")}
        app.quick_field_casts = {name: int}
        before = getattr(settings, name)
        assert not PictureCaptureApp.apply_quick_settings(app, show_status=False)
        assert getattr(settings, name) == before
    for name, input_value in (
        ("batch_interval", "5"),
        ("guide_opacity", "45"),
        ("illustration_fill_opacity", "25"),
        ("main_entry_x_ratio", "37"),
    ):
        app.quick_vars = {name: Value(input_value)}
        app.quick_field_casts = {name: int}
        assert PictureCaptureApp.apply_quick_settings(app, show_status=False)
        expected = int(input_value) / 100 if name == "main_entry_x_ratio" else int(input_value)
        assert getattr(settings, name) == expected
    app.quick_vars = {"right_ratio": Value("95.5")}
    app.quick_field_casts = {"right_ratio": float}
    assert PictureCaptureApp.apply_quick_settings(app, show_status=False)
    assert settings.right_ratio == 95.5


def test_layout_numeric_field_widths_and_percent_gap():
    source = (BASE / "ui" / "compact_layout_profile_menu.py").read_text(encoding="utf-8")
    assert 'width=7 if name != "columns" else 5' in source
    assert 'width=6, justify="center"' in source
    assert 'text="% ", width=2' in source
    assert source.count('width=8)') >= 2
