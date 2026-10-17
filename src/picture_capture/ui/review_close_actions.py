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
    except Exception as exc:
        review.parent.status_var.set(f"校对保存失败，窗口保持打开：{exc}")
        showerror("校对未保存", f"保存失败，校对窗口不会关闭。\\n{exc}", parent=review)
        return
    review._finish_close_review()
