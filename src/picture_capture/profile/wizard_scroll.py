"""Tk main-thread scrolling and descendant routing for ProjectProfileWizard.

This is UI-only code: no worker, persistence, or image decode runs here.
The original class methods remain patchable and pass live Tk dependencies.
"""
from __future__ import annotations


def active_tab_canvas(self, *, tk) -> tk.Canvas | None:
    try:
        index = self.notebook.index(self.notebook.select())
        return self.tab_canvases[index]
    except (tk.TclError, ValueError, IndexError):
        return None


def is_widget_descendant(widget, ancestor, *, tk) -> bool:
    current = widget
    while current is not None:
        if current == ancestor:
            return True
        try:
            parent_name = current.winfo_parent()
            current = current._nametowidget(parent_name) if parent_name else None
        except (tk.TclError, KeyError):
            return False
    return False


def wizard_mousewheel(self, event, *, tk, ttk) -> str | None:
    if isinstance(event.widget, (tk.Spinbox, ttk.Combobox)):
        return None
    delta = int(getattr(event, "delta", 0) or 0)
    if not delta:
        return None
    if hasattr(self, "right_canvas") and self._is_widget_descendant(
        event.widget, self.right_content
    ):
        self.right_canvas.yview_scroll((-1 if delta > 0 else 1) * 3, "units")
        return "break"
    canvas = self._active_tab_canvas()
    if canvas is None:
        return None
    canvas.yview_scroll((-1 if delta > 0 else 1) * 3, "units")
    return "break"


def wizard_linux_wheel(self, event, direction: int, *, tk, ttk) -> str | None:
    if isinstance(event.widget, (tk.Spinbox, ttk.Combobox)):
        return None
    if hasattr(self, "right_canvas") and self._is_widget_descendant(
        event.widget, self.right_content
    ):
        self.right_canvas.yview_scroll(int(direction) * 3, "units")
        return "break"
    canvas = self._active_tab_canvas()
    if canvas is None:
        return None
    canvas.yview_scroll(int(direction) * 3, "units")
    return "break"
