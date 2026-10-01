from __future__ import annotations

"""Direct main-panel installer for the display-only Layout overlay switch.

The Layout visualization switch is intentionally UI-local.  It is not a
project/detection parameter and therefore must not be registered in
``quick_bool_vars`` or written back to the slotted ``AppSettings`` dataclass.

While Layout diagnostics are enabled, the existing global overlay visibility
switch is temporarily forced on so ordinary guides/markers disappear.  Its
previous value is restored when Layout diagnostics are disabled.
"""

from typing import Any
import tkinter as tk
from tkinter import ttk

from .layout_visualization_summary import draw_layout_visualization_detailed


def _hide_var(app: Any) -> Any | None:
    var = getattr(app, "hide_var", None)
    if var is None or not hasattr(var, "get") or not hasattr(var, "set"):
        return None
    return var


def _set_layout_exclusive_visibility(app: Any, enabled: bool) -> None:
    """Hide ordinary overlays while Layout diagnostics are active.

    This changes only the UI variable.  It deliberately does not call the
    normal persistence callback, so project settings remain untouched.
    """
    var = _hide_var(app)
    if var is None:
        return

    if enabled:
        if not hasattr(app, "_layout_visualization_previous_hide_value"):
            try:
                app._layout_visualization_previous_hide_value = bool(var.get())
            except Exception:
                app._layout_visualization_previous_hide_value = False
        try:
            var.set(True)
        except Exception:
            pass
        return

    previous = getattr(app, "_layout_visualization_previous_hide_value", None)
    if previous is not None:
        try:
            var.set(bool(previous))
        except Exception:
            pass
        try:
            delattr(app, "_layout_visualization_previous_hide_value")
        except Exception:
            pass


def _add_layout_toggle(app: Any, section: Any) -> None:
    """Add 【显示Layout】 directly to the existing 【二、显示设置】 section."""
    if getattr(app, "_layout_visualization_toggle_widget", None) is not None:
        return

    var = tk.BooleanVar(value=False)
    app._layout_visualization_var = var

    occupied_rows: list[int] = []
    for child in section.winfo_children():
        try:
            info = child.grid_info()
            if info:
                occupied_rows.append(int(info.get("row", 0)))
        except Exception:
            pass
    row = (max(occupied_rows) + 1) if occupied_rows else 0

    def toggle() -> None:
        enabled = bool(var.get())
        _set_layout_exclusive_visibility(app, enabled)
        # The switch is display-only: invalidate only the visualization snapshot
        # and redraw the canvas.  Do not touch AppSettings or detector state.
        app._layout_visualization_snapshot_key = None
        app._layout_visualization_snapshot = None
        app.redraw()

    checkbox = ttk.Checkbutton(
        section,
        text="显示Layout",
        variable=var,
        command=toggle,
    )
    checkbox.grid(row=row, column=0, columnspan=4, sticky="w", pady=(3, 0))
    app._layout_visualization_toggle_widget = checkbox

    try:
        app._attach_tooltip(
            checkbox,
            "显示当前页版面推理，并临时隐藏其他线框/标记；取消勾选后恢复原显示状态。摘要位于第一栏水平中心、body_top 下方 5 个行高。",
        )
    except Exception:
        pass


def install_layout_visualization(app_module: Any) -> None:
    """Install 【显示Layout】 directly into the main display-settings block."""
    cls = app_module.PictureCaptureApp
    if getattr(cls, "_layout_visualization_v3_installed", False):
        return

    original_section_frame = cls._section_frame
    original_build = cls._build_quick_settings
    original_redraw = cls.redraw

    def section_frame(
        self: Any,
        parent: Any,
        title: str,
        padding: int = 5,
        *,
        section_key: str | None = None,
    ) -> Any:
        frame = original_section_frame(
            self,
            parent,
            title,
            padding,
            section_key=section_key,
        )
        if str(title) == "二、显示设置" or str(section_key or "") == "aux":
            self._layout_visualization_display_section = frame
        return frame

    def build_quick_settings(self: Any, parent: Any) -> Any:
        result = original_build(self, parent)
        section = getattr(self, "_layout_visualization_display_section", None)
        if section is not None:
            _add_layout_toggle(self, section)
        return result

    def redraw(self: Any, *args: Any, **kwargs: Any) -> Any:
        # When Layout is enabled, hide_var is True while the original redraw runs,
        # so all ordinary overlays remain suppressed.
        result = original_redraw(self, *args, **kwargs)

        layout_var = getattr(self, "_layout_visualization_var", None)
        layout_enabled = bool(layout_var.get()) if layout_var is not None else False
        if not layout_enabled:
            return result

        # The base Layout renderer historically respects hide_var.  Temporarily
        # clear it only for this diagnostic draw, then restore the exclusive
        # hidden state without triggering another redraw or persistence callback.
        hide = _hide_var(self)
        previous = None
        if hide is not None:
            try:
                previous = bool(hide.get())
                hide.set(False)
            except Exception:
                previous = None
        try:
            draw_layout_visualization_detailed(self)
        finally:
            if hide is not None and previous is not None:
                try:
                    hide.set(previous)
                except Exception:
                    pass
        return result

    cls._section_frame = section_frame
    cls._build_quick_settings = build_quick_settings
    cls.redraw = redraw
    cls._layout_visualization_v3_installed = True
