from __future__ import annotations

"""User-action orchestration for illustration detection workflows.

Phase 4M moved the stable selected-scope illustration detection entry seam.
Phase 4N moved the stable illustration-crop action entry. Phase 4O moves the
bounded illustration-crop runner orchestration while retaining the parallel
runner and path-policy boundaries on ``PictureCaptureApp``. Detection/crop
algorithms remain outside this controller.
"""

from dataclasses import replace
from tkinter import messagebox
from typing import Any

from ...formats import pdic_path, read_ppp, write_ppp
from ...processing import (
    append_crop_log, append_illustration_crop_log, detect_illustrations_job,
    split_illustrations_job,
)
from ...project_storage import qt_root


class IllustrationController:
    """Coordinate selected-scope illustration detection without owning algorithms."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def split_illustrations_selected_scope(self) -> None:
        app = self.app
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再执行插图切图。")
            return
        if not app.project or not app.current_page or app.image is None:
            messagebox.showinfo(
                "尚未打开",
                "请先打开包含扫描图片的项目目录。",
                parent=app,
            )
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围无效", exc)
            return
        if not indices:
            return

        app._sync_polygon_label_texts()
        write_ppp(
            app._ppp_write_path(app.current_page),
            app.polygons,
            app.current_page.stem,
        )
        app._start_illustration_crop(indices, app._load_crop_settings())

    def _start_illustration_crop(self, indices: list[int], config: dict) -> None:
        """Start PPP illustration export from the shared crop-settings snapshot."""
        app = self.app
        if not app.project or app._batch_active:
            if app._batch_active:
                app.status_var.set("已有批量任务正在运行，未启动插图切图。")
            return
        project = app.project
        settings = replace(app.settings)
        out_dir = qt_root(project.root) / "PIC"
        general_top = int(config.get("general_top_y", settings.start_y))
        general_bottom = int(config.get("general_bottom_y", 0))
        margin = int(config.get("polygon_margin", 0))
        entry_left = int(config.get("entry_left_padding_x", 0))
        entry_right = int(config.get("entry_right_padding_x", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        specials = config.get("special_pages", {}) if isinstance(config.get("special_pages", {}), dict) else {}
        workers = int(config.get("parallel_workers", settings.crop_parallel_workers))

        def job_builder(index: int, _position: int, _total: int):
            page = project.images[index]
            special = specials.get(page.stem, {}) if isinstance(specials.get(page.stem, {}), dict) else {}
            top_y = int(special.get("top_y", general_top))
            bottom_y = int(special.get("bottom_y", general_bottom))
            return (
                str(page), str(app._ppp_read_path(page)), str(out_dir), settings,
                top_y, bottom_y, margin, str(pdic_path(page)), entry_left, entry_right, integrate_illustrations,
                index,
            )

        def consume_result(_index: int, result):
            records = list(getattr(result, "records", []) or [])
            events = list(getattr(result, "events", []) or [])
            append_crop_log(project.root, records)
            append_illustration_crop_log(project.root, events)
            return len(records)

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            count = sum(int(v or 0) for v in results)
            if stopped:
                app.status_var.set(f"插图切图已停止：完成 {completed}/{total_pages} 页，共导出 {count} 张")
            else:
                app.status_var.set(f"插图切图完成：{completed} 页，共 {count} 张")

        app._start_parallel_batch_task(
            "插图切图", indices, split_illustrations_job, job_builder, consume_result, done,
            item_label=lambda i: project.images[i].name,
            max_workers=workers,
        )

    def detect_illustrations_selected_scope(self) -> None:
        app = self.app
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再执行插图识别。")
            return
        if not app.project or not app.current_page or app.image is None:
            messagebox.showinfo(
                "尚未打开",
                "请先打开包含扫描图片的项目目录。",
                parent=app,
            )
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围无效", exc)
            return
        if not indices:
            return

        # Preserve the foreground PPP commit point before the confirmation
        # dialog and before the worker snapshots the selected range.
        write_ppp(
            app._ppp_write_path(app.current_page),
            app.polygons,
            app.current_page.stem,
        )
        first = app.project.images[indices[0]].name
        last = app.project.images[indices[-1]].name
        if not messagebox.askyesno(
            "插图识别",
            f"将在所选范围自动识别插图并写入 PPP：\n{first} → {last}（共 {len(indices)} 页）\n\n"
            "人工绘制的 PPP 多边形会保留；再次识别只替换此前自动生成的 AUTO 区域。\n"
            "识别结果可继续用“绘制插图多边形”手工修正。\n\n开始识别？",
            parent=app,
        ):
            return

        project = app.project
        settings = replace(app.settings)

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            return detect_illustrations_job(str(page), settings, index)

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            auto_count = sum(int((result or {}).get("auto", 0)) for result in results)
            if stopped:
                app.status_var.set(
                    f"插图识别已停止：完成 {completed}/{total_pages} 页，自动识别 {auto_count} 个插图区域"
                )
            else:
                app.status_var.set(
                    f"插图识别完成：{completed} 页，自动识别 {auto_count} 个插图区域；人工 PPP 已保留"
                )
            if app.current_index in indices and app.current_page is not None:
                app.polygons = read_ppp(app._ppp_read_path(app.current_page))
                app._update_page_row(app.current_index)
                app.polygon_var.set(True)
                app.redraw()

        app._start_batch_task(
            "插图识别",
            indices,
            worker,
            done,
            item_label=lambda index: project.images[index].name,
            foreground_page_edit=True,
            page_indexer=lambda index: int(index),
        )
