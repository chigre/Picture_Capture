"""REF rectangle editor: page-local disk-first edits and canvas interactions.

No modifications to PDIC, PPP, OCR decisions, Profile or SECTION. Undo/Redo
is scoped to this single .rbox file and guarded by its current byte hash.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from PIL import Image, ImageColor, ImageTk

from ..ref_boxes import (
    RefBox, next_ref_id, read_ref_boxes, ref_box_ticket, write_ref_boxes,
)
from ..ref_box_geometry import hit_test, transform_box, action_cursor
from ..ref_box_detection import (
    add_ref_sample, associate_ref_to_entry, detect_ref_boxes_job,
    list_ref_samples,
)


class RefBoxController:
    def __init__(self, app):
        self.app = app
        self.editing = False
        self.capture_sample = False
        self.loaded_page: Path | None = None
        self.boxes: list[RefBox] = []
        self.ticket: str | None = None
        self.undo_stack: list[list[RefBox]] = []
        self.redo_stack: list[list[RefBox]] = []
        self.drag_start: tuple[int, int] | None = None
        self.drag_kind: str = "create"
        self.drag_original: RefBox | None = None
        self.drag_box: RefBox | None = None
        self.selected_id: int | None = None
        self._overlay_images: list[ImageTk.PhotoImage] = []
        self.pointer_action: str | None = None

    def load_page(self, page: Path) -> None:
        """Fail closed on corrupt files instead of dropping manually entered rows."""
        self.capture_sample = False
        self.cancel_drag()
        self.selected_id = None
        self.loaded_page = None
        self.boxes = []
        self.ticket = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        try:
            boxes = read_ref_boxes(page)
            ticket = ref_box_ticket(page)
        except (ValueError, OSError) as exc:
            self.stop_edit()
            self.app.status_var.set(f"REF 读取失败；本页 REF 编辑已锁定：{exc}")
            return
        self.loaded_page = Path(page)
        self.boxes, self.ticket = boxes, ticket

    def _ready(self) -> bool:
        return (self.loaded_page is not None
                and self.app.current_page == self.loaded_page
                and self.app.image is not None)

    def _commit(self, proposed: list[RefBox], *, history: bool = True) -> bool:
        if not self._ready():
            self.app.status_var.set("REF 尚未安全加载；不可保存")
            return False
        if proposed == self.boxes:
            return True
        before = list(self.boxes)
        try:
            new_ticket = write_ref_boxes(
                self.loaded_page, proposed, expected_ticket=self.ticket,
            )
        except Exception as exc:
            # Atomic replacement may have succeeded before an error in a
            # post-write hook/verification. Re-read authoritative disk state.
            try:
                self.boxes = read_ref_boxes(self.loaded_page)
                self.ticket = ref_box_ticket(self.loaded_page)
            except Exception:
                self.loaded_page = None
                self.boxes = []
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.app.show_error("保存 REF 框失败；请复核页面", exc)
            self.app.redraw()
            return False
        self.boxes, self.ticket = list(proposed), new_ticket
        if history:
            self.undo_stack.append(before)
            self.undo_stack = self.undo_stack[-100:]
            self.redo_stack.clear()
        self.app.redraw()
        return True

    def undo(self, _event=None):
        if not self._ready() or not self.undo_stack:
            return "break"
        prior = self.undo_stack[-1]
        current = list(self.boxes)
        if self._commit(prior, history=False):
            self.undo_stack.pop()
            self.redo_stack.append(current)
        return "break"

    def redo(self, _event=None):
        if not self._ready() or not self.redo_stack:
            return "break"
        future = self.redo_stack[-1]
        current = list(self.boxes)
        if self._commit(future, history=False):
            self.redo_stack.pop()
            self.undo_stack.append(current)
        return "break"

    def toggle_edit(self):
        app = self.app
        if not app.guard() or app.current_page is None:
            return
        if getattr(app, "_batch_active", False) or app._preprocess_mode_active():
            app.status_var.set("批量任务或预处理期间不能编辑 REF")
            return
        if not self._ready():
            self.load_page(app.current_page)
            if not self._ready():
                return
        active = not self.editing
        self.capture_sample = False
        if active:
            if app.polygon_draw_var.get():
                app.toggle_polygon_drawing()
            if app.auxiliary_mode_var.get():
                app.auxiliary_mode_var.set(False)
                app.toggle_auxiliary_mode()
            if app._section_editing:
                app._set_section_editing(False)
        self.editing = active
        self.cancel_drag()
        self.selected_id = None
        button = getattr(app, "_ref_box_edit_button", None)
        if button is not None:
            button.configure(
                text="结束编辑'REF'" if active else "编辑'REF'",
                style="PC.EditActive.TButton" if active else "PC.Compact.TButton",
            )
        app.status_var.set(
            "REF 编辑：单击选框；拖动内部移动、四边/四角缩放；双击或点击✎编辑文字；点击×/Delete删除；Ctrl+Z/Y撤销重做。"
            if active else "已退出 REF 编辑模式"
        )
        app.redraw()

    def stop_edit(self):
        """Exit both REF pointer modes before unrelated drawing/preprocessing."""
        self.editing = False
        self.capture_sample = False
        self.cancel_drag()
        self.pointer_action = None
        button = getattr(self.app, "_ref_box_edit_button", None)
        if button is not None:
            button.configure(text="编辑'REF'", style="PC.Compact.TButton")

    def start_capture_sample(self):
        app = self.app
        if not app.guard() or not self._ready():
            app.status_var.set("请先打开一张可编辑页面，再到 REF 框设置采集样本")
            return
        if getattr(app, "_batch_active", False) or app._preprocess_mode_active():
            app.status_var.set("批量任务/预处理期间不可采集 REF 样本")
            return
        self.stop_edit()
        self.capture_sample = True
        self.cancel_drag()
        app.status_var.set("REF 样本采集：在主画布拖选一个完整的图案，松开即本地保存。右键取消。")
        app.redraw()

    def cancel_drag(self):
        self.drag_start = None
        self.drag_original = None
        self.drag_box = None
        self.drag_kind = "create"
        self.pointer_action = None

    @property
    def pointer_active(self) -> bool:
        return self.editing or self.capture_sample

    def _hit(self, x: int, y: int) -> RefBox | None:
        box, _ = hit_test(self.boxes, x, y, scale=self.app.view_scale,
                          selected_id=self.selected_id)
        return box

    def _action_buttons(self):
        """Source-coordinate positions for selected REF edit/delete chips."""
        target = next((b for b in self.boxes if b.id == self.selected_id), None)
        if target is None or self.app.image is None:
            return []
        scale = max(0.08, float(self.app.view_scale))
        chip = round(22 / scale)
        gap = round(3 / scale)
        right = min(self.app.image.width, target.x + target.w)
        left = max(0, right - 2 * chip - gap)
        # Position just above box when possible, else below box.
        top = (target.y - chip - gap
               if target.y >= chip + gap else target.y + target.h + gap)
        top = max(0, min(self.app.image.height - chip, top))
        return [
            ("edit", left, top, left + chip, top + chip),
            ("delete", left + chip + gap, top,
             left + chip * 2 + gap, top + chip),
        ]

    def _hit_action(self, x: int, y: int) -> str | None:
        for kind, x0, y0, x1, y1 in self._action_buttons():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return kind
        return None

    def press(self, x: int, y: int) -> str:
        if not self._ready():
            return "break"
        try:
            self.app.canvas.focus_set()
        except (AttributeError, tk.TclError):
            pass
        self.drag_start = (x, y)
        self.drag_original = None
        self.drag_box = None
        self.pointer_action = self._hit_action(x, y) if self.editing else None
        self.drag_kind = "create"
        if self.editing and self.pointer_action is None:
            hit, action = hit_test(
                self.boxes, x, y, scale=self.app.view_scale,
                selected_id=self.selected_id,
            )
            if hit is not None:
                self.selected_id = hit.id
                self.drag_original = hit
                self.drag_kind = action
                self.app.status_var.set(
                    f"已选 REF #{hit.id}：拖动{action}，双击或✎修改文字，×删除"
                )
            else:
                self.selected_id = None
        return "break"

    def drag(self, x: int, y: int) -> str:
        if self.drag_start is None or self.app.image is None:
            return "break"
        if self.pointer_action:
            return "break"
        x = max(0, min(self.app.image.width, x))
        y = max(0, min(self.app.image.height, y))
        sx, sy = self.drag_start
        if self.drag_original is not None:
            self.drag_box = transform_box(
                self.drag_original, self.drag_kind, start=(sx, sy),
                current=(x, y), image_size=self.app.image.size,
            )
        else:
            nx, ny = min(sx, x), min(sy, y)
            self.drag_box = RefBox(
                0, nx, ny, max(1, abs(x-sx)), max(1, abs(y-sy)), None,
            )
        self._preview_drag()
        return "break"

    def hover(self, x: int, y: int) -> None:
        if not self.pointer_active:
            return
        if self.editing and self._hit_action(x, y):
            cursor = "hand2"
        elif self.capture_sample:
            cursor = "crosshair"
        else:
            _box, action = hit_test(
                self.boxes, x, y, scale=self.app.view_scale,
                selected_id=self.selected_id,
            )
            cursor = action_cursor(action)
        try:
            self.app.canvas.configure(cursor=cursor)
        except tk.TclError:
            pass

    def _event_xy_from_overlay(self, event) -> tuple[int, int]:
        """Translate child widget screen coordinates into scrolled page pixels."""
        canvas = self.app.canvas
        cx = canvas.canvasx(event.x_root - canvas.winfo_rootx())
        cy = canvas.canvasy(event.y_root - canvas.winfo_rooty())
        scale = max(0.001, float(self.app.view_scale))
        return round(cx / scale), round(cy / scale)

    def bind_overlay_widgets(self) -> None:
        """Text Entry/PPP labels are Tk windows above Canvas items.

        Their pointer events do not propagate to the canvas; while editing REF
        divert those events to this controller. Redraw recreates the widgets,
        restoring their normal PDIC/PPP bindings outside REF mode.
        """
        if not self.pointer_active:
            return

        def dispatch(kind: str, event):
            xy = self._event_xy_from_overlay(event)
            if kind == "press":
                return self.press(*xy)
            if kind == "drag":
                return self.drag(*xy)
            if kind == "release":
                return self.release(*xy)
            if kind == "double":
                return self.double_click(*xy)
            if kind == "context":
                return self.context_menu(event, coords=xy)
            if kind == "motion":
                self.hover(*xy)
                return None
            return None

        bindings = (
            ("<Button-1>", "press"), ("<B1-Motion>", "drag"),
            ("<ButtonRelease-1>", "release"),
            ("<Double-Button-1>", "double"), ("<Button-3>", "context"),
            ("<Button-2>", "context"), ("<Motion>", "motion"),
        )
        def install(widget):
            for sequence, kind in bindings:
                widget.bind(sequence, lambda event, action=kind: dispatch(action, event))
            for child in widget.winfo_children():
                install(child)
        for widget in list(getattr(self.app, "overlay_widgets", ())):
            install(widget)

    def _preview_drag(self):
        app = self.app
        app.canvas.delete("ref-drag")
        if self.drag_box is None:
            return
        box = self.drag_box
        s = app.view_scale
        app.canvas.create_rectangle(
            box.x*s, box.y*s, (box.x+box.w)*s, (box.y+box.h)*s,
            outline="#1565c0", width=2, dash=(3, 2), tags=("ref-drag",),
        )

    def release(self, x: int, y: int) -> str:
        if self.drag_start is None or self.app.image is None or not self._ready():
            return "break"
        sx, sy = self.drag_start
        x = max(0, min(self.app.image.width, x))
        y = max(0, min(self.app.image.height, y))
        action = self.pointer_action
        if action is None:
            self.drag(x, y)
        candidate = self.drag_box
        original = self.drag_original
        self.cancel_drag()
        self.pointer_action = None
        self.app.canvas.delete("ref-drag")
        if action == "edit":
            self.edit_properties()
            return "break"
        if action == "delete":
            self.delete_selected()
            return "break"
        if self.capture_sample:
            self.capture_sample = False
            if abs(x-sx) < 4 or abs(y-sy) < 4:
                self.app.status_var.set("REF 样本框过小，未保存")
            else:
                try:
                    path = add_ref_sample(
                        self.loaded_page, (min(x,sx), min(y,sy), max(x,sx), max(y,sy)),
                    )
                    self.app.status_var.set(f"REF 样本已保存：{path.name}")
                except Exception as exc:
                    self.app.show_error("保存 REF 样本失败", exc)
            self.app.redraw()
            return "break"
        if candidate is None or not self.editing:
            self.render()
            return "break"
        if original is not None:
            proposed = [candidate if b.id == original.id else b for b in self.boxes]
            if proposed == self.boxes:
                # Do not destroy/redraw PDIC Entry widgets for a click-only
                # selection: otherwise Tk loses the subsequent double-click.
                self.render()
            else:
                self._commit(proposed)
            return "break"
        if abs(x-sx) < 3 and abs(y-sy) < 3:
            line_height = max(
                2.0, float(getattr(self.app.settings, "character_height", 26))
                + float(getattr(self.app.settings, "row_padding", 0)),
            )
            height = max(2, round(line_height * float(
                getattr(self.app.settings, "ref_box_height_lines", 1))))
            width = max(2, round(line_height * float(
                getattr(self.app.settings, "ref_box_width_lines", 2))))
            candidate = replace(candidate, x=sx, y=sy, w=width, h=height)
        image = self.app.image
        candidate = replace(
            candidate, x=max(0, min(image.width-2, candidate.x)),
            y=max(0, min(image.height-2, candidate.y)),
        )
        candidate = replace(
            candidate,
            w=max(2, min(candidate.w, image.width-candidate.x)),
            h=max(2, min(candidate.h, image.height-candidate.y)),
        )
        entry_index = None
        if getattr(self.app.settings, "ref_box_auto_attach", True):
            entry_index = associate_ref_to_entry(
                image, list(self.app.entries), self.app.settings,
                max(0, self.app.current_index), list(self.app.page_sections),
                candidate.x, candidate.y, candidate.w, candidate.h,
            )
        added = replace(candidate, id=next_ref_id(self.boxes), entry_index=entry_index)
        self.selected_id = added.id
        if self._commit([*self.boxes, added]):
            self.app.status_var.set(f"REF #{added.id} 已保存；双击或✎编辑，×删除")
        return "break"

    def edit_properties(self, target_id: int | None = None):
        if not self._ready():
            return
        target = next((b for b in self.boxes if b.id == (target_id or self.selected_id)), None)
        if target is None:
            return
        dialog = tk.Toplevel(self.app)
        dialog.title(f"编辑 REF #{target.id}")
        dialog.transient(self.app)
        panel = ttk.Frame(dialog, padding=12)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="REF 文字：").pack(anchor="w")
        editor = tk.Text(panel, width=48, height=4, undo=True)
        editor.pack(fill="both", expand=True, pady=(3, 12))
        editor.insert("1.0", target.text)
        ttk.Label(panel, text="挂靠本页词条序号（从 000 开始，留空表示未关联）：").pack(anchor="w")
        entry_var = tk.StringVar(value="" if target.entry_index is None else f"{target.entry_index:03d}")
        ttk.Entry(panel, textvariable=entry_var, width=12).pack(anchor="w", pady=(4, 10))

        def save():
            try:
                raw = entry_var.get().strip()
                ordinal = int(raw) if raw else None
                if ordinal is not None and not 0 <= ordinal < len(self.app._ordered_entries_reading_order()):
                    raise ValueError("挂靠词条序号超出本页 PDIC 范围")
                value = replace(target, text=editor.get("1.0", "end-1c"), entry_index=ordinal)
                if self._commit([value if b.id == target.id else b for b in self.boxes]):
                    dialog.destroy()
            except ValueError as exc:
                messagebox.showerror("REF 输入无效", str(exc), parent=dialog)

        ttk.Button(panel, text="保存", command=save).pack(side="right")
        ttk.Button(panel, text="取消", command=dialog.destroy).pack(side="right", padx=8)
        dialog.bind("<Control-Return>", lambda _event: save())
        editor.focus_set()

    def double_click(self, x: int, y: int) -> str:
        self.cancel_drag()  # Suppress a trailing release after Tk double-click.
        target = self._hit(x, y)
        if target:
            self.selected_id = target.id
            self.edit_properties(target.id)
        return "break"

    def delete_selected(self, _event=None):
        selected = self.selected_id
        if selected is None or not self._ready():
            return "break"
        proposed = [b for b in self.boxes if b.id != selected]
        if self._commit(proposed):
            self.selected_id = None
            self.app.redraw()
        return "break"

    def context_menu(self, event, *, coords=None):
        if self.capture_sample:
            self.capture_sample = False
            self.cancel_drag()
            self.app.status_var.set("已取消 REF 图案采集")
            return "break"
        if not self.editing:
            return None
        x, y = coords if coords is not None else self.app.original_xy(event)
        hit = self._hit(x, y)
        if hit is not None:
            self.selected_id = hit.id
        self.render()
        menu = tk.Menu(self.app, tearoff=False)
        menu.add_command(label="编辑 REF 文字/挂靠", command=self.edit_properties,
                         state="normal" if self.selected_id else "disabled")
        menu.add_command(label="删除选中 REF", command=self.delete_selected,
                         state="normal" if self.selected_id else "disabled")
        menu.add_separator()
        menu.add_command(label="撤销 REF", command=self.undo, state="normal" if self.undo_stack else "disabled")
        menu.add_command(label="重做 REF", command=self.redo, state="normal" if self.redo_stack else "disabled")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def render(self):
        # Repaint only REF canvas items when selecting; avoid destroying Tk
        # word-entry windows which are necessary for a stable double-click.
        if hasattr(self.app, "canvas"):
            self.app.canvas.delete("ref-box")
        self._overlay_images = []
        if not self._ready() or not (self.editing or getattr(self.app.settings, "ref_box_show", True)):
            return
        app = self.app
        s = app.view_scale
        config = app.settings
        color = str(getattr(config, "ref_box_fill_color", "#b7d9f5"))
        opacity = min(100.0, max(0.0, float(getattr(config, "ref_box_fill_opacity", 50))))
        try:
            rgb = ImageColor.getrgb(color)
        except ValueError:
            rgb = (183, 217, 245)
        from ..ui_compat import resolve_content_font_family
        family = resolve_content_font_family(
            app, getattr(config, "ref_box_font_family", "自动（系统推荐）"),
            str(getattr(config, "ocr_language", "eng")),
        )
        size = max(6, round(int(getattr(config, "ref_box_font_size", 16)) * s))
        styles = []
        if getattr(config, "ref_box_font_bold", False):
            styles.append("bold")
        if getattr(config, "ref_box_font_italic", False):
            styles.append("italic")
        font_spec = (family, size, *styles)
        for box in self.boxes:
            xx, yy, ww, hh = (round(box.x*s), round(box.y*s),
                              max(1, round(box.w*s)), max(1, round(box.h*s)))
            if opacity > 0:
                rgba = Image.new("RGBA", (ww, hh), (*rgb, round(opacity*255/100)))
                photo = ImageTk.PhotoImage(rgba)
                self._overlay_images.append(photo)
                app.canvas.create_image(
                    xx, yy, image=photo, anchor="nw", tags=("ref-box",),
                )
            if self.editing:
                selected = box.id == self.selected_id
                app.canvas.create_rectangle(
                    xx, yy, xx+ww, yy+hh,
                    outline="#1565c0" if selected else "#477da1",
                    width=2 if selected else 1,
                    dash=() if selected else (3, 3),
                    tags=("ref-box", "ref-box-border"),
                )
            if box.text:
                app.canvas.create_text(
                    xx + 2, yy + 1, text=box.text, anchor="nw",
                    width=max(4, ww-4),
                    fill=getattr(config, "ref_box_text_color", "#15395b"),
                    font=font_spec, tags=("ref-box",),
                )
            if self.editing and box.id == self.selected_id:
                # Eight screen-size handles indicate four sides plus corners.
                radius = 4
                points = (
                    (xx, yy), (xx + ww//2, yy), (xx + ww, yy),
                    (xx, yy + hh//2), (xx + ww, yy + hh//2),
                    (xx, yy + hh), (xx + ww//2, yy + hh), (xx + ww, yy + hh),
                )
                for hx, hy in points:
                    app.canvas.create_rectangle(
                        hx-radius, hy-radius, hx+radius, hy+radius,
                        fill="#ffffff", outline="#1565c0", width=2,
                        tags=("ref-box", "ref-box-handle"),
                    )
        if self.editing:
            for action, x0, y0, x1, y1 in self._action_buttons():
                sx0, sy0, sx1, sy1 = (round(x0*s), round(y0*s),
                                      round(x1*s), round(y1*s))
                app.canvas.create_rectangle(
                    sx0, sy0, sx1, sy1, fill="#eaf3fc",
                    outline="#1565c0", width=1,
                    tags=("ref-box", "ref-box-action", f"ref-{action}"),
                )
                app.canvas.create_text(
                    (sx0+sx1)//2, (sy0+sy1)//2,
                    text="✎" if action == "edit" else "×",
                    font=(family, max(10, round(14*s))),
                    fill="#14508b" if action == "edit" else "#af2929",
                    tags=("ref-box", "ref-box-action", f"ref-{action}"),
                )
        if self.drag_box is not None:
            self._preview_drag()
        # Canvas graphics are drawn last, above PPP/PDIC lines. Tk window
        # widgets may still float above canvas graphics; bind_overlay_widgets
        # explicitly routes their mouse events to the REF editor.

    def recognize_selected_scope(self):
        app = self.app
        if not app.guard() or app.project is None or getattr(app, "_batch_active", False):
            return
        if self.editing or self.capture_sample:
            app.status_var.set("请先结束 REF 编辑/采集模式，再运行自动识别")
            return
        pages = tuple(app.project.images)
        indices = app.selected_page_indices()
        if not indices:
            return
        if not list_ref_samples(app.project.root):
            app.status_var.set("请先在【设置中心 → REF框】采集至少一个样本图案")
            return
        if not messagebox.askyesno(
            "自动识别 REF", f"将在所选 {len(indices)} 页按本地样本图案查找 REF；"
            "只新增不重写现有人工框。继续？", parent=app,
        ):
            return
        # REF association consumes existing on-disk PDIC only. In particular,
        # never flush or autosave in-progress headword edits as a side effect
        # of recognizing a separate annotation layer.
        from dataclasses import replace as settings_copy
        settings = settings_copy(app.settings)
        current = app.current_index

        def job(index, _position, _total):
            return detect_ref_boxes_job(str(pages[index]), settings, index)

        def done(completed, total, stopped, results, error):
            if app.project and current == app.current_index and current in indices:
                self.load_page(pages[current])
                app.redraw()
            failed = [r for r in results if r.get("status") == "failed"]
            added = sum(r.get("added", 0) for r in results)
            app.status_var.set(
                f"REF 识别{'已停止' if stopped else '完成'}：{completed}/{total} 页，"
                f"新增 {added} 框，失败 {len(failed)} 页"
                + (f"；{failed[0]['page']}：{failed[0]['error']}" if failed else "")
            )

        app._start_batch_task(
            "识别 REF", indices, job, on_done=done,
            item_label=lambda index: pages[index].name,
            refresh_page_quality=False, allow_page_navigation=False, allow_pdic_edits=False,
        )


__all__ = ["RefBoxController"]
