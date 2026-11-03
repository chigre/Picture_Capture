"""Keep main-canvas PDIC editors coherent with edits made in proofreading.

Main canvas widgets and ReviewWindow rows edit the same Entry objects, but
Tk widgets keep their own text buffers. An old canvas widget can otherwise
write its stale text back on FocusOut or at the next autosave, including after
section-aware proofreading has saved correctly.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any

from .focused_crop_source_fingerprint import _source_page_index
from .focused_visible_owner import unique_canvas_source_entries


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



def reconcile_focused_save_to_main(
    app: Any, saved_rows: list[tuple[int, int, int, str]],
) -> None:
    """Update exactly one current-page canvas Entry per confirmed PDIC XY.

    A ReviewWindow save result is not authority to modify stale, duplicated
    or implicitly coerced canvas source coordinates. UI widget synchronization
    remains at this canonical main-editor ownership boundary.
    """
    current_index = getattr(app, "current_index", None)
    if current_index is None:
        return
    try:
        page_owner = _source_page_index(current_index)
    except (TypeError, ValueError, RuntimeError, OverflowError):
        return
    current_saved = {
        (x, y): word for page_index, x, y, word in saved_rows
        if int(page_index) == page_owner
    }
    if not current_saved:
        return
    confirmed = []
    for point, entry in unique_canvas_source_entries(
        getattr(app, "entries", ())
    ).items():
        word = current_saved.get(point)
        if word is None:
            continue
        entry.word = word
        entry.confidence = None
        entry.ocr_source = "manual"
        entry.final_engine = "manual"
        entry.manually_selected = True
        confirmed.append(entry)
    if confirmed:
        reconcile_main_editors_after_review(app, confirmed)

def commit_proofread_entries(review: Any) -> None:
    """Persist editor words by rendered Entry identity, then reconcile canvas."""
    # This entry point runs before app.save_pdic; a marker must block edits
    # BEFORE any Entry.word or canvas binding is mutated.
    from .transactions import _recovery_path, _marker_present
    page = getattr(review.parent, "current_page", None)
    if page is not None and _marker_present(_recovery_path(page)):
        raise RuntimeError("Unresolved R3 transaction; refusing editor commit")
    live_ids = {id(entry) for entry in review.parent.entries}
    for entry, var in zip(review._bound_row_entries(), review.vars):
        if id(entry) not in live_ids:
            continue
        entry.word = var.get().strip()
    review._capture_simplified_edits(getattr(review, "_rendered_page_stem", ""))
    reconcile_main_editors_after_review(review.parent, review._bound_row_entries())
