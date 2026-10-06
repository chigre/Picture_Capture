from __future__ import annotations

"""Static true-alpha rendering for editable PPP illustration fills."""

import math
import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable

from PIL import Image, ImageColor, ImageDraw, ImageTk

from .overlay_opacity import flatten_coordinates, normalize_opacity

DEFAULT_DISPLAY_OPACITY = 40.0


def render_alpha_polygon_overlay(
    coordinates: Iterable[float], *, color: str, opacity: float,
) -> tuple[Image.Image, int, int]:
    values = [float(value) for value in coordinates]
    if len(values) < 6 or len(values) % 2:
        raise ValueError("polygon coordinates must contain at least three XY points")
    points = list(zip(values[0::2], values[1::2]))
    min_x = math.floor(min(x for x, _y in points)) - 2
    min_y = math.floor(min(y for _x, y in points)) - 2
    max_x = math.ceil(max(x for x, _y in points)) + 2
    max_y = math.ceil(max(y for _x, y in points)) + 2
    width = max(1, int(max_x - min_x + 1))
    height = max(1, int(max_y - min_y + 1))
    rgb = ImageColor.getrgb(str(color or "#ffe66d"))[:3]
    alpha = round(normalize_opacity(opacity) * 255.0 / 100.0)
    aa = 2
    overlay = Image.new("RGBA", (width * aa, height * aa), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    shifted = [((x - min_x) * aa, (y - min_y) * aa) for x, y in points]
    draw.polygon(shifted, fill=(rgb[0], rgb[1], rgb[2], alpha))
    overlay = overlay.resize((width, height), Image.Resampling.LANCZOS)
    return overlay, int(min_x), int(min_y)


def create_alpha_canvas_polygon(
    owner: Any,
    coordinates: tuple[Any, ...] | list[Any],
    *,
    outline: str,
    fill: str,
    width: float,
    opacity: float,
    tags: Any | None = None,
) -> int:
    """Create the authoritative editable polygon and optional RGBA fill below it."""
    values = flatten_coordinates(tuple(coordinates))
    options: dict[str, Any] = {"outline": outline, "fill": fill, "width": width}
    if tags is not None:
        options["tags"] = tags
    if len(values) < 6:
        return int(owner.canvas.create_polygon(*coordinates, **options))

    normalized = normalize_opacity(opacity)
    if normalized >= 100.0:
        return int(owner.canvas.create_polygon(*coordinates, **options))

    outline_options = dict(options)
    outline_options["fill"] = ""
    fill_item: int | None = None
    photo = None
    if normalized > 0.0:
        overlay, left, top = render_alpha_polygon_overlay(
            values, color=str(fill or "#ffe66d"), opacity=normalized,
        )
        photo = ImageTk.PhotoImage(overlay)
        fill_tags = tuple(tags) if tags and not isinstance(tags, str) else ((tags,) if tags else ())
        fill_tags = tuple(tag for tag in fill_tags if tag) + ("pc-alpha-illustration-fill",)
        fill_item = int(owner.canvas.create_image(
            left, top, anchor="nw", image=photo, tags=fill_tags,
        ))

    polygon_item = int(owner.canvas.create_polygon(*coordinates, **outline_options))
    if fill_item is not None:
        try:
            owner.canvas.tag_lower(fill_item, polygon_item)
        except tk.TclError:
            pass
        owner.__dict__.setdefault("_pc_alpha_polygon_records", {})[polygon_item] = {
            "image_item": fill_item,
            "photo": photo,
        }
    return polygon_item


def clear_alpha_polygon_records(owner: Any) -> None:
    owner.__dict__["_pc_alpha_polygon_records"] = {}


def refresh_alpha_polygon_fill(owner: Any, region_index: int) -> None:
    records = owner.__dict__.get("_pc_alpha_polygon_records", {})
    canvas_records = getattr(owner, "_polygon_canvas_items", {})
    canvas_record = canvas_records.get(region_index) if isinstance(canvas_records, dict) else None
    if not isinstance(canvas_record, dict):
        return
    polygon_item = canvas_record.get("polygon")
    if polygon_item is None or not isinstance(records, dict):
        return
    record = records.get(polygon_item)
    if not isinstance(record, dict):
        return
    if not (0 <= int(region_index) < len(getattr(owner, "polygons", []))):
        return
    region = owner.polygons[int(region_index)]
    values = [
        float(value) * float(getattr(owner, "view_scale", 1.0) or 1.0)
        for point in region.points for value in point
    ]
    if len(values) < 6:
        return
    overlay, left, top = render_alpha_polygon_overlay(
        values,
        color=str(getattr(owner.settings, "illustration_fill_color", "#ffe66d")),
        opacity=getattr(owner.settings, "illustration_fill_opacity", DEFAULT_DISPLAY_OPACITY),
    )
    photo = ImageTk.PhotoImage(overlay)
    image_item = record.get("image_item")
    try:
        owner.canvas.coords(image_item, left, top)
        owner.canvas.itemconfigure(image_item, image=photo)
        owner.canvas.tag_lower(image_item, polygon_item)
    except tk.TclError:
        return
    record["photo"] = photo


def add_quick_illustration_fill_opacity_control(app: Any, row: tk.Misc) -> None:
    name = "illustration_fill_opacity"
    if name in getattr(app, "quick_vars", {}):
        return
    current = normalize_opacity(getattr(app.settings, name, DEFAULT_DISPLAY_OPACITY))
    variable = tk.StringVar(value=f"{current:.0f}" if abs(current - round(current)) < 1e-9 else f"{current:g}")
    app.quick_vars[name] = variable
    app.quick_field_casts[name] = float
    ttk.Label(row, text="区域不透明度：").pack(side="left", padx=(5, 0))
    spin = ttk.Spinbox(row, textvariable=variable, from_=0, to=100, increment=5, width=5)
    spin.pack(side="left", padx=(2, 1))
    ttk.Label(row, text="%").pack(side="left", padx=(0, 8))
    variable.trace_add("write", lambda *_args: app._quick_parameter_changed())
    try:
        app._attach_tooltip(spin, "插图区域背景的真实透明度；默认40%，不改变轮廓或PPP坐标。")
    except Exception:
        pass


__all__ = [
    "DEFAULT_DISPLAY_OPACITY",
    "add_quick_illustration_fill_opacity_control",
    "clear_alpha_polygon_records",
    "create_alpha_canvas_polygon",
    "refresh_alpha_polygon_fill",
    "render_alpha_polygon_overlay",
]
