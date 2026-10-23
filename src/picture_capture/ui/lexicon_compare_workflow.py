"""Canonical native-call owners for lexicon compare workflow.

Keep Tk callback ABI and original patched collaborators through live frozen
dependencies. The owner never imports the heavyweight app shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from pathlib import Path

@dataclass(frozen=True)
class LexiconCompareDeps:
    resolve_wordslist_path: object
    read_noncomment_lines: object
    settings_path: object
    words_of_pages_default_path: object
    filedialog: object
    Path: object
    read_text_detected: object
    write_text_atomic: object
    pdic_path: object
    read_pdic: object
    Image: object
    write_pdic: object
    _build_words_page_lookup: object
    _resolve_words_page_token: object
    re: object
    messagebox: object
    tk: object
    _parse_words_of_pages_text: object
    _compare_page_word_mappings: object
    _page_word_mapping_text: object
    OldNewComparisonWindow: object


def reload_wordslist_reference(
    self, deps: LexiconCompareDeps, selected_path: Path | None = None, *, persist: bool = True, redraw: bool = True,
) -> tuple[Path, int]:
    """Reload the auxiliary wordslist and optionally remember a newly chosen file."""
    resolve_wordslist_path = deps.resolve_wordslist_path
    read_noncomment_lines = deps.read_noncomment_lines
    settings_path = deps.settings_path
    if not self.project:
        raise ValueError("尚未打开项目")
    if selected_path is not None:
        selected_path = selected_path.expanduser().resolve()
        if not selected_path.is_file():
            raise FileNotFoundError(selected_path)
        try:
            stored = selected_path.relative_to(self.project.root.resolve()).as_posix()
        except ValueError:
            stored = str(selected_path)
        self.settings.wordslist_path = stored
        self.project.settings.wordslist_path = stored
    path = resolve_wordslist_path(self.project.root, self.settings.wordslist_path)
    words = read_noncomment_lines(path) if path.exists() else []
    self.project.words = words
    self._project_words = set(words)
    if persist:
        self.settings.to_json(settings_path(self.project.root))
    if redraw and self.current_page is not None and self.image is not None:
        self.redraw()
    return path, len(words)

def _request_wordslist_reload(
    self, deps: LexiconCompareDeps, selected_path: Path | None = None, *, persist: bool = True,
    redraw: bool = True, on_done=None, on_error=None,
) -> None:
    """Read a potentially huge wordslist off-thread, then commit it on Tk."""
    resolve_wordslist_path = deps.resolve_wordslist_path
    read_noncomment_lines = deps.read_noncomment_lines
    settings_path = deps.settings_path
    project = self.project
    if project is None:
        if on_error is not None:
            on_error(ValueError("尚未打开项目"))
        return

    configured = self.settings.wordslist_path
    stored_value: str | None = None
    if selected_path is not None:
        selected_path = selected_path.expanduser().resolve()
        if not selected_path.is_file():
            if on_error is not None:
                on_error(FileNotFoundError(selected_path))
            return
        try:
            stored_value = selected_path.relative_to(project.root.resolve()).as_posix()
        except ValueError:
            stored_value = str(selected_path)
        configured = stored_value

    path = resolve_wordslist_path(project.root, configured)
    self.status_var.set(f"正在后台读取 wordslist：{path.name}…")

    def worker():
        words = read_noncomment_lines(path) if path.exists() else []
        return words

    def done(words) -> None:
        if self.project is not project:
            return
        if stored_value is not None:
            self.settings.wordslist_path = stored_value
            project.settings.wordslist_path = stored_value
        project.words = list(words)
        self._project_words = set(words)
        if persist:
            self.settings.to_json(settings_path(project.root))
        if redraw and self.current_page is not None and self.image is not None:
            self.redraw()
        self.status_var.set(f"wordslist 已载入：{path.name}｜{len(words)} 条")
        if on_done is not None:
            on_done(path, len(words))

    def failed(exc, detail) -> None:
        if detail:
            print(detail)
        if self.project is project:
            self.status_var.set(f"wordslist 读取失败：{exc}")
            if on_error is not None:
                on_error(exc)
            else:
                self.show_error("wordslist 读取失败", exc)

    self._start_ui_worker("wordslist-reload", worker, done, failed)

def import_legacy_words(self, deps: LexiconCompareDeps) -> bool:
    """Import legacy words in a sequential background batch.

    The return value now means that an import task was started; completion is
    reported asynchronously in the status bar.
    """
    words_of_pages_default_path = deps.words_of_pages_default_path
    filedialog = deps.filedialog
    Path = deps.Path
    read_text_detected = deps.read_text_detected
    write_text_atomic = deps.write_text_atomic
    pdic_path = deps.pdic_path
    read_pdic = deps.read_pdic
    Image = deps.Image
    write_pdic = deps.write_pdic
    if not self.project or self._batch_active:
        return False
    project = self.project
    path = words_of_pages_default_path(project.root)
    if not path.exists():
        path_text = filedialog.askopenfilename(
            title="选择 _WordsOfPages.txt",
            filetypes=[("文本", "*.txt"), ("全部", "*")],
            parent=self,
        )
        if not path_text:
            return False
        path = Path(path_text)

    pages = list(project.images)
    pages_meta = [
        (
            page.stem,
            pages[i - 1].stem if i > 0 else "@",
            pages[i + 1].stem if i + 1 < len(pages) else "@",
        )
        for i, page in enumerate(pages)
    ]
    holder: dict[str, object] = {
        "lines": None, "rich": False, "groups": None, "words": None, "cursor": 0,
    }
    items: list[object] = ["__parse__"] + list(range(len(pages)))

    def ensure_parsed() -> None:
        if holder["lines"] is not None:
            return
        text_data, _encoding = read_text_detected(path)
        lines = [line for line in text_data.splitlines() if line.strip()]
        rich = [line for line in lines if line.count("#") >= 7]
        holder["lines"] = lines
        if len(rich) == len(lines):
            groups: dict[str, list[str]] = {}
            for line in rich:
                groups.setdefault(line.split("#")[5], []).append(line)
            holder["rich"] = True
            holder["groups"] = groups
        else:
            holder["words"] = [line.split("#", 1)[0].strip() for line in lines]

    def worker(item, _position: int, _total: int):
        ensure_parsed()
        if item == "__parse__":
            return {"parsed": len(holder["lines"] or [])}
        index = int(item)
        page = pages[index]
        changed = False
        if bool(holder["rich"]):
            groups = holder["groups"] if isinstance(holder["groups"], dict) else {}
            rows = list(groups.get(page.stem, []))
            if rows:
                write_text_atomic(
                    pdic_path(page), "\n".join(rows) + "\n", encoding="utf-8",
                )
                changed = True
        else:
            words = holder["words"] if isinstance(holder["words"], list) else []
            cursor = int(holder["cursor"])
            entries = read_pdic(pdic_path(page))
            for entry in entries:
                if cursor >= len(words):
                    break
                entry.word = str(words[cursor])
                cursor += 1
            holder["cursor"] = cursor
            if entries:
                with Image.open(page) as opened:
                    width = int(opened.width)
                write_pdic(pdic_path(page), entries, width, pages_meta[index])
                changed = True
        return {"index": index, "changed": changed}

    def done(_completed, _total, stopped, results, error):
        if error is not None:
            return
        changed_indices = {
            int(row["index"]) for row in results
            if isinstance(row, dict) and row.get("changed") and "index" in row
        }
        if self.project is project and self.current_index in changed_indices:
            self._request_page_load(
                self.current_index, current_already_saved=True, force=True,
            )
        count = len(holder["lines"] or [])
        suffix = "（提前停止）" if stopped else ""
        self.status_var.set(f"已导入旧版数据：{count} 条{suffix}")

    started = self._start_batch_task(
        "导入旧版数据", items, worker, done,
        item_label=lambda item: (
            f"解析 {path.name}" if item == "__parse__"
            else pages[int(item)].name
        ),
    )
    return bool(started)

def _default_old_new_compare_source(self, deps: LexiconCompareDeps) -> Path | None:
    """Return the best initial file suggestion for 【新旧比较】."""
    resolve_wordslist_path = deps.resolve_wordslist_path
    candidates: list[Path] = []
    if self._old_new_compare_source_path is not None:
        candidates.append(self._old_new_compare_source_path)
    if self._word_fill_source_path is not None:
        candidates.append(self._word_fill_source_path)
    if self.project is not None:
        candidates.append(resolve_wordslist_path(self.project.root, self.settings.wordslist_path))
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return candidates[0] if candidates else None

def _looks_page_aware_compare_source(self, deps: LexiconCompareDeps, path: Path) -> bool:
    """Cheaply recognize whether a TXT carries page boundaries for comparison."""
    _build_words_page_lookup = deps._build_words_page_lookup
    _resolve_words_page_token = deps._resolve_words_page_token
    re = deps.re
    if not self.project or not path.is_file():
        return False
    page_stems = [page.stem for page in self.project.images]
    lookup = _build_words_page_lookup(page_stems)
    checked = 0
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for raw in handle:
                stripped = raw.strip()
                if not stripped or raw.lstrip().startswith("'"):
                    continue
                checked += 1
                fields = raw.rstrip("\r\n").split("#")
                if len(fields) >= 8 and _resolve_words_page_token(fields[5], page_stems, lookup) is not None:
                    return True
                tab_fields = raw.rstrip("\r\n").split("\t", 1)
                if len(tab_fields) == 2 and _resolve_words_page_token(tab_fields[0], page_stems, lookup) is not None:
                    return True
                match = re.match(r"^\[([^\]]+)\]$", stripped)
                if not match:
                    match = re.match(r"^(?:page|页码|頁碼|页|頁)\s*[:：]?\s*(\S+)\s*$", stripped, re.I)
                if match and _resolve_words_page_token(match.group(1), page_stems, lookup) is not None:
                    return True
                if checked >= 1200:
                    break
    except (OSError, UnicodeError):
        return False
    return False

def compare_old_new_selected_scope(self, deps: LexiconCompareDeps, force_choose: bool = False) -> None:
    """Compare selected-range current PDIC headwords with a page-aware wordslist.

    ``PDIC`` is treated as the new/current version; the chosen TXT is the old
    version.  Both are reduced to the exact ``page<TAB>headword`` representation
    before exact line-sequence comparison, page by page.
    """
    messagebox = deps.messagebox
    filedialog = deps.filedialog
    Path = deps.Path
    tk = deps.tk
    read_text_detected = deps.read_text_detected
    _parse_words_of_pages_text = deps._parse_words_of_pages_text
    read_pdic = deps.read_pdic
    pdic_path = deps.pdic_path
    _compare_page_word_mappings = deps._compare_page_word_mappings
    _page_word_mapping_text = deps._page_word_mapping_text
    OldNewComparisonWindow = deps.OldNewComparisonWindow
    if not self.project or not self.current_page or self.image is None:
        messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
        return
    if self._batch_active:
        messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=self)
        return
    try:
        indices = self.selected_page_indices()
    except Exception as exc:
        self.show_error("页面范围无效", exc)
        return
    if not indices:
        return

    source = self._old_new_compare_source_path
    suggested = self._default_old_new_compare_source()
    if not force_choose and (source is None or not source.is_file()):
        if suggested is not None and self._looks_page_aware_compare_source(suggested):
            source = suggested
            self._old_new_compare_source_path = source
    if force_choose or source is None or not source.is_file():
        initialdir = self.project.root
        initialfile = "wordslist.txt"
        if suggested is not None:
            initialdir = suggested.parent
            initialfile = suggested.name
        chosen = filedialog.askopenfilename(
            parent=self,
            title="选择用于新旧比较的 wordslist.txt（需含页码）",
            initialdir=str(initialdir),
            initialfile=initialfile,
            filetypes=[("文本", "*.txt"), ("PDIC/文本", "*.pdic *.txt"), ("全部", "*")],
        )
        if not chosen:
            return
        source = Path(chosen)
        self._old_new_compare_source_path = source

    if source is None or not source.is_file():
        messagebox.showerror("新旧比较", "所选 wordslist 文件不存在，请重新选择。", parent=self)
        self._old_new_compare_source_path = None
        return

    try:
        # Make the visible editor the authoritative newest PDIC before the
        # background comparison starts. Other pages are already on disk.
        self._flush_deferred_page_save()
        self._sync_entry_editor_texts()
        self.save_pdic(silent=True, sync_editors=False)
    except Exception as exc:
        self.show_error("新旧比较准备失败", exc)
        return

    project = self.project
    pages = list(project.images)
    all_page_stems = [page.stem for page in pages]
    selected_stems = [pages[index].stem for index in indices]
    selected_set = set(selected_stems)
    holder: dict[str, object] = {"mapping": None, "present": None}

    def ensure_old_mapping() -> tuple[dict[str, list[str]], set[str]]:
        mapping = holder.get("mapping")
        present = holder.get("present")
        if isinstance(mapping, dict) and isinstance(present, set):
            return mapping, present
        text_data, _encoding = read_text_detected(source)
        present_pages: set[str] = set()
        parsed = _parse_words_of_pages_text(text_data, all_page_stems, present_pages=present_pages)
        if not (present_pages & selected_set):
            raise ValueError(
                "所选 wordslist 中没有当前页面范围的页码记录。\n"
                "新旧比较需要 page\\t词条、完整 8 字段 PDIC/_WordsOfPages，或 [页码] 分组格式。"
            )
        holder["mapping"] = parsed
        holder["present"] = present_pages
        return parsed, present_pages

    def worker(index: int, _position: int, _total: int):
        old_mapping, present_pages = ensure_old_mapping()
        page = pages[index]
        entries = read_pdic(pdic_path(page))
        new_words = [str(entry.word or "").strip() for entry in entries]
        old_words = list(old_mapping.get(page.stem, []))
        return {
            "index": index,
            "page": page.stem,
            "old": old_words,
            "new": new_words,
            "old_present": page.stem in present_pages,
        }

    def done(completed: int, total: int, stopped: bool, results, error) -> None:
        if error is not None:
            # If parsing never succeeded, make the next click ask for another
            # old wordslist rather than repeatedly retrying a wrong file.
            if holder.get("mapping") is None:
                self._old_new_compare_source_path = None
            return
        if stopped:
            return
        by_index = {
            int(item.get("index")): item for item in results if isinstance(item, dict) and "index" in item
        }
        old_mapping: dict[str, list[str]] = {}
        new_mapping: dict[str, list[str]] = {}
        missing_old_pages: list[str] = []
        for index, stem in zip(indices, selected_stems):
            item = by_index.get(index, {})
            old_mapping[stem] = list(item.get("old", []))
            new_mapping[stem] = list(item.get("new", []))
            if not bool(item.get("old_present", False)):
                missing_old_pages.append(stem)

        changes, counts = _compare_page_word_mappings(selected_stems, old_mapping, new_mapping)
        payload: dict[str, object] = {
            "source": str(source),
            "page_order": selected_stems,
            "old_mapping": old_mapping,
            "new_mapping": new_mapping,
            "old_text": _page_word_mapping_text(selected_stems, old_mapping),
            "new_text": _page_word_mapping_text(selected_stems, new_mapping),
            "changes": changes,
            "counts": counts,
            "missing_old_pages": missing_old_pages,
        }
        old_window = self.old_new_compare_window
        if old_window is not None:
            try:
                if old_window.winfo_exists():
                    old_window.destroy()
            except tk.TclError:
                pass
        window = OldNewComparisonWindow(self, payload)
        self.old_new_compare_window = window
        diff_total = counts["新增"] + counts["删除"] + counts["修改"]
        self.status_var.set(
            f"新旧比较完成：{len(selected_stems)} 页｜旧 {counts['old_rows']} 行｜"
            f"新 {counts['new_rows']} 行｜差异 {diff_total} 条"
        )

    started = self._start_batch_task(
        "新旧比较", indices, worker, done,
        item_label=lambda index: pages[index].name,
        foreground_page_edit=False,
        refresh_page_quality=False,
    )
    if started:
        self.status_var.set(
            f"正在比较 {len(indices)} 页：当前 PDIC（新） ↔ {source.name}（旧）；可暂停或停止。"
        )

