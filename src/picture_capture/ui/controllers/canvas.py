from __future__ import annotations

from typing import Any


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
        available = max(120, app.canvas.winfo_width() - 24)
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
        available = max(120, app.canvas.winfo_height() - 24)
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
