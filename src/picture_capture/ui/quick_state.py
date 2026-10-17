"""Canonical Tk state for the seven compact workspace task menus.

No legacy sections or widgets are constructed here.  The same StringVar /
BooleanVar dictionaries, value display conversions, and quick-autosave traces
are shared by the compact menus and Settings Center.
"""
from __future__ import annotations

import os
import tkinter as tk
from typing import Any

from ..geometry.layout_percent_helpers import LAYOUT_PERCENT_AXES
from ..ocr_action_guard import LENS_MODE_LABELS
from ..ui_compat import normalize_content_font_setting
from ..overlay_opacity import normalize_opacity as line_opacity
from ..illustration_fill_opacity import normalize_opacity as fill_opacity
from ..adaptive_denoise import DENOISE_ENV, normalize_denoise_strength
from ..layout_visualization_ui_v3 import _DENOISE_VALUE_TO_LABEL


# Value types intentionally match the original quick UI, including the
# integer-percent presentation of the editor's horizontal offset.
QUICK_FIELD_TYPES: dict[str, type] = {
    "columns": int,
    "start_y": float,
    "manual_x": float,
    "column_width": float,
    "gutter": float,
    "character_height": float,
    "row_padding": float,
    "body_indent": float,
    "horizontal_tolerance": float,
    "page_section_width": int,
    "guide_width": int,
    "guide_opacity": int,
    "illustration_outline_width": int,
    "illustration_fill_opacity": int,
    "marker_height": int,
    "headword_marker_opacity": int,
    "illustration_label_border_width": int,
    "main_entry_width_chars": int,
    "main_entry_x_ratio": int,
    "main_entry_font_family": str,
    "main_entry_font_size": int,
    "illustration_label_font_family": str,
    "illustration_label_font_size": int,
    "crop_preview_font_family": str,
    "crop_preview_font_size": int,
    "batch_interval": int,
    "right_ratio": float,
    "crop_width_percent": float,
    "ocr_language": str,
    "paddle_band_width_ratio": float,
    "paddle_left_tolerance": int,
    "paddle_separator_safety_px": int,
}

QUICK_BOOLEAN_FIELDS = (
    "show_rulers", "show_page_sections", "show_column_guides",
    "show_headword_markers", "show_illustration_labels",
    "main_entry_follow_zoom", "main_entry_font_bold", "main_entry_font_italic",
    "illustration_label_font_bold", "illustration_label_font_italic",
    "crop_preview_font_bold", "crop_preview_font_italic",
    "crop_preview_follow_zoom", "review_main_show_ocr_choices",
    "review_main_show_ocr_background", "paddle_show_candidate_checkboxes",
    "paddle_use_paddleocr", "paddle_compare_tesseract", "paddle_enable_lens",
    "show_main_entry_labels",
)

QUICK_COLOR_FIELDS = (
    "ruler_color", "page_section_color", "guide_color",
    "headword_marker_color", "illustration_outline_color",
    "illustration_fill_color", "illustration_label_border_color",
    "illustration_label_fill_color", "main_entry_default_color",
)

FONT_FIELDS = (
    "main_entry_font_family", "illustration_label_font_family",
    "crop_preview_font_family",
)
OPACITY_FIELDS = ("guide_opacity", "headword_marker_opacity", "illustration_fill_opacity")


def _initial_field_text(settings: Any, name: str) -> str:
    value = getattr(settings, name)
    if name == "main_entry_x_ratio":
        return str(round(float(value) * 100))
    if name == "batch_interval":
        return str(round(float(value)))
    if name in FONT_FIELDS:
        return str(normalize_content_font_setting(value))
    if name in OPACITY_FIELDS:
        normalize = fill_opacity if name == "illustration_fill_opacity" else line_opacity
        return str(round(normalize(value)))
    return str(value)


def initialize_quick_state(app: Any) -> None:
    """Initialize quick state once before building any compact task panels."""
    if getattr(app, "_quick_state_initialized", False):
        return
    settings = app.settings
    app.quick_vars = {}
    app.quick_pixel_vars = {}
    app.quick_bool_vars = {}
    app.quick_color_vars = {}
    app.quick_color_buttons = {}  # New display menu owns its own live swatches.
    app.quick_field_labels = {}   # No legacy label widgets exist.
    app.quick_field_casts = dict(QUICK_FIELD_TYPES)
    app._quick_geometry_edit_source = {}

    for name in QUICK_FIELD_TYPES:
        app.quick_vars[name] = tk.StringVar(master=app, value=_initial_field_text(settings, name))
        if name in LAYOUT_PERCENT_AXES:
            app.quick_pixel_vars[name] = tk.StringVar(
                master=app, value=str(int(getattr(settings, name))),
            )
    for name in QUICK_BOOLEAN_FIELDS:
        app.quick_bool_vars[name] = tk.BooleanVar(
            master=app, value=bool(getattr(settings, name)),
        )
    for name in QUICK_COLOR_FIELDS:
        app.quick_color_vars[name] = tk.StringVar(
            master=app, value=str(getattr(settings, name)),
        )

    app.ocr_refresh_var = tk.StringVar(master=app, value="reuse")
    app.lens_mode_var = tk.StringVar(
        master=app,
        value=LENS_MODE_LABELS.get(settings.paddle_lens_mode, LENS_MODE_LABELS["off"]),
    )
    # Session-only diagnostics were formerly initialized accidentally while
    # constructing hidden controls.  The new display menu uses these vars.
    app.ocr_crop_preview_var = tk.BooleanVar(master=app, value=False)
    app._layout_visualization_var = tk.BooleanVar(master=app, value=False)
    app._layout_display_density_var = tk.StringVar(master=app, value="简洁")
    app._layout_step_replay_var = tk.BooleanVar(master=app, value=False)
    # The compact display menu also needs the transient large-head diagnostic
    # toggle previously created inside the discarded legacy UI builder.
    # Never put this in quick_bool_vars: it is not a persisted AppSettings key.
    app._large_head_visualization_var = tk.BooleanVar(master=app, value=False)
    app._large_head_debug_snapshot_key = None
    app._large_head_debug_snapshot = None
    denoise = normalize_denoise_strength(os.environ.get(DENOISE_ENV, "auto"))
    app._analysis_denoise_strength_var = tk.StringVar(
        master=app, value=_DENOISE_VALUE_TO_LABEL.get(denoise, "自动"),
    )

    # Keep the original debounced-save behaviour. Bind after constructing
    # *all* variables, never once per widget or again when a menu is opened.
    for name, variable in app.quick_vars.items():
        if name in app.quick_pixel_vars:
            variable.trace_add(
                "write", lambda *_args, field=name:
                app._quick_percent_parameter_changed(field),
            )
        else:
            variable.trace_add("write", lambda *_args: app._quick_parameter_changed())
    for name, variable in app.quick_pixel_vars.items():
        variable.trace_add(
            "write", lambda *_args, field=name:
            app._quick_pixel_parameter_changed(field),
        )
    for variable in app.quick_bool_vars.values():
        variable.trace_add("write", lambda *_args: app._quick_parameter_changed())
    app.lens_mode_var.trace_add("write", lambda *_args: app._quick_parameter_changed())
    app._quick_state_initialized = True
    app._quick_trace_ready = True
