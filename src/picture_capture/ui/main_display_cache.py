"""Main canvas display image and per-page Profile geometry cache owner.

No OCR/PDIC writes or Tk widget creation are performed by this module.
Call-time dependencies preserve historical app monkeypatch hooks.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import Image, ImageTk
    from ..models import AppSettings

def _get_cached_display_photo(self, size: tuple[int, int], *, deps: dict[str, Any]) -> ImageTk.PhotoImage:
    """Return the resized page image for the current page/zoom.

    The page background is display-only.  OCR always receives ``self.image``
    in original-page pixels, so reusing this PhotoImage cannot alter OCR or
    separator coordinates.  A new page object or zoom size invalidates the
    cache automatically.
    """
    Image = deps["Image"]
    ImageTk = deps["ImageTk"]
    binary_preview_image = deps["binary_preview_image"]
    themed_display_image = deps["themed_display_image"]
    if self.image is None:
        raise RuntimeError("没有可显示的页面图像")
    binary = bool(self.binary_preview_var.get())
    key = (id(self.image), int(size[0]), int(size[1]), binary, self.appearance_mode)
    if self.photo is None or self._display_photo_cache_key != key:
        display = (
            binary_preview_image(self.image).resize(size, Image.Resampling.LANCZOS)
            if binary else self.image.resize(size, Image.Resampling.LANCZOS)
        )
        display = themed_display_image(display, self.appearance_mode)
        self.photo = ImageTk.PhotoImage(display)
        self._display_photo_cache_key = key
    return self.photo

def _current_effective_profile_settings(self, *, deps: dict[str, Any]) -> AppSettings:
    """Resolve the current page's Project Profile template without mutating project settings."""
    effective_page_settings = deps["effective_page_settings"]
    if self.image is None:
        return self.settings
    return effective_page_settings(
        self.settings, self.image.size,
        max(0, int(self.__dict__.get("current_index", 0) or 0)),
    )

def _display_geometry_key(self, *, deps: dict[str, Any]) -> tuple:
    if self.image is None:
        return ()
    s = self.settings
    return (
        id(self.image), int(self.__dict__.get("current_index", 0) or 0),
        int(s.columns),
        str(s.layout_columns_policy), str(s.layout_column_separator_mode),
        str(s.analysis_threshold_mode),
        float(s.manual_x), float(s.gutter), float(s.column_width),
        float(s.start_y), bool(s.crop_to_bottom_y), float(s.bottom_y),
        bool(s.follow_column_deformation), float(s.column_track_block_height),
        float(s.column_track_radius), float(s.body_indent),
        float(s.column_track_max_step), str(s.layout_transform),
        str(getattr(s, "layout_writing_mode", "horizontal-tb") or "horizontal-tb"),
        str(getattr(s, "layout_text_direction", "ltr") or "ltr"),
        str(getattr(s, "profile_header_mode", "auto")),
        str(getattr(s, "profile_footer_mode", "auto")),
        str(getattr(s, "profile_side_content_mode", "none")),
        str(getattr(s, "profile_page_pair_mode", "same")),
        str(getattr(s, "profile_first_page_variant", "A")),
        float(getattr(s, "profile_header_percent", 6.0)),
        float(getattr(s, "profile_footer_percent", 5.0)),
        float(getattr(s, "profile_side_percent", 8.0)),
        float(getattr(s, "profile_side_percent_a", getattr(s, "profile_side_percent", 8.0))),
        float(getattr(s, "profile_side_percent_b", getattr(s, "profile_side_percent", 8.0))),
    )

def _get_cached_display_geometry(self, *, deps: dict[str, Any]):
    """Reuse the same per-page Profile geometry used by detection."""
    page_template_analysis_image = deps["page_template_analysis_image"]
    derive_geometry = deps["derive_geometry"]
    if self.image is None:
        raise RuntimeError("没有可显示的页面图像")
    key = self._display_geometry_key()
    if self._display_geometry_cache is None or self._display_geometry_cache_key != key:
        effective = self._current_effective_profile_settings()
        analysis_image = page_template_analysis_image(
            self.image, effective, max(0, int(self.current_index)),
        )
        self._display_geometry_cache = derive_geometry(analysis_image, effective)
        self._display_geometry_cache_key = key
    return self._display_geometry_cache
