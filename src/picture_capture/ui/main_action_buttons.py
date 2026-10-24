"""Sidebar and footer action buttons with live theme and Tk providers.

Historical app class names and signatures stay stable; current Tk modules,
thread/queue callbacks, and OCR runtime helpers are injected per invocation.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    import tkinter as tk
    from ..models import AppSettings


def sidebar_action_button_impl(
    self, parent: tk.Misc, text: str, command, *, role: str = "neutral"
    deps: dict[str, Any],
) -> tk.Widget:
    ttk = deps["ttk"]
    tk = deps["tk"]
    """Return one dense action button for the main sidebar.

    Neutral actions intentionally use the exact same ttk style as
    `检测版面参数`, so sections 四/五 share one native button chrome.
    Only the three explicitly emphasized actions use custom colors.
    """
    if role == "neutral":
        return ttk.Button(
            parent,
            text=text,
            command=command,
            style="PC.Compact.TButton",
        )

    colors = self._main_ui_colors
    palette = {
        "primary": (
            colors["primary"], colors["primary_hover"], "#ffffff",
        ),
        "success": (
            colors["success"], colors["success_hover"], "#ffffff",
        ),
    }
    background, active_background, foreground = palette.get(
        role, palette["primary"]
    )
    border = colors["button_border"]
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=background,
        fg=foreground,
        activebackground=active_background,
        activeforeground=foreground,
        relief="flat",
        bd=0,
        anchor="center",
        justify="center",
        highlightthickness=1,
        highlightbackground=border,
        highlightcolor=border,
        padx=7,
        pady=3,
        cursor="hand2",
    )


def footer_action_button_impl(
    self, parent: tk.Misc, text: str, command, *, role: str
    deps: dict[str, Any],
) -> tk.Button:
    tk = deps["tk"]
    """Create one emphasized bottom-bar action with a functional color."""
    colors = self._main_ui_colors
    palette = {
        # Scheme A: project/config entry points share the same green
        # treatment as `保存当前页`.
        "project": (colors["success"], colors["success_hover"], "#ffffff"),
        "config": (colors["success"], colors["success_hover"], "#ffffff"),
    }
    background, active_background, foreground = palette[role]
    border = colors["button_border"]
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=background,
        fg=foreground,
        activebackground=active_background,
        activeforeground=foreground,
        relief="flat",
        bd=0,
        anchor="center",
        justify="center",
        highlightthickness=1,
        highlightbackground=border,
        highlightcolor=border,
        padx=7,
        pady=3,
        cursor="hand2",
    )
