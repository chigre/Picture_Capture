"""Canonical PPP drag, SECTION boundaries and main canvas mouse interactions.

Original PictureCaptureApp Tk callbacks remain on the class; this leaf owns
their implementation and uses only dependencies captured at call time.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tkinter as tk
    from ..models import PolygonRegion


@dataclass(frozen=True)
class CanvasPointerDeps:
    """Original live module symbols for an individual canvas interaction."""
    tk: object
    label_text: object
    user_edited_link: object
    messagebox: object
    polygon_delete_center: object
    refresh_alpha_polygon_fill: object
    PageSection: object
    nearest_polygon_segment: object
    WordEntry: object
    entry_allowed_by_page_template: object
    v_is_inside_sections: object
    column_index_for_click: object


def _sync_polygon_label_texts(self, deps: CanvasPointerDeps) -> None:
    """Carry edited association codes across redraw without reassigning IDs."""
    label_text = deps.label_text
    user_edited_link = deps.user_edited_link
    tk = deps.tk
    if self.__dict__.get("_suppress_polygon_label_sync", False):
        return
    bindings = list(getattr(self, "polygon_label_bindings", []))
    if not bindings or self.current_page is None:
        return
    expected = self._illustration_controller_for_call().preview_labels()
    for widget, region in bindings:
        try:
            index = next(i for i, item in enumerate(self.polygons) if item is region)
            typed = widget.get().strip()
            if typed != label_text(expected[index]):
                region.label = user_edited_link(expected[index], typed)
        except (tk.TclError, ValueError, IndexError, StopIteration):
            continue

def _nearest_polygon_vertex(self, deps: CanvasPointerDeps, x: int, y: int, radius_screen: float = 11.0) -> tuple[int, int] | None:
    if not self.polygons:
        return None
    radius_source = radius_screen / max(self.view_scale, 1e-6)
    best = None; best_d2 = radius_source * radius_source
    for ri, region in enumerate(self.polygons):
        for pi, (px, py) in enumerate(region.points):
            d2 = (px - x) ** 2 + (py - y) ** 2
            if d2 <= best_d2:
                best = (ri, pi); best_d2 = d2
    return best

def _nearest_polygon_edge(self, deps: CanvasPointerDeps, x: int, y: int, radius_screen: float = 9.0) -> tuple[int, str] | None:
    """Hit-test the four draggable sides of rectangular PPP regions."""
    radius_source = radius_screen / max(self.view_scale, 1e-6)
    best: tuple[int, str] | None = None
    best_distance = radius_source + 1
    for ri, region in enumerate(self.polygons):
        bounds = self._rectangle_bounds(region)
        if bounds is None:
            continue
        x0, y0, x1, y1 = bounds
        candidates = []
        if y0 - radius_source <= y <= y1 + radius_source:
            candidates.extend(((abs(x - x0), "left"), (abs(x - x1), "right")))
        if x0 - radius_source <= x <= x1 + radius_source:
            candidates.extend(((abs(y - y0), "top"), (abs(y - y1), "bottom")))
        for distance, side in candidates:
            if distance <= radius_source and distance < best_distance:
                best = (ri, side)
                best_distance = distance
    return best

def _delete_polygon_region(self, deps: CanvasPointerDeps, region: PolygonRegion) -> None:
    messagebox = deps.messagebox
    if self._batch_active and self._batch_allow_pdic_edits:
        self.status_var.set("插图识别期间暂不修改 PPP。")
        return
    if self.current_page is None:
        return
    try:
        index = next(i for i, candidate in enumerate(self.polygons) if candidate is region)
    except StopIteration:
        return
    name = self._polygon_display_name(region, index)
    if not messagebox.askyesno("删除PPP插图", f"删除插图：{name}？\n\n只删除当前这一个 PPP 区域。", parent=self):
        return
    self._sync_polygon_label_texts()
    if self._illustration_controller_for_call().delete_polygon(region):
        self._drag_polygon_vertex = None
        self._drag_polygon_edge = None
        self.status_var.set(f"已删除 PPP 插图：{name}")

def _polygon_label_canvas_position(self, deps: CanvasPointerDeps, region: PolygonRegion, widget: tk.Widget) -> tuple[float, float]:
    tk = deps.tk
    if not region.points:
        return 2.0, 2.0
    min_x = min(p[0] for p in region.points) * self.view_scale
    min_y = min(p[1] for p in region.points) * self.view_scale
    max_x = max(p[0] for p in region.points) * self.view_scale
    max_y = max(p[1] for p in region.points) * self.view_scale
    try:
        label_width = max(widget.winfo_reqwidth(), 1)
        label_height = max(widget.winfo_reqheight(), 1)
    except tk.TclError:
        label_width, label_height = 150, 24
    if self.image is not None:
        canvas_width = self.image.width * self.view_scale
        canvas_height = self.image.height * self.view_scale
    else:
        canvas_width = max(self.canvas.winfo_width(), 1)
        canvas_height = max(self.canvas.winfo_height(), 1)
    return self._external_polygon_label_position(
        min_x, min_y, max_x, max_y, label_width, label_height, canvas_width, canvas_height
    )

def _update_polygon_canvas_geometry(self, deps: CanvasPointerDeps, region_index: int) -> None:
    tk = deps.tk
    polygon_delete_center = deps.polygon_delete_center
    refresh_alpha_polygon_fill = deps.refresh_alpha_polygon_fill
    if not (0 <= region_index < len(self.polygons)):
        return
    region = self.polygons[region_index]
    record = self._polygon_canvas_items.get(region_index)
    if not record:
        return
    coords = [value * self.view_scale for point in region.points for value in point]
    try:
        self.canvas.coords(record["polygon"], *coords)
        for point_index, handle in enumerate(record.get("handles", [])):
            if point_index >= len(region.points):
                break
            px, py = region.points[point_index]
            cx, cy = px * self.view_scale, py * self.view_scale
            r = 5
            self.canvas.coords(handle, cx - r, cy - r, cx + r, cy + r)
        bounds = self._rectangle_bounds(region)
        edge_handles = record.get("edge_handles", {})
        if bounds is not None:
            x0, y0, x1, y1 = bounds
            mids = {
                "left": (x0, (y0 + y1) / 2),
                "right": (x1, (y0 + y1) / 2),
                "top": ((x0 + x1) / 2, y0),
                "bottom": ((x0 + x1) / 2, y1),
            }
            r = 5
            for side, item in edge_handles.items():
                mx, my = mids[side]
                cx, cy = mx * self.view_scale, my * self.view_scale
                self.canvas.coords(item, cx - r, cy - r, cx + r, cy + r)
        if record.get("delete_window") is not None:
            center_x, center_y = polygon_delete_center(region, self.view_scale)
            self.canvas.coords(record["delete_window"], center_x, center_y)
        if region.points and record.get("label_window") is not None:
            label_frame = record.get("label_frame")
            if label_frame is not None:
                label_x, label_y = self._polygon_label_canvas_position(region, label_frame)
                self.canvas.coords(record["label_window"], label_x, label_y)
    except tk.TclError:
        pass
    refresh_alpha_polygon_fill(self, region_index)

def _set_section_editing(self, deps: CanvasPointerDeps, active: bool) -> None:
    tk = deps.tk
    was_editing = bool(getattr(self, "_section_editing", False))
    self._section_editing = bool(active)
    self._drag_section_boundary = None
    try:
        self.canvas.configure(cursor="hand2" if self._section_editing else "")
    except tk.TclError:
        pass
    if self._section_editing:
        # SECTION dragging uses the page boundary lines themselves as the
        # pointer target. Hide the ordinary coordinate crosshair so it
        # cannot be confused with a SECTION boundary.
        self.cursor_canvas_xy = None
        try:
            self.canvas.delete("cursor-guide")
        except tk.TclError:
            pass
    elif was_editing:
        # Restore the ordinary pointer and coordinate crosshair immediately
        # at the current pointer position; the user should not have to move
        # the mouse once just to make the guides reappear.
        try:
            self.after_idle(self._restore_cursor_guides_after_section_edit)
        except tk.TclError:
            pass
    # Unlike a Tk variable, _section_editing is a plain bool: update the
    # button from this canonical edit-state transition, including double-click exit.
    from .workspace_mode_shortcuts import refresh_workspace_mode_shortcut_buttons
    refresh_workspace_mode_shortcut_buttons(self)

def _restore_cursor_guides_after_section_edit(self, deps: CanvasPointerDeps) -> None:
    tk = deps.tk
    if self._section_editing or self.image is None:
        return
    try:
        self.canvas.configure(cursor="")
        widget_x = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx()
        widget_y = self.canvas.winfo_pointery() - self.canvas.winfo_rooty()
        if not (
            0 <= widget_x < self.canvas.winfo_width()
            and 0 <= widget_y < self.canvas.winfo_height()
        ):
            return
        canvas_x = self.canvas.canvasx(widget_x)
        canvas_y = self.canvas.canvasy(widget_y)
        display_width = self.image.width * self.view_scale
        display_height = self.image.height * self.view_scale
        if not (0 <= canvas_x < display_width and 0 <= canvas_y < display_height):
            return
        self.cursor_canvas_xy = (canvas_x, canvas_y)
        self.draw_cursor_guides(canvas_x, canvas_y)
    except tk.TclError:
        return

def _finish_section_editing(self, deps: CanvasPointerDeps) -> bool:
    if not self._section_editing:
        return False
    self._persist_current_page_sections()
    self._set_section_editing(False)
    self.status_var.set(
        f"SECTION 编辑完成：当前页 {len(self.page_sections)} 个 SECTION"
    )
    self.redraw()
    return True

def _nearest_section_boundary(self, deps: CanvasPointerDeps, source_x: int, source_y: int) -> tuple[int, str] | None:
    if not self.page_sections or self.image is None:
        return None
    geometry = self._get_cached_display_geometry()
    _u, v = geometry.source_to_canonical(int(source_x), int(source_y))
    tolerance = max(4, round(10 / max(self.view_scale, 0.05)))
    candidates: list[tuple[int, int, str]] = []
    for index, section in enumerate(self.page_sections):
        candidates.append((abs(v - section.top_v), index, "top"))
        candidates.append((abs(v - section.bottom_v), index, "bottom"))
    distance, index, side = min(candidates, default=(10**9, -1, "top"))
    return (index, side) if distance <= tolerance else None

def _drag_page_section_boundary_to(self, deps: CanvasPointerDeps, source_x: int, source_y: int) -> None:
    PageSection = deps.PageSection
    target = self._drag_section_boundary
    if target is None or self.image is None:
        return
    index, side = target
    if not (0 <= index < len(self.page_sections)):
        return
    geometry = self._get_cached_display_geometry()
    _u, v = geometry.source_to_canonical(int(source_x), int(source_y))
    sections = list(self.page_sections)
    current = sections[index]
    min_height = max(6, round((geometry.bottom - geometry.top) * 0.005))
    if side == "top":
        lower = geometry.top if index == 0 else sections[index - 1].bottom_v
        upper = current.bottom_v - min_height
        new_top = max(lower, min(upper, int(v)))
        sections[index] = PageSection(new_top, current.bottom_v)
    else:
        lower = current.top_v + min_height
        upper = geometry.bottom if index + 1 == len(sections) else sections[index + 1].top_v
        new_bottom = max(lower, min(upper, int(v)))
        sections[index] = PageSection(current.top_v, new_bottom)
    self.page_sections = sections
    self._draw_page_sections(geometry)

def toggle_polygon_drawing(self, deps: CanvasPointerDeps) -> None:
    if self.ref_box_controller.pointer_active:
        self.ref_box_controller.stop_edit()
    if self._batch_active:
        self.status_var.set("批量任务期间暂不编辑 PPP；可校对已开放的 PDIC。")
        return
    if not self.guard(): return
    active = not self.polygon_draw_var.get()
    self.polygon_draw_var.set(active)
    if active:
        if self.polygons:
            self._sync_polygon_label_texts()
            self._save_normalized_ppp()
        if self._section_editing:
            self._set_section_editing(False)
        # Drawing must remain visible even if the ordinary display checkbox
        # was previously off. Keep saved polygons visible as context.
        self.polygon_var.set(True)
        if self.polygon_draw_button is not None:
            self.polygon_draw_button.configure(
                text="结束编辑插图", style="PC.EditActive.TButton"
            )
        self.status_var.set("插图编辑：Shift+单击边线加顶点；拖动调整，右键闭合新图形。")
    else:
        self.new_polygon.clear()
        if self.polygon_draw_button is not None:
            self.polygon_draw_button.configure(
                text="编辑插图", style="PC.Compact.TButton"
            )
        self.status_var.set("已退出插图多边形绘制模式")
    self.redraw()

def canvas_left_click(self, deps: CanvasPointerDeps, event: tk.Event) -> None:
    nearest_polygon_segment = deps.nearest_polygon_segment
    WordEntry = deps.WordEntry
    entry_allowed_by_page_template = deps.entry_allowed_by_page_template
    v_is_inside_sections = deps.v_is_inside_sections
    column_index_for_click = deps.column_index_for_click
    if self.ref_box_controller.pointer_active:
        return self.ref_box_controller.press(*self.original_xy(event)) if self.guard() else "break"
    if not self.guard():
        return
    x, y = self.original_xy(event)
    if not (0 <= x < self.image.width and 0 <= y < self.image.height):
        return
    # The line's [X] is a direct hit target, even outside auxiliary mode.
    if not self._section_editing and self._auxiliary_controller.delete_at_chip(x, y):
        return "break"
    # Shift+left adds an auxiliary line without requiring the mode toggle.
    # Preserve PPP Shift+click (add vertex) and SECTION Shift+drag.
    if (getattr(event, "state", 0) & 0x0001
            and not self._section_editing and not self.polygon_draw_var.get()):
        self._auxiliary_controller.add(x, y)
        return "break"
    if self._section_editing:
        target = self._nearest_section_boundary(x, y)
        if target is None:
            self.status_var.set("SECTION 编辑：请按住并拖动蓝色虚线上下边界。")
            return
        self._drag_section_boundary = target
        section_index, side = target
        side_text = "上边界" if side == "top" else "下边界"
        self.status_var.set(f"正在调整 SECTION {section_index + 1} {side_text}")
        return
    if self.auxiliary_mode_var.get():
        self._auxiliary_controller.click(x, y)
        return
    if self.polygon_draw_var.get():
        existing = self._nearest_polygon_vertex(x, y)
        if existing is not None:
            self._drag_polygon_vertex = existing
            self._drag_polygon_edge = None
            ri, pi = existing
            self.status_var.set(f"正在编辑PPP：拖动插图 {ri + 1} 的顶点 {pi + 1}")
            return
        if event.state & 1:
            segment = nearest_polygon_segment(self.polygons, x, y, view_scale=self.view_scale)
            if segment:
                ri, index, point = segment
                self.polygons[ri].points.insert(index, point)
                self._drag_polygon_vertex = (ri, index)
                self._drag_polygon_edge = None
                self.redraw()
                self.status_var.set("PPP顶点已增加；拖动并松开保存")
                return
        edge = self._nearest_polygon_edge(x, y)
        if edge is not None:
            self._drag_polygon_edge = edge
            self._drag_polygon_vertex = None
            ri, side = edge
            side_name = {"left": "左边", "right": "右边", "top": "上边", "bottom": "下边"}.get(side, side)
            self.status_var.set(f"正在编辑PPP：拖动插图 {ri + 1} 的{side_name}")
            return
        self.new_polygon.append((x, y))
        self.redraw()
        return
    effective = self._current_effective_profile_settings()
    if not entry_allowed_by_page_template(
        x, y, self.image.size, effective, max(0, int(self.current_index)),
    ):
        self.status_var.set("该位置属于 Project Profile 的页边排除区，不添加词条。")
        return
    geometry = self._get_cached_display_geometry()
    canonical_x, canonical_y = geometry.source_to_canonical(x, y)
    if canonical_y < geometry.top or canonical_y >= geometry.bottom:
        self.status_var.set("该位置位于正文区域之外，不添加词条。")
        return
    if self.page_sections and not v_is_inside_sections(
        canonical_y, self.page_sections, geometry.top, geometry.bottom,
    ):
        self.status_var.set("该位置位于 SECTION 间空白区，不添加词条。")
        return
    col = column_index_for_click(x, geometry, y)
    source_x, source_y = geometry.canonical_to_source(geometry.column_starts[col], canonical_y)
    # Only an actual canvas click may initiate a manual-add evidence event.
    queue_add = getattr(self, "_queue_proofreading_add_evidence", None)
    if callable(queue_add):
        queue_add(source_x, source_y)
    self.entries.append(WordEntry("", source_x, source_y))
    self._sort_entries_reading_order()
    self.redraw()

def canvas_left_drag(self, deps: CanvasPointerDeps, event: tk.Event) -> str | None:
    if self.ref_box_controller.pointer_active:
        return self.ref_box_controller.drag(*self.original_xy(event))
    if self._preprocess_mode_active():
        return "break"
    if self.image is None:
        return None
    x, y = self.original_xy(event)
    if self._drag_section_boundary is not None:
        x = max(0, min(self.image.width - 1, x))
        y = max(0, min(self.image.height - 1, y))
        self._drag_page_section_boundary_to(x, y)
        return "break"
    if self.auxiliary_mode_var.get():
        self._auxiliary_controller.drag(x, y)
        return "break"
    if not self.polygon_draw_var.get():
        return None
    x = max(0, min(self.image.width - 1, x))
    y = max(0, min(self.image.height - 1, y))
    if self._drag_polygon_vertex is not None:
        ri, pi = self._drag_polygon_vertex
        if not (0 <= ri < len(self.polygons) and 0 <= pi < len(self.polygons[ri].points)):
            self._drag_polygon_vertex = None
            return None
        self.polygons[ri].points[pi] = (x, y)
        self._update_polygon_canvas_geometry(ri)
        return "break"
    if self._drag_polygon_edge is not None:
        ri, side = self._drag_polygon_edge
        if not (0 <= ri < len(self.polygons)):
            self._drag_polygon_edge = None
            return None
        self._set_rectangle_side(self.polygons[ri], side, x if side in {"left", "right"} else y)
        self._update_polygon_canvas_geometry(ri)
        return "break"
    return None

def canvas_left_release(self, deps: CanvasPointerDeps, _event: tk.Event) -> str | None:
    if self.ref_box_controller.pointer_active:
        return self.ref_box_controller.release(*self.original_xy(_event))
    if self._preprocess_mode_active():
        return "break"
    if self.auxiliary_mode_var.get():
        self._auxiliary_controller.release()
        return "break"
    if self._drag_section_boundary is not None:
        self._drag_section_boundary = None
        try:
            self._persist_current_page_sections()
            self._sort_entries_reading_order()
            gap_count = self._section_gap_entry_count()
            self.redraw()
            if gap_count:
                self.status_var.set(
                    f"SECTION 边界已保存；有 {gap_count} 条现有词条落在 SECTION 间空白，请调整边界。"
                )
            else:
                self.status_var.set("SECTION 边界已保存")
        except Exception as exc:
            self.show_error("保存 SECTION 边界失败", exc)
        return "break"
    target_vertex = self._drag_polygon_vertex
    target_edge = self._drag_polygon_edge
    if target_vertex is None and target_edge is None:
        return None
    self._drag_polygon_vertex = None
    self._drag_polygon_edge = None
    if self.current_page is not None:
        try:
            self._sync_polygon_label_texts()
            if self._illustration_controller_for_call().persist_current(redraw=True):
                self.status_var.set("PPP轮廓已调整并保存")
        except Exception as exc:
            self.show_error("保存PPP轮廓失败", exc)
    return "break"

def canvas_right_click(self, deps: CanvasPointerDeps, event: tk.Event) -> None:
    if self.ref_box_controller.pointer_active:
        return self.ref_box_controller.context_menu(event)
    if getattr(event, "state", 0) & 0x0001:
        self._canvas_shift_right_click(event)
        return
    if self.auxiliary_mode_var.get():
        if self.guard():
            self._auxiliary_controller.delete_at(*self.original_xy(event))
        return
    if self._section_editing:
        self.status_var.set("SECTION 编辑中；点击【结束SECTION】保存并退出。")
        return
    if self.polygon_draw_var.get():
        if not self.guard(): return
        points = self.new_polygon.copy()
        self.new_polygon.clear()
        if len(points) >= 3:
            if self._illustration_controller_for_call().add_manual_polygon(points):
                self.status_var.set("已保存插图，整页序号已按阅读顺序更新")
            else:
                self.redraw()
        else:
            self.redraw()
        return
    if not self.project or not self.current_page or self.image is None:
        return
    # Navigation must not claim/lock a pending OCR-batch page. Only actual
    # foreground edits reserve pages from the background runner.
    self.change_page(1)



# Physical PPP label, rectangle and SECTION geometry callbacks.

def _polygon_display_name(region: PolygonRegion, index: int, *, deps: dict[str, Any]) -> str:
    label_text = deps["label_text"]
    return label_text(region.label) or f"P_{index + 1:02d}"

def _set_polygon_display_name(self, region: PolygonRegion, name: str, *, deps: dict[str, Any]) -> None:
    user_edited_link = deps["user_edited_link"]
    """Compatibility setter: accept only association-code changes."""
    region.label = user_edited_link(region.label, name)

def _update_polygon_label(self, region: PolygonRegion, widget: tk.Entry, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    label_text = deps["label_text"]
    if self._batch_active and self._batch_allow_pdic_edits:
        return
    try:
        text = widget.get().strip()
    except tk.TclError:
        return
    if self._illustration_controller_for_call().update_label(region, text):
        self.status_var.set(f"PPP标签已保存：{label_text(region.label)}")
    try:
        widget.delete(0, tk.END)
        widget.insert(0, label_text(region.label))
    except tk.TclError:
        pass

def _commit_polygon_label_return(self, region: PolygonRegion, widget: tk.Entry, *, deps: dict[str, Any]) -> str:
    tk = deps["tk"]
    self._update_polygon_label(region, widget)
    try:
        self.canvas.focus_set()
    except tk.TclError:
        pass
    return "break"

def _rectangle_bounds(region: PolygonRegion, tolerance: int = 2) -> tuple[int, int, int, int] | None:
    """Return bounds when a four-point PPP is an axis-aligned rectangle."""
    if len(region.points) != 4:
        return None
    xs = [p[0] for p in region.points]
    ys = [p[1] for p in region.points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 - x0 <= tolerance or y1 - y0 <= tolerance:
        return None
    expected = {(x0, y0), (x1, y0), (x1, y1), (x0, y1)}
    for px, py in region.points:
        if not any(abs(px - ex) <= tolerance and abs(py - ey) <= tolerance for ex, ey in expected):
            return None
    return x0, y0, x1, y1

def _set_rectangle_side(region: PolygonRegion, side: str, value: int, *, deps: dict[str, Any]) -> None:
    PictureCaptureApp = deps["PictureCaptureApp"]
    bounds = PictureCaptureApp._rectangle_bounds(region)
    if bounds is None:
        return
    x0, y0, x1, y1 = bounds
    if side == "left":
        value = min(value, x1 - 1)
        region.points = [(value if abs(x - x0) <= 2 else x, y) for x, y in region.points]
    elif side == "right":
        value = max(value, x0 + 1)
        region.points = [(value if abs(x - x1) <= 2 else x, y) for x, y in region.points]
    elif side == "top":
        value = min(value, y1 - 1)
        region.points = [(x, value if abs(y - y0) <= 2 else y) for x, y in region.points]
    elif side == "bottom":
        value = max(value, y0 + 1)
        region.points = [(x, value if abs(y - y1) <= 2 else y) for x, y in region.points]

def _external_polygon_label_position(
    min_x: float, min_y: float, max_x: float, max_y: float,
    label_width: int, label_height: int, canvas_width: float, canvas_height: float,
    gap: int = 6,
) -> tuple[float, float]:
    """Position label above the figure, aligned to its left edge."""
    margin = 2.0
    x = max(margin, min(min_x, max(margin, canvas_width - label_width - margin)))
    y = min_y - gap - label_height
    if y < margin:
        y = min(max(margin, min_y + gap), max(margin, canvas_height - label_height - margin))
    return x, y

def _section_gap_entry_count(self, *, deps: dict[str, Any]) -> int:
    v_is_inside_sections = deps["v_is_inside_sections"]
    if not self.page_sections:
        return 0
    geometry = self._get_cached_display_geometry()
    return sum(
        1 for entry in self.entries
        if not v_is_inside_sections(
            geometry.source_to_canonical(entry.x, entry.y)[1],
            self.page_sections, geometry.top, geometry.bottom,
        )
    )
