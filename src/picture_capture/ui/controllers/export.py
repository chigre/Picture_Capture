from __future__ import annotations

"""User-action orchestration for text import/export and PicDic package builds.

The controller owns only the stable UI action boundary. The ``.OCRed`` format
implementation remains in ``processing`` and project path policy remains in
``project_storage`` so this refactor does not change persisted data semantics.
"""

from tkinter import messagebox
from typing import Any

from ...picdic import PicDicBuildCancelled, build_picdic_package
from ...processing import export_ocred, import_ocred
from ...project_storage import qt_root


class ExportController:
    """Coordinate stable export actions without owning persisted formats."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def export_text(self) -> None:
        app = self.app
        if not app.guard():
            return
        export_ocred(
            qt_root(app.project.root) / f"{app.current_page.stem}.OCRed",
            [entry.word for entry in app._ordered_entries_reading_order()],
        )
        app.status_var.set("当前文本已导出")

    def import_text(self) -> None:
        app = self.app
        if not app.guard():
            return
        path = qt_root(app.project.root) / f"{app.current_page.stem}.OCRed"
        try:
            texts = import_ocred(path)
            if len(texts) != len(app.entries):
                raise ValueError(
                    f"文本 {len(texts)} 行，画线 {len(app.entries)} 条，数量不一致"
                )
            for entry, text in zip(app._ordered_entries_reading_order(), texts):
                entry.word = text
            app.redraw()
            app.status_var.set("当前文本已导入")
        except Exception as exc:
            app.show_error("导入失败", exc)


    def build_picdic(self) -> None:
        app = self.app
        if not app.guard():
            return
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再制作 PicDic。")
            return
        try:
            app.save_pdic(silent=True)
        except Exception as exc:
            app.show_error("PicDic 制作准备失败", exc)
            return
        root = app.project.root
        language = app.settings.ocr_language

        def worker(_item, _position: int, _total: int):
            try:
                return build_picdic_package(
                    root, language, should_stop=app._batch_stop_event.is_set,
                )
            except PicDicBuildCancelled:
                return None

        def done(_completed, _total, stopped, results, error):
            if error is not None or stopped or not results:
                return
            dsl, archive, words, images = results[-1]
            app.status_var.set(f"PicDic 制作完成：{words} 个词头，{images} 张图片")
            messagebox.showinfo(
                "PicDic 制作完成",
                f"词头：{words}\n图片：{images}\n\nDSL：{dsl.name}\n图片包：{archive.name}\n目录：{dsl.parent}",
                parent=app,
            )

        app._start_batch_task(
            "PicDic 制作", [root], worker, done,
            item_label=lambda _item: "生成 DSL 与图片包", refresh_page_quality=False,
        )
