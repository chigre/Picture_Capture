"""Shared, state-aware main-window shortcuts for editing and display modes.

No independent mode flags: the six buttons read the same variables used by the
original menus, page-list editor, and canvas controllers.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any

from ..layout_visualization_ui_v3 import (
    _invalidate_layout_snapshot, _set_layout_exclusive_visibility,
)


# Explicit, theme-aware macaron orange indicates an engaged editing/display mode.
SELECTED_COLORS = {
    "light": ("#F5B873", "#55320F", "#EFA257"),
    "dark": ("#98602F", "#FFF0DA", "#B8753C"),
}

MODE_TOOLTIPS = {
    "图": "编辑插图",
    "区": "编辑Section区域；双击页面列表相应位置亦可进入该编辑模式",
    "辅": "编辑辅助线；SHIFT+左键=画辅助线",
    "L": "显示Layout",
    "A": "切图预览",
    "S": "OCR词头区域预览",
}


def _checked(app: Any, name: str) -> bool:
    value = getattr(app, name, None)
    return bool(value.get()) if value is not None else False


def mode_shortcut_selected(app: Any, label: str) -> bool:
    """Use canonical edit flags/display flags, including menu-driven changes."""
    if label == "图":
        return _checked(app, "polygon_draw_var")
    if label == "区":
        return bool(getattr(app, "_section_editing", False))
    if label == "辅":
        return _checked(app, "auxiliary_mode_var")
    if label == "L":
        return _checked(app, "_layout_visualization_var")
    if label == "A":
        return _checked(app, "crop_preview_var")
    if label == "S":
        return _checked(app, "ocr_crop_preview_var")
    return False


def refresh_workspace_mode_shortcut_buttons(app: Any) -> None:
    """Refresh active/inactive colours, including appearance and page changes."""
    palette = getattr(app, "_main_ui_colors", {})
    appearance = "dark" if str(getattr(app, "appearance_mode", "light")).lower() == "dark" else "light"
    selected_bg, selected_fg, selected_hover = SELECTED_COLORS[appearance]
    for label, button in getattr(app, "workspace_mode_shortcut_buttons", {}).items():
        try:
            if not button.winfo_exists():
                continue
            active = mode_shortcut_selected(app, label)
            background = selected_bg if active else palette.get("button", "#E5E7EB")
            foreground = selected_fg if active else palette.get("text", "#263238")
            hover = selected_hover if active else palette.get("button_hover", "#D6DCE1")
            button.configure(
                bg=background, fg=foreground,
                activebackground=hover, activeforeground=foreground,
            )
        except (AttributeError, tk.TclError):
            # Shortcuts are recreated on workspace rebuilds.
            continue


def create_workspace_mode_shortcut_button(
    app: Any, parent: tk.Misc, label: str, command: Any,
) -> tk.Button:
    """Create a small native Tk button (ttk themes ignore custom selection bg)."""
    colors = getattr(app, "_main_ui_colors", {})
    button = tk.Button(
        parent, text=label, width=2, command=command,
        font="TkDefaultFont", anchor="center", justify="center",
        bg=colors.get("button", "#E5E7EB"),
        fg=colors.get("text", "#263238"),
        activebackground=colors.get("button_hover", "#D6DCE1"),
        activeforeground=colors.get("text", "#263238"),
        relief="flat", bd=0, highlightthickness=0,
        padx=1, pady=1, cursor="hand2",
    )
    button._pc_skip_classic_appearance = True
    app.workspace_mode_shortcut_buttons[label] = button
    app._attach_tooltip(button, MODE_TOOLTIPS[label])
    refresh_workspace_mode_shortcut_buttons(app)
    return button


def install_workspace_mode_shortcut_traces(app: Any) -> None:
    """Keep shortcut colours synced when a *menu*, not a shortcut, edits state."""
    if getattr(app, "_workspace_mode_shortcut_traces_installed", False):
        return
    for name in (
        "polygon_draw_var", "auxiliary_mode_var", "_layout_visualization_var",
        "crop_preview_var", "ocr_crop_preview_var", "display_mode_var",
    ):
        variable = getattr(app, name, None)
        if variable is not None and hasattr(variable, "trace_add"):
            variable.trace_add(
                "write",
                lambda *_args: refresh_workspace_mode_shortcut_buttons(app),
            )
    app._workspace_mode_shortcut_traces_installed = True
    refresh_workspace_mode_shortcut_buttons(app)


def toggle_workspace_illustration_editor(app: Any) -> None:
    """Invoke the drawing menu's polygon editor, avoiding competing edit modes."""
    if not _checked(app, "polygon_draw_var") and _checked(app, "auxiliary_mode_var"):
        app.auxiliary_mode_var.set(False)
        app.toggle_auxiliary_mode()
    app.toggle_polygon_drawing()


def toggle_workspace_section_editor(app: Any) -> None:
    """Use the current page's same count dialog/SECTION editor as the 域 column."""
    app.toggle_current_page_section_editing()


def toggle_workspace_auxiliary_editor(app: Any) -> None:
    """Mirror the auxiliary checkbox, allowing a second click to leave."""
    enabled = not _checked(app, "auxiliary_mode_var")
    if enabled:
        if _checked(app, "polygon_draw_var"):
            app.toggle_polygon_drawing()
        if getattr(app, "_section_editing", False):
            app._finish_section_editing()
    app.auxiliary_mode_var.set(enabled)
    app.toggle_auxiliary_mode()


def toggle_workspace_layout(app: Any) -> None:
    """Same visibility/restore logic as the 显示Layout menu checkbox."""
    variable = app._layout_visualization_var
    enabled = not bool(variable.get())
    variable.set(enabled)
    _set_layout_exclusive_visibility(app, enabled)
    _invalidate_layout_snapshot(app)
    app.redraw()


def toggle_workspace_display_preview(app: Any, target: str) -> None:
    """A/S are mutually exclusive; toggling the active one restores last view."""
    if target not in {"切图预览", "OCR词头区域预览"}:
        raise ValueError(f"未知的预览模式: {target}")
    current = app._display_mode_from_flags()
    if current == target:
        restore = getattr(app, "_workspace_display_before_preview", "原图+标注")
        mode = restore if restore not in {"切图预览", "OCR词头区域预览"} else "原图+标注"
    else:
        if current not in {"切图预览", "OCR词头区域预览"}:
            app._workspace_display_before_preview = current
        mode = target
    app.display_mode_var.set(mode)
    app._apply_display_mode()
