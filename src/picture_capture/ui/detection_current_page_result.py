from __future__ import annotations

"""Current-page detection result handling on the Tk owner side.

The detection worker never publishes GUI state. This module enforces the
original project/page identity gate before touching editable entries, preserves
column-local replacement and calls the same review/redraw/status hooks.
Dependencies remain resolved on every callback so patched legacy helpers
retain their historical behavior.
"""

from typing import Any, Mapping


def apply_current_page_detection_result(
    app: Any,
    *,
    project: Any,
    page: Any,
    settings: Any,
    existing_entries: list[Any],
    clicked_x: int | None,
    stopped: bool,
    results: list[Any],
    error: BaseException | None,
    deps: Mapping[str, Any],
) -> None:
    """Apply a completed detection batch only to the still-active page."""
    if error is not None or stopped or not results:
        return
    if app.project is not project or app.current_page != page:
        return

    detected, geometry, text_stats = results[-1]
    if clicked_x is None:
        app.entries = list(detected)
    else:
        col = deps["column_index_for_click"](clicked_x, geometry)
        merged = [
            entry for entry in existing_entries
            if deps["column_index"](entry.x, geometry, entry.y) != col
        ]
        merged.extend(
            entry for entry in detected
            if deps["column_index"](entry.x, geometry, entry.y) == col
        )
        app.entries = merged

    app._sort_entries_reading_order()
    if settings.detection_method in {"paddleocr", "combined"}:
        app._load_ocr_review_candidates()
        app._refresh_page_quality_colors()
    app.redraw()

    if settings.detection_method in {"paddleocr", "combined"}:
        cache = deps["ocr_cache_root"](project.root) / f"{page.stem}.json"
        quality = app._current_page_quality_text()
        fill_text = ""
        if settings.detection_method == "combined" and text_stats:
            fill_text = (
                f"；普通救漏自动补字 {int(text_stats.get('filled', 0))} 条"
                f"（普通框 {int(text_stats.get('regular', 0))}，"
                f"大字框 {int(text_stats.get('large', 0))}）"
            )
        app.status_var.set(
            f"智能画线完成：{len(app.entries)} 个词条；{quality}"
            f"{fill_text}；紧凑OCR缓存 {cache.name}"
        )
    else:
        app.status_var.set(
            f"智能画线完成：检测到 {len(app.entries)} 个词条；可手动增删后保存"
        )
