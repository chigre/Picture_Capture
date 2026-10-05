from __future__ import annotations

"""User-action orchestration for OCR-backed detection workflows.

This controller intentionally owns only the stable action-entry seam.  The
heavy detection pipeline, batch workers, PDIC persistence, and layout/OCR
algorithms remain on ``PictureCaptureApp`` for later extraction.

``run_normal_draw_action`` is deliberately excluded for now because the legacy
``ordinary_action_runtime`` installer replaces that app method at runtime.  It
should move only when Phase 5 removes that installer so ownership matches the
actual execution path.
"""

from typing import Any


class DetectionController:
    """Coordinate OCR/combined detection entry actions without owning algorithms."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def paddle_detect_current(self, force_refresh: bool = False) -> None:
        app = self.app
        app.settings.detection_method = "paddleocr"
        app.sync_quick_settings()
        app.save_settings()
        app.auto_detect_current(force_paddle_refresh=force_refresh)

    def run_combined_draw_action(self) -> None:
        app = self.app
        if not app.guard() or not app.apply_quick_settings(show_status=False):
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围无效", exc)
            return
        app.settings.detection_method = "combined"
        app.save_settings()
        app._detect_pages(
            indices,
            method="combined",
            force_refresh=app.ocr_refresh_var.get() == "force",
        )

    def run_ocr_draw_action(self) -> None:
        app = self.app
        if not app.guard() or not app.apply_quick_settings(show_status=False):
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围无效", exc)
            return
        app.settings.detection_method = "paddleocr"
        app.save_settings()
        app._detect_pages(
            indices,
            method="paddleocr",
            force_refresh=app.ocr_refresh_var.get() == "force",
        )

    def batch_auto_detect(self, force_paddle_refresh: bool = False) -> None:
        app = self.app
        if not app.project:
            return
        app._detect_pages(
            list(range(len(app.project.images))),
            method=app.settings.detection_method,
            force_refresh=force_paddle_refresh,
        )

    def run_ocr_draw(self, scope: str, force_refresh: bool) -> None:
        app = self.app
        if not app.guard() or not app.apply_quick_settings(show_status=False):
            return
        app.settings.detection_method = "paddleocr"
        indices = (
            [app.current_index]
            if scope == "current"
            else list(range(len(app.project.images)))
        )
        app._detect_pages(
            indices,
            method="paddleocr",
            force_refresh=force_refresh,
        )
