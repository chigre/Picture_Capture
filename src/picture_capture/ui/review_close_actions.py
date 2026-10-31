"""Safe review-close coordinator: never destroy a window after failed save."""
from __future__ import annotations

from typing import Any, Callable


def close_review(review: Any, *, showerror: Callable) -> None:
    if getattr(review, "_filter_rows_active", False):
        try:
            review._flush_focused_changes_now()
        except Exception:
            # The synchronous trigger may fail before or after scheduling
            # asynchronous work. We cannot certify a disk write here, so
            # never close, never discard pending human edits, and never
            # surface exception text (which may contain private source data).
            review._filter_close_after_save = False
            review.parent.status_var.set(
                "筛选校对保存失败或状态未确认，窗口保持打开；请核对后重试。"
            )
            showerror(
                "筛选校对未保存",
                "保存失败或状态未确认，窗口不会关闭；请核对项目文件后重试。",
                parent=review,
            )
            return
        if review._filter_save_running or review._filter_pending_changes:
            review._filter_close_after_save = True
            review.parent.status_var.set("正在保存筛选校对修改，完成后关闭校对窗口。")
            return
        review._finish_close_review()
        return
    try:
        if review.save() is False:
            return
    except Exception:
        # Save errors can embed absolute patient-source paths, headwords, or
        # private sidecar contents. A failed/uncertain save must keep the UI
        # open, but must never surface the exception string to Tk or stdout.
        review.parent.status_var.set(
            "校对保存失败或状态未确认，窗口保持打开；请核对项目文件。"
        )
        showerror(
            "校对未保存",
            "保存失败或状态未确认，校对窗口不会关闭。请核对项目文件后重试。",
            parent=review,
        )
        return
    review._finish_close_review()
