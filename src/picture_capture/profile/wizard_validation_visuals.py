"""Profile Wizard overlay painter, results renderer and validation completion."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import Image
    from ..models import AppSettings


def marker_preview(
    image: Image.Image, entries, geometry, settings: AppSettings,
    page_index: int, preview_width: int, *, deps,
) -> Image.Image:
    Image = deps["Image"]
    ImageDraw = deps["ImageDraw"]
    excluded_source_side = deps["excluded_source_side"]
    excluded_source_side_percent = deps["excluded_source_side_percent"]
    source = image.copy()
    target_width = max(320, int(preview_width))
    target_height = max(
        1, round(source.height * target_width / max(1, source.width)),
    )
    thumb = source.resize(
        (target_width, target_height), Image.Resampling.LANCZOS,
    ).convert("RGB")
    sx = thumb.width / max(1, source.width)
    sy = thumb.height / max(1, source.height)
    # Drawing an RGBA fill onto an RGB image alpha-composites the mask.
    # Drawing onto an RGBA image and then converting to RGB would instead
    # discard alpha and make the validation masks look fully opaque.
    draw = ImageDraw.Draw(thumb, "RGBA")

    def shade_source_box(box: tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = box
        if x1 <= x0 or y1 <= y0:
            return
        draw.rectangle(
            (x0 * sx, y0 * sy, x1 * sx, y1 * sy),
            fill=(255, 215, 0, 105),
        )

    canonical_w, canonical_h = geometry.transform.canonical_size(source.size)
    header_mode = str(getattr(settings, "profile_header_mode", "auto") or "auto")
    footer_mode = str(getattr(settings, "profile_footer_mode", "auto") or "auto")
    if header_mode == "auto" and geometry.top > 0:
        shade_source_box(
            geometry.transform.canonical_box_to_source(
                (0, 0, canonical_w, min(canonical_h, geometry.top)),
                source.size,
            )
        )
    elif header_mode == "present":
        pct = max(0.0, min(
            35.0, float(getattr(settings, "profile_header_percent", 6.0))
        ))
        margin = round(source.height * pct / 100.0)
        shade_source_box((0, 0, source.width, margin))

    if footer_mode == "auto" and geometry.bottom < canonical_h:
        shade_source_box(
            geometry.transform.canonical_box_to_source(
                (0, max(0, geometry.bottom), canonical_w, canonical_h),
                source.size,
            )
        )
    elif footer_mode == "present":
        pct = max(0.0, min(
            35.0, float(getattr(settings, "profile_footer_percent", 5.0))
        ))
        margin = round(source.height * pct / 100.0)
        shade_source_box(
            (0, max(0, source.height - margin), source.width, source.height)
        )

    side = excluded_source_side(settings, page_index)
    if side:
        margin = round(
            source.width
            * excluded_source_side_percent(settings, page_index)
            / 100.0
        )
        if side == "left":
            shade_source_box((0, 0, margin, source.height))
        else:
            shade_source_box((source.width - margin, 0, source.width, source.height))

    for entry in entries:
        u, v = geometry.source_to_canonical(entry.x, entry.y)
        try:
            col = min(
                range(len(geometry.column_starts)),
                key=lambda idx: abs(geometry.x_at(idx, v) - u),
            )
            x0 = geometry.x_at(col, v)
            x1 = x0 + max(8, int(geometry.column_widths[col] * 0.55))
            start, end = geometry.transform.canonical_marker_to_source(
                (x0, v), (x1, v), source.size,
            )
            draw.line(
                (start[0] * sx, start[1] * sy, end[0] * sx, end[1] * sy),
                fill=(255, 0, 0, 255), width=1,
            )
        except Exception:
            x, y = round(entry.x * sx), round(entry.y * sy)
            draw.point((x, y), fill=(255, 0, 0, 255))
    return thumb.convert("RGB")



def render_validation_result(self, *, deps) -> None:
    ttk = deps["ttk"]
    Image = deps["Image"]
    ImageTk = deps["ImageTk"]
    themed_display_image = deps["themed_display_image"]
    for child in self.validation_frame.winfo_children():
        child.destroy()
    self._validation_photos.clear()
    if not self._validation_results:
        self.validation_caption_var.set("")
        self.validation_diagnostic_var.set(
            "测试方式：PaddleOCR（强制重新识别）｜尚无测试结果"
        )
        self.validation_prev_button.configure(state="disabled")
        self.validation_next_button.configure(state="disabled")
        return

    self.validation_preview_slot %= len(self._validation_results)
    _index, name, count, columns, preview, coverage, error = self._validation_results[self.validation_preview_slot]
    total = len(self._validation_results)
    self.validation_caption_var.set(
        f"{self.validation_preview_slot + 1}/{total} · {name}"
    )
    self.validation_diagnostic_var.set(
        coverage or "测试方式：PaddleOCR（强制重新识别）\n诊断信息未生成"
    )
    state = "normal" if total > 1 else "disabled"
    self.validation_prev_button.configure(state=state)
    self.validation_next_button.configure(state=state)

    cell = ttk.LabelFrame(self.validation_frame, text=name, padding=8)
    cell.grid(row=0, column=0, sticky="ew")
    cell.columnconfigure(0, weight=1)
    if preview is not None:
        display = preview.copy()
        self.update_idletasks()
        right_w = int(getattr(self, "right_canvas", self).winfo_width())
        right_h = int(getattr(self, "right_canvas", self).winfo_height())
        available_w = max(
            360,
            (right_w - 24) if right_w > 100 else self._wizard_image_width - 24,
        )
        available_h = max(
            360,
            (right_h - 120) if right_h > 200 else self._wizard_height - 160,
        )
        if getattr(self, "validation_fit_mode", "height") == "width":
            scale = available_w / max(1, display.width)
        else:
            scale = available_h / max(1, display.height)
        target = (
            max(1, round(display.width * scale)),
            max(1, round(display.height * scale)),
        )
        if target != display.size:
            display = display.resize(target, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(
            themed_display_image(
                display, getattr(self.parent, "appearance_mode", "light")
            )
        )
        self._validation_photos.append(photo)
        ttk.Label(cell, image=photo, anchor="n").pack(anchor="n")
        ttk.Label(
            cell, text=f"检出 {count} 个词头 · {columns} 栏",
        ).pack(anchor="w", pady=(4, 0))
    else:
        ttk.Label(
            cell, text=f"测试失败：{error}", wraplength=620,
        ).pack(anchor="w", padx=10, pady=30)



def finish_validation(self, results) -> None:
    self._validation_running = False
    self.validate_button.configure(state="normal")
    revision_changed = self._validation_revision_started != self._profile_revision
    self._validation_results = list(results)
    self.validation_preview_slot = 0

    failures = sum(
        1 for _index, _name, _count, _columns, preview, _coverage, _error in results
        if preview is None
    )
    validated_pages = [
        name for _index, name, _count, _columns, preview, _coverage, _error in results
        if preview is not None
    ]
    self.working.profile_last_validated_pages = (
        validated_pages if failures == 0 and not revision_changed else []
    )
    if revision_changed:
        self.validation_status_var.set(
            "测试期间设置已改变；本次结果仅供参考，请按当前设置重新测试"
        )
    elif failures:
        self.validation_status_var.set(
            f"完成：{len(results)-failures}/{len(results)} 页成功；请逐页检查失败页后重新测试"
        )
    else:
        self.validation_status_var.set(
            f"完成：{len(results)} 页均已测试；可用左右按钮逐页检查"
        )
    if results and not revision_changed:
        self._set_feedback_buttons("normal")
    self._render_validation_result()

