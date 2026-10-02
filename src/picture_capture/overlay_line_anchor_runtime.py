from __future__ import annotations

"""Keep display-line thickness on the intended side of its structural anchor.

The stored/detected coordinates are boundaries, not visual centre lines:
- a headword marker's Y is its *top* anchor, so extra thickness grows downward;
- a column guide's X/path is its *right* anchor, so extra thickness grows left.

A one-pixel line therefore stays exactly where it was.  Only the additional
thickness beyond that original pixel is displaced to the requested side.  This
adapter patches the shared opacity renderer so the rule is identical for native
100% Canvas lines and Pillow RGBA semi-transparent lines.
"""

from functools import wraps
from typing import Any
import tkinter as tk
from tkinter import ttk

from . import overlay_opacity_runtime as opacity_runtime


def one_sided_line_coordinates(
    coordinates: tuple[Any, ...] | list[Any],
    *,
    width: float,
    growth: str,
) -> tuple[float, ...]:
    """Shift a centred stroke so added width grows only down or left.

    Width=1 is the historical reference stroke and is intentionally unchanged.
    For width W, only (W-1)/2 is used as the centre-line offset, preserving the
    original one-pixel footprint while placing all added thickness on one side.
    """

    values: tuple[Any, ...]
    if len(coordinates) == 1 and isinstance(coordinates[0], (list, tuple)):
        values = tuple(coordinates[0])
    else:
        values = tuple(coordinates)
    if len(values) < 4 or len(values) % 2:
        return tuple(float(value) for value in values)

    try:
        flattened = [float(value) for value in values]
        effective_width = max(1.0, float(width or 1.0))
    except (TypeError, ValueError):
        return tuple(float(value) for value in values)

    offset = max(0.0, (effective_width - 1.0) / 2.0)
    if offset <= 0.0:
        return tuple(flattened)

    normalized = str(growth or "").strip().lower()
    if normalized == "down":
        for index in range(1, len(flattened), 2):
            flattened[index] += offset
    elif normalized == "left":
        for index in range(0, len(flattened), 2):
            flattened[index] -= offset
    return tuple(flattened)


def _find_checkbutton(root: tk.Misc, text: str):
    for child in root.winfo_children():
        if isinstance(child, (ttk.Checkbutton, tk.Checkbutton)):
            try:
                if str(child.cget("text") or "") == text:
                    return child
            except tk.TclError:
                pass
        found = _find_checkbutton(child, text)
        if found is not None:
            return found
    return None


def _move_marker_opacity_after_height(app: Any) -> None:
    """Place marker opacity before the illustration-label controls on its row."""

    marker = _find_checkbutton(app, "词头横线")
    if marker is None:
        return
    row = marker.master
    target = _find_checkbutton(row, "插图标签：外框")
    if target is None:
        return

    packed = list(row.pack_slaves())
    opacity_label = None
    for widget in packed:
        if not isinstance(widget, ttk.Label):
            continue
        try:
            if str(widget.cget("text") or "") == "不透明度：":
                opacity_label = widget
                break
        except tk.TclError:
            continue
    if opacity_label is None:
        return

    try:
        start = packed.index(opacity_label)
    except ValueError:
        return
    # overlay_opacity_runtime creates exactly: label, Spinbox, '%' label.
    group = packed[start : start + 3]
    if len(group) != 3:
        return
    for widget in group:
        try:
            widget.pack_configure(before=target)
        except tk.TclError:
            return


def install_overlay_line_anchor_runtime(app_module: Any) -> None:
    """Install one-sided line growth and correct marker-opacity control order."""

    app_class = app_module.PictureCaptureApp
    if bool(getattr(app_class, "_pc_overlay_line_anchor_installed", False)):
        return

    native_alpha_canvas_line = opacity_runtime._alpha_canvas_line

    @wraps(native_alpha_canvas_line)
    def anchored_alpha_canvas_line(
        owner: Any,
        original_create_line,
        coordinates: tuple[Any, ...],
        options: dict[str, Any],
        *,
        opacity: float,
    ) -> int:
        # Column guides are the smooth paths; headword markers are straight.
        growth = "left" if bool(options.get("smooth", False)) else "down"
        shifted = one_sided_line_coordinates(
            coordinates,
            width=float(options.get("width") or 1.0),
            growth=growth,
        )
        return native_alpha_canvas_line(
            owner,
            original_create_line,
            shifted,
            options,
            opacity=opacity,
        )

    opacity_runtime._alpha_canvas_line = anchored_alpha_canvas_line

    # Clarify the directional meaning in Settings Center as well.
    help_map = dict(getattr(app_module.SettingsDialog, "SETTING_HELP", {}))
    if "marker_height" in help_map:
        help_map["marker_height"] = (
            str(help_map["marker_height"]).rstrip()
            + "\n\n粗细方向：词头横线的原始 Y 为上边界锚点；宽度增加时只向下方扩展，不向上遮挡词头。"
        )
    if "guide_width" in help_map:
        help_map["guide_width"] = (
            str(help_map["guide_width"]).rstrip()
            + "\n\n粗细方向：栏左路径为右边界锚点；宽度增加时只向左侧扩展，不向正文栏内扩展。"
        )
    app_module.SettingsDialog.SETTING_HELP = help_map

    original_init = app_class.__init__

    @wraps(original_init)
    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _move_marker_opacity_after_height(self)

    app_class.__init__ = wrapped_init
    app_class._pc_overlay_line_anchor_installed = True


__all__ = [
    "install_overlay_line_anchor_runtime",
    "one_sided_line_coordinates",
]
