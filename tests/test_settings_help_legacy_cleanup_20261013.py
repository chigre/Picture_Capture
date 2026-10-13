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


def test_state_initialization_requires_no_visual_widgets_and_binds_traces_once():
    import tkinter as tk
    from picture_capture.models import AppSettings
    from picture_capture.ui.quick_state import (
        QUICK_FIELD_TYPES, QUICK_BOOLEAN_FIELDS, QUICK_COLOR_FIELDS,
        initialize_quick_state,
    )

    interp = tk.Tcl()  # No display server / Tk widgets required.
    calls = []
    app = SimpleNamespace(
        tk=interp.tk,
        _root=lambda: interp,
        settings=AppSettings(),
        _quick_percent_parameter_changed=lambda key: calls.append(("percent", key)),
        _quick_pixel_parameter_changed=lambda key: calls.append(("pixel", key)),
        _quick_parameter_changed=lambda: calls.append(("plain", None)),
    )
    initialize_quick_state(app)
    assert set(QUICK_FIELD_TYPES) <= set(app.quick_vars)
    assert set(QUICK_BOOLEAN_FIELDS) <= set(app.quick_bool_vars)
    assert set(QUICK_COLOR_FIELDS) == set(app.quick_color_vars)
    assert "manual_x" in app.quick_pixel_vars
    # Session-only controls used in the compact Display menu must exist
    # before widgets are constructed (regression for the GUI smoke failure).
    assert app._layout_visualization_var.get() is False
    assert app._layout_step_replay_var.get() is False
    assert app._large_head_visualization_var.get() is False
    assert "_large_head_visualization_var" not in app.quick_bool_vars
    assert app._large_head_debug_snapshot is None
    assert app.quick_field_labels == {}
    assert app.quick_color_buttons == {}
    assert app._quick_trace_ready

    # Reopening compact menus must never install duplicate callbacks.
    old_var = app.quick_vars["columns"]
    initialize_quick_state(app)
    assert app.quick_vars["columns"] is old_var
    app.quick_vars["columns"].set("2")
    assert calls == [("plain", None)]
    calls.clear()
    app.quick_vars["manual_x"].set("12")
    assert calls == [("percent", "manual_x")]
    calls.clear()
    app.quick_pixel_vars["manual_x"].set("250")
    assert calls == [("pixel", "manual_x")]
    calls.clear()
    app.quick_bool_vars["show_rulers"].set(False)
    assert calls == [("plain", None)]
