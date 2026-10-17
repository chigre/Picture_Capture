"""Deferred PDIC save transaction: preserve snapshots on I/O failures.

Pure call-time dependencies; no application shell import or global hook.
"""
from __future__ import annotations

import tkinter as tk


def flush_deferred_page_save(app, *, write_pdic, pdic_path) -> None:
    """Commit queued checkbox edits before any page/batch ownership change."""
    if app._deferred_save_job is not None:
        try:
            app.after_cancel(app._deferred_save_job)
        except tk.TclError:
            pass
    app._deferred_save_job = None
    if app.__dict__.get("_deferred_save_uncertain", False):
        raise RuntimeError("R3 PDIC write outcome uncertain; refusing stale deferred save")
    snapshot = getattr(app, "_deferred_save_snapshot", None)
    if snapshot is not None:
        from .proofreading_transactions import _recovery_path
        if _recovery_path(snapshot[0]).exists():
            raise RuntimeError("Unresolved R3 transaction; refusing deferred save")
        page, entries, image_width, pages, page_index = snapshot
        write_pdic(pdic_path(page), entries, image_width, pages)
    # Keep pending snapshot on write failure; clear after publication.
    app._deferred_save_snapshot = None
    app._deferred_save_page = None
    if snapshot is not None:
        if app.project and 0 <= page_index < len(app.project.images) and app.project.images[page_index] == page:
            app._refresh_word_fill_check_from_line_count(page_index, len(entries), persist=True)
            app._update_page_row(page_index)
    app._flush_pending_manual_override()
    app._flush_proofreading_candidate_evidence()
    app._flush_proofreading_add_evidence()

