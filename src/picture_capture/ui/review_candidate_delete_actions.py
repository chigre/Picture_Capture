"""Thin ReviewWindow coordinator for OCR candidate-owned deletion.

No candidate, Tk checkbox, Entry membership or simplified cache mutation
occurs before the three-file persistence transaction has committed.
"""
from __future__ import annotations

from typing import Any

from ..proofreading_candidate_delete import commit_candidate_delete
from ..proofreading_transactions import snapshot_review
from .review_transaction_actions import invalidate_review_history


def delete_owned_review_candidate(
    review: Any, index: int, row_entries: list[Any],
) -> str:
    app = review.parent
    entry = row_entries[index]
    cid = str(getattr(entry, "candidate_id", "") or "")
    candidates = [
        row for row in getattr(app, "ocr_review_candidates", ())
        if isinstance(row, dict) and str(row.get("candidate_id", "")) == cid
    ]
    page = getattr(app, "current_page", None)
    if (
        not cid or page is None or len(candidates) != 1
        or getattr(app.settings, "proofreading_event_capture", False)
        or page.stem in getattr(review, "_simplified_dirty_pages", set())
        or any(
            i >= len(row_entries)
            or var.get().strip() != row_entries[i].word
            for i, var in enumerate(getattr(review, "vars", ()))
        )
    ):
        app.status_var.set(
            "候选词条删除未执行：请先保存未提交文字或简体校对，"
            "并确认唯一 OCR 候选、关闭实验事件记录。"
        )
        return "break"

    before = snapshot_review(review)
    if before is None:
        app.status_var.set(
            "候选词条删除未执行：页面/PDIC/人工覆盖与当前校对状态不一致。"
        )
        return "break"
    try:
        result = commit_candidate_delete(before, entry, candidates[0])
    except (OSError, ValueError, RuntimeError):
        app.status_var.set(
            "候选词条删除写入失败：已尝试从临时恢复标记回滚；"
            "如磁盘异常未解除，请先修复再重新打开页面。"
        )
        return "break"
    if result is None:
        app.status_var.set(
            "候选词条删除未执行：OCR 归属、来源指纹或原始文件不满足事务条件。"
        )
        return "break"

    # Only after the disk transaction has succeeded: update shared objects,
    # the candidate checkbox, caches and canvas. Never match by list index
    # after sorting the Entries.
    candidates[0]["selected"] = False
    app.entries[:] = [row for row in app.entries if row is not entry]
    check = getattr(app, "candidate_check_vars", {}).get(cid)
    if check is not None:
        try:
            check.set(False)
        except Exception:
            # A destroyed checkbox is presentation-only; the authoritative
            # candidate model and all durable files already agree.
            pass
    cache = getattr(review, "_simplified_page_cache", None)
    if isinstance(cache, dict):
        cache.pop(page.stem, None)
    getattr(review, "_simplified_dirty_pages", set()).discard(page.stem)
    invalidate_review_history(review)  # Candidate Undo remains unsupported.
    app._sort_entries_reading_order()
    app._last_pdic_write_changed = True
    # Word-count cards are derived UI/project metadata, not primary PDIC.
    try:
        app._refresh_word_fill_check_from_line_count(
            app.current_index, len(app.entries), persist=True,
        )
        app._update_page_row(app.current_index)
    except (OSError, ValueError, AttributeError):
        pass
    app.clear_review_entry_highlight()
    app.redraw()
    review.active_index = min(index, max(0, len(app.entries) - 1))
    review._request_render_rows(focus_index=review.active_index)
    if not app.entries:
        review._show_ocr_options(None)
        review._update_title()
    app.status_var.set(
        "已安全删除 OCR 关联词条；人工覆盖、PDIC 与简体记录同步保存。"
        "本操作的撤销仍待候选所有权恢复机制验收。"
    )
    return "break"
