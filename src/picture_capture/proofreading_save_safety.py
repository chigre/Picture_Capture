"""Fail-closed in-memory state protection around ordinary R3 PDIC saves.

The persisted PDIC is authoritative. Restore in-memory Entry and editor state
only when exact pre-save PDIC bytes remain unchanged after a write failure.
Never overwrite a changed file or claim cross-file OS atomicity.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from typing import Any

import tkinter as tk

from .formats import pdic_path


def _bytes_or_absent(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _editor_state(app: Any):
    result = []
    for editor, entry in tuple(app.__dict__.get("entry_editor_bindings", ())):
        try:
            result.append((editor, entry, str(editor.get())))
        except (tk.TclError, RuntimeError):
            pass
    return result


def _restore_editor_state(items):
    for editor, _entry, value in items:
        try:
            if str(editor.get()) != value:
                editor.delete(0, "end")
                editor.insert(0, value)
        except (tk.TclError, RuntimeError):
            pass


@contextmanager
def protect_app_pdic_commit(app: Any):
    """Rollback pre-publication mutations; quarantine ambiguous post-write errors."""
    page = app.current_page
    path = pdic_path(page)
    before = _bytes_or_absent(path)
    entries = tuple(app.entries)
    words = tuple((entry, str(entry.word)) for entry in entries)
    editors = _editor_state(app)
    try:
        yield
    except Exception:
        if app.current_page == page and _bytes_or_absent(path) == before:
            app.entries[:] = entries
            for entry, word in words:
                entry.word = word
            _restore_editor_state(editors)
        else:
            # An exception after os.replace may still have committed new bytes.
            # Do not retry a stale deferred snapshot over an uncertain write.
            app.__dict__["_deferred_save_uncertain"] = True
        raise


@contextmanager
def protect_review_pdic_commit(review: Any):
    """Preserve unsaved ReviewWindow vars if the PDIC did not change."""
    app = review.parent
    page = app.current_page
    path = pdic_path(page)
    before = _bytes_or_absent(path)
    entries = tuple(app.entries)
    words = tuple((entry, str(entry.word)) for entry in entries)
    editors = _editor_state(app)
    stem = getattr(review, "_rendered_page_stem", "")
    cache = deepcopy(getattr(review, "_simplified_page_cache", {}))
    dirty = set(getattr(review, "_simplified_dirty_pages", set()))
    flags = list(getattr(review, "simplified_manual_flags", []))
    values = list(getattr(review, "simplified_actual_values", []))
    try:
        yield
    except Exception:
        if app.current_page == page and _bytes_or_absent(path) == before:
            app.entries[:] = entries
            for entry, word in words:
                entry.word = word
            _restore_editor_state(editors)
            if hasattr(review, "_simplified_page_cache"):
                review._simplified_page_cache = cache
            if hasattr(review, "_simplified_dirty_pages"):
                review._simplified_dirty_pages = dirty
            if hasattr(review, "simplified_manual_flags"):
                review.simplified_manual_flags[:] = flags
            if hasattr(review, "simplified_actual_values"):
                review.simplified_actual_values[:] = values
        else:
            # The disk may have committed despite a later error. Keep the UI
            # open; the caller must not discard the user-edited Tk variables.
            app.__dict__["_deferred_save_uncertain"] = True
        raise
