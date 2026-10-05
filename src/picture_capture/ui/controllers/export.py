from __future__ import annotations

"""User-action orchestration for text import/export and PicDic outputs.

The controller owns only the stable UI action boundary. The ``.OCRed`` format
implementation remains in ``processing`` and project path policy remains in
``project_storage`` so this refactor does not change persisted data semantics.
"""

import os
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

from PIL import Image

from ...formats import pdic_path, read_pdic, read_picdic_index_records
from ...page_sections import read_page_sections
from ...pdic_restore import parse_merged_pdic_text, write_pdic_atomic
from ...picdic import PicDicBuildCancelled, build_picdic_package
from ...processing import (
    derive_nominal_geometry, export_ocred, import_ocred,
    sort_entries_column_y, sort_entries_reading_order,
)
from ...project_storage import exports_root, qt_root
from ...text_encoding import read_text_detected


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

    def repair_pdic_order_selected_scope(self) -> None:
        """Rewrite selected-page PDIC files in stable column/Y order.

        X deliberately does not participate in this repair sort.  Existing
        word<->coordinate pairs remain intact; records sharing the same column
        and Y retain their current relative order.
        """
        app = self.app
        if not app.project or not app.current_page or app.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=app)
            return
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再修复排序。")
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围错误", exc)
            return
        if not indices:
            app.status_var.set("没有选中需要修复的页面")
            return

        existing = [i for i in indices if pdic_path(app.project.images[i]).exists()]
        if not existing:
            app.status_var.set("所选范围没有已有 PDIC 文件")
            return
        try:
            app._flush_deferred_page_save()
            app._sync_entry_editor_texts()
            app.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            app.show_error("修复排序准备失败", exc)
            return

        if not messagebox.askyesno(
            "修复排序",
            f"将对所选范围中 {len(existing)} 个已有 PDIC 页面按“栏号 → Y”重新排序并原子写回（X 不参与排序）。\n\n"
            "每条记录现有的词条文字与 X/Y 坐标会保持绑定，不会重新 OCR 或改词。\n"
            "建议先点击【备份PDIC】保留当前状态。\n\n继续？",
            parent=app,
        ):
            return

        project = app.project
        settings = app.settings

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            target = pdic_path(page)
            entries = read_pdic(target)
            if not entries:
                return (index, 0, False)
            before = [(e.word, int(e.x), int(e.y)) for e in entries]
            with Image.open(page) as opened:
                width, height = map(int, opened.size)
            geometry = derive_nominal_geometry(width, height, settings)
            ordered = sort_entries_column_y(
                entries, geometry, read_page_sections(page),
            )
            after = [(e.word, int(e.x), int(e.y)) for e in ordered]
            previous = project.images[index - 1].stem if index > 0 else "@"
            following = project.images[index + 1].stem if index + 1 < len(project.images) else "@"
            write_pdic_atomic(target, ordered, width, (page.stem, previous, following))
            return (index, len(ordered), before != after)

        def done(completed: int, total: int, stopped: bool, results, error) -> None:
            if error is not None:
                return
            changed = sum(1 for result in results if result and result[2])
            records = sum(int(result[1]) for result in results if result)
            if app.current_index in existing:
                app.load_page(app.current_index)
            state = "已停止" if stopped else "完成"
            app.status_var.set(
                f"修复排序{state}：处理 {completed}/{total} 页；实际改序 {changed} 页；{records} 条记录"
            )

        app._start_batch_task(
            "修复排序", existing, worker, done,
            item_label=lambda i: project.images[i].name,
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

    def restore_from_pdic_backup(self) -> None:
        """Rebuild the selected page range from one PDIC backup text.

        The selected range is authoritative: every selected page is overwritten.
        If a selected page has no records in the merged source, its PDIC is
        replaced by an empty file instead of borrowing records from adjacent
        pages. Parsing and per-page commits run off the Tk thread.
        """
        app = self.app
        if not app.project or not app.current_page or app.image is None:
            messagebox.showinfo(
                "尚未打开", "请先打开包含扫描图片的项目目录。", parent=app,
            )
            return
        if app._batch_active:
            messagebox.showinfo(
                "批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=app,
            )
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围无效", exc)
            return
        if not indices:
            return

        path_text = filedialog.askopenfilename(
            title="选择备份的PDIC 备份 文本",
            initialdir=str(app.project.root),
            filetypes=[
                ("PDIC/文本", "*.pdic *.txt"),
                ("PDIC", "*.pdic"),
                ("文本", "*.txt"),
                ("全部", "*"),
            ],
            parent=app,
        )
        if not path_text:
            return
        source = Path(path_text)
        if not messagebox.askyesno(
            "恢复PDIC",
            f"将从：\n{source.name}\n\n覆盖重建主界面所选范围内的 {len(indices)} 个页面 PDIC。\n"
            "范围外页面不会修改。PDIC 备份 中若某个选定页面没有记录，该页会被重建为空 PDIC。\n\n"
            "每页完成后立即原子覆盖，可暂停或停止；已完成页面不会回滚。继续？",
            parent=app,
        ):
            return

        try:
            app._flush_deferred_page_save()
            app._sync_entry_editor_texts()
            app.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            app.show_error("PDIC 备份 恢复准备失败", exc)
            return

        project = app.project
        settings_snapshot = replace(app.settings)
        pages = list(project.images)
        page_stems = [page.stem for page in pages]
        pages_meta = {i: app.pages_tuple(i) for i in indices}
        parsed_holder: dict[str, object] = {"mapping": None, "stats": None}
        parse_lock = threading.Lock()

        def ensure_parsed():
            mapping = parsed_holder.get("mapping")
            stats = parsed_holder.get("stats")
            if isinstance(mapping, dict) and isinstance(stats, dict):
                return mapping, stats
            with parse_lock:
                mapping = parsed_holder.get("mapping")
                stats = parsed_holder.get("stats")
                if not isinstance(mapping, dict) or not isinstance(stats, dict):
                    text_data, _encoding = read_text_detected(source)
                    mapping, stats = parse_merged_pdic_text(text_data, page_stems)
                    parsed_holder["mapping"] = mapping
                    parsed_holder["stats"] = stats
            return mapping, stats

        def worker(index: int, _position: int, _total: int):
            mapping, stats = ensure_parsed()
            page = pages[index]
            entries = [replace(entry) for entry in mapping.get(page.stem, [])]
            with Image.open(page) as opened:
                width, height = map(int, opened.size)
            entries = sort_entries_reading_order(
                entries,
                derive_nominal_geometry(width, height, settings_snapshot),
                read_page_sections(page),
            )
            write_pdic_atomic(pdic_path(page), entries, width, pages_meta[index])
            return {
                "index": index,
                "records": len(entries),
                "empty": not entries,
                "source_records": int(stats.get("records", 0)),
                "source_matched": int(stats.get("matched", 0)),
                "source_unmatched": int(stats.get("unmatched", 0)),
            }

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            rebuilt = 0
            records = 0
            empty_pages = 0
            completed_indices: set[int] = set()
            stats = (
                parsed_holder.get("stats")
                if isinstance(parsed_holder.get("stats"), dict)
                else {}
            )
            for result in results:
                if not isinstance(result, dict):
                    continue
                index = int(result.get("index", -1))
                if index >= 0:
                    completed_indices.add(index)
                rebuilt += 1
                records += int(result.get("records", 0) or 0)
                empty_pages += int(bool(result.get("empty")))

            app._clear_word_fill_checks_for_indices(completed_indices, persist=True)
            for index in completed_indices:
                app._update_page_row(index)
            app._schedule_page_cell_overlay_refresh()
            if app.current_index in completed_indices:
                app.load_page(app.current_index)

            unmatched = int(stats.get("unmatched", 0) or 0)
            if stopped:
                app.status_var.set(
                    f"PDIC 备份 恢复已停止：完成 {completed}/{total_pages} 页，重建 {records} 条；"
                    f"空页 {empty_pages} 页"
                )
            else:
                extra = (
                    f"；源文件有 {unmatched} 条记录未对应当前项目页面"
                    if unmatched
                    else ""
                )
                app.status_var.set(
                    f"PDIC 备份 恢复完成：{rebuilt}/{total_pages} 页，重建 {records} 条；"
                    f"空页 {empty_pages} 页{extra}"
                )

        started = app._start_batch_task(
            "恢复PDIC",
            indices,
            worker,
            done,
            item_label=lambda i: pages[i].name,
            foreground_page_edit=False,
        )
        if started:
            app.batch_text_var.set(
                f"恢复PDIC：准备读取备份文件 0/{len(indices)}"
            )
            app.status_var.set(
                f"正在后台解析PDIC 备份 并逐页覆盖重建：共 {len(indices)} 页；"
                "进度按页面更新，可暂停或停止。"
            )
