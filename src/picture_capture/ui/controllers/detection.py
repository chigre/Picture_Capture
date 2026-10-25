from __future__ import annotations

"""User-action orchestration for OCR-backed detection workflows.

This controller owns the stable detection action-entry seams, including the
ordinary OCR-independent drawing action, batch OCR orchestration, and the
current-page detection worker/batch bridge.  The heavy multi-page detection
pipeline, generic batch runner, and broader app/UI persistence infrastructure
remain on ``PictureCaptureApp``.
"""

from dataclasses import replace
from tkinter import messagebox
from typing import Any

from PIL import Image

from ...io.formats import pdic_path, read_pdic, write_pdic
from ...preprocess.analysis_image import normalize_page_rgb
from ...layout.mask_source_guard import missing_saved_illustrations, detection_mask_source_path
from ...ordinary.quick_settings import _apply_quick_settings_for_ordinary
from ...ocr.action_guard import guard_ocr_action_selection
from ...ocr.batch_existing_entries import process_existing_pdic_page
from ...detection.current_page_worker import detect_current_page
from ..detection_current_page_result import apply_current_page_detection_result
from ..batch_ocr_flow import run_existing_pdic_batch
from ..detection_selected_scope_actions import run_selected_draw_action
from ...persistence.page_sections import read_page_sections
from ...paddle_headwords import HEADWORD_FILTER_RULES_FILENAME
from ...processing import (
    column_index,
    column_index_for_click,
    derive_geometry,
    detect_entries,
    export_ocred,
    load_replace_rules,
    ocr_entries,
    ocr_existing_entry_words_from_markers,
    sort_entries_reading_order,
)
from ...profile.semantics import effective_page_settings, page_template_analysis_image
from ...persistence.project_storage import (
    headword_filter_rules_path,
    ocr_cache_root,
    profile_path as project_profile_path,
    qt_root,
    replace_rules_path,
)


class DetectionController:
    """Coordinate OCR/combined detection entry actions and batch OCR."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def auto_detect_current(
        self, clicked_x: int | None = None, force_paddle_refresh: bool = False,
    ) -> None:
        """Run backward-compatible single-page detection through the batch worker."""
        app = self.app
        if app._batch_active:
            app.status_var.set("后台画线任务运行中，暂不启动前台自动识别；可进行人工校对。")
            return
        if not app.guard():
            return
        if not app._guard_transformed_geometry("自动画线"):
            return

        project = app.project
        page = app.current_page
        if missing_saved_illustrations((page,), app.settings):
            app.status_var.set("当前页缺少 PPP 插图数据：请先识别插图，或在设置中心→插图关闭‘使用已有的插图数据’。")
            return
        page_index = int(app.current_index)
        settings = replace(app.settings)
        page_sections = list(app.page_sections)
        existing_entries = [replace(entry) for entry in app.entries]
        cache_path = (
            ocr_cache_root(project.root) / f"{page.stem}.json"
            if settings.detection_method in {"paddleocr", "combined"} else None
        )
        filter_path = (
            headword_filter_rules_path(project.root, HEADWORD_FILTER_RULES_FILENAME)
            if settings.detection_method in {"paddleocr", "combined"} else None
        )

        def worker(_item, _position: int, _total: int):
            return detect_current_page(
                page, project.root, settings,
                page_index=page_index,
                page_sections=page_sections,
                cache_path=cache_path,
                filter_path=filter_path,
                force_paddle_refresh=force_paddle_refresh,
                deps={
                    "Image": Image,
                    "normalize_page_rgb": normalize_page_rgb,
                    "detect_entries": detect_entries,
                    "detection_mask_source_path": detection_mask_source_path,
                    "ocr_existing_entry_words_from_markers": ocr_existing_entry_words_from_markers,
                    "load_replace_rules": load_replace_rules,
                    "replace_rules_path": replace_rules_path,
                    "project_profile_path": project_profile_path,
                },
            )

        def done(_completed, _total, stopped, results, error):
            return apply_current_page_detection_result(
                app,
                project=project,
                page=page,
                settings=settings,
                existing_entries=existing_entries,
                clicked_x=clicked_x,
                stopped=stopped,
                results=results,
                error=error,
                deps={
                    "column_index_for_click": column_index_for_click,
                    "column_index": column_index,
                    "ocr_cache_root": ocr_cache_root,
                },
            )

        label = {
            "combined": "融合画线 当前页识别",
            "paddleocr": "OCR画线 当前页识别",
        }.get(settings.detection_method, "当前页自动画线")
        app._start_batch_task(
            label, [page_index], worker, done,
            item_label=lambda _item: page.name,
            refresh_page_quality=settings.detection_method in {"paddleocr", "combined"},
        )

    def run_normal_draw_action(self) -> None:
        """Ordinary selected-page drawing; retain the legacy public entrypoint."""
        return run_selected_draw_action(
            self.app,
            method="left_edge",
            ordinary_settings_guard=_apply_quick_settings_for_ordinary,
        )

    def paddle_detect_current(self, force_refresh: bool = False) -> None:
        app = self.app
        # This legacy entrypoint can be invoked directly, bypassing the
        # ordinary toolbar action. Keep the same preflight on every OCR path.
        if not guard_ocr_action_selection(app):
            return
        app.settings.detection_method = "paddleocr"
        app.sync_quick_settings()
        app.save_settings()
        app.auto_detect_current(force_paddle_refresh=force_refresh)

    def run_combined_draw_action(self) -> None:
        """Combined selected-page drawing with the live OCR preflight."""
        return run_selected_draw_action(
            self.app, method="combined",
            ocr_engine_guard=guard_ocr_action_selection,
        )

    def run_ocr_draw_action(self) -> None:
        """OCR selected-page drawing with the live OCR preflight."""
        return run_selected_draw_action(
            self.app, method="paddleocr",
            ocr_engine_guard=guard_ocr_action_selection,
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

    def batch_ocr(self) -> None:
        """Delegate the existing-PDIC OCR action to the dedicated UI owner.

        Resolve original controller globals for every dispatch and worker
        execution, retaining tests and runtime module monkeypatch behavior.
        """
        return run_existing_pdic_batch(
            self.app,
            dependencies=lambda: {
                "read_pdic": read_pdic,
                "pdic_path": pdic_path,
                "messagebox": messagebox,
                "load_replace_rules": load_replace_rules,
                "replace_rules_path": replace_rules_path,
                "process_existing_pdic_page": process_existing_pdic_page,
                "Image": Image,
                "normalize_page_rgb": normalize_page_rgb,
                "effective_page_settings": effective_page_settings,
                "page_template_analysis_image": page_template_analysis_image,
                "read_page_sections": read_page_sections,
                "sort_entries_reading_order": sort_entries_reading_order,
                "derive_geometry": derive_geometry,
                "ocr_entries": ocr_entries,
                "qt_root": qt_root,
                "export_ocred": export_ocred,
                "write_pdic": write_pdic,
            },
        )

    def run_ocr_draw(self, scope: str, force_refresh: bool) -> None:
        app = self.app
        # The historical direct API must not bypass the current OCR-engine
        # preflight or treat an unknown scope as an implicit all-page request.
        if not guard_ocr_action_selection(app):
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
        app._detect_pages(
            indices,
            method="paddleocr",
            force_refresh=force_refresh,
        )
