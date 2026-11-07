"""Main canvas rendering of page pixels, review markers, SECTIONs and PPP.

Canonical implementation for the four main page-draw entrypoints. The
PictureCaptureApp API remains unchanged and keeps runtime call-site patchpoints.
No heavy app-module imports, global installer or duplicate geometry pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL import Image


@dataclass(frozen=True)
class MainCanvasRenderDeps:
    """Capture the original live application module bindings per redraw call."""
    clear_alpha_line_photos: object
    clear_alpha_polygon_records: object
    draw_layout_visualization_if_enabled: object
    draw_ocr_crop_preview: object
    parameter_scale: object
    create_alpha_canvas_line: object
    scaled_overlay_line_width: object
    tk: object
    create_alpha_canvas_polygon: object
    _entry_font_spec: object
    resolve_content_font_family: object
    label_text: object
    create_illustration_delete_control: object
    entry_crop_piece_filename: object
    _review_crop_settings: object
    _review_line_box: object
    Image: object
    ImageTk: object


def _draw_crop_plan_preview(self, deps: MainCanvasRenderDeps) -> None:
    """Overlay the exact entry/PPP crop plan on the main page image."""
    draw_layout_visualization_if_enabled = deps.draw_layout_visualization_if_enabled
    _entry_font_spec = deps._entry_font_spec
    resolve_content_font_family = deps.resolve_content_font_family
    entry_crop_piece_filename = deps.entry_crop_piece_filename
    if self.image is None:
        draw_layout_visualization_if_enabled(self)
        return
    try:
        plan = self._current_page_crop_plan()
    except Exception as exc:
        self.status_var.set(f"切图预览生成失败：{exc}")
        return
    if plan is None:
        return
    from ..crop.preview_labels import draw_crop_preview_label, format_crop_preview_entry_label
    scale = self.view_scale
    illustrated_entries = {p.entry_ref_index for p in plan.entry_pieces if p.source_mode == "linked_original" and p.entry_ref_index is not None}
    from ..crop.preview_display_settings import crop_preview_font_spec
    preview_font = crop_preview_font_spec(
        self, scale, resolve_content_font_family, _entry_font_spec,
    )
    for piece in plan.entry_pieces:
        x0,y0,x1,y1=piece.box
        if piece.entry_ref_index in illustrated_entries:
            color = "#2e7d32"
            dash = ()
        else:
            color = "#00acc1"
            dash = (6, 4)
        self.canvas.create_rectangle(x0*scale,y0*scale,x1*scale,y1*scale,outline=color,width=2,dash=dash,tags=("crop-plan",))
        filename = entry_crop_piece_filename(self.current_page.stem, piece)
        label = format_crop_preview_entry_label(piece.word, filename)
        draw_crop_preview_label(
            self.canvas, ((x0+x1)/2)*scale, (y0+3)*scale,
            text=label, outline=color, anchor="n", justify="center",
            font=preview_font,
        )
        if piece.merge_polygon_indices:
            for pi in piece.merge_polygon_indices:
                if 0 <= pi < len(self.polygons):
                    region=self.polygons[pi]
                    coords=[v*scale for pt in region.points for v in pt]
                    if len(coords)>=6:
                        self.canvas.create_polygon(*coords,fill="",outline="#ef6c00",width=3,tags=("crop-plan",))
    # A stop line ends the preceding real entry; the following region
    # remains visible in preview only and is NEVER exported as a WW image.
    for x0, y0, x1, y1 in plan.auxiliary_gaps:
        color = "#d97706"
        self.canvas.create_rectangle(
            x0 * scale, y0 * scale, x1 * scale, y1 * scale,
            outline=color, width=2, dash=(4, 3),
            tags=("crop-plan", "auxiliary-gap"),
        )
        draw_crop_preview_label(
            self.canvas, ((x0 + x1) / 2) * scale, (y0 + 3) * scale,
            text="【辅助不切】", outline=color, anchor="n",
            justify="center", font=preview_font,
        )
    # PPP decisions: green/orange travel with headword; magenta/red are
    # standalone and will be whitened before ordinary headword cropping.
    standalone_count=linked_count=partial_count=0
    for dec in plan.illustrations:
        if not (0 <= dec.polygon_index < len(self.polygons)):
            continue
        region=self.polygons[dec.polygon_index]
        coords=[v*scale for pt in region.points for v in pt]
        if len(coords)<6: continue
        if dec.relation=="contained": color="#2e7d32"; text="随词条｜完整包含"; linked_count+=1
        elif dec.relation=="partial":
            if plan.integrate_illustrations:
                color="#ef6c00"; text="随词条｜部分相交→联合"
            else:
                color="#8e24aa"; text="独立PPP｜部分超出词条（未综合插图）"; standalone_count+=1
            partial_count+=1
        elif dec.associated_entry_index is not None: color="#8e24aa"; text="独立PPP｜关联词条外部"; standalone_count+=1
        else: color="#d32f2f"; text="独立PPP｜未关联"; standalone_count+=1
        self.canvas.create_polygon(*coords,fill="",outline=color,width=3,tags=("crop-plan",))
        minx=min(p[0] for p in region.points); miny=min(p[1] for p in region.points)
        label=f"{dec.name}  {text}" + (f"  [{dec.associated_word}]" if dec.associated_word else "")
        draw_crop_preview_label(
            self.canvas, (minx+4)*scale, (miny+4)*scale, text=label,
            outline=color, anchor="nw",
            font=("Microsoft YaHei", max(7, round(9*scale)), "bold"),
        )
    mode = "综合插图" if plan.integrate_illustrations else "仅词条矩形"
    self.status_var.set(
        f"切图预览｜{mode}｜词条切图片段 {len(plan.entry_pieces)}｜辅助不切 {len(plan.auxiliary_gaps)}｜随词条PPP {linked_count}｜部分相交 {partial_count}｜独立PPP {standalone_count}"
    )

def redraw(self, deps: MainCanvasRenderDeps) -> None:
    clear_alpha_line_photos = deps.clear_alpha_line_photos
    clear_alpha_polygon_records = deps.clear_alpha_polygon_records
    draw_layout_visualization_if_enabled = deps.draw_layout_visualization_if_enabled
    draw_ocr_crop_preview = deps.draw_ocr_crop_preview
    parameter_scale = deps.parameter_scale
    create_alpha_canvas_line = deps.create_alpha_canvas_line
    scaled_overlay_line_width = deps.scaled_overlay_line_width
    tk = deps.tk
    create_alpha_canvas_polygon = deps.create_alpha_canvas_polygon
    _entry_font_spec = deps._entry_font_spec
    resolve_content_font_family = deps.resolve_content_font_family
    label_text = deps.label_text
    create_illustration_delete_control = deps.create_illustration_delete_control
    clear_alpha_line_photos(self)
    clear_alpha_polygon_records(self)
    self._sync_polygon_label_texts()
    self.canvas.delete("all")
    for widget in self.overlay_widgets:
        widget.destroy()
    self.overlay_widgets.clear()
    self.entry_editor_bindings.clear()
    self.polygon_label_bindings.clear()
    self._polygon_canvas_items.clear()
    self.candidate_check_vars.clear()
    self._entry_visuals.clear()
    if self.image is None:
        return
    size = (max(1, round(self.image.width * self.view_scale)), max(1, round(self.image.height * self.view_scale)))
    if self._preprocess_mode_active():
        self._redraw_preprocess_preview(size)
        draw_layout_visualization_if_enabled(self)
        return
    photo = self._get_cached_display_photo(size)
    self.canvas.create_image(0, 0, image=photo, anchor="nw", tags="page")
    from .illustrated_main_canvas import render_illustrated_main_overlay
    if render_illustrated_main_overlay(self):
        return
    if self.crop_preview_var.get():
        self._draw_crop_plan_preview()
        crop_geometry = self._get_cached_display_geometry()
        self._draw_page_sections(crop_geometry)
        self._auxiliary_controller.redraw()
        self._draw_percentage_rulers(crop_geometry)
        ruler_margin = 28 if self._rulers_visible() else 0
        self.canvas.configure(
            scrollregion=(-ruler_margin, 0, size[0] + ruler_margin, size[1] + ruler_margin)
        )
        if self.cursor_canvas_xy is not None:
            self.draw_cursor_guides(*self.cursor_canvas_xy)
        self.ref_box_controller.render()
        self.ref_box_controller.bind_overlay_widgets()
        draw_ocr_crop_preview(self)
        draw_layout_visualization_if_enabled(self)
        return
    hidden = bool(self.hide_var.get())
    geometry = self._get_cached_display_geometry()
    overlay_scale = self.view_scale / parameter_scale(self.image, self.settings)
    self._draw_review_entry_highlight(geometry)
    show_guides = (
        self.quick_bool_vars.get("show_column_guides").get()
        if hasattr(self, "quick_bool_vars") and "show_column_guides" in self.quick_bool_vars
        else self.settings.show_column_guides
    )
    if show_guides:
        for path in geometry.column_paths:
            source_points = [geometry.canonical_to_source(x, y) for y, x in path.points]
            coords = [coordinate * self.view_scale for point in source_points for coordinate in point]
            if len(coords) >= 4:
                create_alpha_canvas_line(
                    self,
                    tuple(coords),
                    fill=self.settings.guide_color,
                    width=scaled_overlay_line_width(self.settings.guide_width, overlay_scale),
                    opacity=self.settings.guide_opacity,
                    smooth=True,
                )
    self._draw_page_sections(geometry)
    self._auxiliary_controller.redraw()
    self._draw_percentage_rulers(geometry)
    if not hidden:
        processing_readonly = self._foreground_batch_state(self.current_index) == "processing"
        for index, entry in enumerate(self._ordered_entries_reading_order()):
            self._draw_entry_overlay(
                entry, index, geometry, size, overlay_scale,
                processing_readonly=processing_readonly,
            )

    # v2.0: expose every OCR left-edge candidate as a right-side checkbox.
    # Rejected lemma rows can therefore be promoted manually without
    # changing parser thresholds or adding a special filter rule.
    show_candidates = (
        self.quick_bool_vars.get("paddle_show_candidate_checkboxes").get()
        if hasattr(self, "quick_bool_vars") and "paddle_show_candidate_checkboxes" in self.quick_bool_vars
        else self.settings.paddle_show_candidate_checkboxes
    )
    if show_candidates:
        for cand in self.ocr_review_candidates:
            try:
                col = max(0, min(len(geometry.column_starts) - 1, int(cand.get("column", 0))))
                cy_source = int(cand.get("source_y", 0))
            except (TypeError, ValueError):
                continue
            if cy_source <= 0:
                continue
            cx_source = int(cand.get("source_x", 0))
            _cand_u, cand_v = geometry.source_to_canonical(cx_source, cy_source)
            control_source = geometry.canonical_to_source(
                geometry.x_at(col, cand_v) + round(geometry.column_widths[col] * 0.955),
                cand_v,
            )
            cx = control_source[0] * self.view_scale
            cy = control_source[1] * self.view_scale
            cid = str(cand.get("candidate_id", ""))
            if not cid:
                continue
            var = tk.BooleanVar(value=self._candidate_is_selected(cand))
            self.candidate_check_vars[cid] = var
            conf = cand.get("confidence")
            try:
                conf_value = float(conf) if conf is not None else None
            except (TypeError, ValueError):
                conf_value = None
            is_original_y = str(cand.get("position_variant", "refined")) in {"original", "anchor"}
            bg = "#d9ecff" if is_original_y else self._confidence_bg(conf_value)
            outline = "#1976d2" if is_original_y else ("#d84315" if cand.get("issue_types") else "#9e9e9e")
            check = tk.Checkbutton(
                self.canvas, variable=var, bg=bg, activebackground=bg,
                selectcolor=bg, bd=0, highlightthickness=1,
                highlightbackground=outline,
                command=lambda c=cid, v=var: self.candidate_checkbox_changed(c, v),
            )
            self.overlay_widgets.append(check)
            self.canvas.create_window(cx, cy, window=check, anchor="nw")
    show_shapes = bool(self.polygon_var.get() or self.polygon_draw_var.get())
    show_labels = bool(self.settings.show_illustration_labels)
    numbered_labels = (
        self._illustration_controller_for_call().preview_labels() if show_labels else []
    )
    if show_shapes or show_labels:
        for region_index, region in enumerate(self.polygons):
            coords = [value * self.view_scale for point in region.points for value in point]
            if len(coords) < 6:
                continue
            polygon_item = None
            if show_shapes:
                polygon_item = create_alpha_canvas_polygon(
                    self,
                    tuple(coords),
                    outline=self.settings.illustration_outline_color,
                    fill=self.settings.illustration_fill_color,
                    width=scaled_overlay_line_width(self.settings.illustration_outline_width, overlay_scale),
                    opacity=self.settings.illustration_fill_opacity,
                    tags=("ppp-overlay", f"ppp-region-{region_index}"),
                )
            handles: list[int] = []
            edge_handles: dict[str, int] = {}
            if self.polygon_draw_var.get():
                radius = 5
                for point_index, (px, py) in enumerate(region.points):
                    cx, cy = px * self.view_scale, py * self.view_scale
                    handles.append(self.canvas.create_oval(
                        cx - radius, cy - radius, cx + radius, cy + radius,
                        fill="#ffffff", outline=self.settings.illustration_outline_color, width=2,
                        tags=("ppp-overlay", f"ppp-handle-{region_index}-{point_index}"),
                    ))
                bounds = self._rectangle_bounds(region)
                if bounds is not None:
                    x0, y0, x1, y1 = bounds
                    mids = {
                        "left": (x0, (y0 + y1) / 2),
                        "right": (x1, (y0 + y1) / 2),
                        "top": ((x0 + x1) / 2, y0),
                        "bottom": ((x0 + x1) / 2, y1),
                    }
                    for side, (mx, my) in mids.items():
                        cx, cy = mx * self.view_scale, my * self.view_scale
                        edge_handles[side] = self.canvas.create_rectangle(
                            cx - radius, cy - radius, cx + radius, cy + radius,
                            fill=self.settings.illustration_outline_color, outline="#ffffff", width=1,
                            tags=("ppp-overlay", f"ppp-edge-{region_index}-{side}"),
                        )

            label_item = None
            label_frame = None
            if show_labels:
                label_frame = tk.Frame(
                    self.canvas, bg=self.settings.illustration_label_fill_color,
                    bd=0, highlightthickness=max(0, int(self.settings.illustration_label_border_width)),
                    highlightbackground=self.settings.illustration_label_border_color,
                    highlightcolor=self.settings.illustration_label_border_color,
                )
                label_entry = tk.Entry(
                    label_frame, width=18, relief="flat", bd=0, highlightthickness=0,
                    bg=self.settings.illustration_label_fill_color,
                    font=_entry_font_spec(
                        resolve_content_font_family(
                            self.canvas,
                            self.settings.illustration_label_font_family,
                            self.settings.ocr_language,
                        ),
                        max(7, round(self.settings.illustration_label_font_size * self.view_scale)),
                        self.settings.illustration_label_font_bold,
                        self.settings.illustration_label_font_italic,
                    ),
                )
                label_entry.insert(0, label_text(numbered_labels[region_index]))
                label_entry.bind("<FocusOut>", lambda _e, r=region, w=label_entry: self._update_polygon_label(r, w))
                label_entry.bind("<Return>", lambda _e, r=region, w=label_entry: self._commit_polygon_label_return(r, w))
                label_entry.pack(side="left")
                self.overlay_widgets.append(label_frame)
                self.polygon_label_bindings.append((label_entry, region))
                label_frame.update_idletasks()
                label_x, label_y = self._polygon_label_canvas_position(region, label_frame)
                label_item = self.canvas.create_window(
                    label_x, label_y, window=label_frame, anchor="nw", tags=("ppp-overlay",)
                )
            delete_item = (create_illustration_delete_control(self, region, region_index)
                           if show_shapes else None)
            self._polygon_canvas_items[region_index] = {
                "polygon": polygon_item,
                "handles": handles,
                "edge_handles": edge_handles,
                "label_window": label_item,
                "label_frame": label_frame,
                "delete_window": delete_item,
            }
        if self.new_polygon:
            coords = [value * self.view_scale for point in self.new_polygon for value in point]
            if len(coords) >= 4:
                self.canvas.create_line(*coords, fill="#00aa55", width=2, tags=("ppp-overlay",))
            for px, py in self.new_polygon:
                cx, cy = px * self.view_scale, py * self.view_scale
                self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#ffffff", outline="#00aa55", width=2, tags=("ppp-overlay",))
    ruler_margin = 28 if self._rulers_visible() else 0
    self.canvas.configure(
        scrollregion=(-ruler_margin, 0, size[0] + ruler_margin, size[1] + ruler_margin)
    )
    if self.cursor_canvas_xy is not None:
        self.draw_cursor_guides(*self.cursor_canvas_xy)

    self._apply_current_appearance(self.canvas)
    self.ref_box_controller.render()
    self.ref_box_controller.bind_overlay_widgets()
    draw_ocr_crop_preview(self)
    draw_layout_visualization_if_enabled(self)

def _draw_page_sections(self, deps: MainCanvasRenderDeps, geometry=None) -> None:
    """Draw page-local SECTION bounds in source space on the main canvas."""
    parameter_scale = deps.parameter_scale
    scaled_overlay_line_width = deps.scaled_overlay_line_width
    tk = deps.tk
    self.canvas.delete("page-section-overlay")
    if not self.page_sections or self.image is None:
        return
    show_sections = bool(getattr(self.settings, "show_page_sections", True))
    if not show_sections and not self._section_editing:
        return
    geometry = geometry or self._get_cached_display_geometry()
    canonical_width, _canonical_height = geometry.transform.canonical_size(self.image.size)
    overlay_scale = self.view_scale / parameter_scale(self.image, self.settings)
    line_width = scaled_overlay_line_width(
        int(getattr(self.settings, "page_section_width", 2) or 2),
        overlay_scale,
    )
    line_fill = str(getattr(self.settings, "page_section_color", "#1976d2") or "#1976d2")
    for index, section in enumerate(self.page_sections):
        for side, v in (("top", section.top_v), ("bottom", section.bottom_v)):
            start = geometry.canonical_to_source(0, int(v))
            end = geometry.canonical_to_source(canonical_width, int(v))
            self.canvas.create_line(
                start[0] * self.view_scale, start[1] * self.view_scale,
                end[0] * self.view_scale, end[1] * self.view_scale,
                fill=line_fill, width=line_width, dash=(7, 4),
                tags=("page-section-overlay", f"page-section-{index}-{side}"),
            )
        # Keep the SECTION badge centered above that SECTION's starting
        # boundary. This makes the label read as the caption of the top
        # boundary rather than as content inside the SECTION.
        top_start = geometry.canonical_to_source(0, int(section.top_v))
        top_end = geometry.canonical_to_source(canonical_width, int(section.top_v))
        label_x = ((top_start[0] + top_end[0]) / 2.0) * self.view_scale
        label_y = min(top_start[1], top_end[1]) * self.view_scale - max(
            4, round(4 * self.view_scale)
        )
        text_item = self.canvas.create_text(
            label_x,
            label_y,
            text=f"SECTION {index + 1}",
            fill="#ffffff", anchor="s",
            font=("Microsoft YaHei", max(8, round(10 * self.view_scale)), "bold"),
            tags=("page-section-overlay",),
        )
        bbox = self.canvas.bbox(text_item)
        if bbox:
            pad_x, pad_y = 4, 2
            label_bg = self.canvas.create_rectangle(
                bbox[0] - pad_x, bbox[1] - pad_y,
                bbox[2] + pad_x, bbox[3] + pad_y,
                fill=line_fill, outline=line_fill,
                tags=("page-section-overlay",),
            )
            self.canvas.tag_lower(label_bg, text_item)
    try:
        self.canvas.tag_raise("page-section-overlay")
    except tk.TclError:
        pass

def _draw_review_entry_highlight(self, deps: MainCanvasRenderDeps, geometry=None) -> None:
    tk = deps.tk
    _review_crop_settings = deps._review_crop_settings
    _review_line_box = deps._review_line_box
    Image = deps.Image
    ImageTk = deps.ImageTk
    self._review_entry_highlight_photo = None
    try:
        self.canvas.delete("proofread-entry-highlight")
    except tk.TclError:
        return
    target = self._review_entry_highlight_target
    if self.image is None or target is None or target[0] != self.current_index:
        return
    _page_index, x_source, y_source = target
    ordered = self._ordered_entries_reading_order()
    entry = min(
        ordered,
        key=lambda item: abs(int(item.x) - x_source) + abs(int(item.y) - y_source),
        default=None,
    )
    if entry is None or abs(int(entry.x) - x_source) > 30 or abs(int(entry.y) - y_source) > 30:
        return
    if geometry is None:
        geometry = self._get_cached_display_geometry()
    # Use exactly the same crop geometry as the proofreading row. Ordinary
    # entries therefore start half a row-gap above the marker and use
    # ``character_height + row_padding``; single-CJK entries retain the
    # review window's independent single-character height.
    review_settings = _review_crop_settings(
        self.image, self.settings, self.canvas.winfo_width()
    )
    left, top, right, bottom = _review_line_box(
        entry, geometry, self.image, review_settings
    )
    # Tk Canvas rectangle fills have no real alpha channel; the previous
    # ``gray50`` stipple therefore looked grainy/frosted.  Use a tiny RGBA
    # PhotoImage instead so the marker is a genuinely translucent pale-yellow
    # highlighter and the scanned text remains clearly visible underneath.
    x0 = int(round(left * self.view_scale))
    y0 = int(round(top * self.view_scale))
    x1 = int(round(right * self.view_scale))
    y1 = int(round(bottom * self.view_scale))
    overlay = Image.new(
        "RGBA",
        (max(1, x1 - x0), max(1, y1 - y0)),
        (255, 238, 128, 92),
    )
    self._review_entry_highlight_photo = ImageTk.PhotoImage(overlay)
    item = self.canvas.create_image(
        x0, y0, anchor="nw", image=self._review_entry_highlight_photo,
        tags=("proofread-entry-highlight",),
    )
    # Keep the highlight above the scanned page but below all editable
    # overlays, so it reads as a line-level marker rather than a cover.
    try:
        self.canvas.tag_raise(item, "page")
    except tk.TclError:
        pass



# Main-canvas crop plan assembly; preview and publication share the same planner.

def _current_page_crop_plan(self, *, deps: dict[str, Any]):
    build_page_crop_plan = deps["build_page_crop_plan"]
    if self.image is None or self.current_page is None:
        return None
    config = self._load_crop_settings()
    special = config.get("special_pages", {}).get(self.current_page.stem, {}) if isinstance(config.get("special_pages", {}), dict) else {}
    top_y = int(special.get("top_y", config.get("general_top_y", self.settings.start_y)))
    bottom_y = int(special.get("bottom_y", config.get("general_bottom_y", 0)))
    margin = int(config.get("polygon_margin", 0))
    entry_left = int(config.get("entry_left_padding_x", 0))
    entry_right = int(config.get("entry_right_padding_x", 0))
    integrate_illustrations = bool(config.get("integrate_illustrations", True))
    return build_page_crop_plan(
        self.image, list(self.entries), list(self.polygons), self.settings,
        top_y=top_y, bottom_y=bottom_y, illustration_margin=margin,
        entry_left_padding=entry_left, entry_right_padding=entry_right,
        integrate_illustrations=integrate_illustrations,
        profile_page_index=max(0, int(self.current_index)),
        page_sections=list(self.page_sections),
        auxiliary_lines=list(self._auxiliary_edits.lines), page_stem=self.current_page.stem, previous_entry_ref=self._illustration_controller_for_call().previous_entry_ref(),
    )
