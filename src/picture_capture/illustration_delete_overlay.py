"""Standalone PPP shape-linked delete overlay."""
from __future__ import annotations

import tkinter as tk

from .illustration_delete_geometry import interior_polygon_center


def polygon_delete_center(region, scale: float) -> tuple[float, float]:
    if not region.points:
        return 0.0, 0.0
    x, y = interior_polygon_center(region.points)
    return x * scale, y * scale


def create_illustration_delete_control(app, region, region_index: int) -> int:
    button = tk.Button(
        app.canvas, text="[X]", padx=3, pady=1, relief="flat", bd=0,
        highlightthickness=0, bg="#bdbdbd", activebackground="#a5a5a5",
        fg="#202020", activeforeground="#202020", font=("TkDefaultFont", 16),
        command=lambda: app._delete_polygon_region(region),
    )
    app.overlay_widgets.append(button)
    x, y = polygon_delete_center(region, app.view_scale)
    return app.canvas.create_window(
        x, y, window=button, anchor="center",
        tags=("ppp-overlay", f"ppp-delete-{region_index}"),
    )
