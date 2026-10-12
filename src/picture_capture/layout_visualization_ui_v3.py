from __future__ import annotations

"""Static main-panel helpers for Layout diagnostics and analysis display controls."""

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
LAYOUT_DISPLAY_MODES = ("简洁", "候选", "详细")


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


def on_layout_density_change(app: Any) -> None:
    """Redraw the scan and show verbose text only in a separate window."""
    app.redraw()
    mode = getattr(app, "_layout_display_density_var", None)
    if mode is not None and str(mode.get()) == "详细":
        from .layout_details_window import show_layout_details_window
        show_layout_details_window(app)


def _add_layout_toggle(app: Any, section: Any) -> None:
    if getattr(app, "_layout_visualization_toggle_widget", None) is not None:
        return

    var = tk.BooleanVar(value=False)
    app._layout_visualization_var = var
    # UI-only display preference. Do not persist diagnostic density in AppSettings.
    app._layout_display_density_var = tk.StringVar(value="简洁")
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
    """Compose opt-in diagnostic displays and shared-analysis controls."""
    _add_layout_toggle(app, section)
    row = _next_grid_row(section)
    ttk.Label(section, text="Layout显示密度").grid(row=row, column=0, sticky="w")
    density = ttk.Combobox(
        section, textvariable=app._layout_display_density_var,
        values=LAYOUT_DISPLAY_MODES, state="readonly", width=9,
    )
    density.grid(row=row, column=1, columnspan=2, sticky="w")
    density.bind("<<ComboboxSelected>>", lambda _event: on_layout_density_change(app))
    app._layout_display_density_widget = density
    from .layout_details_window import add_layout_details_button
    add_layout_details_button(app, section)
    from .ordinary_layout_inspector import add_unified_layout_inspector_controls
    add_unified_layout_inspector_controls(app, section)
    from .large_head_visualization_ui import add_large_head_debug_controls
    add_large_head_debug_controls(app, section)
    _add_denoise_control(app, section)


def draw_layout_visualization_if_enabled(app: Any) -> None:
    """Draw the diagnostic Layout overlay with the historical hide semantics."""
    layout_var = getattr(app, "_layout_visualization_var", None)
    layout_enabled = bool(layout_var.get()) if layout_var is not None else False
    large_var = getattr(app, "_large_head_visualization_var", None)
    large_enabled = bool(large_var.get()) if large_var is not None else False
    if not layout_enabled and not large_enabled:
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
        if layout_enabled:
            mode_var = getattr(app, "_layout_display_density_var", None)
            mode = str(mode_var.get()) if mode_var is not None else "简洁"
            if mode == "详细":
                draw_layout_visualization_detailed(app)
            else:
                from .layout_visualization_summary import draw_layout_visualization_clean
                draw_layout_visualization_clean(app)
            from .layout_details_window import refresh_layout_details_if_open
            refresh_layout_details_if_open(app)
        if large_enabled:
            from .large_head_visualization_ui import draw_large_head_debug_overlay
            draw_large_head_debug_overlay(app)
        if layout_enabled:
            from .ordinary_unified_visualization import draw_unified_candidate_overlay
            draw_unified_candidate_overlay(app, layout_enabled=True)
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
