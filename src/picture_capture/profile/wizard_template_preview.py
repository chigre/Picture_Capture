"""Owner for Profile Wizard background template preview and UI-thread callbacks."""
from __future__ import annotations


def refresh_template_preview(self) -> None:
    ttk = deps["ttk"]
    tk = deps["tk"]
    Image = deps["Image"]
    ImageDraw = deps["ImageDraw"]
    ImageTk = deps["ImageTk"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    derive_geometry = deps["derive_geometry"]
    excluded_source_side = deps["excluded_source_side"]
    excluded_source_side_percent = deps["excluded_source_side_percent"]
    effective_page_settings = deps["effective_page_settings"]
    page_template_analysis_image = deps["page_template_analysis_image"]
    page_variant = deps["page_variant"]
    themed_display_image = deps["themed_display_image"]
    HEADER_LABEL_TO_VALUE = deps["HEADER_LABEL_TO_VALUE"]
    FOOTER_LABEL_TO_VALUE = deps["FOOTER_LABEL_TO_VALUE"]
    """Render the representative-page template preview without blocking Tk."""
    if not hasattr(self, "template_preview_frame"):
        return
    for child in self.template_preview_frame.winfo_children():
        child.destroy()
    self._template_photos.clear()
    self._template_preview_canvas = None
    self._template_line_items = []
    self._template_line_paths = []
    self._template_nudge_vector = (0.0, 0.0)
    if not self.sample_indices:
        ttk.Label(self.template_preview_frame, text="没有可预览页面").grid(row=0, column=0)
        self.template_preview_caption_var.set("")
        return

    sample_count = len(self.sample_indices)
    self.template_preview_slot %= sample_count
    slot = int(self.template_preview_slot)
    index = int(self.sample_indices[slot])
    path = self.project.images[index]
    try:
        settings = self._settings_from_ui()
        header_mode = HEADER_LABEL_TO_VALUE.get(self.header_mode_var.get(), "auto")
        footer_mode = FOOTER_LABEL_TO_VALUE.get(self.footer_mode_var.get(), "none")
        header_percent = max(0.0, min(35.0, float(self.header_percent_var.get())))
        footer_percent = max(0.0, min(35.0, float(self.footer_percent_var.get())))
        self.update_idletasks()
        right_width = int(getattr(self, "right_canvas", self).winfo_width())
        target_width = max(
            420,
            (right_width - 24) if right_width > 100
            else (self._wizard_image_width - 24),
        )
        target_height = max(420, int(self._wizard_height * 0.72))
    except Exception as exc:
        ttk.Label(
            self.template_preview_frame,
            text=f"{path.name}\n预览参数无效：{exc}",
        ).grid(row=0, column=0)
        self.template_preview_caption_var.set(path.name)
        return

    ttk.Label(
        self.template_preview_frame,
        text=f"正在后台生成预览…\n{path.name}",
        justify="center",
    ).grid(row=0, column=0, sticky="n", pady=30)
    self.template_preview_caption_var.set(
        f"{slot + 1}/{sample_count} · {path.name} · 正在生成…"
    )
    worker_key = f"profile-template-preview-{id(self)}"
    selected_column = self._selected_column_index()

    def worker():
        with Image.open(path) as opened:
            source = normalize_page_rgb(opened)
        preview = source.copy()
        preview.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(preview, "RGBA")
        w, h = preview.size

        if header_mode == "present":
            draw.rectangle(
                (0, 0, w, round(h * header_percent / 100.0)),
                fill=(255, 215, 0, 105),
            )
        if footer_mode == "present":
            draw.rectangle(
                (0, round(h * (1.0 - footer_percent / 100.0)), w, h),
                fill=(255, 215, 0, 105),
            )

        side = excluded_source_side(settings, index)
        if side:
            sp = excluded_source_side_percent(settings, index)
            margin = round(w * sp / 100.0)
            if side == "left":
                draw.rectangle((0, 0, margin, h), fill=(255, 215, 0, 105))
            else:
                draw.rectangle((w - margin, 0, w, h), fill=(255, 215, 0, 105))

        effective = effective_page_settings(settings, source.size, index)
        analysis_image = page_template_analysis_image(source, effective, index)
        geometry = derive_geometry(analysis_image, effective)
        sx = w / max(1, source.width)
        sy = h / max(1, source.height)
        canonical_w, canonical_h = geometry.transform.canonical_size(source.size)

        if header_mode == "auto" and geometry.top > 0:
            x0, y0, x1, y1 = geometry.transform.canonical_box_to_source(
                (0, 0, canonical_w, min(canonical_h, geometry.top)),
                source.size,
            )
            draw.rectangle(
                (x0 * sx, y0 * sy, x1 * sx, y1 * sy),
                fill=(255, 215, 0, 105),
            )
        if footer_mode == "auto" and geometry.bottom < canonical_h:
            x0, y0, x1, y1 = geometry.transform.canonical_box_to_source(
                (0, max(0, geometry.bottom), canonical_w, canonical_h),
                source.size,
            )
            draw.rectangle(
                (x0 * sx, y0 * sy, x1 * sx, y1 * sy),
                fill=(255, 215, 0, 105),
            )
        line_paths: list[list[tuple[float, float]]] = []
        for path_points in geometry.column_paths:
            points = [
                geometry.canonical_to_source(x, y)
                for y, x in path_points.points
            ]
            line_paths.append([(px * sx, py * sy) for px, py in points])

        # One nudge is exactly one full-resolution image pixel. Cache only
        # the direction induced by an internal mirror/rotation transform.
        canonical_step = 1.0
        anchor_u = canonical_w / 2.0
        anchor_v = canonical_h / 2.0
        p0 = geometry.canonical_to_source(anchor_u, anchor_v)
        p1 = geometry.canonical_to_source(anchor_u + canonical_step, anchor_v)
        nudge_vector = (
            (p1[0] - p0[0]) * sx,
            (p1[1] - p0[1]) * sy,
        )

        variant = page_variant(settings, index)
        side_text = side or "无页边排除"
        region = ("前部", "中部", "后部")[min(2, slot // 2)]
        caption = (
            f"{region} · {slot + 1}/{sample_count} · "
            f"{variant} 页 · {path.name} · 页边：{side_text}"
        )
        return preview, caption, index, slot, line_paths, nudge_vector

    def done(payload) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        preview, caption, result_index, result_slot, line_paths, nudge_vector = payload
        if (
            result_slot != self.template_preview_slot
            or result_slot >= sample_count
            or self.sample_indices[result_slot] != result_index
        ):
            return
        for child in self.template_preview_frame.winfo_children():
            child.destroy()
        photo = ImageTk.PhotoImage(
            themed_display_image(
                preview, getattr(self.parent, "appearance_mode", "light")
            )
        )
        self._template_photos[:] = [photo]
        canvas = tk.Canvas(
            self.template_preview_frame,
            width=preview.width, height=preview.height,
            highlightthickness=0, borderwidth=0,
        )
        canvas.grid(row=0, column=0, sticky="n")
        canvas.create_image(0, 0, image=photo, anchor="nw")
        self._template_preview_canvas = canvas
        self._template_line_paths = [
            [(float(x), float(y)) for x, y in points] for points in line_paths
        ]
        self._template_nudge_vector = (
            float(nudge_vector[0]), float(nudge_vector[1])
        )
        self._template_line_items = []
        for column_index, points in enumerate(self._template_line_paths):
            coords = [coordinate for point in points for coordinate in point]
            if len(coords) < 4:
                self._template_line_items.append(-1)
                continue
            item = canvas.create_line(
                *coords,
                fill="#ee7c00" if column_index == selected_column else "#1e78d2",
                width=4 if column_index == selected_column else 2,
            )
            self._template_line_items.append(item)
        canvas.bind(
            "<Button-1>",
            lambda event: self._select_template_column(
                event, self._template_line_paths
            ),
        )
        self.template_preview_caption_var.set(caption)

    def failed(exc, detail) -> None:
        if detail:
            print(detail)
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        for child in self.template_preview_frame.winfo_children():
            child.destroy()
        ttk.Label(
            self.template_preview_frame,
            text=f"{path.name}\n预览失败：{exc}",
        ).grid(row=0, column=0)
        self.template_preview_caption_var.set(path.name)

    self.parent._start_ui_worker(worker_key, worker, done, failed)

