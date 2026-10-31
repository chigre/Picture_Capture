"""Project Profile Wizard representative-page thumbnails and slot-only picker.

Decoding happens in snapshot workers; Tk photos and cell mutation stay on UI thread.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from tkinter import ttk
    from PIL import Image


def sample_groups(self, *, deps) -> list[ttk.LabelFrame]:
    ttk = deps["ttk"]
    for child in self.sample_frame.winfo_children():
        child.destroy()
    self._sample_cells.clear()
    self._sample_photo_by_slot.clear()
    region_titles = ("前部", "中部", "后部")
    groups: list[ttk.LabelFrame] = []
    for column, title in enumerate(region_titles):
        group = ttk.LabelFrame(self.sample_frame, text=title, padding=5)
        group.grid(row=0, column=column, sticky="nsew", padx=3, pady=2)
        group.columnconfigure(0, weight=1)
        group.rowconfigure(0, weight=1, uniform="sample_row")
        group.rowconfigure(1, weight=1, uniform="sample_row")
        groups.append(group)
    return groups



def show_sample_loading_state(self, *, deps) -> None:
    ttk = deps["ttk"]
    groups = self._sample_groups()
    self._photos.clear()
    for slot, index in enumerate(self.sample_indices):
        path = self.project.images[index]
        group = groups[min(2, slot // 2)]
        cell = ttk.Frame(group)
        cell.grid(row=slot % 2, column=0, sticky="nsew", pady=3)
        cell.columnconfigure(0, weight=1)
        cell.rowconfigure(0, weight=1)
        self._sample_cells[slot] = cell
        ttk.Label(
            cell, text="正在加载代表页…", anchor="center",
        ).pack(fill="x", ipady=24)
        ttk.Label(cell, text=path.name, wraplength=260).pack(anchor="center", pady=(3, 0))
        ttk.Button(
            cell, text="更换…", command=lambda s=slot: self._choose_sample_page(s),
        ).pack(anchor="center", pady=(3, 0))



def start_sample_thumbnail_load(self, *, deps) -> None:
    queue = deps["queue"]
    threading = deps["threading"]
    Image = deps["Image"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    if self._closing or not self.winfo_exists():
        return
    self._thumbnail_load_generation += 1
    generation = self._thumbnail_load_generation
    indices = list(self.sample_indices)
    paths = [self.project.images[index] for index in indices]
    self._show_sample_loading_state()
    self.update_idletasks()
    right_w = int(getattr(self, "right_canvas", self).winfo_width())
    right_h = int(getattr(self, "right_canvas", self).winfo_height())
    available_w = right_w if right_w > 200 else self._wizard_image_width
    available_h = right_h if right_h > 300 else self._wizard_height
    thumb_w = max(180, (available_w - 54) // 3)
    thumb_h = max(220, (available_h - 150) // 2 - 42)

    result_queue: queue.Queue = queue.Queue(maxsize=1)
    self._thumbnail_queue = result_queue

    def worker() -> None:
        results = []
        for slot, (index, path) in enumerate(zip(indices, paths)):
            try:
                with Image.open(path) as opened:
                    image = normalize_page_rgb(opened)
                image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
                results.append((slot, index, path.name, image, None))
            except Exception as exc:
                results.append((slot, index, path.name, None, str(exc)))
        result_queue.put((generation, results))

    threading.Thread(target=worker, daemon=True).start()
    self.after(50, self._poll_sample_thumbnail_load)



def poll_sample_thumbnail_load(self, *, deps) -> None:
    queue = deps["queue"]
    if self._closing:
        self._thumbnail_queue = None
        return
    if self._thumbnail_queue is None:
        return
    try:
        generation, results = self._thumbnail_queue.get_nowait()
    except queue.Empty:
        if self.winfo_exists():
            self.after(50, self._poll_sample_thumbnail_load)
        return
    self._thumbnail_queue = None
    if generation != self._thumbnail_load_generation:
        return
    self._finish_sample_thumbnail_load(results)



def render_sample_thumbnail_slot(
    self, slot: int, index: int, name: str,
    image: Image.Image | None, error: str | None,
    *, deps,
) -> None:
    ttk = deps["ttk"]
    ImageTk = deps["ImageTk"]
    themed_display_image = deps["themed_display_image"]
    """Replace one representative-page cell without rebuilding its siblings."""
    if slot >= len(self.sample_indices) or self.sample_indices[slot] != index:
        return
    cell = self._sample_cells.get(slot)
    if cell is None or not cell.winfo_exists():
        return
    for child in cell.winfo_children():
        child.destroy()
    if image is not None:
        photo = ImageTk.PhotoImage(
            themed_display_image(
                image, getattr(self.parent, "appearance_mode", "light")
            )
        )
        self._sample_photo_by_slot[slot] = photo
        ttk.Label(cell, image=photo, anchor="center").pack(fill="both", expand=True)
    else:
        self._sample_photo_by_slot.pop(slot, None)
        ttk.Label(
            cell, text=f"缩略图失败：{error}", wraplength=250,
        ).pack(fill="x", ipady=20)
    ttk.Label(cell, text=name, wraplength=260).pack(anchor="center", pady=(3, 0))
    ttk.Button(
        cell, text="更换…", command=lambda s=slot: self._choose_sample_page(s),
    ).pack(anchor="center", pady=(3, 0))



def finish_sample_thumbnail_load(self, results, *, deps) -> None:
    ttk = deps["ttk"]
    groups = self._sample_groups()
    self._photos.clear()
    for slot, index, name, image, error in results:
        if slot >= len(self.sample_indices) or self.sample_indices[slot] != index:
            continue
        group = groups[min(2, slot // 2)]
        cell = ttk.Frame(group)
        cell.grid(row=slot % 2, column=0, sticky="nsew", pady=3)
        cell.columnconfigure(0, weight=1)
        cell.rowconfigure(0, weight=1)
        self._sample_cells[slot] = cell
        self._render_sample_thumbnail_slot(slot, index, name, image, error)



def start_sample_thumbnail_slot_load(self, slot: int, *, deps) -> None:
    threading = deps["threading"]
    Image = deps["Image"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    """Decode only one replacement thumbnail and keep all other cells intact."""
    if self._closing or not self.winfo_exists() or not (0 <= slot < len(self.sample_indices)):
        return
    index = self.sample_indices[slot]
    path = self.project.images[index]
    generation = self._thumbnail_slot_generation.get(slot, 0) + 1
    self._thumbnail_slot_generation[slot] = generation
    token = (slot, generation)
    self._thumbnail_slot_pending.add(token)
    result_queue = self._thumbnail_slot_queue

    self.update_idletasks()
    right_w = int(getattr(self, "right_canvas", self).winfo_width())
    right_h = int(getattr(self, "right_canvas", self).winfo_height())
    available_w = right_w if right_w > 200 else self._wizard_image_width
    available_h = right_h if right_h > 300 else self._wizard_height
    thumb_w = max(180, (available_w - 54) // 3)
    thumb_h = max(220, (available_h - 150) // 2 - 42)

    def worker() -> None:
        image = None
        error = None
        try:
            with Image.open(path) as opened:
                image = normalize_page_rgb(opened)
            image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        except Exception as exc:
            error = str(exc)
        result_queue.put(
            (slot, generation, index, path.name, image, error)
        )

    threading.Thread(target=worker, daemon=True).start()
    self.after(50, self._poll_sample_thumbnail_slot_load)



def poll_sample_thumbnail_slot_load(self, *, deps) -> None:
    queue = deps["queue"]
    if self._closing:
        self._thumbnail_slot_pending.clear()
        return
    processed = False
    while True:
        try:
            slot, generation, index, name, image, error = (
                self._thumbnail_slot_queue.get_nowait()
            )
        except queue.Empty:
            break
        processed = True
        self._thumbnail_slot_pending.discard((slot, generation))
        if self._thumbnail_slot_generation.get(slot) != generation:
            continue
        self._render_sample_thumbnail_slot(slot, index, name, image, error)

    if self._thumbnail_slot_pending and self.winfo_exists():
        self.after(50, self._poll_sample_thumbnail_slot_load)
    elif processed:
        self.update_idletasks()



def choose_sample_page(self, slot: int, *, deps) -> None:
    tk = deps["tk"]
    ttk = deps["ttk"]
    messagebox = deps["messagebox"]
    all_indices = list(range(len(self.project.images)))
    if not all_indices:
        return
    auto_candidates = set(self.sample_candidates)
    picker = tk.Toplevel(self)
    picker.title("更换代表页")
    picker.geometry("680x540")
    picker.transient(self)
    picker.grab_set()

    ttk.Label(
        picker,
        text=(
            "自动抽样会避开 0000_*、目录、附录等明显非正文页；"
            "手动更换时仍可从项目全部页面中选择。"
        ),
        wraplength=640,
    ).pack(anchor="w", padx=10, pady=(10, 6))
    body = ttk.Frame(picker)
    body.pack(fill="both", expand=True, padx=10)
    scrollbar = ttk.Scrollbar(body, orient="vertical")
    listing = tk.Listbox(body, yscrollcommand=scrollbar.set, exportselection=False)
    scrollbar.configure(command=listing.yview)
    listing.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    current = self.sample_indices[slot]
    selected_row = current
    for row, index in enumerate(all_indices):
        path = self.project.images[index]
        status = "正文候选" if index in auto_candidates else "自动略过 · 手动可选"
        listing.insert("end", f"{index + 1:05d}    [{status}]    {path.name}")
        if index == current:
            selected_row = row
    listing.selection_set(selected_row)
    listing.see(selected_row)

    def apply_choice(_event=None) -> None:
        selection = listing.curselection()
        if not selection:
            return
        index = all_indices[int(selection[0])]
        current_index = self.sample_indices[slot]
        if index == current_index:
            picker.destroy()
            return
        if index in self.sample_indices:
            messagebox.showinfo("代表页已使用", "这张页面已经在代表页中，请选择另一张。", parent=picker)
            return
        preview_uses_slot = self.template_preview_slot == slot
        self.sample_indices[slot] = index
        self.template_preview_slot = min(
            self.template_preview_slot, len(self.sample_indices) - 1
        )
        self._profile_revision += 1
        self._mark_validation_stale()
        self._analysis_suggestion = {}
        if hasattr(self, "analysis_suggestion_var"):
            self.analysis_suggestion_var.set("代表页已更换，请重新分析当前代表页。")
            self.apply_analysis_button.configure(state="disabled")

        self._start_sample_thumbnail_slot_load(slot)

        # The template preview is hidden while representative pages are
        # being edited. Refresh it only when it is actually visible and the
        # replaced slot is the page currently previewed there.
        if preview_uses_slot and hasattr(self, "notebook"):
            try:
                if self.notebook.index(self.notebook.select()) == 1:
                    self._refresh_template_preview()
            except (tk.TclError, ValueError):
                pass
        picker.destroy()

    listing.bind("<Double-Button-1>", apply_choice)
    footer = ttk.Frame(picker)
    footer.pack(fill="x", padx=10, pady=10)
    ttk.Button(footer, text="取消", command=picker.destroy).pack(side="right")
    ttk.Button(footer, text="使用此页", command=apply_choice).pack(side="right", padx=(0, 8))

