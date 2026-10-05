from __future__ import annotations

"""User-action orchestration for text import/export and PicDic outputs.

The controller owns only the stable UI action boundary. The ``.OCRed`` format
implementation remains in ``processing`` and project path policy remains in
``project_storage`` so this refactor does not change persisted data semantics.
"""

import os
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import Any

from ...formats import pdic_path, read_picdic_index_records
from ...picdic import PicDicBuildCancelled, build_picdic_package
from ...processing import export_ocred, import_ocred
from ...project_storage import exports_root, qt_root


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

    def export_picdic_index(self) -> None:
        """Export a project-wide four-column text index from saved PDIC records.

        The output is intentionally simple for downstream PicDic conversion::

            WORD<TAB>xx.xx<TAB>yy.yy<TAB>page

        Percentages are taken from the persisted PDIC percentage fields rather
        than recalculated from pixels.  This preserves the coordinate semantics
        of the source PDIC, including legacy projects.  Large projects are
        streamed in the background and never accumulated into one giant string.
        """
        app = self.app
        if not app.project or not app.current_page or app.image is None:
            messagebox.showinfo(
                "尚未打开", "请先打开包含扫描图片的项目目录。", parent=app,
            )
            return
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再导出PicDic索引。")
            return
        try:
            app._flush_deferred_page_save()
            app._sync_entry_editor_texts()
            app.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            app.show_error("导出PicDic索引失败", exc)
            return

        project = app.project
        pages = [page for page in project.images if pdic_path(page).exists()]
        if not pages:
            messagebox.showinfo(
                "导出PicDic索引", "当前项目没有可导出的 PDIC 文件。", parent=app,
            )
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = exports_root(project.root) / f"PicDic_index_{stamp}.txt"
        temp = target.with_name(f".{target.name}.tmp")
        state: dict[str, object] = {
            "stream": None, "page_count": 0, "record_count": 0,
        }

        def worker(page: Path, _position: int, _total: int):
            stream = state.get("stream")
            if stream is None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                stream = temp.open("w", encoding="utf-8", newline="\n")
                state["stream"] = stream
            records = read_picdic_index_records(
                pdic_path(page), fallback_page=page.stem,
            )
            if records:
                stream.write("\n".join(records))
                stream.write("\n")
                state["page_count"] = int(state.get("page_count", 0)) + 1
                state["record_count"] = int(state.get("record_count", 0)) + len(records)
            return len(records)

        def done(completed: int, total: int, stopped: bool, _results, error) -> None:
            stream = state.get("stream")
            if stream is not None:
                try:
                    stream.flush()
                    stream.close()
                except OSError:
                    pass
                state["stream"] = None
            if error is not None or stopped:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                if error is None:
                    app.status_var.set(
                        f"PicDic索引导出已停止：完成 {completed}/{total} 页，未生成不完整索引。"
                    )
                return
            try:
                if not temp.exists():
                    temp.write_text("", encoding="utf-8")
                os.replace(temp, target)
                page_count = int(state.get("page_count", 0))
                record_count = int(state.get("record_count", 0))
                app.status_var.set(
                    f"PicDic索引导出完成：{target.name}｜{page_count} 页｜{record_count} 条"
                )
                messagebox.showinfo(
                    "导出PicDic索引",
                    f"已生成：\n{target}\n\n共 {page_count} 个有记录页面，{record_count} 条索引。\n"
                    "格式：WORD\\txx.xx%\\tyy.yy%\\tpage",
                    parent=app,
                )
            except Exception as exc:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                app.show_error("导出PicDic索引失败", exc)

        app._start_batch_task(
            "导出PicDic索引", pages, worker, done,
            item_label=lambda page: page.name,
            refresh_page_quality=False,
        )

    def backup_pdic(self) -> None:
        """Stream every page PDIC into one timestamped backup without blocking Tk.

        Large projects can contain thousands of tiny PDIC files. Reading every
        file and joining all records on the Tk thread made the window appear
        frozen even though disk I/O was still progressing. The backup uses the
        existing sequential background-task runner and writes each page directly
        to a temporary output stream. No page image pixels are read and the full
        backup is never accumulated in memory.
        """
        app = self.app
        if not app.project or not app.current_page or app.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=app)
            return
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再备份PDIC。")
            return
        try:
            app._flush_deferred_page_save()
            app._sync_entry_editor_texts()
            app.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            app.show_error("备份PDIC失败", exc)
            return

        project = app.project
        pages = [page for page in project.images if pdic_path(page).exists()]
        if not pages:
            messagebox.showinfo("备份PDIC", "当前项目没有可备份的 PDIC 文件。", parent=app)
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = exports_root(project.root) / f"all_pdic_backup_{stamp}.txt"
        temp = target.with_name(f".{target.name}.tmp")
        state: dict[str, object] = {"stream": None, "page_count": 0, "record_count": 0}

        def worker(page: Path, _position: int, _total: int):
            stream = state.get("stream")
            if stream is None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                stream = temp.open("w", encoding="utf-8", newline="\n")
                state["stream"] = stream
            source = pdic_path(page)
            # Keep only one page in memory at a time. This is substantially
            # faster than per-line writes on Windows/network disks while still
            # avoiding the old project-wide list/join memory spike.
            page_lines = [
                raw for raw in source.read_text(encoding="utf-8-sig").splitlines()
                if raw.strip()
            ]
            count = len(page_lines)
            if count:
                stream.write("\n".join(page_lines))
                stream.write("\n")
                state["page_count"] = int(state.get("page_count", 0)) + 1
                state["record_count"] = int(state.get("record_count", 0)) + count
            return count

        def done(completed: int, total: int, stopped: bool, _results, error) -> None:
            stream = state.get("stream")
            if stream is not None:
                try:
                    stream.flush()
                    stream.close()
                except OSError:
                    pass
                state["stream"] = None
            if error is not None or stopped:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                if error is None:
                    app.status_var.set(
                        f"PDIC备份已停止：完成 {completed}/{total} 页，未生成不完整备份。"
                    )
                return
            try:
                if not temp.exists():
                    temp.write_text("", encoding="utf-8")
                os.replace(temp, target)
                page_count = int(state.get("page_count", 0))
                record_count = int(state.get("record_count", 0))
                app.status_var.set(
                    f"PDIC备份完成：{target.name}｜{page_count} 页｜{record_count} 条"
                )
                messagebox.showinfo(
                    "备份PDIC",
                    f"已生成：\n{target}\n\n包含 {page_count} 个有记录页面，共 {record_count} 条 PDIC。",
                    parent=app,
                )
            except Exception as exc:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                app.show_error("备份PDIC失败", exc)

        app._start_batch_task(
            "备份PDIC", pages, worker, done, item_label=lambda page: page.name,
            refresh_page_quality=False,
        )
