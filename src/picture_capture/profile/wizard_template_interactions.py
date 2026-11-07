"""Profile Wizard column offset interactions and template controls.

Moves cached overlay lines without re-decoding page images. Legacy methods
remain on ProjectProfileWizard and delegate through live Tk/setting globals.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import tkinter as tk


def selected_column_index(self) -> int:
    count = max(1, int(self.columns_var.get()))
    self.selected_column_index = max(
        0, min(count - 1, int(getattr(self, "selected_column_index", 0)))
    )
    return self.selected_column_index



def column_offsets_for_count(self, count: int | None = None) -> list[int]:
    count = max(1, int(self.columns_var.get() if count is None else count))
    raw = list(getattr(self.working, "column_start_offsets", []) or [])
    offsets: list[int] = []
    for index in range(count):
        try:
            offsets.append(int(round(float(raw[index]))) if index < len(raw) else 0)
        except (TypeError, ValueError):
            offsets.append(0)
    return offsets



def refresh_column_adjust_status(self) -> None:
    if not hasattr(self, "column_adjust_status_var"):
        return
    index = self._selected_column_index()
    offsets = self._column_offsets_for_count()
    column_width = max(1, int(getattr(self.working, "column_width", 1) or 1))
    percent = float(offsets[index]) * 100.0 / column_width
    self.column_adjust_status_var.set(
        f"当前：第 {index + 1} 栏｜人工偏移 {percent:+.2f}% 单栏宽"
    )



def update_template_column_highlight(self, *, deps) -> None:
    tk = deps["tk"]
    canvas = getattr(self, "_template_preview_canvas", None)
    if canvas is None:
        return
    selected = self._selected_column_index()
    for index, item in enumerate(getattr(self, "_template_line_items", [])):
        if item < 0:
            continue
        try:
            canvas.itemconfigure(
                item,
                fill="#ee7c00" if index == selected else "#1e78d2",
                width=4 if index == selected else 2,
            )
        except tk.TclError:
            return



def nudge_template_column_preview(self, index: int, delta: int, *, deps) -> None:
    tk = deps["tk"]
    """Move only the cached overlay line; do not reload/re-render the page image."""
    if not delta:
        return
    canvas = getattr(self, "_template_preview_canvas", None)
    items = getattr(self, "_template_line_items", [])
    paths = getattr(self, "_template_line_paths", [])
    if canvas is None or index >= len(items) or index >= len(paths) or items[index] < 0:
        return
    dx = float(self._template_nudge_vector[0]) * int(delta)
    dy = float(self._template_nudge_vector[1]) * int(delta)
    try:
        canvas.move(items[index], dx, dy)
    except tk.TclError:
        return
    paths[index] = [(x + dx, y + dy) for x, y in paths[index]]



def shift_selected_column(self, delta: int) -> None:
    index = self._selected_column_index()
    offsets = self._column_offsets_for_count()
    old_value = offsets[index]
    column_width = max(1, int(getattr(self.working, "column_width", 1) or 1))
    step_px = max(1, int(round(column_width * 0.001)))
    max_offset = max(step_px, int(round(column_width * 0.25)))
    offsets[index] = max(
        -max_offset,
        min(max_offset, old_value + (step_px if int(delta) > 0 else -step_px)),
    )
    actual_delta = offsets[index] - old_value
    if not actual_delta:
        return
    self.working.column_start_offsets = offsets
    self._refresh_column_adjust_status()
    self._nudge_template_column_preview(index, actual_delta)
    self._profile_input_changed(refresh_preview=False)



def reset_selected_column(self) -> None:
    index = self._selected_column_index()
    offsets = self._column_offsets_for_count()
    old_value = offsets[index]
    if old_value == 0:
        return
    offsets[index] = 0
    self.working.column_start_offsets = offsets
    self._refresh_column_adjust_status()
    self._nudge_template_column_preview(index, -old_value)
    self._profile_input_changed(refresh_preview=False)



def reset_all_column_offsets(self) -> None:
    offsets = self._column_offsets_for_count()
    if not any(offsets):
        return
    for index, value in enumerate(offsets):
        if value:
            self._nudge_template_column_preview(index, -value)
    self.working.column_start_offsets = [0] * len(offsets)
    self._refresh_column_adjust_status()
    self._profile_input_changed(refresh_preview=False)



def preview_path_distance_sq(
    points: list[tuple[float, float]], x: float, y: float,
) -> float:
    if not points:
        return float("inf")
    if len(points) == 1:
        dx, dy = x - points[0][0], y - points[0][1]
        return dx * dx + dy * dy
    best = float("inf")
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        dx, dy = x1 - x0, y1 - y0
        denom = dx * dx + dy * dy
        if denom <= 0:
            px, py = x0, y0
        else:
            t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / denom))
            px, py = x0 + t * dx, y0 + t * dy
        ex, ey = x - px, y - py
        best = min(best, ex * ex + ey * ey)
    return best



def select_template_column(
    self, event: tk.Event, line_paths: list[list[tuple[float, float]]],
) -> None:
    if not line_paths:
        return
    distances = [
        self._preview_path_distance_sq(points, float(event.x), float(event.y))
        for points in line_paths
    ]
    index = min(range(len(distances)), key=distances.__getitem__)
    if distances[index] > 18.0 * 18.0:
        return
    self.selected_column_index = index
    self._refresh_column_adjust_status()
    self._update_template_column_highlight()




def refresh_template_controls(self, *, deps) -> None:
    tk = deps["tk"]
    HEADER_LABEL_TO_VALUE = deps["HEADER_LABEL_TO_VALUE"]
    FOOTER_LABEL_TO_VALUE = deps["FOOTER_LABEL_TO_VALUE"]
    SIDE_LABEL_TO_VALUE = deps["SIDE_LABEL_TO_VALUE"]
    """Enable only page-template controls that currently have meaning."""
    if not hasattr(self, "header_percent_spin"):
        return
    header_present = HEADER_LABEL_TO_VALUE.get(self.header_mode_var.get()) == "present"
    footer_present = FOOTER_LABEL_TO_VALUE.get(self.footer_mode_var.get()) == "present"
    side_value = SIDE_LABEL_TO_VALUE.get(self.side_mode_var.get(), "none")
    fixed_side = side_value in {"left", "right"}
    alternating = side_value in {"outer", "inner"}
    self.columns_spin.configure(state="normal")
    self.header_percent_spin.configure(state="normal" if header_present else "disabled")
    self.footer_percent_spin.configure(state="normal" if footer_present else "disabled")
    self.side_percent_spin.configure(state="normal" if fixed_side else "disabled")
    self.side_percent_a_spin.configure(state="normal" if alternating else "disabled")
    self.side_percent_b_spin.configure(state="normal" if alternating else "disabled")
    self.first_variant_combo.configure(state="readonly" if alternating else "disabled")
    if hasattr(self, "template_preview_frame") and hasattr(self, "notebook"):
        try:
            preview_visible = self.notebook.index(self.notebook.select()) == 1
        except (tk.TclError, ValueError):
            preview_visible = False
        if preview_visible:
            self.after_idle(self._refresh_template_preview)



def move_template_preview(self, delta: int) -> None:
    if not self.sample_indices:
        return
    self.template_preview_slot = (
        int(self.template_preview_slot) + int(delta)
    ) % len(self.sample_indices)
    self._refresh_template_preview()

