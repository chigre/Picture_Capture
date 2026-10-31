from __future__ import annotations

"""Legacy direct detection actions, separate from selected-button UI workflows.

Retains the callable contracts for historical direct OCR/current/all entrypoints
without modifying the native Tk controller or installing runtime monkeypatches.
Every OCR path checks its engine configuration before mutating the draw mode.
"""

from typing import Any, Callable


def run_current_paddle_action(
    app: Any,
    *,
    force_refresh: bool,
    ocr_engine_guard: Callable[[Any], bool],
) -> None:
    """Historical paddle_detect_current preflight/sync/save/current dispatch."""
    if not ocr_engine_guard(app):
        return
    app.settings.detection_method = "paddleocr"
    app.sync_quick_settings()
    app.save_settings()
    app.auto_detect_current(force_paddle_refresh=force_refresh)


def run_all_pages_auto_detect(app: Any, *, force_refresh: bool) -> None:
    """Historical batch_auto_detect dispatch, without implicit settings save."""
    if not app.project:
        return
    app._detect_pages(
        list(range(len(app.project.images))),
        method=app.settings.detection_method,
        force_refresh=force_refresh,
    )


def run_legacy_scoped_ocr(
    app: Any,
    *,
    scope: str,
    force_refresh: bool,
    ocr_engine_guard: Callable[[Any], bool],
) -> None:
    """Historical current/all OCR entrypoint with explicit invalid-scope guard."""
    if not ocr_engine_guard(app):
        return
    if not app.guard() or not app.apply_quick_settings(show_status=False):
        return
    if scope not in {"current", "all"}:
        app.show_error("页面范围无效", ValueError(f"未知 OCR 页面范围: {scope!r}"))
        return
    app.settings.detection_method = "paddleocr"
    indices = (
        [app.current_index]
        if scope == "current"
        else list(range(len(app.project.images)))
    )
    app._detect_pages(indices, method="paddleocr", force_refresh=force_refresh)
