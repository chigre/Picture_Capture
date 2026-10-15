"""Lightweight pale 1px cell grid for the scrollable page-index Treeview.

ttk.Treeview paints no native per-cell grid on Windows/macOS/themes. We do
not replace it with Canvas rows (which would break sorting, selection, OCR
overlays and thumbnails). Instead draw a bounded number of tiny frame rulers
on top of its current viewport, at the row/column boundaries reported by Tk.
Only widget pixels in the visible viewport are inspected; no scan data I/O.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any, Callable


LIGHT_GRID = "#dee5ec"
DARK_GRID = "#4c5663"


def page_grid_segments(tree: Any) -> list[tuple[int, int, int, int]]:
    """Return x, y, width, height for lines inside *actual displayed cells*.

    Row borders follow identify_row; vertical rulers use displayed column
    bbox geometry from the first visible row. Never infer X from
    identify_column(): its draggable heading grip can shift the hitbox by
    several pixels or entirely past the viewport's edge. Native bbox
    respects #0 thumbnail, optional columns, reordering, DPI and xscroll.
    """
    try:
        width = max(0, int(tree.winfo_width()))
        height = max(0, int(tree.winfo_height()))
    except (tk.TclError, TypeError, ValueError):
        return []
    if width <= 3 or height <= 3:
        return []
    try:
        def row(y: int) -> str:
            return str(tree.identify_row(y) or "")

        def column(x: int) -> str:
            return str(tree.identify_column(x) or "")

        body_top = next((y for y in range(height) if row(y)), None)
        if body_top is None:
            return []
        segments: list[tuple[int, int, int, int]] = []
        preceding = row(body_top)
        # Every transition after a data row is its bottom border. Ignore
        # the heading/body change because the theme draws its own heading.
        for y in range(body_top + 1, height):
            current = row(y)
            if current != preceding and preceding:
                segments.append((0, y - 1, width, 1))
            preceding = current

        first_visible_iid = row(body_top)
        if all(hasattr(tree, attr) for attr in ("bbox", "cget", "tk")):
            # Native Treeview: enumerate DISPLAYED columns, never hit-testing
            # boundaries. ttk heading separator resize-grips can extend past
            # the widget edge (and are offset from the real cell boundary).
            # Iterating bbox also includes a last-column border that remains
            # visible even when identify_column never transitions to "".
            displayed = tuple(
                str(item) for item in tree.tk.splitlist(tree.cget("displaycolumns"))
            )
            if not displayed or displayed == ("#all",):
                displayed = tuple(
                    str(item) for item in tree.tk.splitlist(tree.cget("columns"))
                )
            # Tk 8.6 can return Tcl_Obj index objects rather than Python str
            # for 'show'. Compare their string values, or #0 disappears.
            show = {str(item) for item in tree.tk.splitlist(tree.cget("show"))}
            columns = (("#0",) if "tree" in show else ()) + displayed
            for column_id in columns:
                cell = tree.bbox(first_visible_iid, column_id)
                if not cell or len(cell) != 4:
                    continue
                boundary = int(cell[0]) + int(cell[2]) - 1
                if 0 < boundary < width:
                    segments.append((boundary, body_top, 1, height - body_top))
        else:
            # Compatibility for non-Tk geometry doubles used by older tests.
            preceding = column(0)
            for x in range(1, width):
                current = column(x)
                if current != preceding and preceding:
                    boundary = x - 1
                    if hasattr(tree, "bbox"):
                        cell = tree.bbox(first_visible_iid, preceding)
                        if not cell or len(cell) != 4:
                            preceding = current
                            continue
                        boundary = int(cell[0]) + int(cell[2]) - 1
                    if 0 < boundary < width:
                        segments.append((boundary, body_top, 1, height - body_top))
                preceding = current
        return segments
    except (tk.TclError, ValueError, TypeError):
        return []


class PageListGrid:
    """Reuses a small pool of 1px borders; no widget-per-data-row growth."""

    def __init__(self, tree: Any):
        self.tree = tree
        self._lines: list[tk.Frame] = []
        self._active = 0

    def clear(self) -> None:
        for frame in self._lines:
            try:
                frame.place_forget()
            except tk.TclError:
                pass
        self._active = 0

    def _relay(self, event: tk.Event, sequence: str) -> None:
        try:
            x = event.widget.winfo_x() + int(event.x)
            y = event.widget.winfo_y() + int(event.y)
            if sequence == "<MouseWheel>":
                self.tree.event_generate(
                    sequence, x=x, y=y, delta=int(getattr(event, "delta", 0)),
                )
            else:
                self.tree.event_generate(sequence, x=x, y=y)
        except tk.TclError:
            pass

    def repaint(self, *, dark: bool = False) -> None:
        try:
            segments = page_grid_segments(self.tree)
            color = DARK_GRID if dark else LIGHT_GRID
            for index, (x, y, width, height) in enumerate(segments):
                if index >= len(self._lines):
                    line = tk.Frame(
                        self.tree, background=color,
                        borderwidth=0, highlightthickness=0,
                    )
                    # A click precisely on a 1px line must still navigate.
                    line.bind(
                        "<Button-1>",
                        lambda e: self._relay(e, "<Button-1>"),
                    )
                    line.bind(
                        "<Double-1>",
                        lambda e: self._relay(e, "<Double-1>"),
                    )
                    line.bind(
                        "<MouseWheel>",
                        lambda e: self._relay(e, "<MouseWheel>"),
                    )
                    self._lines.append(line)
                line = self._lines[index]
                if str(line.cget("background")) != color:
                    line.configure(background=color)
                line.place(x=x, y=y, width=width, height=height)
            for line in self._lines[len(segments):]:
                line.place_forget()
            self._active = len(segments)
        except tk.TclError:
            self.clear()

    @property
    def visible_segment_count(self) -> int:
        return self._active


__all__ = ["PageListGrid", "page_grid_segments", "LIGHT_GRID", "DARK_GRID"]
