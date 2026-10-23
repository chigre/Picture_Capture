"""ReviewWindow font, padding, crop-height and zoom settings.

ReviewWindow delegates without importing the heavyweight GUI shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from pathlib import Path


@dataclass(frozen=True)
class ReviewAppearanceDeps:
    """Live legacy collaborators captured separately for each callback."""
    tk: object
    font: object
    normalize_content_font_setting: object
    resolve_content_font_family: object
    _entry_font_spec: object
    _review_height_percent_to_pixels: object
    _format_review_height_percent: object
    _effective_review_regular_crop_height: object
    _effective_review_single_cjk_line_height: object
    parse_review_crop_multiplier: object
    _format_layout_percent: object


def _schedule_review_font_apply(self, deps: ReviewAppearanceDeps) -> None:
    tk = deps.tk
    font = deps.font
    """Apply review-font edits quickly while coalescing rapid Spinbox typing."""
    if self._review_font_apply_job is not None:
        try:
            self.after_cancel(self._review_font_apply_job)
        except tk.TclError:
            pass
    self._review_font_apply_job = self.after(120, self._apply_review_font_settings)


def _apply_review_font_settings(self, deps: ReviewAppearanceDeps) -> None:
    tk = deps.tk
    font = deps.font
    normalize_content_font_setting = deps.normalize_content_font_setting
    resolve_content_font_family = deps.resolve_content_font_family
    _entry_font_spec = deps._entry_font_spec
    self._review_font_apply_job = None
    family = normalize_content_font_setting(self.review_font_family_var.get())
    try:
        size = int(float(self.review_font_size_var.get().strip()))
    except (TypeError, ValueError):
        return
    size = max(6, min(96, size))
    # Normalize the visible value after clamping, but avoid recursive work
    # unless the text actually differs.
    if self.review_font_size_var.get() != str(size):
        self.review_font_size_var.set(str(size))
        return
    bold = bool(self.review_font_bold_var.get())
    italic = bool(self.review_font_italic_var.get())
    settings = self.parent.settings
    settings.review_entry_font_family = family
    settings.review_entry_font_size = size
    settings.review_font_semantics_version = 2
    settings.review_entry_font_bold = bold
    settings.review_entry_font_italic = italic

    resolved_family = resolve_content_font_family(
        self, family, self.parent.settings.ocr_language,
    )
    spec = _entry_font_spec(resolved_family, size, bold, italic)
    measure_font = font.Font(
        family=resolved_family, size=size,
        weight="bold" if bold else "normal",
        slant="italic" if italic else "roman",
    )
    char_px = max(1, measure_font.measure("0"))
    for index, editor in enumerate(self.editors):
        width_px = self.editor_crop_widths[index] if index < len(self.editor_crop_widths) else 0
        width_chars = max(8, min(140, round(width_px / char_px))) if width_px else int(editor.cget("width"))
        try:
            editor.configure(font=spec, width=width_chars)
        except tk.TclError:
            pass
    self.parent.save_settings()


def _schedule_review_simplified_font_apply(self, deps: ReviewAppearanceDeps) -> None:
    tk = deps.tk
    """Coalesce edits to the Simplified companion typography."""
    if self._review_simplified_font_apply_job is not None:
        try:
            self.after_cancel(self._review_simplified_font_apply_job)
        except tk.TclError:
            pass
    self._review_simplified_font_apply_job = self.after(120, self._apply_review_simplified_font_settings)


def _apply_review_simplified_font_settings(self, deps: ReviewAppearanceDeps) -> None:
    tk = deps.tk
    font = deps.font
    normalize_content_font_setting = deps.normalize_content_font_setting
    resolve_content_font_family = deps.resolve_content_font_family
    _entry_font_spec = deps._entry_font_spec
    self._review_simplified_font_apply_job = None
    family = normalize_content_font_setting(self.review_simplified_font_family_var.get())
    try:
        size = int(float(self.review_simplified_font_size_var.get().strip()))
    except (TypeError, ValueError):
        return
    size = max(6, min(96, size))
    if self.review_simplified_font_size_var.get() != str(size):
        self.review_simplified_font_size_var.set(str(size))
        return
    bold = bool(self.review_simplified_font_bold_var.get())
    italic = bool(self.review_simplified_font_italic_var.get())
    settings = self.parent.settings
    settings.review_simplified_font_family = family
    settings.review_simplified_font_size = size
    settings.review_simplified_font_bold = bold
    settings.review_simplified_font_italic = italic

    resolved_family = resolve_content_font_family(
        self, family, self.parent.settings.ocr_language,
    )
    spec = _entry_font_spec(resolved_family, size, bold, italic)
    measure_font = font.Font(
        family=resolved_family, size=size,
        weight="bold" if bold else "normal",
        slant="italic" if italic else "roman",
    )
    char_px = max(1, measure_font.measure("0"))
    for index, editor in enumerate(self.simplified_editors):
        width_px = self.editor_crop_widths[index] if index < len(self.editor_crop_widths) else 0
        width_chars = max(8, min(140, round(width_px / char_px))) if width_px else int(editor.cget("width"))
        try:
            editor.configure(font=spec, width=width_chars)
        except tk.TclError:
            pass
    self.parent.save_settings()


def _schedule_review_padding_apply(self, deps: ReviewAppearanceDeps) -> None:
    tk = deps.tk
    if self._review_padding_apply_job is not None:
        try:
            self.after_cancel(self._review_padding_apply_job)
        except tk.TclError:
            pass
    self._review_padding_apply_job = self.after(120, self._apply_review_padding_setting)


def _apply_review_padding_setting(self, deps: ReviewAppearanceDeps) -> None:
    tk = deps.tk
    self._review_padding_apply_job = None
    try:
        padding = int(float(self.review_left_padding_var.get().strip()))
    except (TypeError, ValueError):
        return
    padding = max(0, min(80, padding))
    if self.review_left_padding_var.get() != str(padding):
        self.review_left_padding_var.set(str(padding))
        return
    self.parent.settings.review_entry_left_padding = padding
    for editor in self.editors:
        try:
            editor.pack_configure(padx=(padding, 0))
        except tk.TclError:
            pass
    self.parent.save_settings()


def _schedule_review_vertical_padding_apply(self, deps: ReviewAppearanceDeps) -> None:
    tk = deps.tk
    if self._review_vertical_padding_apply_job is not None:
        try:
            self.after_cancel(self._review_vertical_padding_apply_job)
        except tk.TclError:
            pass
    self._review_vertical_padding_apply_job = self.after(120, self._apply_review_vertical_padding_setting)


def _apply_review_vertical_padding_setting(self, deps: ReviewAppearanceDeps) -> None:
    tk = deps.tk
    self._review_vertical_padding_apply_job = None
    try:
        padding = int(float(self.review_vertical_padding_var.get().strip()))
    except (TypeError, ValueError):
        return
    padding = max(0, min(30, padding))
    if self.review_vertical_padding_var.get() != str(padding):
        self.review_vertical_padding_var.set(str(padding))
        return
    self.parent.settings.review_entry_vertical_padding = padding
    for editor in self.editors:
        try:
            editor.pack_configure(ipady=padding)
        except tk.TclError:
            pass
    self.parent.save_settings()


def _review_height_pixels_from_percent_var(
    self, deps: ReviewAppearanceDeps,
    variable: tk.StringVar,
    *,
    minimum: int,
    maximum: int,
) -> tuple[int, str]:
    _review_height_percent_to_pixels = deps._review_height_percent_to_pixels
    _format_review_height_percent = deps._format_review_height_percent
    raw = variable.get().strip().rstrip("%").strip()
    percent = float(raw)
    percent = max(0.0, min(100.0, percent))
    pixels = _review_height_percent_to_pixels(self.parent.image, percent)
    pixels = max(minimum, min(maximum, pixels))
    normalized = _format_review_height_percent(self.parent.image, pixels)
    return pixels, normalized


def _review_height_pixels_from_pixel_var(deps: ReviewAppearanceDeps, 
    variable: tk.StringVar,
    *,
    minimum: int,
    maximum: int,
) -> tuple[int, str]:
    pixels = int(round(float(variable.get().strip().rstrip("px").strip())))
    pixels = max(minimum, min(maximum, pixels))
    return pixels, str(pixels)


def _sync_review_height_vars(self, deps: ReviewAppearanceDeps) -> None:
    _format_review_height_percent = deps._format_review_height_percent
    _effective_review_regular_crop_height = deps._effective_review_regular_crop_height
    _effective_review_single_cjk_line_height = deps._effective_review_single_cjk_line_height
    """Refresh linked % + px controls without changing persisted pixel values."""
    self._syncing_review_height_vars = True
    try:
        values = (
            (
                self.review_line_height_var,
                self.review_line_height_px_var,
                max(1, int(self.parent.settings.character_height)),
            ),
            (
                self.review_row_padding_var,
                self.review_row_padding_px_var,
                max(0, int(self.parent.settings.row_padding)),
            ),
            (
                self.review_regular_crop_height_var,
                self.review_regular_crop_height_px_var,
                _effective_review_regular_crop_height(self.parent.settings),
            ),
            (
                self.review_single_cjk_line_height_var,
                self.review_single_cjk_line_height_px_var,
                _effective_review_single_cjk_line_height(self.parent.settings),
            ),
        )
        for percent_var, pixel_var, pixels in values:
            rendered_percent = _format_review_height_percent(self.parent.image, pixels)
            rendered_pixels = str(int(pixels))
            if percent_var.get() != rendered_percent:
                percent_var.set(rendered_percent)
            if pixel_var.get() != rendered_pixels:
                pixel_var.set(rendered_pixels)
        self._review_height_edit_source.clear()
    finally:
        self._syncing_review_height_vars = False


def _schedule_review_line_height_apply(self, deps: ReviewAppearanceDeps, source: str = "percent") -> None:
    tk = deps.tk
    if self._syncing_review_height_vars:
        return
    self._review_height_edit_source["line_height"] = source
    if self._review_line_height_apply_job is not None:
        try:
            self.after_cancel(self._review_line_height_apply_job)
        except tk.TclError:
            pass
    self._review_line_height_apply_job = self.after(160, self._apply_review_line_height_setting)


def _apply_review_line_height_setting(self, deps: ReviewAppearanceDeps) -> None:
    self._review_line_height_apply_job = None
    try:
        if self._review_height_edit_source.get("line_height") == "pixel":
            line_height, _normalized = self._review_height_pixels_from_pixel_var(
                self.review_line_height_px_var, minimum=1, maximum=500
            )
        else:
            line_height, _normalized = self._review_height_pixels_from_percent_var(
                self.review_line_height_var, minimum=1, maximum=500
            )
    except (TypeError, ValueError):
        return
    self.parent.settings.character_height = line_height
    self._sync_review_height_vars()
    self.parent.sync_quick_settings()
    self.parent.save_settings()
    self._commit_edits()
    active = self.active_index
    self._request_render_rows(focus_index=active)
    self.parent.redraw()


def _schedule_review_row_padding_apply(self, deps: ReviewAppearanceDeps, source: str = "percent") -> None:
    tk = deps.tk
    if self._syncing_review_height_vars:
        return
    self._review_height_edit_source["row_padding"] = source
    if self._review_row_padding_apply_job is not None:
        try:
            self.after_cancel(self._review_row_padding_apply_job)
        except tk.TclError:
            pass
    self._review_row_padding_apply_job = self.after(160, self._apply_review_row_padding_setting)


def _apply_review_row_padding_setting(self, deps: ReviewAppearanceDeps) -> None:
    self._review_row_padding_apply_job = None
    try:
        if self._review_height_edit_source.get("row_padding") == "pixel":
            padding, _normalized = self._review_height_pixels_from_pixel_var(
                self.review_row_padding_px_var, minimum=0, maximum=200
            )
        else:
            padding, _normalized = self._review_height_pixels_from_percent_var(
                self.review_row_padding_var, minimum=0, maximum=200
            )
    except (TypeError, ValueError):
        return
    self.parent.settings.row_padding = padding
    self._sync_review_height_vars()
    self.parent.sync_quick_settings()
    self.parent.save_settings()
    self._commit_edits()
    self._request_render_rows(focus_index=self.active_index)
    self.parent.redraw()


def _schedule_review_regular_crop_height_apply(self, deps: ReviewAppearanceDeps, source: str = "percent") -> None:
    tk = deps.tk
    if self._syncing_review_height_vars:
        return
    self._review_height_edit_source["regular_crop_height"] = source
    if self._review_regular_crop_height_apply_job is not None:
        try:
            self.after_cancel(self._review_regular_crop_height_apply_job)
        except tk.TclError:
            pass
    self._review_regular_crop_height_apply_job = self.after(
        160, self._apply_review_regular_crop_height_setting
    )


def _apply_review_regular_crop_height_setting(self, deps: ReviewAppearanceDeps) -> None:
    self._review_regular_crop_height_apply_job = None
    try:
        if self._review_height_edit_source.get("regular_crop_height") == "pixel":
            height, _normalized = self._review_height_pixels_from_pixel_var(
                self.review_regular_crop_height_px_var, minimum=1, maximum=500
            )
        else:
            height, _normalized = self._review_height_pixels_from_percent_var(
                self.review_regular_crop_height_var, minimum=1, maximum=500
            )
    except (TypeError, ValueError):
        return
    self.parent.settings.review_regular_crop_height = height
    self._sync_review_height_vars()
    self.parent.save_settings()
    self._commit_edits()
    self._request_render_rows(focus_index=self.active_index)


def _schedule_review_single_cjk_height_apply(self, deps: ReviewAppearanceDeps, source: str = "percent") -> None:
    tk = deps.tk
    if self._syncing_review_height_vars:
        return
    self._review_height_edit_source["single_cjk_height"] = source
    if self._review_single_cjk_height_apply_job is not None:
        try:
            self.after_cancel(self._review_single_cjk_height_apply_job)
        except tk.TclError:
            pass
    self._review_single_cjk_height_apply_job = self.after(160, self._apply_review_single_cjk_height_setting)


def _apply_review_single_cjk_height_setting(self, deps: ReviewAppearanceDeps) -> None:
    self._review_single_cjk_height_apply_job = None
    try:
        if self._review_height_edit_source.get("single_cjk_height") == "pixel":
            line_height, _normalized = self._review_height_pixels_from_pixel_var(
                self.review_single_cjk_line_height_px_var, minimum=1, maximum=500
            )
        else:
            line_height, _normalized = self._review_height_pixels_from_percent_var(
                self.review_single_cjk_line_height_var, minimum=1, maximum=500
            )
    except (TypeError, ValueError):
        return
    self.parent.settings.review_single_cjk_line_height = line_height
    self._sync_review_height_vars()
    self.parent.save_settings()
    self._commit_edits()
    active = self.active_index
    self._request_render_rows(focus_index=active)


def _schedule_review_extended_crop_multiplier_apply(self, deps: ReviewAppearanceDeps) -> None:
    tk = deps.tk
    """Debounce changes without regenerating all inline proofreading crops."""
    job = self._review_extended_crop_multiplier_job
    if job is not None:
        try:
            self.after_cancel(job)
        except tk.TclError:
            pass
    self._review_extended_crop_multiplier_job = self.after(
        240, self._apply_review_extended_crop_multiplier_setting
    )


def _apply_review_extended_crop_multiplier_setting(
    self, deps: ReviewAppearanceDeps, *, revert_invalid: bool = False,
) -> None:
    tk = deps.tk
    parse_review_crop_multiplier = deps.parse_review_crop_multiplier
    job = self._review_extended_crop_multiplier_job
    self._review_extended_crop_multiplier_job = None
    if job is not None:
        try:
            self.after_cancel(job)
        except tk.TclError:
            pass
    previous = float(
        getattr(self.parent.settings, "review_extended_crop_height_multiplier", 2.5)
    )
    try:
        multiplier = parse_review_crop_multiplier(
            self.review_extended_crop_multiplier_var.get()
        )
    except (TypeError, ValueError):
        # Do not interrupt intermediate values while the user is typing.
        if revert_invalid:
            self.review_extended_crop_multiplier_var.set(f"{previous:g}")
        return
    rendered = f"{multiplier:g}"
    if self.review_extended_crop_multiplier_var.get() != rendered:
        self.review_extended_crop_multiplier_var.set(rendered)
    if multiplier == previous:
        return
    self.parent.settings.review_extended_crop_height_multiplier = multiplier
    self._active_crop_fixed_size = None
    self.parent.save_settings()
    self._update_active_crop_preview(self.active_index)


def _apply_review_main_ocr_display_options(self, deps: ReviewAppearanceDeps) -> None:
    self.parent.settings.review_main_show_ocr_choices = bool(self.review_main_ocr_choices_var.get())
    self.parent.settings.review_main_show_ocr_background = bool(self.review_main_ocr_background_var.get())
    self.parent.save_settings()
    self.parent.redraw()


def change_review_zoom(self, deps: ReviewAppearanceDeps, factor: float) -> None:
    _format_layout_percent = deps._format_layout_percent
    self._commit_edits()
    self.review_zoom_auto = False
    self.review_zoom = max(0.20, min(2.5, self.review_zoom * factor))
    self.parent.settings.review_zoom_percent = self._stored_review_zoom_percent()
    self.parent.save_settings()
    self.review_zoom_var.set(f"{_format_layout_percent(self.review_zoom * 100.0)}%")
    active = self.active_index
    self._request_render_rows(focus_index=active)


def apply_review_zoom_text(self, deps: ReviewAppearanceDeps, _event=None) -> None:
    _format_layout_percent = deps._format_layout_percent
    raw = self.review_zoom_var.get().strip()
    if not raw or raw.casefold().startswith(("自动", "auto")):
        if self.review_zoom_auto:
            return
        self.reset_review_zoom()
        return
    try:
        percent = float(raw.rstrip("%"))
    except ValueError:
        self.review_zoom_var.set(
            f"自动 {_format_layout_percent(self.review_zoom * 100.0)}%"
            if self.review_zoom_auto else f"{_format_layout_percent(self.review_zoom * 100.0)}%"
        )
        return
    self._commit_edits()
    self.review_zoom_auto = False
    self.review_zoom = min(2.5, max(0.20, percent / 100.0))
    self.parent.settings.review_zoom_percent = self._stored_review_zoom_percent()
    self.parent.save_settings()
    self.review_zoom_var.set(f"{_format_layout_percent(self.review_zoom * 100.0)}%")
    active = self.active_index
    self._request_render_rows(focus_index=active)


def reset_review_zoom(self, deps: ReviewAppearanceDeps) -> None:
    self._commit_edits()
    self.review_zoom_auto = True
    self.parent.settings.review_zoom_percent = 0.0
    self.parent.save_settings()
    self.review_zoom_var.set("自动")
    self._review_auto_zoom_width = self._review_image_area_width()
    active = self.active_index
    self._request_render_rows(focus_index=active)

