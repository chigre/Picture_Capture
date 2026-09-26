from __future__ import annotations

"""Small Tk dialogs for capturing and managing dictionary marker samples."""

from pathlib import Path
from typing import Callable, Sequence
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from .image_utils import normalize_page_rgb
from .visual_marker_templates import build_visual_marker_sample


_ROLE_LABEL_TO_VALUE = {
    "入口标记": "entry_marker",
    "括号起始": "bracket_open",
}
_ROLE_VALUE_TO_LABEL = {value: label for label, value in _ROLE_LABEL_TO_VALUE.items()}


class VisualMarkerCaptureDialog(tk.Toplevel):
    """Capture one visual marker sample from an actual project page."""

    def __init__(
        self,
        parent: tk.Misc,
        images: Sequence[Path],
        *,
        initial_index: int = 0,
        initial_role: str = "entry_marker",
        initial_literal: str = "",
        on_saved: Callable[[dict], None],
    ) -> None:
        super().__init__(parent)
        self.images = [Path(path) for path in images]
        self.page_index = max(0, min(len(self.images) - 1, int(initial_index)))
        self.on_saved = on_saved
        self.source_image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        # Marker capture is deliberately shown at 100% source-pixel scale by
        # default. Small dictionary symbols are easy to miss when a full page is
        # auto-fitted into the dialog; explicit zoom + scroll keeps source-pixel
        # geometry inspectable and makes sample boxes precise.
        self.zoom_percent = 100
        self.display_scale = 1.0
        self.selection_source: tuple[int, int, int, int] | None = None
        self.selection_item: int | None = None
        self.drag_start: tuple[int, int] | None = None
        self._render_job: str | None = None

        self.title("添加视觉标记样本")
        self.geometry("980x780")
        self.minsize(720, 560)
        self.transient(parent)
        self.grab_set()

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(3, weight=1)
        outer.columnconfigure(0, weight=1)

        nav = ttk.Frame(outer)
        nav.grid(row=0, column=0, sticky="ew")
        ttk.Button(nav, text="◀ 上一页", command=lambda: self._move_page(-1)).pack(
            side="left"
        )
        ttk.Button(nav, text="下一页 ▶", command=lambda: self._move_page(1)).pack(
            side="right"
        )
        self.page_var = tk.StringVar(value="")
        ttk.Label(nav, textvariable=self.page_var).pack(side="left", expand=True)

        options = ttk.Frame(outer)
        options.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        ttk.Label(options, text="样本角色：").pack(side="left")
        self.role_var = tk.StringVar(
            value=_ROLE_VALUE_TO_LABEL.get(initial_role, "入口标记")
        )
        ttk.Combobox(
            options,
            textvariable=self.role_var,
            values=tuple(_ROLE_LABEL_TO_VALUE),
            state="readonly",
            width=10,
        ).pack(side="left", padx=(4, 14))
        ttk.Label(options, text="具体符号（可选）：").pack(side="left")
        self.literal_var = tk.StringVar(value=str(initial_literal or ""))
        ttk.Entry(options, textvariable=self.literal_var, width=12).pack(
            side="left", padx=(4, 10)
        )
        ttk.Label(
            options,
            text="在图片中拖框，只框住一个实际印刷标记。",
            foreground="#666666",
        ).pack(side="left")

        zoom_bar = ttk.Frame(outer)
        zoom_bar.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(
            zoom_bar,
            text="图片缩放（默认 100% 原始像素）：",
        ).pack(side="left")
        ttk.Button(
            zoom_bar, text="−", width=3, command=lambda: self._zoom_by(-25),
        ).pack(side="left", padx=(6, 2))
        ttk.Button(
            zoom_bar, text="100%", command=lambda: self._set_zoom(100),
        ).pack(side="left", padx=2)
        ttk.Button(
            zoom_bar, text="+", width=3, command=lambda: self._zoom_by(25),
        ).pack(side="left", padx=2)
        ttk.Button(
            zoom_bar, text="适合窗口", command=self._fit_window,
        ).pack(side="left", padx=(6, 0))
        self.zoom_var = tk.StringVar(value="100%")
        ttk.Label(zoom_bar, textvariable=self.zoom_var).pack(side="left", padx=(10, 0))
        ttk.Label(
            zoom_bar,
            text="Ctrl+滚轮可缩放；滚动条用于移动页面。",
            foreground="#666666",
        ).pack(side="left", padx=(12, 0))

        canvas_host = ttk.Frame(outer)
        canvas_host.grid(row=3, column=0, sticky="nsew")
        canvas_host.rowconfigure(0, weight=1)
        canvas_host.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            canvas_host,
            background="#d9d9d9",
            highlightthickness=1,
            relief="sunken",
            xscrollincrement=1,
            yscrollincrement=1,
        )
        xscroll = ttk.Scrollbar(
            canvas_host, orient="horizontal", command=self.canvas.xview
        )
        yscroll = ttk.Scrollbar(
            canvas_host, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(
            xscrollcommand=xscroll.set,
            yscrollcommand=yscroll.set,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._finish_drag)
        self.canvas.bind("<Control-MouseWheel>", self._mousewheel_zoom, add="+")
        self.canvas.bind(
            "<Control-Button-4>", lambda _event: self._zoom_by(25), add="+"
        )
        self.canvas.bind(
            "<Control-Button-5>", lambda _event: self._zoom_by(-25), add="+"
        )

        footer = ttk.Frame(outer)
        footer.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.selection_var = tk.StringVar(value="尚未框选")
        ttk.Label(footer, textvariable=self.selection_var).pack(side="left")
        ttk.Button(footer, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="保存样本", command=self._save).pack(
            side="right", padx=(0, 8)
        )

        if not self.images:
            messagebox.showerror("无法采样", "项目中没有可用页面。", parent=self)
            self.after_idle(self.destroy)
        else:
            self.after_idle(self._load_page)

    def _move_page(self, delta: int) -> None:
        if not self.images:
            return
        self.page_index = (self.page_index + int(delta)) % len(self.images)
        self._load_page()

    def _load_page(self) -> None:
        if not self.images:
            return
        path = self.images[self.page_index]
        try:
            with Image.open(path) as opened:
                self.source_image = normalize_page_rgb(opened)
        except Exception as exc:
            messagebox.showerror(
                "页面读取失败", f"{path.name}\n{exc}", parent=self
            )
            return
        self.page_var.set(
            f"{self.page_index + 1}/{len(self.images)} · {path.name}"
        )
        self.selection_source = None
        self.selection_item = None
        self.drag_start = None
        self.selection_var.set("尚未框选")
        self._render(reset_view=True)

    def _schedule_render(self, _event=None) -> None:
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except tk.TclError:
                pass
        self._render_job = self.after(40, self._render)

    def _set_zoom(self, percent: int | float) -> None:
        if self.source_image is None:
            return
        target = max(25, min(800, int(round(float(percent)))))
        if target == self.zoom_percent:
            return
        # Keep the same relative viewport position while changing scale.
        try:
            x_fraction = float(self.canvas.xview()[0])
            y_fraction = float(self.canvas.yview()[0])
        except (tk.TclError, IndexError):
            x_fraction = y_fraction = 0.0
        self.zoom_percent = target
        self._render()
        try:
            self.canvas.xview_moveto(x_fraction)
            self.canvas.yview_moveto(y_fraction)
        except tk.TclError:
            pass

    def _zoom_by(self, delta: int) -> None:
        self._set_zoom(self.zoom_percent + int(delta))

    def _fit_window(self) -> None:
        if self.source_image is None:
            return
        self.update_idletasks()
        width = max(1, int(self.canvas.winfo_width()) - 4)
        height = max(1, int(self.canvas.winfo_height()) - 4)
        percent = 100.0 * min(
            width / max(1, self.source_image.width),
            height / max(1, self.source_image.height),
        )
        self._set_zoom(percent)

    def _mousewheel_zoom(self, event: tk.Event):
        delta = int(getattr(event, "delta", 0) or 0)
        if delta:
            self._zoom_by(25 if delta > 0 else -25)
        return "break"

    def _render(self, *, reset_view: bool = False) -> None:
        self._render_job = None
        if self.source_image is None or not self.winfo_exists():
            return
        self.update_idletasks()
        scale = max(0.25, min(8.0, float(self.zoom_percent) / 100.0))
        target = (
            max(1, round(self.source_image.width * scale)),
            max(1, round(self.source_image.height * scale)),
        )
        if target == self.source_image.size:
            display = self.source_image
        else:
            display = self.source_image.resize(target, Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(display)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, target[0], target[1]))
        self.display_scale = scale
        self.zoom_var.set(f"{self.zoom_percent}%")

        self.selection_item = None
        self.drag_start = None
        if self.selection_source is not None:
            x0, y0, x1, y1 = self.selection_source
            self.selection_item = self.canvas.create_rectangle(
                round(x0 * scale),
                round(y0 * scale),
                round(x1 * scale),
                round(y1 * scale),
                outline="#e53935",
                width=2,
            )
        if reset_view:
            try:
                self.canvas.xview_moveto(0.0)
                self.canvas.yview_moveto(0.0)
            except tk.TclError:
                pass

    def _event_canvas_point(self, event: tk.Event) -> tuple[int, int]:
        return (
            int(round(float(self.canvas.canvasx(event.x)))),
            int(round(float(self.canvas.canvasy(event.y)))),
        )

    def _clamp_point(self, x: int, y: int) -> tuple[int, int]:
        if self.source_image is None:
            return x, y
        x1 = round(self.source_image.width * self.display_scale)
        y1 = round(self.source_image.height * self.display_scale)
        return max(0, min(x1, x)), max(0, min(y1, y))

    def _start_drag(self, event: tk.Event) -> None:
        if self.source_image is None:
            return
        canvas_x, canvas_y = self._event_canvas_point(event)
        self.drag_start = self._clamp_point(canvas_x, canvas_y)
        self.selection_source = None
        if self.selection_item is not None:
            self.canvas.delete(self.selection_item)
        x, y = self.drag_start
        self.selection_item = self.canvas.create_rectangle(
            x, y, x, y, outline="#e53935", width=2
        )

    def _drag(self, event: tk.Event) -> None:
        if self.drag_start is None or self.selection_item is None:
            return
        canvas_x, canvas_y = self._event_canvas_point(event)
        x, y = self._clamp_point(canvas_x, canvas_y)
        self.canvas.coords(
            self.selection_item,
            self.drag_start[0],
            self.drag_start[1],
            x,
            y,
        )

    def _finish_drag(self, event: tk.Event) -> None:
        if self.drag_start is None or self.source_image is None:
            return
        canvas_x, canvas_y = self._event_canvas_point(event)
        x, y = self._clamp_point(canvas_x, canvas_y)
        x0, y0 = self.drag_start
        left, right = sorted((x0, x))
        top, bottom = sorted((y0, y))
        if right - left < 3 or bottom - top < 3:
            self.selection_source = None
            self.selection_var.set("框选区域太小，请重新框选。")
            return

        scale = max(1e-9, self.display_scale)
        source_box = (
            max(0, min(self.source_image.width, round(left / scale))),
            max(0, min(self.source_image.height, round(top / scale))),
            max(0, min(self.source_image.width, round(right / scale))),
            max(0, min(self.source_image.height, round(bottom / scale))),
        )
        if source_box[2] <= source_box[0] or source_box[3] <= source_box[1]:
            self.selection_source = None
            self.selection_var.set("框选区域太小，请重新框选。")
            return
        self.selection_source = source_box
        self.selection_var.set(
            f"已框选原图 {source_box[2] - source_box[0]}×"
            f"{source_box[3] - source_box[1]} px ｜ 当前缩放 {self.zoom_percent}%"
        )

    def _source_box(self) -> tuple[int, int, int, int] | None:
        return self.selection_source

    def _save(self) -> None:
        if self.source_image is None or not self.images:
            return
        box = self._source_box()
        if box is None:
            messagebox.showinfo(
                "请先框选", "请在右侧页面中拖框选择一个实际印刷标记。", parent=self
            )
            return
        role = _ROLE_LABEL_TO_VALUE.get(self.role_var.get(), "entry_marker")
        path = self.images[self.page_index]
        crop = self.source_image.crop(box)
        sample_id = (
            f"{role}:{path.stem}:"
            + "-".join(str(value) for value in box)
        )
        try:
            sample = build_visual_marker_sample(
                crop,
                role=role,
                literal=self.literal_var.get().strip(),
                sample_id=sample_id,
                source_page=path.name,
                source_box=box,
            )
        except Exception as exc:
            messagebox.showerror(
                "样本无效",
                f"无法从该框选区域建立视觉模板：\n{exc}",
                parent=self,
            )
            return
        self.on_saved(sample)
        self.destroy()


class VisualMarkerSamplesDialog(tk.Toplevel):
    """Inspect and delete saved marker samples."""

    def __init__(
        self,
        parent: tk.Misc,
        samples: list[dict],
        *,
        on_changed: Callable[[list[dict]], None],
    ) -> None:
        super().__init__(parent)
        self.samples = [dict(sample) for sample in samples]
        self.on_changed = on_changed
        self.title("本词典视觉标记样本")
        self.geometry("660x420")
        self.transient(parent)
        self.grab_set()

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)
        ttk.Label(
            outer,
            text="样本保存在 Project Profile 中；删除不会修改原始扫描页。",
            foreground="#666666",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        frame = ttk.Frame(outer)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(frame, exportselection=False)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        preview = ttk.LabelFrame(frame, text="归一化模板", padding=8)
        preview.grid(row=0, column=2, sticky="ns", padx=(10, 0))
        self.preview_label = ttk.Label(preview, text="选择一个样本")
        self.preview_label.pack(anchor="center", padx=8, pady=8)
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.listbox.bind("<<ListboxSelect>>", self._show_selected_preview)
        self._refresh()

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(footer, text="删除所选", command=self._delete_selected).pack(
            side="left"
        )
        ttk.Button(footer, text="关闭", command=self.destroy).pack(side="right")

    def _refresh(self) -> None:
        self.listbox.delete(0, "end")
        for index, sample in enumerate(self.samples, start=1):
            role = _ROLE_VALUE_TO_LABEL.get(
                str(sample.get("role") or ""), str(sample.get("role") or "")
            )
            literal = str(sample.get("literal") or "未指定")
            page = str(sample.get("source_page") or "未知页")
            box = sample.get("source_box") or []
            self.listbox.insert(
                "end", f"{index:>2}. {role} · {literal} · {page} · {box}"
            )

    def _show_selected_preview(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if not selection:
            self.preview_photo = None
            self.preview_label.configure(image="", text="选择一个样本")
            return
        sample = self.samples[int(selection[0])]
        try:
            size = int(sample.get("size") or 0)
            bitmap = str(sample.get("bitmap") or "")
            if size <= 0 or len(bitmap) != size * size:
                raise ValueError("invalid bitmap")
            pixels = [0 if value == "1" else 255 for value in bitmap]
            image = Image.new("L", (size, size), 255)
            image.putdata(pixels)
            image = image.resize((160, 160), Image.Resampling.NEAREST)
            self.preview_photo = ImageTk.PhotoImage(image.convert("RGB"))
            self.preview_label.configure(image=self.preview_photo, text="")
        except Exception:
            self.preview_photo = None
            self.preview_label.configure(image="", text="模板预览不可用")

    def _delete_selected(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        del self.samples[int(selection[0])]
        self.on_changed([dict(sample) for sample in self.samples])
        self._refresh()
        self._show_selected_preview()
