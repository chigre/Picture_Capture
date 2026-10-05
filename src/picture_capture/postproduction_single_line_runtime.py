from __future__ import annotations

"""Shared preflight helpers for post-production single-line actions.

Phase 5D moved the main selected-scope single-line worker onto the app-owned
batch runner.  The remaining helpers are intentionally retained here because
the still-runtime-owned unlined export reuses the same selected-scope snapshot
and button/status adapters.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any
import tkinter as tk

from .ordinary_action_runtime import _apply_quick_settings_for_ordinary


def _set_job_button_state(app: Any, active: bool) -> None:
    button = getattr(app, "_pc_single_line_crop_button", None)
    if button is None:
        return
    try:
        button.configure(state="disabled" if active else "normal")
    except tk.TclError:
        pass


def _status(app: Any, text: str) -> None:
    try:
        app.status_var.set(text)
    except Exception:
        pass


def _snapshot_scope(app: Any) -> tuple[Path, tuple[Path, ...], tuple[int, ...], Any] | None:
    if not app.guard():
        return None
    # Single-line export is OCR-independent. Reuse the ordinary-action settings
    # adapter so a project with every OCR engine disabled is still allowed to
    # apply current quick geometry before cropping.
    if not _apply_quick_settings_for_ordinary(app):
        return None

    save_current = getattr(app, "save_current_page", None)
    if callable(save_current):
        save_current()

    project = getattr(app, "project", None)
    if project is None:
        return None
    indices = tuple(int(index) for index in app.selected_page_indices())
    if not indices:
        _status(app, "单行切图：当前没有可处理的选定页面。")
        return None
    images = tuple(Path(path) for path in project.images)
    valid = tuple(index for index in indices if 0 <= index < len(images))
    if not valid:
        _status(app, "单行切图：选定范围内没有有效页面。")
        return None
    return Path(project.root), images, valid, replace(app.settings)


__all__ = []
