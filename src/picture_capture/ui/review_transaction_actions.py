"""Thin ReviewWindow wiring for conservative committed-edit session history."""
from __future__ import annotations

from typing import Any
from ..proofreading_transactions import ReviewSessionHistory, snapshot_review
from ..review_main_editor_sync import reconcile_main_editors_after_review


def _history(review: Any) -> ReviewSessionHistory:
    found = review.__dict__.get("_r3_saved_edit_history")
    if found is None:
        found = ReviewSessionHistory()
        review.__dict__["_r3_saved_edit_history"] = found
    return found


def capture_review_before(review: Any):
    return snapshot_review(review)


def record_review_after(review: Any, before: Any, *, allow_unbound: bool = False) -> None:
    _history(review).record(
        before, snapshot_review(review, allow_unbound=allow_unbound),
    )


def invalidate_review_history(review: Any) -> None:
    hist = review.__dict__.get("_r3_saved_edit_history")
    if hist is not None:
        hist.invalidate()


def history_page_changed(review: Any, page_stem: str) -> None:
    former = getattr(review, "_rendered_page_stem", "")
    if former and former != page_stem:
        invalidate_review_history(review)


def _do(review: Any, *, redo: bool) -> str:
    history = _history(review)
    success = history.redo(review) if redo else history.undo(review)
    if not success:
        review.parent.status_var.set(
            "不能重做保存：来源已变化或操作不属于安全单页文字事务。"
            if redo else "不能撤销保存：还有未提交文字、来源已变化或操作涉及其他文件。"
        )
        return "break"
    # Shared WordEntry objects are already updated after atomic PDIC replace.
    # Never let stale main-canvas editor buffers overwrite this restored PDIC.
    reconcile_main_editors_after_review(review.parent, review._bound_row_entries())
    review.parent._sort_entries_reading_order()
    review.parent.redraw()
    review._request_render_rows(focus_index=review.active_index)
    review.parent.status_var.set("已重做本次保存" if redo else "已撤销本次保存")
    return "break"


def undo_saved_review(review: Any) -> str:
    return _do(review, redo=False)


def redo_saved_review(review: Any) -> str:
    return _do(review, redo=True)
