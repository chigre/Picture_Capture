from __future__ import annotations

"""User-action orchestration for illustration detection workflows.

Phase 4M moved the stable selected-scope illustration detection entry seam.
Phase 4N also moves the stable illustration-crop action entry while retaining
the actual crop runner on ``PictureCaptureApp``. Detection/crop algorithms
remain outside this controller, and project path policy stays exposed through
the existing app compatibility boundary.
"""

from dataclasses import replace
from tkinter import messagebox
from typing import Any

from ...formats import read_ppp, write_ppp
from ...processing import detect_illustrations_job


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
