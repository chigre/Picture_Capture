"""Standalone PPP shape-linked delete overlay."""
from __future__ import annotations

import tkinter as tk

from .illustration_delete_geometry import interior_polygon_center
from .ui.overlay_delete_button import fixed_overlay_control_font


def polygon_delete_center(region, scale: float) -> tuple[float, float]:
    if not region.points:
        return 0.0, 0.0
    x, y = interior_polygon_center(region.points)
    return x * scale, y * scale


def create_illustration_delete_control(app, region, region_index: int) -> int:
    button = tk.Button(
        app.canvas,
        text="[X]",
        width=3,
        font=fixed_overlay_control_font(app.canvas, app.settings.ocr_language),
        takefocus=False,
        relief="flat",
        bd=0,
        highlightthickness=0,
        padx=1,
        pady=0,
        cursor="hand2",
        fg="#222222",
        bg="#bdbdbd",
        activeforeground="#222222",
        activebackground="#a5a5a5",
        command=lambda: app._delete_polygon_region(region),
    )
    button._pc_skip_classic_appearance = True
    if callable(getattr(app, "_attach_tooltip", None)):
        app._attach_tooltip(button, "删除插图")
    app.overlay_widgets.append(button)
    x, y = polygon_delete_center(region, app.view_scale)
    return app.canvas.create_window(
        x, y, window=button, anchor="center",
        tags=("ppp-overlay", f"ppp-delete-{region_index}"),
    )
