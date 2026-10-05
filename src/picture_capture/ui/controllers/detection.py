from __future__ import annotations

"""User-action orchestration for OCR-backed detection workflows.

This controller owns the stable detection action-entry seams plus batch OCR
orchestration.  The heavy detection pipeline, single-page detection bridge,
generic batch runner, and broader app/UI persistence infrastructure remain on
``PictureCaptureApp`` for later extraction.

``run_normal_draw_action`` is deliberately excluded for now because the legacy
``ordinary_action_runtime`` installer replaces that app method at runtime.  It
should move only when Phase 5 removes that installer so ownership matches the
actual execution path.
"""

from dataclasses import replace
from tkinter import messagebox
from typing import Any

from PIL import Image

from ...formats import pdic_path, read_pdic, write_pdic
from ...image_utils import normalize_page_rgb
from ...page_sections import read_page_sections
from ...processing import (
    derive_geometry,
    export_ocred,
    load_replace_rules,
    ocr_entries,
    sort_entries_reading_order,
)
from ...profile_semantics import effective_page_settings, page_template_analysis_image
from ...project_storage import qt_root, replace_rules_path


class DetectionController:
    """Coordinate OCR/combined detection entry actions and batch OCR."""

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

    def batch_ocr(self) -> None:
        app = self.app
        if not app.project or app._batch_active:
            return
        if not app._guard_transformed_geometry("批量 OCR"):
            return
        indices = [
            i
            for i, page in enumerate(app.project.images)
            if read_pdic(pdic_path(page))
        ]
        if not indices:
            app.status_var.set("没有含 PDIC 词条的页面可执行批量 OCR")
            return
        if not messagebox.askyesno(
            "批量 OCR",
            f"将对 {len(indices)} 个已有 PDIC 的页面执行 OCR。\n\n"
            "处理期间可暂停或停止；当前页会先完整处理并保存。继续？",
            parent=app,
        ):
            return

        project = app.project
        settings = replace(app.settings)
        rules = load_replace_rules(replace_rules_path(project.root))
        pages_info = {i: app.pages_tuple(i) for i in indices}

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            entries = read_pdic(pdic_path(page))
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            effective_settings = effective_page_settings(settings, image.size, index)
            analysis_image = page_template_analysis_image(image, effective_settings, index)
            sections = read_page_sections(page)
            entries = sort_entries_reading_order(
                entries,
                derive_geometry(analysis_image, effective_settings),
                sections,
            )
            texts = ocr_entries(
                image,
                entries,
                settings,
                rules,
                profile_page_index=index,
                page_sections=sections,
            )
            for entry, text in zip(entries, texts):
                entry.word = text
            export_ocred(
                qt_root(project.root) / f"{page.stem}.OCRed",
                texts,
            )
            write_pdic(
                pdic_path(page),
                entries,
                image.width,
                pages_info[index],
            )
            return len(texts)

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            count = sum(int(value or 0) for value in results)
            app.load_page(app.current_index)
            if stopped:
                app.status_var.set(
                    f"批量 OCR 已停止：完成 {completed}/{total_pages} 页，共 {count} 个词条"
                )
            else:
                app.status_var.set(f"批量 OCR 完成：{count} 个词条")

        app._start_batch_task(
            "批量 OCR",
            indices,
            worker,
            done,
            item_label=lambda i: project.images[i].name,
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
