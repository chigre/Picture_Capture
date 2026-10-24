"""Dynamic global-appearance reconfiguration for the main Tk application."""
from __future__ import annotations


def apply_resolved_appearance(self, mode: object, *, deps) -> None:
    normalize_appearance_mode = deps["normalize_appearance_mode"]
    appearance_palette = deps["appearance_palette"]
    tk = deps["tk"]
    normalized = normalize_appearance_mode(mode)
    self.appearance_mode = normalized
    self._configure_global_appearance()
    self._configure_main_workspace_styles()
    previews = self.__dict__.get("_page_thumbnails")
    if previews is not None:
        previews.apply()  # Theme reconfiguration resets the Treeview rowheight.
    self._apply_current_appearance(self)
    from .workspace_tools import (
        refresh_compact_header_buttons, refresh_macaron_action_buttons,
    )
    from .simple_page_controls import refresh_compact_range_appearance
    refresh_macaron_action_buttons(self)
    refresh_compact_header_buttons(self)
    refresh_compact_range_appearance(self)
    palette = appearance_palette(normalized)
    for name, color_key in (("sidebar_canvas", "bg"), ("canvas", "canvas")):
        widget = self.__dict__.get(name)
        if widget is not None:
            try:
                widget.configure(bg=(self._main_ui_colors["canvas"] if name == "canvas" else palette[color_key]))
            except tk.TclError:
                pass

    review = self.__dict__.get("review_window")
    if review is not None:
        try:
            if review.winfo_exists():
                review._configure_word_list_appearance()
                review._configure_review_styles()
                if getattr(review, "_filter_rows_active", False):
                    review._request_filter_batch_render()
                else:
                    review._request_render_rows(focus_index=review.active_index)
        except tk.TclError:
            pass

    settings_dialog = self.__dict__.get("_settings_dialog")
    if settings_dialog is not None:
        try:
            if settings_dialog.winfo_exists():
                settings_dialog.refresh_appearance()
        except tk.TclError:
            pass
    guide = self.__dict__.get("_usage_guide_window")
    if guide is not None:
        try:
            if guide.winfo_exists():
                guide.refresh_appearance()
        except tk.TclError:
            pass
    comparison = self.__dict__.get("old_new_compare_window")
    if comparison is not None:
        try:
            if comparison.winfo_exists():
                comparison.refresh_appearance()
        except tk.TclError:
            pass
    recent_dialog = self.__dict__.get("_recent_projects_dialog")
    recent_rebuild = self.__dict__.get("_recent_projects_rebuild")
    if recent_dialog is not None and callable(recent_rebuild):
        try:
            if recent_dialog.winfo_exists():
                recent_rebuild()
        except tk.TclError:
            pass

    self.photo = None
    self._display_photo_cache_key = None
    self._preprocess_photo = None
    self._preprocess_photo_cache_key = None
    self._schedule_page_cell_overlay_refresh()
    if self.image is not None:
        self.redraw()
