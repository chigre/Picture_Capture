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

from ..io.formats import pdic_path


def _bytes_or_absent(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _verified_same_disk_snapshot(app: Any, page, path, before) -> bool:
    """Only a successful byte readback may authorize an in-memory rollback.

    After an original PDIC writer error, a second readback can fail too.
    Never let that diagnostic I/O error mask the original exception or
    pretend that failed verification proves a pre-publication state.
    """
    if app.current_page != page:
        return False
    try:
        return _bytes_or_absent(path) == before
    except OSError:
        return False


def _editor_state(app: Any):
    result = []
    for editor, entry in tuple(app.__dict__.get("entry_editor_bindings", ())):
        try:
            result.append((editor, entry, str(editor.get())))
        except (tk.TclError, RuntimeError):
            pass
    return result


def _live_editors_unchanged(app: Any, saved) -> bool:
    """Only restore Tk state when no newer text or widget binding appeared."""
    bindings = tuple(app.__dict__.get("entry_editor_bindings", ()))
    if len(bindings) != len(saved):
        return False
    for (editor, entry), (old_editor, old_entry, text) in zip(bindings, saved):
        if editor is not old_editor or entry is not old_entry:
            return False
        try:
            if str(editor.get()) != text:
                return False
        except (tk.TclError, RuntimeError):
            return False
    return True


def _review_vars_state(review: Any):
    """Freeze the word-input values without altering live ReviewWindow vars."""
    result = []
    try:
        for var in tuple(getattr(review, "vars", ())):
            result.append((var, str(var.get())))
    except (tk.TclError, RuntimeError):
        return None
    return tuple(result)


def _review_vars_unchanged(review: Any, saved) -> bool:
    if saved is None:
        return False
    live = tuple(getattr(review, "vars", ()))
    if len(live) != len(saved):
        return False
    for var, (old_var, text) in zip(live, saved):
        if var is not old_var:
            return False
        try:
            if str(var.get()) != text:
                return False
        except (tk.TclError, RuntimeError):
            return False
    return True


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
        if (
            _verified_same_disk_snapshot(app, page, path, before)
            and _live_editors_unchanged(app, editors)
        ):
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
    review_vars = _review_vars_state(review)
    try:
        yield
    except Exception:
        if (
            _verified_same_disk_snapshot(app, page, path, before)
            and _live_editors_unchanged(app, editors)
            and _review_vars_unchanged(review, review_vars)
        ):
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
