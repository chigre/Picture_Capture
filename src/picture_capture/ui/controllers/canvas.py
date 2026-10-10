from __future__ import annotations

from typing import Any
import tkinter as tk
from tkinter import ttk


class CanvasController:
    """Coordinate main-canvas display modes and viewport interactions.

    Rendering, image caches, geometry derivation, and editing state remain owned by
    ``PictureCaptureApp``.  This controller only coordinates existing UI state and
    delegates repaint/status work back to the app.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def display_mode_from_flags(self) -> str:
        app = self.app
        if app.crop_preview_var.get():
            return "切图预览"
        binary = bool(app.binary_preview_var.get())
        hidden = bool(app.hide_var.get())
        if hidden:
            return "仅二值" if binary else "仅原图"
        return "二值+标注" if binary else "原图+标注"

    def sync_display_mode_from_flags(self) -> None:
        app = self.app
        if getattr(app, "_display_mode_syncing", False):
            return
        try:
            app._display_mode_syncing = True
            app.display_mode_var.set(self.display_mode_from_flags())
        finally:
            app._display_mode_syncing = False

    def apply_display_mode(self, _event: Any = None) -> None:
        app = self.app
        states = {
            "原图+标注": (False, False, False),
            "二值+标注": (True, False, False),
            "仅原图": (False, True, False),
            "仅二值": (True, True, False),
            "切图预览": (False, False, True),
        }
        mode = str(app.display_mode_var.get() or "原图+标注")
        binary, hidden, crop_preview = states.get(mode, states["原图+标注"])
        previous_binary = bool(app.binary_preview_var.get())
        try:
            app._display_mode_syncing = True
            app.binary_preview_var.set(binary)
            app.hide_var.set(hidden)
            app.crop_preview_var.set(crop_preview)
        finally:
            app._display_mode_syncing = False
        if previous_binary != binary:
            app.photo = None
            app._display_photo_cache_key = None
        if crop_preview:
            app.status_var.set(
                "切图预览：普通编辑线框已临时隐藏；切回其他显示模式即可恢复编辑。"
            )
        app.redraw()

    def toggle_binary_preview(self) -> None:
        app = self.app
        app.photo = None
        app._display_photo_cache_key = None
        self.sync_display_mode_from_flags()
        app.redraw()

    def toggle_hide_overlays(self) -> None:
        app = self.app
        if app.hide_var.get() and app.crop_preview_var.get():
            app.crop_preview_var.set(False)
        self.sync_display_mode_from_flags()
        app.redraw()

    def toggle_crop_preview(self) -> None:
        app = self.app
        if app.crop_preview_var.get():
            if app.binary_preview_var.get():
                app.binary_preview_var.set(False)
                app.photo = None
                app._display_photo_cache_key = None
            app.hide_var.set(False)
            app.status_var.set(
                "切图预览：普通编辑线框已临时隐藏；关闭预览即可恢复编辑。"
            )
        self.sync_display_mode_from_flags()
        app.redraw()

    def rulers_visible(self) -> bool:
        app = self.app
        if app.image is None:
            return False
        visible = (
            app.quick_bool_vars.get("show_rulers").get()
            if hasattr(app, "quick_bool_vars") and "show_rulers" in app.quick_bool_vars
            else bool(getattr(app.settings, "show_rulers", False))
        )
        return bool(visible)

    def draw_percentage_rulers(self, geometry=None) -> None:
        """Draw four fixed percentage rulers on the page edges."""
        _ = geometry
        app = self.app
        if not self.rulers_visible() or app.image is None:
            return
        display_width = float(max(1, app.image.width - 1)) * app.view_scale
        display_height = float(max(1, app.image.height - 1)) * app.view_scale
        color = str(getattr(app.settings, "ruler_color", "#1976d2") or "#1976d2")
        margin = 28
        margin_color = str(
            getattr(app, "_main_ui_colors", {}).get(
                "ruler_margin",
                "#20252b" if app.appearance_mode == "dark" else "#f1f3f6",
            )
        )
        app.canvas.create_rectangle(
            -margin, 0, 0, display_height + margin,
            fill=margin_color, outline="", tags=("ruler-margin",),
        )
        app.canvas.create_rectangle(
            display_width, 0, display_width + margin, display_height + margin,
            fill=margin_color, outline="", tags=("ruler-margin",),
        )
        app.canvas.create_rectangle(
            0, display_height, display_width, display_height + margin,
            fill=margin_color, outline="", tags=("ruler-margin",),
        )

        major_tick = 7
        minor_tick = 4
        label_gap = major_tick + 2
        font_spec = ("TkDefaultFont", 8)

        for ruler_id, y in (("top", 0.0), ("bottom", display_height)):
            tags = ("measurement-ruler", "ruler-horizontal", f"ruler-{ruler_id}")
            app.canvas.create_line(
                0, y, display_width, y,
                fill=color, width=1, tags=tags,
            )
            for half_percent in range(201):
                pct = half_percent * 0.5
                x = display_width * pct / 100.0
                tick = major_tick if half_percent % 2 == 0 else minor_tick
                app.canvas.create_line(
                    x, y - tick, x, y + tick,
                    fill=color, width=1, tags=tags,
                )
            for value in range(5, 100, 5):
                x = display_width * value / 100.0
                app.canvas.create_text(
                    x, y + label_gap, text=str(value), fill=color,
                    anchor="n", font=font_spec, tags=tags,
                )

        for ruler_id, x in (("left", 0.0), ("right", display_width)):
            tags = ("measurement-ruler", "ruler-vertical", f"ruler-{ruler_id}")
            app.canvas.create_line(
                x, 0, x, display_height,
                fill=color, width=1, tags=tags,
            )
            for half_percent in range(201):
                pct = half_percent * 0.5
                y = display_height * pct / 100.0
                tick = major_tick if half_percent % 2 == 0 else minor_tick
                app.canvas.create_line(
                    x - tick, y, x + tick, y,
                    fill=color, width=1, tags=tags,
                )
            label_x = x - label_gap if ruler_id == "left" else x + label_gap
            anchor = "e" if ruler_id == "left" else "w"
            for value in range(5, 100, 5):
                y = display_height * value / 100.0
                app.canvas.create_text(
                    label_x, y, text=str(value), fill=color,
                    anchor=anchor, font=font_spec, tags=tags,
                )

    def ruler_hit_id(self, source_x: float, source_y: float) -> str | None:
        app = self.app
        if not self.rulers_visible() or app.image is None:
            return None
        max_x = float(max(1, app.image.width - 1))
        max_y = float(max(1, app.image.height - 1))
        tolerance = max(3.0, 8.0 / max(0.05, float(app.view_scale)))
        distances = {
            "top": abs(float(source_y)),
            "bottom": abs(float(source_y) - max_y),
            "left": abs(float(source_x)),
            "right": abs(float(source_x) - max_x),
        }
        ruler_id, distance = min(distances.items(), key=lambda item: item[1])
        return ruler_id if distance <= tolerance else None

    def hide_ruler_hint(self) -> None:
        app = self.app
        popup = getattr(app, "_ruler_hint", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
        app._ruler_hint = None

    def show_ruler_hint(self, event: Any) -> None:
        app = self.app
        text = "标尺可以帮助版面参数的手动填写。"
        popup = getattr(app, "_ruler_hint", None)
        if popup is None:
            popup = tk.Toplevel(app.canvas)
            popup.wm_overrideredirect(True)
            ttk.Label(
                popup, text=text, padding=(7, 4), relief="solid",
            ).pack()
            app._ruler_hint = popup
        try:
            popup.wm_geometry(f"+{event.x_root + 14}+{event.y_root + 18}")
        except tk.TclError:
            app._ruler_hint = None

    def update_view_zoom_label(self) -> None:
        app = self.app
        if hasattr(app, "view_zoom_var"):
            app.view_zoom_var.set(f"{round(app.view_scale * 100):d}%")

    def zoom(self, factor: float) -> None:
        app = self.app
        if app.image:
            app.view_scale = min(3.0, max(0.08, app.view_scale * factor))
            app._update_view_zoom_label()
            app.redraw()
            app._set_idle_cursor_status()

    def apply_view_zoom_text(self, _event: Any = None) -> None:
        app = self.app
        if not app.image:
            return
        try:
            percent = float(app.view_zoom_var.get().strip().rstrip("%"))
        except ValueError:
            app._update_view_zoom_label()
            return
        app.view_scale = min(3.0, max(0.08, percent / 100.0))
        app._update_view_zoom_label()
        app.redraw()
        app._set_idle_cursor_status()

    def fit_page_width(self) -> None:
        app = self.app
        if not app.image:
            return
        app.update_idletasks()
        available = max(1, app.canvas.winfo_width())
        app.view_scale = min(3.0, max(0.08, available / app.image.width))
        app._update_view_zoom_label()
        app.redraw()
        app._set_idle_cursor_status()
        app.canvas.xview_moveto(0.0)

    def fit_page_height(self) -> None:
        app = self.app
        if not app.image:
            return
        app.update_idletasks()
        available = max(1, app.canvas.winfo_height())
        app.view_scale = min(3.0, max(0.08, available / app.image.height))
        app._update_view_zoom_label()
        app.redraw()
        app._set_idle_cursor_status()
        app.canvas.yview_moveto(0.0)

    def canvas_mousewheel(self, event: Any) -> str:
        step = -1 if event.delta > 0 else 1
        self.app.canvas.yview_scroll(step * 3, "units")
        return "break"

    def canvas_shift_mousewheel(self, event: Any) -> str:
        step = -1 if event.delta > 0 else 1
        self.app.canvas.xview_scroll(step * 3, "units")
        return "break"

    def canvas_ctrl_mousewheel(self, event: Any) -> str:
        self.zoom(1.15 if event.delta > 0 else 0.87)
        return "break"

    def canvas_linux_mousewheel(self, event: Any, step: int) -> str:
        app = self.app
        if event.state & 0x0004:
            self.zoom(0.87 if step > 0 else 1.15)
        elif event.state & 0x0001:
            app.canvas.xview_scroll(step * 3, "units")
        else:
            app.canvas.yview_scroll(step * 3, "units")
        return "break"

    def original_xy(self, event: Any) -> tuple[int, int]:
        app = self.app
        return (
            round(app.canvas.canvasx(event.x) / app.view_scale),
            round(app.canvas.canvasy(event.y) / app.view_scale),
        )

    def draw_cursor_guides(self, canvas_x: float, canvas_y: float) -> None:
        """Draw the blue dashed crosshair in the current canvas view."""
        app = self.app
        app.canvas.delete("cursor-guide")
        if app.image is None or app._section_editing:
            return
        width = app.image.width * app.view_scale
        height = app.image.height * app.view_scale
        if not (0 <= canvas_x < width and 0 <= canvas_y < height):
            return
        style = dict(fill="#1976d2", width=1, dash=(4, 4), tags=("cursor-guide",))
        app.canvas.create_line(0, canvas_y, width, canvas_y, **style)
        app.canvas.create_line(canvas_x, 0, canvas_x, height, **style)
        app.canvas.tag_raise("cursor-guide")

    def canvas_leave(self, _event: Any) -> None:
        app = self.app
        app.cursor_canvas_xy = None
        app.canvas.delete("cursor-guide")
        app._hide_ruler_hint()
        app._set_idle_cursor_status()

    def set_idle_cursor_status(self) -> None:
        app = self.app
        zoom = round(app.view_scale * 100)
        if app._preprocess_mode_active():
            app.cursor_status_var.set(f"坐标：—｜预处理预览｜缩放 {zoom}%")
        else:
            app.cursor_status_var.set(f"坐标：—｜缩放 {zoom}%｜词条 {len(app.entries)}")
