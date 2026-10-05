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

from ...formats import pdic_path, read_pdic, write_pdic
from ...image_utils import normalize_page_rgb
from ...ordinary_action_runtime import _apply_quick_settings_for_ordinary
from ...page_sections import read_page_sections
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
from ...profile_semantics import effective_page_settings, page_template_analysis_image
from ...project_storage import (
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
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            detected, geometry = detect_entries(
                image,
                settings,
                paddle_cache_path=cache_path,
                force_paddle_refresh=force_paddle_refresh,
                paddle_filter_rules_path=filter_path,
                profile_page_index=page_index,
                page_sections=page_sections,
            )
            text_stats = None
            if settings.detection_method == "combined":
                original_coords = [
                    (int(entry.x), int(entry.y)) for entry in detected
                ]
                detected, text_stats = ocr_existing_entry_words_from_markers(
                    image,
                    detected,
                    settings,
                    load_replace_rules(replace_rules_path(project.root)),
                    profile_page_index=page_index,
                    page_sections=page_sections,
                    profile_path=project_profile_path(project.root),
                    only_blank=True,
                )
                if [
                    (int(entry.x), int(entry.y)) for entry in detected
                ] != original_coords:
                    raise RuntimeError(
                        "融合画线自动补字不得修改任何画线坐标"
                    )
            return detected, geometry, text_stats

        def done(_completed, _total, stopped, results, error):
            if error is not None or stopped or not results:
                return
            if app.project is not project or app.current_page != page:
                return
            detected, geometry, text_stats = results[-1]
            if clicked_x is None:
                app.entries = list(detected)
            else:
                col = column_index_for_click(clicked_x, geometry)
                merged = [
                    entry for entry in existing_entries
                    if column_index(entry.x, geometry, entry.y) != col
                ]
                merged.extend(
                    entry for entry in detected
                    if column_index(entry.x, geometry, entry.y) == col
                )
                app.entries = merged
            app._sort_entries_reading_order()
            if settings.detection_method in {"paddleocr", "combined"}:
                app._load_ocr_review_candidates()
                app._refresh_page_quality_colors()
            app.redraw()
            if settings.detection_method in {"paddleocr", "combined"}:
                cache = ocr_cache_root(project.root) / f"{page.stem}.json"
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

        label = {
            "combined": "融合画线 当前页识别",
            "paddleocr": "PaddleOCR 当前页识别",
        }.get(settings.detection_method, "当前页自动画线")
        app._start_batch_task(
            label, [page_index], worker, done,
            item_label=lambda _item: page.name,
            refresh_page_quality=settings.detection_method in {"paddleocr", "combined"},
        )

    def run_normal_draw_action(self) -> None:
        """Run ordinary OCR-independent drawing for the selected page scope."""
        app = self.app
        if not app.guard() or not _apply_quick_settings_for_ordinary(app):
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围无效", exc)
            return
        app.settings.detection_method = "left_edge"
        app.save_settings()
        app._detect_pages(indices, method="left_edge", force_refresh=False)

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
