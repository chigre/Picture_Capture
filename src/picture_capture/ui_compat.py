from __future__ import annotations

import ctypes
import platform
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Iterable


def bind_context_menu(widget: tk.Misc, callback: Callable, *, add: str = "+") -> None:
    """Bind a secondary-click callback across Windows, Linux/X11, and macOS/Aqua."""
    widget.bind("<Button-3>", callback, add=add)
    if platform.system() == "Darwin":
        widget.bind("<Button-2>", callback, add=add)
        widget.bind("<Control-Button-1>", callback, add=add)


def preferred_font_family(
    widget: tk.Misc,
    candidates: Iterable[str],
    *,
    fallback_named_font: str = "TkDefaultFont",
) -> str:
    """Return the first installed family, else the active Tk named-font family."""
    try:
        available = {name.casefold(): name for name in tkfont.families(widget)}
    except tk.TclError:
        available = {}
    for candidate in candidates:
        found = available.get(str(candidate).casefold())
        if found:
            return found
    try:
        return str(tkfont.nametofont(fallback_named_font, root=widget).actual("family"))
    except (tk.TclError, TypeError):
        return str(next(iter(candidates), "TkDefaultFont"))


def screen_work_area(widget: tk.Misc) -> tuple[int, int, int, int]:
    """Return a conservative usable work area in Tk pixels."""
    screen_w = max(640, int(widget.winfo_screenwidth()))
    screen_h = max(480, int(widget.winfo_screenheight()))
    if platform.system() == "Windows":
        try:
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long),
                ]
            rect = RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return (
                    int(rect.left), int(rect.top),
                    max(1, int(rect.right - rect.left)),
                    max(1, int(rect.bottom - rect.top)),
                )
        except (AttributeError, OSError, TypeError, ValueError):
            pass
    margin_x = min(24, max(0, screen_w // 40))
    margin_y = min(36, max(0, screen_h // 30))
    return margin_x, margin_y, max(1, screen_w - 2 * margin_x), max(1, screen_h - 2 * margin_y)


def fit_window_to_work_area(
    window: tk.Misc,
    width: int,
    height: int,
    *,
    min_width: int = 560,
    min_height: int = 420,
) -> tuple[int, int]:
    """Clamp and center a Toplevel within the current platform work area."""
    try:
        window.update_idletasks()
        x0, y0, work_w, work_h = screen_work_area(window)
        fitted_w = max(320, min(int(width), work_w))
        fitted_h = max(260, min(int(height), work_h))
        x = x0 + max(0, (work_w - fitted_w) // 2)
        y = y0 + max(0, (work_h - fitted_h) // 2)
        window.geometry(f"{fitted_w}x{fitted_h}+{x}+{y}")
        window.minsize(min(int(min_width), fitted_w), min(int(min_height), fitted_h))
        return fitted_w, fitted_h
    except tk.TclError:
        return int(width), int(height)
