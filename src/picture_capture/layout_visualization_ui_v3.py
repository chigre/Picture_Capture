from __future__ import annotations

"""Direct main-panel installer for the display-only Layout overlay switch.

The Layout visualization switch is intentionally UI-local.  It is not a
project/detection parameter and therefore must not be registered in
``quick_bool_vars`` or written back to the slotted ``AppSettings`` dataclass.
"""

from typing import Any
import tkinter as tk
from tkinter import ttk

from .layout_visualization_summary import draw_layout_visualization_detailed


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
            "在主图上显示当前页实际采用的版面推理：正文上下界、每栏几何、栏间宽度、推理方法/置信度及自动字段 raw/used 状态。仅影响显示。",
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
        result = original_redraw(self, *args, **kwargs)
        draw_layout_visualization_detailed(self)
        return result

    cls._section_frame = section_frame
    cls._build_quick_settings = build_quick_settings
    cls.redraw = redraw
    cls._layout_visualization_v3_installed = True
