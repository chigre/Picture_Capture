from __future__ import annotations

"""Selected-page drawing actions, independent of controller method ownership.

The Tk controller keeps the historical public methods and injects its live
ordinary/OCR guards on each invocation. This UI owner centralizes scope
resolution, validation order, saved drawing mode and detector dispatch.

The preflight must run before any settings mutation. In particular, an OCR
engine selection that is not runnable must not become a detector request, and
an invalid selected-page range must not change the saved drawing mode.
"""

from typing import Any, Callable


def run_selected_draw_action(
    app: Any,
    *,
    method: str,
    ordinary_settings_guard: Callable[[Any], bool] | None = None,
    ocr_engine_guard: Callable[[Any], bool] | None = None,
) -> None:
    """Dispatch ordinary, OCR or combined drawing over selected pages.

    Preserve existing ordering: OCR preflight first; then project guard and
    relevant quick-settings check; then selected-page range; only then save
    the chosen mode and start the detector.
    """
    if method == "left_edge":
        if ordinary_settings_guard is None:
            raise ValueError("ordinary drawing requires its quick-settings guard")
        if not app.guard() or not ordinary_settings_guard(app):
            return
        force_refresh = False
    elif method in {"paddleocr", "combined"}:
        if ocr_engine_guard is None:
            raise ValueError("OCR drawing requires its engine guard")
        if not ocr_engine_guard(app):
            return
        if not app.guard() or not app.apply_quick_settings(show_status=False):
            return
        force_refresh = None
    else:
        raise ValueError(f"unknown selected drawing method: {method!r}")

    try:
        indices = app.selected_page_indices()
    except Exception as exc:
        app.show_error("页面范围无效", exc)
        return

    app.settings.detection_method = method
    app.save_settings()
    if force_refresh is None:
        force_refresh = app.ocr_refresh_var.get() == "force"
    app._detect_pages(indices, method=method, force_refresh=force_refresh)
