"""Route existing one-click word actions by the active project's page kind.

Traditional callbacks are passed through unchanged. Illustrated pages use the
dedicated disk-first text-group window; never invoke a legacy PDIC draw/save.
This is call-time routing, so page navigation needs no Tk button reconstruction.
"""
from __future__ import annotations

from typing import Any, Callable

from ..illustrated_profile import effective_page_kind


def run_page_quick_action(app: Any, action: str,
                          traditional_callback: Callable[[], Any]) -> Any:
    if effective_page_kind(app.settings, getattr(app, "current_page", None)) != "illustrated":
        return traditional_callback()
    if action == "save":
        # Illustrated rectangles are committed atomically on each edit.
        app.status_var.set("图解词条修改已即时保存；未接受的 OCR 候选尚未写盘。")
        return None
    from .illustrated_dictionary_window import open_illustrated_dictionary_editor
    return open_illustrated_dictionary_editor(
        app, action="detect" if action == "ocr" else "open",
    )
