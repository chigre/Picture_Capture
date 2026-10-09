from __future__ import annotations

"""Direct main-panel installer for Layout diagnostics and analysis display controls."""

import os
from typing import Any
import tkinter as tk
from tkinter import ttk

from .adaptive_denoise import DENOISE_ENV, normalize_denoise_strength
from .layout_visualization_summary import draw_layout_visualization_detailed


_DENOISE_LABEL_TO_VALUE = {
    "关闭": "off",
    "弱": "weak",
    "自动": "auto",
    "强": "strong",
}
_DENOISE_VALUE_TO_LABEL = {value: label for label, value in _DENOISE_LABEL_TO_VALUE.items()}


def _hide_var(app: Any) -> Any | None:
    var = getattr(app, "hide_var", None)
    if var is None or not hasattr(var, "get") or not hasattr(var, "set"):
        return None
    return var


def _set_layout_exclusive_visibility(app: Any, enabled: bool) -> None:
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


def _next_grid_row(section: Any) -> int:
    occupied_rows: list[int] = []
    for child in section.winfo_children():
        try:
            info = child.grid_info()
            if info:
                occupied_rows.append(int(info.get("row", 0)))
        except Exception:
            pass
    return (max(occupied_rows) + 1) if occupied_rows else 0


def _invalidate_layout_snapshot(app: Any) -> None:
    app._layout_visualization_snapshot_key = None
    app._layout_visualization_snapshot = None
    try:
        app._layout_visualization_indent_blocks = []
    except Exception:
        pass


def _add_layout_toggle(app: Any, section: Any) -> None:
    if getattr(app, "_layout_visualization_toggle_widget", None) is not None:
        return

    var = tk.BooleanVar(value=False)
    app._layout_visualization_var = var
    row = _next_grid_row(section)

    def toggle() -> None:
        enabled = bool(var.get())
        _set_layout_exclusive_visibility(app, enabled)
        _invalidate_layout_snapshot(app)
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
            "显示当前页版面推理，并临时隐藏其他线框/标记；取消勾选后恢复原显示状态。",
        )
    except Exception:
        pass


def _add_denoise_control(app: Any, section: Any) -> None:
    """Add session-level shared-analysis denoise strength control."""
    if getattr(app, "_analysis_denoise_strength_widget", None) is not None:
        return

    current = normalize_denoise_strength(os.environ.get(DENOISE_ENV, "auto"))
    var = tk.StringVar(value=_DENOISE_VALUE_TO_LABEL.get(current, "自动"))
    app._analysis_denoise_strength_var = var
    row = _next_grid_row(section)

    label = ttk.Label(section, text="去噪强度：")
    label.grid(row=row, column=0, sticky="w", pady=(3, 0))
    combo = ttk.Combobox(
        section,
        textvariable=var,
        values=tuple(_DENOISE_LABEL_TO_VALUE),
        state="readonly",
        width=7,
    )
    combo.grid(row=row, column=1, sticky="w", padx=(4, 8), pady=(3, 0))

    def apply_strength(_event: Any | None = None) -> None:
        value = _DENOISE_LABEL_TO_VALUE.get(str(var.get()), "auto")
        os.environ[DENOISE_ENV] = value
        _invalidate_layout_snapshot(app)
        # Redraw immediately so 【显示Layout】 recomputes its Page Understanding
        # from the newly cleaned shared analysis image. Ordinary drawing jobs
        # started afterwards inherit the same environment setting.
        try:
            app.redraw()
        except Exception:
            pass

    combo.bind("<<ComboboxSelected>>", apply_strength)
    app._analysis_denoise_strength_widget = combo

    help_text = (
        "共享分析图去噪强度。自动：先分析整页稀疏墨迹分布再选择阈值；"
        "弱：更保护标点/小笔画；强：清理更多成团扫描残墨；关闭：不去噪。"
        "该设置影响 Layout、Page Understanding 和普通画线使用的同一张分析图。"
    )
    for widget in (label, combo):
        try:
            app._attach_tooltip(widget, help_text)
        except Exception:
            pass


def add_layout_visualization_controls(app: Any, section: Any) -> None:
    """Add the current Layout toggle and denoise control to the display section."""
    _add_layout_toggle(app, section)
    _add_denoise_control(app, section)


def draw_layout_visualization_if_enabled(app: Any) -> None:
    """Draw the diagnostic Layout overlay with the historical hide semantics."""
    layout_var = getattr(app, "_layout_visualization_var", None)
    layout_enabled = bool(layout_var.get()) if layout_var is not None else False
    if not layout_enabled:
        return

    hide = _hide_var(app)
    previous = None
    if hide is not None:
        try:
            previous = bool(hide.get())
            hide.set(False)
        except Exception:
            previous = None
    try:
        draw_layout_visualization_detailed(app)
    finally:
        if hide is not None and previous is not None:
            try:
                hide.set(previous)
            except Exception:
                pass


def install_layout_visualization(app_module: Any) -> None:
    """Compatibility no-op; Layout visualization wiring is static."""
    _ = app_module


__all__ = [
    "add_layout_visualization_controls",
    "draw_layout_visualization_if_enabled",
    "install_layout_visualization",
]
