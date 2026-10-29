"""Physical Tk owner of proofreading pane controls, responsive layout and zoom events.

ReviewWindow retains its stable public method signatures and all callbacks execute
on the existing Tk event thread. Legacy monkeypatchable tkinter providers are
passed by the root app at invocation, never captured at import time.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from tkinter import ttk

def review_window_dimensions(screen_w: int, screen_h: int) -> tuple[int, int]:
    """Default proofreading window: 60% × 70%, clamped to the screen."""
    screen_w = max(1, int(screen_w))
    screen_h = max(1, int(screen_h))
    width = min(screen_w, max(560, int(round(screen_w * 0.60))))
    height = min(screen_h, max(420, int(round(screen_h * 0.70))))
    return width, height


def _review_flat_button(
    self, parent: tk.Misc, text: str, command, *, role: str = "neutral",
    width: int | None = None, anchor: str = "center",
 deps: dict[str, Any]) -> tk.Button:
    tk = deps["tk"]
    """Create one flat review-workspace button without changing global Tk styling."""
    # Classic Tk widgets are authored in the light palette even when the
    # window opens while dark mode is active; the global reversible mapper
    # darkens them after creation.
    palette = {
        "neutral": ("#eceff3", "#e1e5ea", "#30343b"),
        "primary": ("#5e9f69", "#4f8e5c", "#ffffff"),
        "danger": ("#f3eeee", "#f4d9d9", "#9b3a3a"),
    }
    background, active_background, foreground = palette.get(role, palette["neutral"])
    options = {
        "text": text,
        "command": command,
        "bg": background,
        "fg": foreground,
        "activebackground": active_background,
        "activeforeground": foreground,
        "relief": "flat",
        "bd": 0,
        "highlightthickness": 0,
        "padx": 8,
        "pady": 4,
        "cursor": "hand2",
        "anchor": anchor,
    }
    if width is not None:
        options["width"] = width
    return tk.Button(parent, **options)

def _review_collapsible_section(
    self, parent: tk.Misc, key: str, title: str, *, padding: int = 6,
    fill: str = "x", expand: bool = False, pady=(0, 6),
 deps: dict[str, Any]) -> ttk.Frame:
    tk = deps["tk"]
    ttk = deps["ttk"]
    """Create one flat right-pane section while honoring its initial state."""
    frame = ttk.Frame(parent, padding=(padding, 2), style="PCR.Surface.TFrame")
    frame.pack(fill=fill, expand=expand, pady=pady)
    state = self.review_right_section_expanded.get(key)
    expanded = True if state is None else bool(state.get())
    title_var = tk.StringVar(value=("▾ " if expanded else "▸ ") + title)
    toggle = ttk.Label(
        frame, textvariable=title_var, style="PCR.Header.TLabel", cursor="hand2",
    )
    toggle.pack(fill="x")
    toggle.bind(
        "<Button-1>", lambda _event, section_key=key: self._toggle_review_right_section(section_key)
    )
    ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(3, 5))
    body = ttk.Frame(frame, style="PCR.Surface.TFrame")
    if expanded:
        body.pack(fill="both", expand=True)
    self._review_right_sections[key] = {
        "frame": frame,
        "body": body,
        "title": title,
        "title_var": title_var,
        "expand_when_open": bool(expand),
    }
    if not expanded:
        frame.pack_configure(expand=False)
    return body

def _toggle_review_right_section(self, key: str, *, deps: dict[str, Any]) -> None:
    section = self._review_right_sections.get(key)
    state = self.review_right_section_expanded.get(key)
    if section is None or state is None:
        return
    expanded = not bool(state.get())
    state.set(expanded)
    title = str(section["title"])
    title_var = section["title_var"]
    body = section["body"]
    frame = section["frame"]
    title_var.set(("▾ " if expanded else "▸ ") + title)
    if expanded:
        body.pack(fill="both", expand=True)
        frame.pack_configure(expand=bool(section["expand_when_open"]))
    else:
        body.pack_forget()
        frame.pack_configure(expand=False)

def _toggle_focused_panel(self, *, deps: dict[str, Any]) -> None:
    expanded = not bool(self.focused_panel_expanded.get())
    self.focused_panel_expanded.set(expanded)
    self.focused_panel_title.set(("▾ " if expanded else "▸ ") + "重点筛选校对")
    if expanded:
        self.focused_panel_body.pack(fill="x", pady=(4, 0))
    else:
        self.focused_panel_body.pack_forget()

def _fit_review_left_pane_to_toolbar(self, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    """Size the left pane just wide enough to show the complete top toolbar."""
    panes = getattr(self, "review_panes", None)
    row = getattr(self, "review_control_row", None)
    if panes is None or row is None:
        return
    try:
        self.update_idletasks()
        required = int(row.winfo_reqwidth()) + 14
        available = max(1, int(panes.winfo_width()) - 1)
        panes.sashpos(0, min(required, available))
    except (tk.TclError, ValueError):
        return

def _initialize_review_layout_and_rows(self, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    """Finalize pane geometry before the first proofreading crop render."""
    try:
        if not self.winfo_exists():
            return
    except tk.TclError:
        return
    self._fit_review_left_pane_to_toolbar()
    try:
        self.update_idletasks()
    except tk.TclError:
        return
    if self._review_auto_zoom_job is not None:
        try:
            self.after_cancel(self._review_auto_zoom_job)
        except tk.TclError:
            pass
        self._review_auto_zoom_job = None
    self._review_auto_zoom_width = self._review_image_area_width()
    self._request_render_rows(focus_index=0)

def _review_image_area_width(self, canvas_width: int | None = None, *, deps: dict[str, Any]) -> int:
    tk = deps["tk"]
    """Leave room for the main-style sequence badge beside each crop."""
    try:
        if canvas_width is None:
            canvas_width = int(self.canvas.winfo_width())
        from .review_crop_sequence import review_sequence_gutter
        badge_width = review_sequence_gutter(self)
    except (AttributeError, tk.TclError, TypeError, ValueError):
        return 1
    # 6px outer padding on each side, plus the measured badge and gap.
    return max(1, int(canvas_width) - 12 - badge_width)

def _review_canvas_configured(self, event: tk.Event, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    try:
        self.canvas.itemconfigure(self.rows_window, width=event.width)
    except tk.TclError:
        return
    if not self.review_zoom_auto:
        return
    usable_width = self._review_image_area_width(event.width)
    # Ignore geometry noise that cannot change the rounded crop width.
    if abs(usable_width - int(self._review_auto_zoom_width or 0)) <= 1:
        return
    self._review_auto_zoom_width = usable_width
    if self._review_auto_zoom_job is not None:
        try:
            self.after_cancel(self._review_auto_zoom_job)
        except tk.TclError:
            pass
    self._review_auto_zoom_job = self.after(120, self._apply_auto_review_zoom_resize)

def _apply_auto_review_zoom_resize(self, *, deps: dict[str, Any]) -> None:
    self._review_auto_zoom_job = None
    if not self.review_zoom_auto:
        return
    if getattr(self, "_filter_rows_active", False):
        self._request_filter_batch_render()
    else:
        self._request_render_rows(focus_index=self.active_index)

def _stored_review_zoom_percent(self, *, deps: dict[str, Any]) -> float:
    return 0.0 if self.review_zoom_auto else round(self.review_zoom * 100.0, 2)
