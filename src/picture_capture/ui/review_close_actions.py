"""Safe review-close coordinator: never destroy a window after failed save."""
from __future__ import annotations

from typing import Any, Callable


def close_review(review: Any, *, showerror: Callable) -> None:
    if getattr(review, "_filter_rows_active", False):
        review._flush_focused_changes_now()
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
