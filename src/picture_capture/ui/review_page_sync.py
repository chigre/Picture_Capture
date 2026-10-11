"""Bind a modeless proofreading window to the committed main page.

The shared parent load_page() is the sole page-commit entry point, regardless
of whether navigation originated in the page list, quick buttons or review.
The old review entries must be saved *before* the parent changes current_page.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any


def _live_review(app: Any) -> Any | None:
    review = getattr(app, "review_window", None)
    if review is None:
        return None
    try:
        if review.winfo_exists():
            return review
    except (AttributeError, tk.TclError):
        pass
    app.review_window = None
    return None


def save_review_before_page_change(app: Any, index: int, *, already_saved: bool = False) -> bool:
    """Persist old-page edits, avoiding stale row-to-new-page misalignment.

    Return True if the review owned the page commit; callers must not resync
    the main canvas' potentially stale inline text over those edits.
    """
    review = _live_review(app)
    page = getattr(app, "current_page", None)
    if (
        review is None or already_saved or page is None
        or getattr(review, "_filter_rows_active", False)
        or getattr(review, "_rendered_page_stem", None) != page.stem
    ):
        return False
    review.save(redraw_main=False)
    return True


def refresh_review_after_page_change(app: Any, preloaded: dict | None = None) -> None:
    """Show only the newly committed page, resetting focus, scroll and caches."""
    review = _live_review(app)
    if review is None or getattr(app, "current_page", None) is None:
        return
    if getattr(review, "_filter_rows_active", False):
        review._flush_focused_changes_now()
    review.active_index = 0
    review._active_crop_fixed_size = None
    review._active_crop_page_stem = None
    review._review_display_crops = []
    review._clear_review_workspace("正在加载当前页词条切片…")
    review._sync_review_height_vars()
    if getattr(review, "_filter_rows_active", False):
        # The selected page takes priority over cross-page focused filtering.
        review.review_mode_var.set("single")
        review._change_review_mode()
    else:
        review._set_filter_navigation(False)
        # The proofreading pager's already-prefetched PIL crops remain valid
        # only when the effective crop/profile signature still matches.
        crops = None
        if (
            not review.review_zoom_auto and preloaded is not None
            and preloaded.get("review_key") == review._review_prefetch_key()
        ):
            crops = preloaded.get("review_crops")
        if crops is not None and len(crops) >= len(app.entries):
            review.render_rows(preloaded_crops=list(crops))
        else:
            review._request_render_rows(focus_index=0, reset_scroll=True)
    review._reset_rows_scroll_top()
    review._update_title()
