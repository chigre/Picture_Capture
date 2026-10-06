from __future__ import annotations

"""Static display-opacity helpers for column guides and headword marker lines.

Line opacity is presentation-only. AppSettings owns the persisted percentages;
this module owns rendering and the small quick-control constructor. No class or
module is patched at import/startup time.
"""

import math
import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable

from PIL import Image, ImageColor, ImageDraw, ImageTk

from .overlay_line_anchor import one_sided_line_coordinates


DEFAULT_DISPLAY_OPACITY = 40.0


def normalize_opacity(value: object, default: float = DEFAULT_DISPLAY_OPACITY) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    return max(0.0, min(100.0, number))


def flatten_coordinates(values: tuple[Any, ...]) -> list[float]:
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        values = tuple(values[0])
    coords: list[float] = []
    for value in values:
        try:
            coords.append(float(value))
        except (TypeError, ValueError):
            return []
    return coords


def _smooth_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    current = list(points)
    for _ in range(2):
        output = [current[0]]
        for first, second in zip(current, current[1:]):
            q = (
                0.75 * first[0] + 0.25 * second[0],
                0.75 * first[1] + 0.25 * second[1],
            )
            r = (
                0.25 * first[0] + 0.75 * second[0],
                0.25 * first[1] + 0.75 * second[1],
            )
            output.extend((q, r))
        output.append(current[-1])
        current = output
    return current


def render_alpha_line_overlay(
    coordinates: Iterable[float],
    *,
    color: str,
    width: float,
    opacity: float,
    smooth: bool = False,
) -> tuple[Image.Image, int, int]:
    """Return a tightly bounded RGBA line image and its Canvas top-left."""
    values = [float(value) for value in coordinates]
    if len(values) < 4 or len(values) % 2:
        raise ValueError("line coordinates must contain at least two XY points")
    points = list(zip(values[0::2], values[1::2]))
    if smooth:
        points = _smooth_points(points)

    line_width = max(1, int(round(float(width or 1.0))))
    pad = max(3, int(math.ceil(line_width / 2.0)) + 2)
    min_x = math.floor(min(point[0] for point in points)) - pad
    min_y = math.floor(min(point[1] for point in points)) - pad
    max_x = math.ceil(max(point[0] for point in points)) + pad
    max_y = math.ceil(max(point[1] for point in points)) + pad
    image_width = max(1, int(max_x - min_x + 1))
    image_height = max(1, int(max_y - min_y + 1))

    rgb = ImageColor.getrgb(str(color or "#000000"))[:3]
    alpha = round(normalize_opacity(opacity) * 255.0 / 100.0)
    aa = 2
    overlay = Image.new("RGBA", (image_width * aa, image_height * aa), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    shifted = [((x - min_x) * aa, (y - min_y) * aa) for x, y in points]
    draw.line(
        shifted,
        fill=(rgb[0], rgb[1], rgb[2], alpha),
        width=max(1, line_width * aa),
        joint="curve",
    )
    overlay = overlay.resize((image_width, image_height), Image.Resampling.LANCZOS)
    return overlay, int(min_x), int(min_y)


def create_alpha_canvas_line(
    owner: Any,
    coordinates: tuple[Any, ...] | list[Any],
    *,
    fill: str,
    width: float,
    opacity: float,
    smooth: bool = False,
    tags: Any | None = None,
    state: str | None = None,
) -> int:
    """Draw one anchored line directly, using Canvas or Pillow by opacity."""
    growth = "right" if bool(smooth) else "down"
    shifted = one_sided_line_coordinates(
        tuple(coordinates),
        width=float(width or 1.0),
        growth=growth,
    )
    options: dict[str, Any] = {
        "fill": fill,
        "width": width,
    }
    if smooth:
        options["smooth"] = True
    if tags is not None:
        options["tags"] = tags
    if state is not None:
        options["state"] = state

    normalized = normalize_opacity(opacity)
    if normalized >= 100.0:
        return int(owner.canvas.create_line(*shifted, **options))
    if normalized <= 0.0:
        hidden = dict(options)
        hidden["state"] = "hidden"
        return int(owner.canvas.create_line(*shifted, **hidden))

    flattened = flatten_coordinates(tuple(shifted))
    if len(flattened) < 4:
        return int(owner.canvas.create_line(*shifted, **options))

    overlay, left, top = render_alpha_line_overlay(
        flattened,
        color=str(fill or "#000000"),
        width=float(width or 1.0),
        opacity=normalized,
        smooth=bool(smooth),
    )
    photo = ImageTk.PhotoImage(overlay)
    image_options: dict[str, Any] = {"anchor": "nw", "image": photo}
    if tags is not None:
        image_options["tags"] = tags
    if state in {"hidden", "disabled", "normal"}:
        image_options["state"] = state
    item = int(owner.canvas.create_image(left, top, **image_options))
    photos = owner.__dict__.setdefault("_pc_alpha_line_photos", {})
    photos[item] = photo
    return item


def clear_alpha_line_photos(owner: Any) -> None:
    owner.__dict__["_pc_alpha_line_photos"] = {}


def release_alpha_line_photos(owner: Any, item_ids: Iterable[int]) -> None:
    photos = owner.__dict__.get("_pc_alpha_line_photos", {})
    if not isinstance(photos, dict):
        return
    for item in item_ids:
        photos.pop(item, None)


def add_quick_opacity_control(app: Any, row: tk.Misc, *, name: str) -> None:
    """Create one final-position opacity Spinbox during normal app UI build."""
    if name in getattr(app, "quick_vars", {}):
        return
    current = normalize_opacity(getattr(app.settings, name, DEFAULT_DISPLAY_OPACITY))
    rendered = f"{current:.0f}" if abs(current - round(current)) < 1e-9 else f"{current:g}"
    variable = tk.StringVar(value=rendered)
    app.quick_vars[name] = variable
    app.quick_field_casts[name] = float
    ttk.Label(row, text="不透明度：").pack(side="left")
    spin = ttk.Spinbox(
        row,
        textvariable=variable,
        from_=0,
        to=100,
        increment=5,
        width=5,
    )
    spin.pack(side="left", padx=(2, 1))
    ttk.Label(row, text="%").pack(side="left", padx=(0, 8))
    variable.trace_add("write", lambda *_args: app._quick_parameter_changed())
    try:
        app._attach_tooltip(
            spin,
            "100%=完全不透明，0%=完全透明；只改变主画布显示，不改变识别、坐标或切图。",
        )
    except Exception:
        pass


def _descendants(root: tk.Misc):
    for child in root.winfo_children():
        yield child
        yield from _descendants(child)


def find_checkbutton(root: tk.Misc, text: str):
    """Compatibility helper retained for the separate illustration-fill seam."""
    for widget in _descendants(root):
        if not isinstance(widget, (ttk.Checkbutton, tk.Checkbutton)):
            continue
        try:
            if str(widget.cget("text") or "") == text:
                return widget
        except tk.TclError:
            continue
    return None


__all__ = [
    "DEFAULT_DISPLAY_OPACITY",
    "add_quick_opacity_control",
    "clear_alpha_line_photos",
    "create_alpha_canvas_line",
    "find_checkbutton",
    "flatten_coordinates",
    "normalize_opacity",
    "release_alpha_line_photos",
    "render_alpha_line_overlay",
]
