"""Bidirectional UI-only conversion between per-column crop width and page ruler %.

The persisted/exported source of truth remains AppSettings.crop_width_percent.
The page-relative field is an ephemeral view of that setting for the currently
shown page; never persist a second percentage with ambiguous page context.
"""
from __future__ import annotations

import math
import tkinter as tk
from typing import Any

from ..layout_rows_cache import _profile_geometry, load_layout_rows_cache


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _format(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _reference_column_pixels(app: Any) -> tuple[int, int] | None:
    """First column, as in the unlined export's Layout left-prefix rule.

    Prefer the identical persisted physical-row geometry when it is available;
    otherwise use the Profile fast-path geometry (no OCR or image processing).
    """
    image = getattr(app, "image", None)
    if image is None:
        return None
    page_width = int(getattr(image, "width", 0) or 0)
    if page_width <= 0:
        return None
    settings = getattr(app, "settings", None)
    if settings is None:
        return None
    effective_getter = getattr(app, "_current_effective_profile_settings", None)
    effective = effective_getter() if callable(effective_getter) else settings

    vars_ = getattr(app, "quick_vars", {})
    raw_width = _number(vars_["column_width"].get()) if "column_width" in vars_ else None
    raw_left = _number(vars_["manual_x"].get()) if "manual_x" in vars_ else None
    settings_width = int(round(float(getattr(settings, "column_width", 1))))
    settings_left = int(round(float(getattr(settings, "manual_x", 0))))
    draft_width = (
        int(round(page_width * raw_width / 100.0))
        if raw_width is not None and 0 < raw_width <= 100
        else settings_width
    )
    draft_left = (
        int(round(page_width * raw_left / 100.0))
        if raw_left is not None and 0 <= raw_left <= 100
        else settings_left
    )
    geometry_draft = draft_width != settings_width or draft_left != settings_left

    layout = None
    project = getattr(app, "project", None)
    page = getattr(app, "current_page", None)
    if not geometry_draft and project is not None and page is not None:
        layout = load_layout_rows_cache(
            project.root, page, int(getattr(app, "current_index", 0)),
            settings, source_size=tuple(image.size),
        )
    if layout is not None:
        columns = list(getattr(layout, "columns", []) or [])
        if columns:
            first = columns[0]
            width = int(first.right) - int(first.left)
            if width > 0:
                return page_width, width

    # This matches recover_physical_rows_fast -> _profile_geometry's first
    # column. Per-page Profile adjustments are preserved unless the user has
    # unsaved new quick values.
    starts, rights = _profile_geometry(page_width, effective)
    width = max(1, rights[0] - starts[0])
    if geometry_draft:
        left = max(0, min(max(0, page_width - 2), draft_left))
        width = max(1, min(page_width, left + max(1, draft_width)) - left)
    return page_width, width


def column_to_page_percent(column_percent: float, page_width: int, column_width: int) -> float:
    return float(column_percent) * float(column_width) / max(1, int(page_width))


def page_to_column_percent(page_percent: float, page_width: int, column_width: int) -> float:
    return float(page_percent) * max(1, int(page_width)) / max(1, int(column_width))


class CropWidthEquivalence:
    """Transient two-way Tk binder with no duplicated persisted setting."""

    def __init__(self, app: Any):
        self.app = app
        self.page_percent_var = tk.StringVar(
            master=app.quick_vars["crop_width_percent"]._root, value="—",
        )
        self._updating = False
        # The main column field already has a debounced autosave trace.
        # These additional traces only synchronize the computed second field.
        app.quick_vars["crop_width_percent"].trace_add("write", self.refresh)
        for name in ("column_width", "manual_x", "columns", "gutter"):
            if name in app.quick_vars:
                app.quick_vars[name].trace_add("write", self.refresh)
        self.page_percent_var.trace_add("write", self.from_page)
        self.refresh()

    def reference(self) -> tuple[int, int] | None:
        return _reference_column_pixels(self.app)

    def refresh(self, *_args: object) -> None:
        if self._updating:
            return
        size = self.reference()
        value = _number(self.app.quick_vars["crop_width_percent"].get())
        if size is None:
            display = "—"
        elif value is None or not 1.0 <= value <= 100.0:
            return  # Incomplete source edit: do not replace the last good value.
        else:
            display = _format(column_to_page_percent(value, *size))
        self._updating = True
        try:
            if self.page_percent_var.get() != display:
                self.page_percent_var.set(display)
        finally:
            self._updating = False

    def from_page(self, *_args: object) -> None:
        if self._updating:
            return
        size = self.reference()
        value = _number(self.page_percent_var.get())
        if size is None or value is None:
            return
        column_percent = page_to_column_percent(value, *size)
        if not 1.0 <= column_percent <= 100.0:
            return
        self._updating = True
        try:
            self.app.quick_vars["crop_width_percent"].set(_format(column_percent))
        finally:
            self._updating = False

    def commit_page(self, _event: object = None) -> None:
        """Commit valid drafts; restore canonical value for impossible entries."""
        size = self.reference()
        value = _number(self.page_percent_var.get())
        if size is not None and value is not None:
            column_percent = page_to_column_percent(value, *size)
            if 1.0 <= column_percent <= 100.0:
                self.from_page()
        self.refresh()


__all__ = [
    "CropWidthEquivalence", "column_to_page_percent",
    "page_to_column_percent", "_reference_column_pixels",
]
