"""Physical ReviewWindow crop workflow owner.

No import of the heavyweight app module; original Tk callback signatures remain.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from PIL import Image, ImageTk


@dataclass(frozen=True)
class ReviewCropDeps:
    """Original module bindings captured fresh on dispatch."""
    tk: object
    Image: object
    ImageTk: object
    replace: object
    _review_crop_context: object
    _review_line_box: object
    parse_review_crop_multiplier: object
    extended_review_crop_box: object
    _focused_review_is_single_character: object
    themed_display_image: object

def _update_active_crop_preview(self, deps: ReviewCropDeps, index: int) -> None:
    """Expand the active preview downward from its ordinary crop's top Y."""
    tk = deps.tk
    Image = deps.Image
    ImageTk = deps.ImageTk
    _review_crop_context = deps._review_crop_context
    _review_line_box = deps._review_line_box
    parse_review_crop_multiplier = deps.parse_review_crop_multiplier
    extended_review_crop_box = deps.extended_review_crop_box
    themed_display_image = deps.themed_display_image
    if not (0 <= index < len(self._review_display_crops)):
        self.active_crop_photo = None
        self.active_crop_label.configure(image="")
        return
    crop = self._review_display_crops[index]
    row_entries = self._bound_row_entries()
    if index >= len(row_entries) or self.parent.image is None:
        return
    try:
        entry = row_entries[index]
        # Match the source box calculation used by the inline-crop worker:
        # effective page Profile settings and page-specific geometry.
        crop_settings, geometry = _review_crop_context(
            self.parent.image, self.parent.settings,
            self.parent.canvas.winfo_width(), self.parent.current_index,
        )
        ordinary_box = _review_line_box(
            entry, geometry, self.parent.image, crop_settings,
            editor_text=self.vars[index].get(),
        )
        multiplier = parse_review_crop_multiplier(
            getattr(self.parent.settings, "review_extended_crop_height_multiplier", 2.5)
        )
        extended_box = extended_review_crop_box(
            ordinary_box, self.parent.image.height, multiplier,
        )
        extended = self.parent.image.crop(extended_box).convert("RGB")
        # At the bottom of the page, pad below rather than stretching
        # the clipped text to the expected larger preview height.
        source_height = max(1, ordinary_box[3] - ordinary_box[1])
        expected_height = max(1, round(source_height * multiplier))
        if extended.height < expected_height:
            padded = Image.new("RGB", (extended.width, expected_height), "white")
            padded.paste(extended, (0, 0))
            extended = padded
        current_zoom = max(0.01, float(self.review_zoom))
        if self._active_crop_fixed_size is None:
            self._active_crop_fixed_size = (
                crop.width, max(1, round(multiplier * crop.height)),
            )
            self._active_crop_fixed_zoom = current_zoom
        else:
            from ..proofreading.crop_extension import resize_fixed_review_preview
            self._active_crop_fixed_size = resize_fixed_review_preview(
                self._active_crop_fixed_size,
                getattr(self, "_active_crop_fixed_zoom", None),
                current_zoom,
            )
            self._active_crop_fixed_zoom = current_zoom
        preview = extended.resize(self._active_crop_fixed_size, Image.Resampling.LANCZOS)
        self.active_crop_photo = ImageTk.PhotoImage(
            themed_display_image(preview, self.parent.appearance_mode)
        )
        self.active_crop_label.configure(image=self.active_crop_photo)
        self.active_crop_host.configure(height=self._active_crop_fixed_size[1] + 14)
    except (ValueError, tk.TclError, AttributeError):
        return


def _schedule_review_crop_height_update(self, deps: ReviewCropDeps, index: int) -> None:
    """Debounce editor text-length transitions without rebuilding/focusing rows."""
    tk = deps.tk
    _focused_review_is_single_character = deps._focused_review_is_single_character
    flags = getattr(self, "_review_crop_single_flags", [])
    if not (0 <= index < len(flags) and index < len(self.vars)):
        return
    jobs = getattr(self, "_review_crop_height_jobs", {})
    prior = jobs.pop(index, None)
    if prior is not None:
        try:
            self.after_cancel(prior)
        except tk.TclError:
            pass
    if _focused_review_is_single_character(self.vars[index].get()) == flags[index]:
        return
    jobs[index] = self.after(120, lambda i=index: self._refresh_review_row_crop(i))
    self._review_crop_height_jobs = jobs


def _refresh_review_row_crop(self, deps: ReviewCropDeps, index: int) -> None:
    """Re-crop only the changed editor row, with all PIL work off Tk."""
    tk = deps.tk
    Image = deps.Image
    replace = deps.replace
    _review_crop_context = deps._review_crop_context
    _review_line_box = deps._review_line_box
    _focused_review_is_single_character = deps._focused_review_is_single_character
    getattr(self, "_review_crop_height_jobs", {}).pop(index, None)
    rows = self._bound_row_entries()
    if not (0 <= index < len(rows) and index < len(self.vars)
            and index < len(self._review_display_crops)):
        return
    image, page = self.parent.image, self.parent.current_page
    if image is None or page is None:
        return
    entry = rows[index]
    text = self.vars[index].get()
    single = _focused_review_is_single_character(text)
    settings = replace(self.parent.settings)
    viewer_width = max(1, int(self.parent.canvas.winfo_width()))
    page_index = int(self.parent.current_index)
    zoom = max(0.01, float(self.review_zoom))
    generation = getattr(self, "_review_crop_render_generation", 0)
    snapshot = replace(entry)

    def worker():
        crop_settings, geometry = _review_crop_context(
            image, settings, viewer_width, page_index,
        )
        box = _review_line_box(
            snapshot, geometry, image, crop_settings, editor_text=text,
        )
        crop = image.crop(box).convert("RGB")
        return crop.resize(
            (max(1, round(crop.width * zoom)),
             max(1, round(crop.height * zoom))),
            Image.Resampling.LANCZOS,
        )

    def done(crop):
        try:
            if (not self.winfo_exists() or self.parent.current_page != page
                    or getattr(self, "_review_crop_render_generation", 0) != generation
                    or self.parent.current_index != page_index
                    or self.parent.settings != settings
                    or self.review_zoom != zoom
                    or index >= len(self._review_row_pictures)
                    or index >= len(self._bound_row_entries())
                    or self._bound_row_entries()[index] is not entry
                    or _focused_review_is_single_character(
                        self.vars[index].get()) != single):
                return
            self._review_display_crops[index] = crop
            photo = self._ordinary_review_photo(index)
            self._review_row_pictures[index].configure(image=photo)
            self.thumbnails[index] = photo
            self.editor_crop_widths[index] = crop.width
            self._review_crop_single_flags[index] = single
            if index == self.active_index:
                self._active_crop_fixed_size = None
                self._update_active_crop_preview(index)
        except (AttributeError, IndexError, tk.TclError):
            return

    self.parent._start_ui_worker(
        f"{self._review_render_worker_key}-height-{index}",
        worker, done,
    )


def _ordinary_review_photo(self, deps: ReviewCropDeps, index: int) -> ImageTk.PhotoImage:
    """Build the ordinary single-line crop for each review editor row."""
    ImageTk = deps.ImageTk
    themed_display_image = deps.themed_display_image
    crop = self._review_display_crops[index]
    return ImageTk.PhotoImage(
        themed_display_image(crop, self.parent.appearance_mode)
    )

