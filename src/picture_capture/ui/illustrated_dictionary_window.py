"""Standalone two-stage illustrated-dictionary editor.

The app remains on its existing PDIC/REF drawing mode. This dedicated canvas
owns spatial groups and never binds main-canvas pointer events. All manual
edits are disk-first; page OCR is review-only until explicitly accepted.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from ..illustrated_entries import (
    IllustratedEntry, file_ticket, make_entry, read_entries, write_entries,
)
from ..illustrated_export import export_illustrated_index
from ..illustrated_ocr import (
    ocr_one_group, proposal_overlaps, propose_page_entries,
)
from ..image_utils import normalize_page_rgb
from ..ref_text_label_layout import ref_text_label_rect
from .illustrated_entry_dialog import edit_illustrated_group


class IllustratedDictionaryEditor:
    def __init__(self, app):
        self.app = app
        self.project = app.project
        self.pages = tuple(self.project.images)
        self.page_index = max(0, int(app.current_index))
        self.page: Path = self.pages[self.page_index]
        self.image: Image.Image | None = None
        self.entries: list[IllustratedEntry] = []
        self.proposals: list[IllustratedEntry] = []
        self.ticket: str | None = None
        self.selected: tuple[str, str] | None = None
        self.drag_origin: tuple[int, int] | None = None
        self.drag_kind = ""
        self.drag_box: tuple[int, int, int, int] | None = None
        self.drag_initial: IllustratedEntry | None = None
        self.busy = False
        self.scale = 1.
        self.photo: ImageTk.PhotoImage | None = None
        self.status = tk.StringVar(value="")
        self.show_labels = tk.BooleanVar(value=False)
        self.split_aliases = tk.StringVar(
            value="多语言拆分索引" if getattr(app.settings, "illustrated_export_split_aliases", True)
            else "每组一条索引"
        )
        self.export_pages = tk.StringVar(value="全项目")
        self.window = tk.Toplevel(app)
        self.window.title("图解词典 · 空间词条框与多语言 OCR")
        self.window.geometry("1190x835")
        self.window.minsize(720, 480)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self._load_page(self.page_index)

    def _build(self):
        top = ttk.Frame(self.window, padding=5)
        top.pack(fill="x")
        for caption, callback in (
            ("◀ 上页", lambda: self._load_page(self.page_index - 1)),
            ("下页 ▶", lambda: self._load_page(self.page_index + 1)),
            ("－", lambda: self._zoom(1 / 1.25)),
            ("＋", lambda: self._zoom(1.25)),
            ("编辑选中", self.edit_selected),
            ("删除/拒绝", self.delete_selected),
            ("框内 OCR", self.ocr_selected),
            ("全页 OCR 提议", self.propose_page),
            ("接受选中", self.accept_selected),
            ("接受全部", self.accept_all),
            ("清空候选", self.clear_proposals),
        ):
            ttk.Button(top, text=caption, command=callback).pack(side="left", padx=2)
        ttk.Checkbutton(top, text="显示转写标签", variable=self.show_labels,
                        command=self._draw).pack(side="left", padx=4)

        body = ttk.PanedWindow(self.window, orient="horizontal")
        body.pack(fill="both", expand=True)
        viewer = ttk.Frame(body)
        sidebar = ttk.Frame(body, padding=6)
        body.add(viewer, weight=4)
        body.add(sidebar, weight=1)
        self.canvas = tk.Canvas(viewer, bg="#e8e8e8", highlightthickness=0)
        xv = ttk.Scrollbar(viewer, orient="horizontal", command=self.canvas.xview)
        yv = ttk.Scrollbar(viewer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xv.set, yscrollcommand=yv.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yv.grid(row=0, column=1, sticky="ns")
        xv.grid(row=1, column=0, sticky="ew")
        viewer.rowconfigure(0, weight=1)
        viewer.columnconfigure(0, weight=1)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Double-Button-1>", lambda _event: self.edit_selected())
        self.canvas.bind("<Delete>", lambda _event: self.delete_selected())
        self.canvas.bind("<Escape>", lambda _event: self._cancel_drag())
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(3, "units"))

        ttk.Label(sidebar, text="空间文字组 · 蓝色为待确认 OCR").pack(anchor="w")
        self.listbox = tk.Listbox(sidebar, width=32, exportselection=False)
        self.listbox.pack(fill="both", expand=True, pady=(5, 8))
        self.listbox.bind("<<ListboxSelect>>", self._select_list)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.edit_selected())
        ttk.Label(sidebar, text="拖拽空白区域新建矩形；拖拽已选框移动；\nShift+拖动已选框右下角调整大小。\n双击编辑文字；所有修改即刻保存。",
                  justify="left", wraplength=260).pack(anchor="w")
        ttk.Separator(sidebar).pack(fill="x", pady=8)
        ttk.Label(sidebar, text="索引导出").pack(anchor="w")
        ttk.Combobox(sidebar, textvariable=self.split_aliases, state="readonly",
                     values=("每组一条索引", "多语言拆分索引")).pack(fill="x", pady=(4, 6))
        ttk.Combobox(sidebar, textvariable=self.export_pages, state="readonly",
                     values=("全项目", "当前页")).pack(fill="x", pady=(0, 6))
        ttk.Button(sidebar, text="导出 TSV 索引", command=self.export).pack(fill="x")
        ttk.Label(sidebar, text="不同语言可检索同一个文字组；\n不会写入或覆盖工作 PDIC。",
                  justify="left", wraplength=260).pack(anchor="w", pady=8)
        ttk.Label(self.window, textvariable=self.status, padding=5).pack(fill="x")

    def _valid(self) -> bool:
        return (self.window.winfo_exists()
                and self.app.project is self.project
                and self.image is not None)

    def close(self) -> None:
        if self.image is not None:
            self.image.close()
            self.image = None
        if getattr(self.app, "_illustrated_dictionary_window", None) is self:
            self.app._illustrated_dictionary_window = None
        self.window.destroy()

    def _load_page(self, index: int) -> None:
        if self.busy:
            self.status.set("正在执行 OCR，请等待任务完成再翻页。")
            return
        if not (0 <= index < len(self.pages)):
            return
        page = self.pages[index]
        try:
            entries = read_entries(self.project.root, page)
            ticket = file_ticket(self.project.root, page)
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
        except (ValueError, OSError) as exc:
            messagebox.showerror("图解词条读取失败", str(exc), parent=self.window)
            return
        if self.image is not None:
            self.image.close()
        self.page_index, self.page = index, page
        self.image, self.entries, self.ticket = image, entries, ticket
        self.proposals, self.selected = [], None
        self.scale = min(1., 960 / max(1, image.width), 730 / max(1, image.height))
        self.window.title(f"图解词典 · {page.name} · 第 {index+1}/{len(self.pages)} 页")
        self._refresh_list()
        self._draw()
        self.status.set(f"{page.name}：{len(entries)} 个已保存文字组。拖框新建；OCR 仅产生候选。")

    def _zoom(self, multiplier: float) -> None:
        if self.image is None:
            return
        self.scale = max(.10, min(3.0, self.scale * multiplier))
        self._draw()

    def _wheel(self, event) -> None:
        self.canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")

    def _pos(self, event) -> tuple[int, int]:
        assert self.image is not None
        x = int(self.canvas.canvasx(event.x) / max(.001, self.scale))
        y = int(self.canvas.canvasy(event.y) / max(.001, self.scale))
        return (max(0, min(self.image.width-1, x)),
                max(0, min(self.image.height-1, y)))

    @staticmethod
    def _contains(item: IllustratedEntry, x: int, y: int) -> bool:
        return item.x <= x <= item.x+item.w and item.y <= y <= item.y+item.h

    def _target(self) -> IllustratedEntry | None:
        if self.selected is None:
            return None
        collection = self.entries if self.selected[0] == "saved" else self.proposals
        return next((item for item in collection if item.id == self.selected[1]), None)

    def _hit(self, x: int, y: int) -> tuple[str, str] | None:
        for kind, collection in (("saved", self.entries), ("candidate", self.proposals)):
            for item in reversed(collection):
                if self._contains(item, x, y):
                    return kind, item.id
        return None

    def _refresh_list(self) -> None:
        keys = [("saved", item.id) for item in self.entries]
        keys.extend(("candidate", item.id) for item in self.proposals)
        self._list_keys = keys
        self.listbox.delete(0, "end")
        for kind, id_ in keys:
            collection = self.entries if kind == "saved" else self.proposals
            item = next(row for row in collection if row.id == id_)
            label = item.primary or next(iter(item.lines), "（空文字框）")
            self.listbox.insert("end", f"{'●' if kind == 'saved' else '◇'} {label[:28]}")
        if self.selected in keys:
            i = keys.index(self.selected)
            self.listbox.selection_set(i)
            self.listbox.see(i)

    def _select_list(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if selection and selection[0] < len(self._list_keys):
            self.selected = self._list_keys[selection[0]]
            self._draw()

    def _draw(self) -> None:
        if self.image is None:
            return
        size = (max(1, round(self.image.width*self.scale)),
                max(1, round(self.image.height*self.scale)))
        preview = self.image.resize(size, Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(preview)
        preview.close()
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, size[0], size[1]))
        for kind, collection in (("saved", self.entries), ("candidate", self.proposals)):
            for item in collection:
                active = self.selected == (kind, item.id)
                color = "#1565c0" if active else (
                    "#1d7c55" if kind == "saved" and item.status == "reviewed"
                    else "#e6913a" if kind == "saved" else "#158dc1"
                )
                coords = tuple(round(v * self.scale) for v in (
                    item.x, item.y, item.x+item.w, item.y+item.h
                ))
                self.canvas.create_rectangle(
                    *coords, outline=color, width=3 if active else 2,
                    dash=() if kind == "saved" else (4, 4),
                )
                if (self.show_labels.get() or active) and (item.primary or item.lines):
                    self._draw_label(item)
        if self.drag_box is not None:
            x, y, w, h = self.drag_box
            self.canvas.create_rectangle(
                round(x*self.scale), round(y*self.scale),
                round((x+w)*self.scale), round((y+h)*self.scale),
                outline="#e54324", width=2, dash=(5, 3),
            )

    def _draw_label(self, item: IllustratedEntry) -> None:
        assert self.image is not None
        text = item.primary or (item.lines[0] if item.lines else "")
        if not text:
            return
        lx, ly, lw, lh = ref_text_label_rect(
            (item.x, item.y, item.w, item.h), self.image.size,
            text=text, scale=self.scale, font_size=12, gap=4, padding=4,
        )
        self.canvas.create_rectangle(
            lx, ly, lx+lw, ly+lh, fill="#e3f0fb", outline="#779ab5",
        )
        self.canvas.create_text(lx+4, ly+4, text=text, anchor="nw",
                                font=("TkDefaultFont", 12), fill="#173452",
                                width=max(1, lw-8))

    def _cancel_drag(self) -> None:
        self.drag_origin, self.drag_box, self.drag_initial = None, None, None
        self.drag_kind = ""
        self._draw()

    def _press(self, event) -> None:
        if not self._valid() or self.busy:
            return
        self.canvas.focus_set()
        x, y = self._pos(event)
        self.drag_origin = (x, y)
        self.drag_initial, self.drag_box = None, None
        hit = self._hit(x, y)
        if hit:
            self.selected = hit
            target = self._target()
            if hit[0] == "saved" and target is not None:
                self.drag_initial = target
                corner = (abs(x-(target.x+target.w)) <= max(5, round(12/self.scale))
                          and abs(y-(target.y+target.h)) <= max(5, round(12/self.scale)))
                self.drag_kind = "resize" if corner and (event.state & 0x0001) else "move"
            else:
                self.drag_kind = "select"
        else:
            self.selected = None
            self.drag_kind = "create"
        self._refresh_list()
        self._draw()

    def _drag(self, event) -> None:
        if self.drag_origin is None or self.image is None:
            return
        x, y = self._pos(event)
        ox, oy = self.drag_origin
        if self.drag_kind == "create":
            self.drag_box = (min(x, ox), min(y, oy), abs(x-ox), abs(y-oy))
        elif self.drag_initial is not None:
            target = self.drag_initial
            if self.drag_kind == "move":
                xx = max(0, min(self.image.width-target.w, target.x+x-ox))
                yy = max(0, min(self.image.height-target.h, target.y+y-oy))
                self.drag_box = (xx, yy, target.w, target.h)
            elif self.drag_kind == "resize":
                self.drag_box = (target.x, target.y,
                                 max(1, min(self.image.width-target.x, target.w+x-ox)),
                                 max(1, min(self.image.height-target.y, target.h+y-oy)))
        self._draw()

    def _release(self, event) -> None:
        if self.drag_origin is None or self.image is None:
            return
        rect, kind, target = self.drag_box, self.drag_kind, self.drag_initial
        self.drag_origin, self.drag_box, self.drag_initial = None, None, None
        self.drag_kind = ""
        if kind == "create" and rect and rect[2] >= 6 and rect[3] >= 6:
            added = make_entry(*rect)
            if self._commit([*self.entries, added]):
                self.selected = ("saved", added.id)
        elif target is not None and rect and rect != (target.x, target.y, target.w, target.h):
            changed = replace(target, x=rect[0], y=rect[1], w=rect[2], h=rect[3])
            self._commit([changed if v.id == target.id else v for v in self.entries])
        self._refresh_list()
        self._draw()

    def _commit(self, proposal: list[IllustratedEntry]) -> bool:
        if not self._valid() or self.busy:
            return False
        if proposal == self.entries:
            return True
        try:
            ticket = write_entries(
                self.project.root, self.page, proposal,
                expected_ticket=self.ticket, image_size=self.image.size,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror("图解词条保存失败", str(exc), parent=self.window)
            return False
        self.entries, self.ticket = list(proposal), ticket
        self.status.set(f"{self.page.name}：已保存 {len(proposal)} 个文字组")
        self._refresh_list()
        return True

    def edit_selected(self) -> None:
        item = self._target()
        if item is None or self.busy:
            return
        if self.selected and self.selected[0] == "candidate":
            # An explicit edit is also an explicit acceptance.
            if not self.accept_selected():
                return
            item = self._target()
        if item is None:
            return

        def commit(updated: IllustratedEntry) -> bool:
            ok = self._commit([
                updated if row.id == updated.id else row for row in self.entries
            ])
            if ok:
                self._refresh_list()
                self._draw()
            return ok

        edit_illustrated_group(self.window, item, commit)

    def delete_selected(self) -> None:
        if not self.selected or self.busy:
            return
        kind, id_ = self.selected
        if kind == "saved":
            if not messagebox.askyesno("删除词条", "确定删除这个图解词条吗？",
                                       parent=self.window):
                return
            if not self._commit([v for v in self.entries if v.id != id_]):
                return
        else:
            self.proposals = [v for v in self.proposals if v.id != id_]
        self.selected = None
        self._refresh_list()
        self._draw()

    def clear_proposals(self) -> None:
        self.proposals = []
        if self.selected and self.selected[0] == "candidate":
            self.selected = None
        self._refresh_list()
        self._draw()

    def accept_selected(self) -> bool:
        if not self.selected or self.selected[0] != "candidate" or self.busy:
            return False
        item = self._target()
        if item is None:
            return False
        if any(proposal_overlaps(item, old) for old in self.entries):
            self.status.set("候选与已有框重叠，需先人工调整；原数据未改变")
            return False
        if not self._commit([*self.entries, item]):
            return False
        self.proposals = [v for v in self.proposals if v.id != item.id]
        self.selected = ("saved", item.id)
        self._refresh_list()
        self._draw()
        return True

    def accept_all(self) -> None:
        if self.busy or not self.proposals:
            return
        added = []
        for item in self.proposals:
            if not any(proposal_overlaps(item, x) for x in [*self.entries, *added]):
                added.append(item)
        if not added:
            self.status.set("OCR 候选都与已有文字框重叠；未覆盖人工内容")
            return
        if getattr(self.app.settings, "illustrated_require_review", True):
            if not messagebox.askyesno(
                "接受图解 OCR 候选",
                f"将保存 {len(added)} 个候选文字组为待校对状态。继续？",
                parent=self.window,
            ):
                return
        if self._commit([*self.entries, *added]):
            ids = {v.id for v in added}
            self.proposals = [v for v in self.proposals if v.id not in ids]
            self._refresh_list()
            self._draw()

    def _run_ocr(self, title, worker, done) -> None:
        if self.busy or not self._valid():
            return
        if getattr(self.app, "_batch_active", False):
            self.status.set("另一个批处理任务运行中，请稍后")
            return
        self.busy = True
        page_index = self.page_index
        project = self.project

        def finished(_completed, _total, stopped, results, error):
            self.busy = False
            if not self._valid() or self.project is not project or self.page_index != page_index:
                return
            if error is not None:
                self.status.set(f"OCR 失败：{error}")
                return
            if stopped or not results:
                self.status.set("OCR 已停止或未返回结果")
                return
            done(results[-1])

        try:
            self.app._start_batch_task(
                title, [page_index], worker, finished,
                item_label=lambda i: self.pages[i].name,
            )
            self.status.set(f"{title}运行中；候选不会自动写入")
        except Exception as exc:
            self.busy = False
            messagebox.showerror(title, str(exc), parent=self.window)

    def propose_page(self) -> None:
        settings = replace(self.app.settings)
        page = self.page

        def completed(proposed):
            self.proposals = [
                row for row in proposed
                if not any(proposal_overlaps(row, saved) for saved in self.entries)
            ]
            self.selected = None
            self._refresh_list()
            self._draw()
            self.status.set(
                f"全页 OCR 产生 {len(self.proposals)} 个待审核文字组；"
                "蓝色虚线尚未保存，须接受后才写盘。"
            )

        self._run_ocr(
            "图解词典全页 OCR", lambda *_args: propose_page_entries(page, settings),
            completed,
        )

    def ocr_selected(self) -> None:
        target = self._target()
        if target is None or self.busy:
            return
        if target.lines or target.primary.strip():
            self.status.set("已有文字不会被 OCR 覆盖；可双击人工修改。")
            return
        settings = replace(self.app.settings)
        page = self.page
        target_id = target.id

        def completed(lines):
            if not lines:
                self.status.set("此框 OCR 未识别到文字")
                return
            kind = self.selected[0] if self.selected else ""
            if kind == "candidate":
                self.proposals = [
                    replace(row, lines=tuple(lines), primary=lines[0])
                    if row.id == target_id else row for row in self.proposals
                ]
            else:
                self._commit([
                    replace(row, lines=tuple(lines), primary=lines[0], status="draft")
                    if row.id == target_id and not row.lines else row
                    for row in self.entries
                ])
            self._refresh_list()
            self._draw()

        self._run_ocr(
            "图解词典框内 OCR",
            lambda *_args: ocr_one_group(
                page, settings, (target.x, target.y, target.w, target.h)
            ), completed,
        )

    def export(self) -> None:
        if not self._valid() or self.busy:
            return
        split = self.split_aliases.get() == "多语言拆分索引"
        pages = self.pages if self.export_pages.get() == "全项目" else (self.page,)
        try:
            dest, count = export_illustrated_index(self.project.root, pages,
                                                   split_aliases=split)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导出图解索引失败", str(exc), parent=self.window)
            return
        self.status.set(f"已导出 {count} 条索引：{dest}")
        messagebox.showinfo("图解词典索引", f"导出 {count} 条\n{dest}", parent=self.window)


def open_illustrated_dictionary_editor(app, *, action: str = "open") -> None:
    """Open the integrated main-canvas illustrated editor, not a second viewer."""
    from .illustrated_main_canvas import illustrated_main_action
    illustrated_main_action(app, action=action)
