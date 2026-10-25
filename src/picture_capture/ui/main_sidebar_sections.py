"""Physical owner of collapsible main-window sidebar geometry and persistence.

The public app callback methods inject live Tk globals and still run on the
Tk main thread. Grid preservation and section state are not UI shims.
"""
from __future__ import annotations
from typing import Any
import tkinter as tk
from tkinter import ttk

def _ensure_sidebar_navigation_width(self, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    """Keep the sidebar at its mode-specific size, not the old 520px."""
    paned = self.__dict__.get("main_paned")
    if paned is None or not hasattr(self, "workspace_rail_width"):
        return
    try:
        from .workspace_tools import preferred_sidebar_width
        self.update_idletasks()
        target = preferred_sidebar_width(
            self, extreme=self.workspace_mode == "极简",
            compact=self.workspace_mode == "紧凑",
        )
        available = max(1, self.winfo_width() - 160)
        paned.sashpos(0, min(target, available))
    except (tk.TclError, ValueError):
        return

def _section_frame(
    self, parent: tk.Misc, title: str, padding: int = 5, *, section_key: str | None = None
, deps: dict[str, Any]) -> ttk.LabelFrame:
    tk = deps["tk"]
    ttk = deps["ttk"]
    """Create a clickable, collapsible left-sidebar section.

    The content widgets keep their normal ``grid`` geometry.  Collapsing uses
    ``grid_remove`` so all original row/column options are preserved and can
    be restored losslessly.
    """
    key = section_key or title
    expanded = bool(self.section_expanded.get(key, True))
    title_var = tk.StringVar(value=("▾ " if expanded else "▸ ") + title)
    label = ttk.Label(
        parent,
        textvariable=title_var,
        style="PC.SectionTitle.TLabel",
        cursor="hand2",
    )
    frame = ttk.LabelFrame(
        parent,
        labelwidget=label,
        padding=(padding, max(3, padding - 1), padding, padding),
        style="PC.Section.TLabelframe",
    )
    frame._collapse_key = key  # type: ignore[attr-defined]
    frame._collapse_title = title  # type: ignore[attr-defined]
    frame._collapse_title_var = title_var  # type: ignore[attr-defined]
    frame._collapse_label = label  # type: ignore[attr-defined]
    label.bind("<Button-1>", lambda _event, section=frame: self._toggle_section(section))
    self._collapsible_sections[key] = frame
    return frame

def _set_section_expanded(self, section: ttk.LabelFrame, expanded: bool, *, persist: bool = True, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    key = str(getattr(section, "_collapse_key", ""))
    title = str(getattr(section, "_collapse_title", key))
    title_var = getattr(section, "_collapse_title_var", None)
    if isinstance(title_var, tk.StringVar):
        title_var.set(("▾ " if expanded else "▸ ") + title)

    # Every direct content child in the five sidebar groups is grid-managed.
    # Merely calling grid_remove() is not enough for a ttk.LabelFrame: Tk keeps
    # the old requested grid size cached, which leaves a large blank rectangle.
    # When collapsed we therefore disable grid propagation and pin the section
    # to the title-row height.  Expanding restores propagation before putting
    # the original grid slaves back, so their geometry options remain intact.
    label = getattr(section, "_collapse_label", None)
    if expanded:
        try:
            section.grid_propagate(True)
            section.configure(height=1)
        except tk.TclError:
            pass
        for child in section.winfo_children():
            if child.winfo_manager() == "":
                try:
                    child.grid()
                except tk.TclError:
                    pass
    else:
        for child in section.winfo_children():
            if child.winfo_manager() == "grid":
                child.grid_remove()
        try:
            section.update_idletasks()
            title_height = int(label.winfo_reqheight()) if label is not None else 20
            # A small allowance keeps the LabelFrame border/padding visible
            # without retaining any of the former content height.
            section.grid_propagate(False)
            section.configure(height=max(26, title_height + 8))
        except tk.TclError:
            pass

    self.section_expanded[key] = bool(expanded)
    if key == "pages" and hasattr(self, "sidebar"):
        self.sidebar.rowconfigure(1, weight=1 if expanded else 0)
    if persist and hasattr(self, "page_range_var"):
        self._save_session_state()

def _toggle_section(self, section: ttk.LabelFrame, *, deps: dict[str, Any]) -> None:
    key = str(getattr(section, "_collapse_key", ""))
    if self._preprocess_mode_active() and key not in {"preprocess", "pages"}:
        self.status_var.set("预处理模式中：主界面仅保留图片预处理、页面浏览和缩放。")
        return
    self._set_section_expanded(section, not bool(self.section_expanded.get(key, True)))

def _apply_initial_section_states(self, *, deps: dict[str, Any]) -> None:
    for key, section in self._collapsible_sections.items():
        self._set_section_expanded(section, bool(self.section_expanded.get(key, True)), persist=False)

def _apply_new_project_sidebar_defaults(self, *, deps: dict[str, Any]) -> None:
    """Apply the release workspace layout only to a newly created project."""
    defaults = {
        "preprocess": False,
        "normal": True,
        "aux": False,
        "ocr": False,
        "actions": False,
        "postproduction": False,
        "pages": True,
    }
    for key, expanded in defaults.items():
        self.section_expanded[key] = expanded
        section = self._collapsible_sections.get(key)
        if section is not None:
            self._set_section_expanded(section, expanded, persist=False)


def _pointer_over_sidebar(self, *, deps: dict[str, Any]) -> bool:
    tk = deps["tk"]
    canvas = self.__dict__.get("sidebar_canvas")
    if canvas is None:
        return False
    try:
        x = canvas.winfo_pointerx() - canvas.winfo_rootx()
        y = canvas.winfo_pointery() - canvas.winfo_rooty()
        return 0 <= x < canvas.winfo_width() and 0 <= y < canvas.winfo_height()
    except tk.TclError:
        return False


def _sidebar_mousewheel(self, event: tk.Event, *, deps: dict[str, Any]) -> str | None:
    if not self._pointer_over_sidebar():
        return None
    delta = int(getattr(event, "delta", 0) or 0)
    if delta:
        self.sidebar_canvas.yview_scroll((-1 if delta > 0 else 1) * 3, "units")
        return "break"
    return None


def _sidebar_linux_mousewheel(self, _event: tk.Event, direction: int, *, deps: dict[str, Any]) -> str | None:
    if not self._pointer_over_sidebar():
        return None
    self.sidebar_canvas.yview_scroll(direction * 3, "units")
    return "break"
