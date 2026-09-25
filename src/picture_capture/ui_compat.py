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


AUTO_FONT_FAMILY = "自动（系统推荐）"


def _content_script(ocr_language: str) -> str:
    """Map OCR-language identifiers to the script family used for UI fonts."""
    language = str(ocr_language or "").strip().lower().replace("-", "_")
    if language.startswith(("jpn", "ja")):
        return "japanese"
    if language.startswith(("kor", "ko")):
        return "korean"
    if language.startswith(("chi_tra", "zh_tw", "zh_hk", "zh_hant", "zho_hant")):
        return "chinese_traditional"
    if language.startswith(("chi", "zh", "zho", "cmn")):
        return "chinese_simplified"
    return "latin"


def recommended_content_font_candidates(
    ocr_language: str,
    system_name: str | None = None,
) -> tuple[str, ...]:
    """Return platform-native sans-serif choices for editable dictionary text."""
    system = str(system_name or platform.system() or "").strip().lower()
    script = _content_script(ocr_language)

    if system == "windows":
        choices = {
            "chinese_simplified": (
                "Microsoft YaHei UI", "Microsoft YaHei", "DengXian", "SimHei",
                "Segoe UI", "Arial",
            ),
            "chinese_traditional": (
                "Microsoft JhengHei UI", "Microsoft JhengHei",
                "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Arial",
            ),
            "japanese": (
                "Yu Gothic UI", "Yu Gothic", "Meiryo UI", "Meiryo",
                "Segoe UI", "Arial",
            ),
            "korean": (
                "Malgun Gothic", "Malgun Gothic Semilight", "Segoe UI", "Arial",
            ),
            "latin": ("Segoe UI", "Arial", "Calibri", "DejaVu Sans"),
        }
    elif system == "darwin":
        choices = {
            "chinese_simplified": (
                "PingFang SC", "Hiragino Sans GB", "Helvetica Neue", "Helvetica", "Arial",
            ),
            "chinese_traditional": (
                "PingFang TC", "PingFang HK", "Heiti TC",
                "Helvetica Neue", "Helvetica", "Arial",
            ),
            "japanese": (
                "Hiragino Sans", "YuGothic", "Helvetica Neue", "Helvetica", "Arial",
            ),
            "korean": (
                "Apple SD Gothic Neo", "Helvetica Neue", "Helvetica", "Arial",
            ),
            "latin": ("Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"),
        }
    else:
        choices = {
            "chinese_simplified": (
                "Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Micro Hei",
                "Noto Sans", "DejaVu Sans",
            ),
            "chinese_traditional": (
                "Noto Sans CJK TC", "Noto Sans TC", "Noto Sans", "DejaVu Sans",
            ),
            "japanese": (
                "Noto Sans CJK JP", "Noto Sans JP", "Noto Sans", "DejaVu Sans",
            ),
            "korean": (
                "Noto Sans CJK KR", "Noto Sans KR", "Noto Sans", "DejaVu Sans",
            ),
            "latin": ("Noto Sans", "DejaVu Sans", "Liberation Sans", "Arial"),
        }
    return choices[script]


def normalize_content_font_setting(value: str | None) -> str:
    """Normalize empty/legacy auto spellings to the user-facing automatic sentinel."""
    text = str(value or "").strip()
    if not text or text.casefold() in {"auto", "system", "default"} or text.startswith("自动"):
        return AUTO_FONT_FAMILY
    return text


def resolve_content_font_family(
    widget: tk.Misc,
    configured_family: str | None,
    ocr_language: str,
) -> str:
    """Resolve manual font overrides first, otherwise choose by OS + OCR language."""
    configured = normalize_content_font_setting(configured_family)
    recommended = recommended_content_font_candidates(ocr_language)
    candidates = recommended if configured == AUTO_FONT_FAMILY else (configured, *recommended)
    return preferred_font_family(widget, candidates)


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
