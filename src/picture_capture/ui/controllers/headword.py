from __future__ import annotations

"""User-action orchestration for page-aware headword filling.

The controller owns the stable source-selection and fill action boundary. Existing
app-owned cache fields, fill-status persistence, batch execution, page refresh,
and PDIC format semantics remain unchanged so this refactor does not alter the
persisted data contract.
"""

from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable

from PIL import Image

from ...formats import pdic_path, read_pdic, write_pdic
from ...page_sections import read_page_sections
from ...processing import derive_nominal_geometry, sort_entries_reading_order
from ...text_encoding import read_text_detected


class HeadwordController:
    """Coordinate selection and batch filling of page-aware headword sources."""

    def __init__(
        self,
        app: Any,
        *,
        parse_words_of_pages_text: Callable[..., dict[str, list[str]]],
        fill_page_entries: Callable[[list[Any], list[str]], tuple[int, int, int]],
    ) -> None:
        self.app = app
        self._parse_words_of_pages_text = parse_words_of_pages_text
        self._fill_page_entries = fill_page_entries

    @staticmethod
    def _file_signature(path: Path) -> tuple[str, int, int]:
        stat = path.stat()
        return (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))

    def select_existing_headwords_file(self) -> None:
        """Choose the page-aware TXT used by subsequent fill operations."""
        app = self.app
        if not app.project:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=app)
            return
        if app._batch_active:
            messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=app)
            return
        initialdir = app.project.root
        initialfile = "_WordsOfPages.txt"
        if app._word_fill_source_path is not None:
            initialdir = app._word_fill_source_path.parent
            initialfile = app._word_fill_source_path.name
        path_text = filedialog.askopenfilename(
            title="选择包含既有词条的 TXT",
            initialdir=str(initialdir),
            initialfile=initialfile,
            filetypes=[("文本", "*.txt"), ("全部", "*")],
            parent=app,
        )
        if not path_text:
            return
        path = Path(path_text)
        try:
            signature = self._file_signature(path)
        except Exception as exc:
            app.show_error("词条文件不可用", exc)
            return

        # Re-selecting an unchanged source keeps the already parsed mapping.
        # Choosing another file, or choosing a changed version of the same file,
        # invalidates only the parse cache; no PDIC is touched at this stage.
        if signature != app._word_fill_source_signature:
            app._word_fill_source_mapping = None
            app._word_fill_source_present_pages = None
        app._word_fill_source_path = path
        app._word_fill_source_signature = signature
        cached = "（已缓存解析结果）" if app._word_fill_source_mapping is not None else ""
        app.status_var.set(f"已选择词条文件：{path.name}{cached}；调整页面范围后点击[填充词条]。")

    def fill_existing_headwords(self) -> None:
        """Fill the selected range from the already chosen page-aware TXT.

        The source file picker is intentionally *not* opened here. Once a file
        has been selected, the parsed mapping survives repeated fill batches in
        this project. If the source changes on disk, its signature invalidates
        the cache and the next batch reparses it in the worker thread.
        """
        app = self.app
        if not app.project or not app.current_page or app.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=app)
            return
        if app._batch_active:
            messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=app)
            return
        if app._word_fill_source_path is None:
            messagebox.showinfo("尚未选择词条文件", "请先点击[选择词条文件]，再执行填充。", parent=app)
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围无效", exc)
            return
        if not indices:
            return

        txt_path = app._word_fill_source_path
        try:
            current_signature = self._file_signature(txt_path)
        except Exception as exc:
            app.show_error("词条文件不可用", exc)
            return
        if current_signature != app._word_fill_source_signature:
            app._word_fill_source_signature = current_signature
            app._word_fill_source_mapping = None
            app._word_fill_source_present_pages = None

        try:
            # Commit any live Entry edits before the worker starts reading PDIC.
            # During this task foreground page edits/navigation are intentionally
            # blocked, so a worker can never race a stale canvas copy.
            app._flush_deferred_page_save()
            app._sync_entry_editor_texts()
            app.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            app.show_error("填充词条失败", exc)
            return

        project = app.project
        settings_snapshot = replace(app.settings)
        pages = list(project.images)
        page_stems = [page.stem for page in pages]
        pages_meta = [
            (
                page.stem,
                pages[i - 1].stem if i > 0 else "@",
                pages[i + 1].stem if i + 1 < len(pages) else "@",
            )
            for i, page in enumerate(pages)
        ]
        # A holder local to this batch avoids any race where the first worker
        # resolves the app-level cache while subsequent page commits start.
        mapping_holder = {
            "value": app._word_fill_source_mapping,
            "present": app._word_fill_source_present_pages,
        }

        def ensure_mapping() -> tuple[dict[str, list[str]], set[str]]:
            mapping = mapping_holder["value"]
            present = mapping_holder["present"]
            if mapping is None or present is None:
                text_data, _detected_encoding = read_text_detected(txt_path)
                present = set()
                mapping = self._parse_words_of_pages_text(
                    text_data, page_stems, present_pages=present,
                )
                mapping_holder["value"] = mapping
                mapping_holder["present"] = present
            return mapping, present

        def worker(index: int, _position: int, _total: int):
            mapping, present_pages = ensure_mapping()
            page = pages[index]
            entries = read_pdic(pdic_path(page))
            with Image.open(page) as opened:
                width, height = map(int, opened.size)
            entries = sort_entries_reading_order(
                entries,
                derive_nominal_geometry(width, height, settings_snapshot),
                read_page_sections(page),
            )
            has_data = page.stem in present_pages
            words = list(mapping.get(page.stem, [])) if has_data else []
            filled, line_count, word_count = self._fill_page_entries(entries, words)

            # Empty pages stay empty; a page with TXT words but no lines must not
            # get a fabricated PDIC. Each completed page is its own commit point.
            if entries or pdic_path(page).exists():
                write_pdic(pdic_path(page), entries, width, pages_meta[index])
            return {
                "index": index,
                "filled": filled,
                "line_count": line_count,
                "word_count": word_count,
                "has_data": has_data,
                "mismatch": has_data and line_count != word_count,
            }

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            if (
                app.project is project
                and app._word_fill_source_path == txt_path
                and app._word_fill_source_signature == current_signature
            ):
                mapping = mapping_holder.get("value")
                present = mapping_holder.get("present")
                if isinstance(mapping, dict) and isinstance(present, set):
                    app._word_fill_source_mapping = mapping
                    app._word_fill_source_present_pages = present
            filled_total = 0
            mismatch_count = 0
            no_data_count = 0
            completed_indices: set[int] = set()
            for result in results:
                if not isinstance(result, dict):
                    continue
                index = int(result.get("index", -1))
                if index < 0:
                    continue
                completed_indices.add(index)
                filled_total += int(result.get("filled", 0) or 0)
                line_count = int(result.get("line_count", 0) or 0)
                word_count = int(result.get("word_count", 0) or 0)
                has_data = bool(result.get("has_data", True))
                app._record_word_fill_check(
                    index,
                    line_count,
                    word_count,
                    source=txt_path.name,
                    has_data=has_data,
                    persist=False,
                    refresh_overlay=False,
                    refresh_row=False,
                )
                if not has_data:
                    no_data_count += 1
                elif line_count != word_count:
                    mismatch_count += 1

            if completed_indices:
                app._persist_word_fill_status()
            if app.current_index in completed_indices:
                app.load_page(app.current_index)

            source_name = txt_path.name
            if stopped:
                app.status_var.set(
                    f"既有词条填充已停止：完成 {completed}/{total_pages} 页，填入 {filled_total} 个词条；"
                    f"已完成页面中数量不一致 {mismatch_count} 页，无资料 {no_data_count} 页；来源：{source_name}"
                )
            else:
                app.status_var.set(
                    f"既有词条填充完成：{completed}/{total_pages} 页，填入 {filled_total} 个词条；"
                    f"数量不一致 {mismatch_count} 页（填充状态格淡红提示），无资料 {no_data_count} 页；来源：{source_name}"
                )

        started = app._start_batch_task(
            "填充词条",
            indices,
            worker,
            done,
            item_label=lambda i: pages[i].name,
            foreground_page_edit=False,
        )
        if started:
            cached = app._word_fill_source_mapping is not None
            phase = "使用已缓存词条索引" if cached else "准备读取并解析词条文件"
            app.batch_text_var.set(f"填充词条：{phase} 0/{len(indices)}")
            app.status_var.set(
                f"正在后台逐页填充：共 {len(indices)} 页；来源：{txt_path.name}；"
                "进度按页面更新，可暂停或停止。"
            )
