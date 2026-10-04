from __future__ import annotations

import json
import tkinter as tk
from typing import Any


class ReviewController:
    """Coordinate read-side OCR review lookup and main-canvas navigation.

    Durable candidate edits, PDIC/manual-override writes, and the detailed
    translucent proofreading highlight renderer remain owned by
    ``PictureCaptureApp``.  This controller only owns candidate lookup/matching
    plus lightweight highlight/navigation state.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def load_ocr_review_candidates(self) -> None:
        app = self.app
        app.ocr_review_candidates = []
        path = app._paddle_cache_path()
        if not path or not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            app.ocr_review_candidates = list(payload.get("review_candidates") or [])
        except Exception:
            app.ocr_review_candidates = []

    def get_review_candidate(self, candidate_id: str) -> dict | None:
        for item in self.app.ocr_review_candidates:
            if str(item.get("candidate_id", "")) == candidate_id:
                return item
        return None

    def candidate_is_selected(self, cand: dict) -> bool:
        app = self.app
        cid = str(cand.get("candidate_id", ""))
        y = int(cand.get("source_y", -99999))
        x = int(cand.get("source_x", -99999))
        for entry in app.entries:
            if cid and entry.candidate_id == cid:
                return True
            if abs(entry.x - x) <= 12 and abs(entry.y - y) <= max(
                5, round(app._quick_geometry_value("character_height") * 0.45)
            ):
                return True
        return False

    def entry_for_candidate(self, cand: dict):
        app = self.app
        cid = str(cand.get("candidate_id", ""))
        y = int(cand.get("source_y", -99999))
        x = int(cand.get("source_x", -99999))
        for entry in app.entries:
            if cid and entry.candidate_id == cid:
                return entry
            if abs(entry.x - x) <= 12 and abs(entry.y - y) <= max(
                5, round(app._quick_geometry_value("character_height") * 0.45)
            ):
                return entry
        return None

    def clear_review_entry_highlight(self) -> None:
        app = self.app
        app._review_entry_highlight_target = None
        app._review_entry_highlight_photo = None
        try:
            app.canvas.delete("proofread-entry-highlight")
        except tk.TclError:
            pass

    def highlight_review_entry(self, entry: Any) -> None:
        app = self.app
        if app.image is None or app.current_index < 0:
            return
        app._review_entry_highlight_target = (
            app.current_index,
            int(entry.x),
            int(entry.y),
        )
        app._draw_review_entry_highlight()

    def jump_to_review_candidate(self, cand: dict) -> None:
        app = self.app
        if not app.image:
            return
        y = int(cand.get("source_y", 0))
        canvas_h = max(1, app.canvas.winfo_height())
        target = max(0.0, y * app.view_scale - canvas_h * 0.30)
        total = max(1.0, app.image.height * app.view_scale)
        app.canvas.yview_moveto(min(1.0, target / total))
        app.canvas.delete("review-highlight")
        geometry = app._get_cached_display_geometry()
        col = max(0, min(len(geometry.column_starts) - 1, int(cand.get("column", 0))))
        x_source = int(cand.get("source_x", 0))
        _u, v = geometry.source_to_canonical(x_source, y)
        canonical_box = (
            geometry.x_at(col, v),
            v - 5,
            geometry.x_at(col, v) + round(geometry.column_widths[col] * 0.98),
            v + 18,
        )
        x0, y0, x1, y1 = geometry.transform.canonical_box_to_source(
            canonical_box, app.image.size
        )
        app.canvas.create_rectangle(
            x0 * app.view_scale,
            y0 * app.view_scale,
            x1 * app.view_scale,
            y1 * app.view_scale,
            outline="#00bcd4",
            width=3,
            tags=("review-highlight",),
        )
        app.canvas.tag_raise("review-highlight")
