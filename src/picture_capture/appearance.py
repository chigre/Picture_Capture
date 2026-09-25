from __future__ import annotations

import colorsys
import ctypes
import sys
import tkinter as tk
from tkinter import ttk

from PIL import Image


LIGHT_PALETTE = {
    "bg": "#f6f7f9",
    "surface": "#ffffff",
    "surface_alt": "#f1f3f6",
    "panel": "#f7f8fa",
    "border": "#d8dde5",
    "text": "#111827",
    "muted": "#68707b",
    "input_bg": "#ffffff",
    "input_fg": "#111827",
    "button": "#f4f5f7",
    "button_hover": "#e7eaee",
    "selection": "#dce8f7",
    "selection_fg": "#111827",
    "canvas": "#30343b",
    "accent": "#4f7cac",
    "accent_hover": "#416a94",
    "success": "#69a875",
    "success_hover": "#588f64",
    "danger": "#9b3a3a",
}

DARK_PALETTE = {
    "bg": "#181c21",
    "surface": "#20252b",
    "surface_alt": "#252b32",
    "panel": "#242a31",
    "border": "#3b434d",
    "text": "#e6edf3",
    "muted": "#9ba7b4",
    "input_bg": "#12171d",
    "input_fg": "#edf2f7",
    "button": "#2b323a",
    "button_hover": "#373f49",
    "selection": "#274963",
    "selection_fg": "#f2f7fb",
    "canvas": "#0f1318",
    "accent": "#76a9d5",
    "accent_hover": "#8bb8df",
    "success": "#67ad73",
    "success_hover": "#78bd84",
    "danger": "#db7b7b",
}


def normalize_appearance_mode(value: object) -> str:
    """Return a supported global appearance mode."""
    return "dark" if str(value or "").strip().lower() == "dark" else "light"


def appearance_palette(mode: object) -> dict[str, str]:
    """Return a copy so callers cannot mutate the shared palette."""
    source = DARK_PALETTE if normalize_appearance_mode(mode) == "dark" else LIGHT_PALETTE
    return dict(source)


def themed_display_image(image: Image.Image, mode: object) -> Image.Image:
    """Return a display-only night-friendly rendering of an image.

    Low-saturation paper/text pixels receive a strong luminance reversal, turning
    white paper dark and dark print light. Saturated artwork keeps progressively
    more of its original value so colour identity is not naively RGB-inverted.
    The source object is never mutated. Alpha, when present, is preserved.
    """
    if normalize_appearance_mode(mode) != "dark":
        return image

    alpha = image.getchannel("A") if "A" in image.getbands() else None
    rgb = image.convert("RGB")
    hue, saturation, value = rgb.convert("HSV").split()

    # White paper: 255 -> 28. Black print: 0 -> 232.
    reversed_value = value.point(
        [max(0, min(255, 232 - round(204 * level / 255))) for level in range(256)]
    )
    # Greyscale text/paper uses the full reversal. Highly saturated pixels keep
    # 75% of their original brightness, avoiding cyan/magenta-style negative art.
    reversal_strength = saturation.point(
        [max(64, 255 - round(191 * level / 255)) for level in range(256)]
    )
    night_value = Image.composite(reversed_value, value, reversal_strength)
    rendered = Image.merge("HSV", (hue, saturation, night_value)).convert("RGB")
    if alpha is not None:
        rendered.putalpha(alpha)
    return rendered


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for channel in rgb:
        value = channel / 255.0
        channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _widget_rgb(widget: tk.Misc, value: object) -> tuple[int, int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        red, green, blue = widget.winfo_rgb(text)
    except tk.TclError:
        return None
    return red // 257, green // 257, blue // 257


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(value)))) for value in rgb))


def _semantic_dark_color(rgb: tuple[int, int, int], *, foreground: bool) -> str:
    red, green, blue = (component / 255.0 for component in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    if foreground:
        target_lightness = 0.76 if saturation >= 0.16 else 0.90
        target_saturation = min(0.70, max(0.18, saturation))
    else:
        target_lightness = 0.24 if saturation >= 0.16 else 0.15
        target_saturation = min(0.55, max(0.12, saturation))
    out = colorsys.hls_to_rgb(hue, target_lightness, target_saturation)
    return _hex(tuple(round(channel * 255) for channel in out))


def _dark_option_value(
    widget: tk.Misc,
    option: str,
    original: object,
    *,
    widget_class: str,
    palette: dict[str, str],
) -> str | None:
    rgb = _widget_rgb(widget, original)
    if rgb is None:
        return None
    luminance = _relative_luminance(rgb)
    red, green, blue = (component / 255.0 for component in rgb)
    _hue, _lightness, saturation = colorsys.rgb_to_hls(red, green, blue)

    background_options = {
        "background", "activebackground", "selectbackground",
        "highlightbackground", "highlightcolor", "troughcolor",
        "disabledbackground", "readonlybackground", "buttonbackground",
    }
    foreground_options = {
        "foreground", "activeforeground", "disabledforeground",
        "insertbackground", "selectforeground",
    }

    if option in background_options:
        if saturation < 0.16:
            if (
                widget_class in {"Entry", "Text", "Listbox", "Spinbox"}
                and option in {"background", "disabledbackground", "readonlybackground"}
            ):
                return palette["input_bg"]
            if widget_class == "Spinbox" and option == "buttonbackground":
                return palette["button"]
            if widget_class == "Button":
                return palette["button_hover"] if option == "activebackground" else palette["button"]
            if option == "selectbackground":
                return palette["selection"]
            if option in {"highlightbackground", "highlightcolor"}:
                return palette["border"]
            if luminance >= 0.50:
                return palette["surface"]
            # Deliberately preserve already-dark drawing/viewer surfaces.
            return str(original)
        if luminance >= 0.48:
            return _semantic_dark_color(rgb, foreground=False)
        return str(original)

    if option in foreground_options:
        if option == "selectforeground":
            return palette["selection_fg"]
        if saturation < 0.16:
            if luminance <= 0.65:
                return palette["input_fg"] if widget_class in {"Entry", "Text", "Listbox", "Spinbox"} else palette["text"]
            return palette["text"]
        if luminance <= 0.55:
            return _semantic_dark_color(rgb, foreground=True)
        return str(original)

    return None


_CLASSIC_COLOR_OPTIONS = (
    "background",
    "foreground",
    "activebackground",
    "activeforeground",
    "disabledbackground",
    "readonlybackground",
    "buttonbackground",
    "disabledforeground",
    "insertbackground",
    "selectbackground",
    "selectforeground",
    "highlightbackground",
    "highlightcolor",
    "troughcolor",
)


def apply_classic_widget_appearance(root: tk.Misc, mode: object) -> None:
    """Theme classic Tk descendants while leaving ttk widgets to ttk.Style.

    Original light values are captured per widget and restored exactly when the
    user returns to light mode. This lets semantic warning colours and custom
    button colours survive repeated light/dark toggles.
    """
    normalized = normalize_appearance_mode(mode)
    palette = appearance_palette(normalized)
    stack: list[tk.Misc] = [root]
    while stack:
        widget = stack.pop()
        try:
            stack.extend(widget.winfo_children())
        except tk.TclError:
            continue
        is_ttk = isinstance(widget, ttk.Widget)
        if bool(getattr(widget, "_pc_skip_classic_appearance", False)):
            continue
        original = getattr(widget, "_pc_light_theme_options", None)
        if normalized == "light":
            if isinstance(original, dict):
                for option, value in original.items():
                    try:
                        widget.configure(**{option: value})
                    except tk.TclError:
                        pass
                try:
                    delattr(widget, "_pc_light_theme_options")
                except AttributeError:
                    pass
            continue

        if not isinstance(original, dict):
            original = {}
            try:
                keys = set(widget.keys())
            except tk.TclError:
                keys = set()
            candidate_options = (
                ("foreground",)
                if is_ttk
                else _CLASSIC_COLOR_OPTIONS
            )
            for option in candidate_options:
                if option not in keys:
                    continue
                try:
                    value = widget.cget(option)
                except tk.TclError:
                    continue
                # Empty ttk foreground/background values mean “inherit from
                # Style”; leave those to the global ttk theme.
                if is_ttk and not str(value or "").strip():
                    continue
                original[option] = value
            try:
                setattr(widget, "_pc_light_theme_options", original)
            except Exception:
                pass

        widget_class = str(widget.winfo_class() or "")
        for option, value in original.items():
            themed = _dark_option_value(
                widget, option, value, widget_class=widget_class, palette=palette,
            )
            if themed is None:
                continue
            try:
                widget.configure(**{option: themed})
            except tk.TclError:
                pass


def apply_native_titlebar_appearance(window: tk.Misc, mode: object) -> None:
    """Ask Windows DWM to match an app Toplevel title bar to light/dark mode.

    Tk's client window is wrapped by a native top-level HWND on Windows, so the
    DWM attribute must be applied to the parent HWND. Unsupported Windows builds
    and non-Windows platforms intentionally fall back to the operating-system
    title-bar appearance.
    """
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        client_hwnd_value = int(window.winfo_id())
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi

        # Declare pointer-sized signatures explicitly. Without these ctypes
        # defaults HWND arguments/return values to 32-bit c_int, which can
        # truncate handles in the 64-bit Windows build used by most users.
        get_parent = user32.GetParent
        get_parent.argtypes = [ctypes.c_void_p]
        get_parent.restype = ctypes.c_void_p
        parent_hwnd_value = get_parent(ctypes.c_void_p(client_hwnd_value))
        native_hwnd = ctypes.c_void_p(parent_hwnd_value or client_hwnd_value)

        set_attribute = dwmapi.DwmSetWindowAttribute
        set_attribute.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint,
        ]
        set_attribute.restype = ctypes.c_long

        enabled = ctypes.c_int(1 if normalize_appearance_mode(mode) == "dark" else 0)
        # Attribute 20 is used by current Windows 10/11. Attribute 19 is the
        # compatibility value used by earlier Windows 10 builds.
        result = int(
            set_attribute(
                native_hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled)
            )
        )
        if result != 0:
            set_attribute(
                native_hwnd, 19, ctypes.byref(enabled), ctypes.sizeof(enabled)
            )
    except (
        AttributeError, OSError, TypeError, ValueError, ctypes.ArgumentError, tk.TclError
    ):
        return


def usage_guide_palette(mode: object) -> dict[str, str]:
    """Palette for the guide's intentionally custom classic-Tk card layout."""
    if normalize_appearance_mode(mode) == "dark":
        return {
            "bg": "#181c21",
            "surface": "#20252b",
            "sidebar": "#242a31",
            "border": "#3b434d",
            "text": "#e6edf3",
            "muted": "#9ba7b4",
            "accent": "#76a9d5",
            "accent_soft": "#263d52",
            "tip": "#222a33",
        }
    return {
        "bg": "#f5f7fb",
        "surface": "#ffffff",
        "sidebar": "#eef2f6",
        "border": "#dde3ea",
        "text": "#111827",
        "muted": "#667085",
        "accent": "#4f7cac",
        "accent_soft": "#e9f1f9",
        "tip": "#f7f9fc",
    }
