"""Settings Center completeness and retired quick-menu safety checks."""
from __future__ import annotations

from types import SimpleNamespace

from picture_capture.ui import workspace_tools
from picture_capture.ui.settings import crop, schema
from picture_capture.crop.settings import (
    SINGLE_LINE_MERGE_KEY,
    UNLINED_FILTER_ENABLED_KEY,
    UNLINED_FILTER_BLANK_KEY,
    UNLINED_BLANK_INK_PERCENT_KEY,
)


def test_all_schema_fields_and_visible_checkboxes_have_dedicated_help():
    field_names = {name for _, name, _ in schema.FIELDS}
    check_groups = (
        schema.NORMAL_CHECKS, schema.OCR_COMMON_CHECKS,
        schema.OCR_ADVANCED_CHECKS, schema.DISPLAY_STYLE_CHECKS,
        schema.DISPLAY_CHECKS, schema.ILLUSTRATION_CHECKS,
    )
    check_names = {name for group in check_groups for _, name in group}
    check_names |= {"ocr_replace", "lowercase_ocr", "paddle_enable_lens"}
    assert field_names <= schema.SETTING_HELP.keys()
    assert check_names <= schema.CHECK_HELP.keys()
    for name in field_names:
        assert len(schema.SETTING_HELP[name].strip()) >= 35, name
    for name in check_names:
        assert len(schema.CHECK_HELP[name].strip()) >= 30, name
    # Values created as bespoke controls rather than members of FIELDS.
    for name in ("detection_method", "paddle_lens_mode", "ocr_engine",
                 "headword_sort_mode", "headword_custom_order",
                 "headword_custom_fold_accents"):
        assert name in schema.SETTING_HELP, name


def test_every_custom_crop_setting_has_specialized_help():
    custom = {
        "general_top_y", "general_bottom_y",
        "entry_left_padding_x", "entry_right_padding_x",
        "integrate_illustrations", "polygon_margin", "parallel_workers",
        "entry_width_mode", "entry_fixed_width",
        "illustration_pad_to_entry_width",
        "entry_transparent_background", "illustration_transparent_background",
    }
    assert set(crop.CROP_CONTROL_HELP) == custom
    assert all(len(title) >= 5 and len(body) >= 45
               for title, body in crop.CROP_CONTROL_HELP.values())
    # The other four crop controls already use explicit merge/filter help
    # rather than this registry.
    for key in (SINGLE_LINE_MERGE_KEY, UNLINED_FILTER_ENABLED_KEY,
                UNLINED_FILTER_BLANK_KEY, UNLINED_BLANK_INK_PERCENT_KEY):
        assert key not in crop.CROP_CONTROL_HELP


def test_crop_input_controls_dispatch_distinct_right_panel_explanations():
    class Widget:
        def __init__(self, variable="", *, children=()):
            self.variable = variable
            self.children = children
            self.help_callback = None

        def cget(self, name):
            if name in ("variable", "textvariable"):
                return self.variable
            raise KeyError(name)

        def winfo_children(self):
            return self.children

    field_a = Widget("PY_VAR_A")
    field_b = Widget("PY_VAR_B")
    merge = Widget("PY_VAR_MERGE")
    root = Widget(children=[field_a, Widget(children=[field_b]), merge])
    recorded = []
    bound = []

    class Dialog:
        crop_vars = {
            "general_top_y": "PY_VAR_A",
            "parallel_workers": "PY_VAR_B",
            SINGLE_LINE_MERGE_KEY: "PY_VAR_MERGE",
        }

        def _bind_help_widget(self, widget, callback):
            widget.help_callback = callback
            bound.append(widget)

        def _show_settings_help(self, title, body):
            recorded.append((title, body))

    crop.bind_crop_control_help(Dialog(), root)
    assert bound == [field_a, field_b]
    assert merge.help_callback is None  # Dedicated merge/filter path unchanged.
    field_a.help_callback()
    field_b.help_callback()
    assert recorded[0] == crop.CROP_CONTROL_HELP["general_top_y"]
    assert recorded[1] == crop.CROP_CONTROL_HELP["parallel_workers"]
    assert recorded[0] != recorded[1]


def test_retirement_destroys_all_replaced_legacy_widgets_not_shared_state():
    class Widget:
        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    old = {name: Widget() for name in (
        "preprocess", "normal", "aux", "ocr", "actions", "postproduction",
    )}
    replacements = {
        title: Widget() for title in (
            "图片预处理(前置)", "一、版面参数", "二、显示设置",
            "三、共享 OCR 通道 / OCR画线",
            "四、画线 / OCR / 插图 / 校对",
            "五、后期词典制作",
        )
    }
    quick = {"body_indent": object()}
    booleans = {"show_rulers": object()}
    old_labels = {"body_indent": object()}
    old_buttons = {"ruler_color": object()}
    app = SimpleNamespace(
        _collapsible_sections=old,
        quick_vars=quick,
        quick_bool_vars=booleans,
        quick_field_labels=old_labels,
        quick_color_buttons=old_buttons,
        preprocess_panel=None,
    )
    workspace_tools.retire_superseded_quick_panels(app, replacements)
    assert old == {}  # No hidden legacy quick-menu tree remains.
    assert all(not widget.destroyed for widget in replacements.values())
    assert app.preprocess_panel is replacements["图片预处理(前置)"]
    assert app.quick_vars is quick and app.quick_bool_vars is booleans
    assert old_labels == {} and old_buttons == {}
