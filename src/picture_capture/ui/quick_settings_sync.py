"""Live Profile pixel-to-percent quick settings and lens UI sync.

Historical app class names and signatures stay stable; current Tk modules,
thread/queue callbacks, and OCR runtime helpers are injected per invocation.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    import tkinter as tk
    from ..models import AppSettings


def sync_quick_settings_impl(self, *, deps: dict[str, Any]) -> None:
    LAYOUT_PERCENT_AXES = deps["LAYOUT_PERCENT_AXES"]
    _format_layout_percent = deps["_format_layout_percent"]
    _layout_pixels_to_percent = deps["_layout_pixels_to_percent"]
    normalize_content_font_setting = deps["normalize_content_font_setting"]
    LENS_MODE_LABELS = deps["LENS_MODE_LABELS"]
    if not hasattr(self, "quick_vars"):
        return
    self._quick_syncing = True
    try:
        self._refresh_quick_coordinate_labels()
        for name, var in self.quick_vars.items():
            if hasattr(self.settings, name):
                value = getattr(self.settings, name)
                if name in LAYOUT_PERCENT_AXES:
                    source_value = self._quick_geometry_value(name)
                    if self.image is not None:
                        value = _format_layout_percent(
                            _layout_pixels_to_percent(self.image, name, source_value)
                        )
                    else:
                        value = source_value
                    pixel_var = getattr(self, "quick_pixel_vars", {}).get(name)
                    if pixel_var is not None:
                        pixel_var.set(str(int(round(source_value))))
                if name == "main_entry_x_ratio":
                    value = round(float(value) * 100)
                elif name in {
                    "batch_interval", "guide_opacity", "headword_marker_opacity",
                    "illustration_fill_opacity",
                }:
                    value = round(float(value))
                if name in {
                    "main_entry_font_family",
                    "illustration_label_font_family",
                    "review_entry_font_family",
                    "review_simplified_font_family",
                }:
                    value = normalize_content_font_setting(value)
                var.set(str(value))
        for name, var in getattr(self, "quick_bool_vars", {}).items():
            if hasattr(self.settings, name):
                var.set(bool(getattr(self.settings, name)))
        for name, var in getattr(self, "quick_color_vars", {}).items():
            if hasattr(self.settings, name):
                value = str(getattr(self.settings, name))
                var.set(value)
                button = getattr(self, "quick_color_buttons", {}).get(name)
                if button is not None:
                    self._style_color_button(button, value)
        if hasattr(self, "lens_mode_var"):
            self.lens_mode_var.set(
                LENS_MODE_LABELS.get(
                    self.settings.paddle_lens_mode, LENS_MODE_LABELS["off"]
                )
            )
        self._quick_geometry_edit_source.clear()
    finally:
        self._quick_syncing = False
