"""Canvas interactions for independent, undoable auxiliary crop lines."""
from __future__ import annotations

from .auxiliary_lines import AuxiliaryLine, AuxiliaryLineEdits, read_auxiliary_lines, write_auxiliary_lines
from .processing import column_index_for_click
from .page_sections import v_is_inside_sections
from .overlay_layout_helpers import (
    canonical_headword_marker_span, effective_overlay_column_width,
)
from .ui.overlay_delete_button import create_overlay_delete_button


class AuxiliaryLineController:
    def __init__(self, app):
        self.app = app

    def toggle_mode(self):
        app = self.app
        if app.auxiliary_mode_var.get() and (app.polygon_draw_var.get() or app._section_editing):
            app.auxiliary_mode_var.set(False)
            app.status_var.set("请先结束 PPP/SECTION 编辑，再启用辅助线模式")
            return
        app.redraw()

    def load_page(self, page):
        self.app._auxiliary_edits = AuxiliaryLineEdits(read_auxiliary_lines(page))
        self.app._auxiliary_drag = None

    def _source_line(self, x, y):
        app = self.app
        geometry = app._get_cached_display_geometry()
        _, v = geometry.source_to_canonical(x, y)
        if app.page_sections and not v_is_inside_sections(
            v, app.page_sections, geometry.top, geometry.bottom,
        ):
            return None
        col = column_index_for_click(x, geometry, y)
        sx, sy = geometry.canonical_to_source(geometry.column_starts[col], v)
        return AuxiliaryLine(int(sx), int(sy))

    def _nearest(self, x, y):
        app = self.app
        geometry = app._get_cached_display_geometry()
        u, v = geometry.source_to_canonical(x, y)
        scale = max(float(app.view_scale), 1e-6)
        tolerance = 11.0 / scale
        found = None
        distance = tolerance
        for i, line in enumerate(app._auxiliary_edits.lines):
            au, av = geometry.source_to_canonical(line.x, line.y)
            column = column_index_for_click(line.x, geometry, line.y)
            left = geometry.column_starts[column]
            _, right = canonical_headword_marker_span(
                left,
                effective_overlay_column_width(
                    geometry, column, app.settings.column_width,
                ),
                app.settings.right_ratio,
            )
            if not left <= u <= right:
                continue
            if abs(v - av) < distance:
                found = i
                distance = abs(v - av)
        return found

    def _persist(self, verb):
        app = self.app
        write_auxiliary_lines(app.current_page, app._auxiliary_edits.lines)
        app.redraw()
        app.status_var.set(f"辅助线{verb}；独立存储，不计入 PDIC 词条")

    def add(self, x, y):
        """Shift-click always inserts, even if a nearby line could be dragged."""
        app = self.app
        marker = self._source_line(x, y)
        if marker is None:
            app.status_var.set("辅助线不能放在 SECTION 间空白区域")
            return
        app._auxiliary_edits.add(marker)
        self._persist("已添加")

    def click(self, x, y):
        app = self.app
        idx = self._nearest(x, y)
        if idx is not None:
            app._auxiliary_drag = (idx, None)
            return
        self.add(x, y)

    def delete_at_chip(self, x, y):
        """Click the visible [X] chip without modifying the PDIC marker rows."""
        scale = max(0.01, float(self.app.view_scale))
        px, py = x * scale, y * scale
        for left, top, right, bottom, index in getattr(
            self.app, "_auxiliary_delete_hitboxes", ()
        ):
            if left <= px <= right and top <= py <= bottom:
                self.delete_index(index)
                return True
        return False

    def delete_index(self, index: int) -> None:
        """Delete the explicitly bound auxiliary row without touching PDIC."""
        if self.app._auxiliary_edits.delete(index):
            self._persist("已删除")

    def drag(self, x, y):
        app = self.app
        active = app._auxiliary_drag
        if active is None:
            return
        marker = self._source_line(x, y)
        if marker is None:
            return
        app._auxiliary_drag = (active[0], marker)
        app.redraw()

    def release(self):
        app = self.app
        active = app._auxiliary_drag
        app._auxiliary_drag = None
        if active is None or active[1] is None:
            return
        if app._auxiliary_edits.move(active[0], active[1]):
            self._persist("已移动")

    def delete_at(self, x, y):
        idx = self._nearest(x, y)
        if idx is None:
            return
        if self.app._auxiliary_edits.delete(idx):
            self._persist("已删除")

    def undo(self, _event=None):
        app = self.app
        if not app.auxiliary_mode_var.get():
            return None
        if app._auxiliary_edits.undo():
            self._persist("已撤销")
        return "break"

    def redraw(self):
        app = self.app
        if app.image is None:
            return
        lines = app._auxiliary_edits.lines
        app._auxiliary_delete_hitboxes = []
        if not lines:
            return
        geometry = app._get_cached_display_geometry()
        scale = float(app.view_scale)
        preview = app._auxiliary_drag
        for i, marker in enumerate(lines):
            if preview and preview[0] == i and preview[1] is not None:
                marker = preview[1]
            _u, v = geometry.source_to_canonical(marker.x, marker.y)
            col = column_index_for_click(marker.x, geometry, marker.y)
            x0 = geometry.column_starts[col]
            x0, x1 = canonical_headword_marker_span(
                x0,
                effective_overlay_column_width(
                    geometry, col, app.settings.column_width,
                ),
                app.settings.right_ratio,
            )
            left = geometry.canonical_to_source(x0, v)
            right = geometry.canonical_to_source(x1, v)
            app.canvas.create_line(
                left[0] * scale, left[1] * scale,
                right[0] * scale, right[1] * scale,
                fill="#d97706", width=2, dash=(6, 3),
                tags=("auxiliary-overlay",),
            )
            if app.auxiliary_mode_var.get():
                app.canvas.create_rectangle(
                    marker.x * scale - 4, marker.y * scale - 4,
                    marker.x * scale + 4, marker.y * scale + 4,
                    fill="#ffffff", outline="#d97706",
                    tags=("auxiliary-overlay",),
                )
            # A native Tk Button shares font/colours/cursor/tooltip with
            # headword [X]. Its cursor is hand2 only while hovered; on leaving
            # Tk restores the normal canvas cursor automatically.
            # Keep the widget in overlay_widgets for app.redraw cleanup.
            max_x = float(app.image.width) * scale
            max_y = float(app.image.height) * scale
            line_right = max(float(left[0]), float(right[0])) * scale
            line_y = (float(left[1]) + float(right[1])) * 0.5 * scale
            button = create_overlay_delete_button(
                app.canvas,
                command=lambda index=i: self.delete_index(index),
                attach_tooltip=app._attach_tooltip,
                tooltip="点击删除该辅助线!",
                ocr_language=app.settings.ocr_language,
                kind="auxiliary",
            )
            app.overlay_widgets.append(button)
            chip_width = max(1, button.winfo_reqwidth())
            chip_height = max(1, button.winfo_reqheight())
            # Align the button's right border with the drawn horizontal
            # segment's rightmost endpoint; never slide it toward the page
            # edge or beyond the configured right_ratio.
            right_edge = line_right
            top_edge = max(0.0, min(max_y - chip_height, line_y))
            # Legacy canvas-click hit routing is retained; the native widget
            # itself handles ordinary clicks and hover events.
            box = (
                right_edge - chip_width, top_edge,
                right_edge, top_edge + chip_height,
            )
            app._auxiliary_delete_hitboxes.append((*box, i))
            app.canvas.create_window(
                right_edge, top_edge, window=button, anchor="ne",
                tags=("auxiliary-overlay", "auxiliary-delete"),
            )
