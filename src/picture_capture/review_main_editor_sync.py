"""Keep main-canvas PDIC editors coherent with edits made in proofreading.

Main canvas widgets and ReviewWindow rows edit the same Entry objects, but
Tk widgets keep their own text buffers. An old canvas widget can otherwise
write its stale text back on FocusOut or at the next autosave, including after
section-aware proofreading has saved correctly.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any


def reconcile_main_editors_after_review(app: Any, rendered_entries: list[Any]) -> None:
    """Update only widgets whose Entry object was saved by ReviewWindow."""
    saved_ids = {id(entry) for entry in rendered_entries}
    for editor, entry in tuple(getattr(app, "entry_editor_bindings", ())):
        if id(entry) not in saved_ids:
            continue
        expected = str(entry.word)
        try:
            existing = str(editor.get())
            if existing == expected:
                continue
            editor.delete(0, "end")
            editor.insert(0, expected)
        except (tk.TclError, RuntimeError):
            # Already destroyed during navigation, or a transient Tk update.
            continue


def commit_proofread_entries(review: Any) -> None:
    """Persist editor words by rendered Entry identity, then reconcile canvas."""
    live_ids = {id(entry) for entry in review.parent.entries}
    for entry, var in zip(review._bound_row_entries(), review.vars):
        if id(entry) not in live_ids:
            continue
        entry.word = var.get().strip()
    review._capture_simplified_edits(getattr(review, "_rendered_page_stem", ""))
    reconcile_main_editors_after_review(review.parent, review._bound_row_entries())
