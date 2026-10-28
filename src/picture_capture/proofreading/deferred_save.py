"""Deferred PDIC save transaction: preserve snapshots on I/O failures.

Pure call-time dependencies; no application shell import or global hook.
"""
from __future__ import annotations

import tkinter as tk

from .transactions import _bytes_or_absent
from ..ui.review_selection_workflow import verify_pending_manual_source


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
        from .transactions import _recovery_path
        if _recovery_path(snapshot[0]).exists():
            raise RuntimeError("Unresolved R3 transaction; refusing deferred save")
        page, entries, image_width, pages, page_index = snapshot
        # Both source pins must still describe the first checkbox click.
        # Preflight BEFORE PDIC, not after it has already overwritten a
        # different proofreader's page.
        verify_pending_manual_source(app, page.stem)
        pin = app.__dict__.get("_deferred_save_pdic_origin")
        if not isinstance(pin, tuple) or len(pin) != 2 or pin[0] != page:
            raise RuntimeError("R3 延迟 PDIC 缺少可信页面来源，不允许写入")
        pdic = pdic_path(page)
        before = _bytes_or_absent(pdic)
        if before != pin[1]:
            raise RuntimeError("R3 延迟 PDIC 来源已被其他人修改，拒绝覆盖")
        try:
            write_pdic(pdic, entries, image_width, pages)
        except Exception:
            # A writer can replace PDIC and *then* raise; the old snapshot
            # must not be replayed over those bytes on the next timer tick.
            try:
                uncertain = _bytes_or_absent(pdic) != before
            except OSError:
                uncertain = True
            if uncertain:
                app.__dict__["_deferred_save_uncertain"] = True
            raise
    # If manual publication fails after PDIC, keep every queued object but
    # quarantine retries. This is a mixed state needing human reconciliation,
    # not evidence of atomic PDIC+manual_selection publication.
    try:
        app._flush_pending_manual_override()
    except Exception:
        if snapshot is not None:
            app.__dict__["_deferred_save_uncertain"] = True
        raise
    app._deferred_save_snapshot = None
    app._deferred_save_page = None
    app.__dict__.pop("_deferred_save_pdic_origin", None)
    if snapshot is not None:
        if app.project and 0 <= page_index < len(app.project.images) and app.project.images[page_index] == page:
            app._refresh_word_fill_check_from_line_count(page_index, len(entries), persist=True)
            app._update_page_row(page_index)
    app._flush_proofreading_candidate_evidence()
    app._flush_proofreading_add_evidence()

