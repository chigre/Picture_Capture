from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/picture_capture/app.py"
CONTROLLER = ROOT / "src/picture_capture/ui/controllers/export.py"
SERVICE = ROOT / "src/picture_capture/pdic_restore.py"
EXPORT_TESTS = ROOT / "tests/test_ui_export_controller.py"
RESTORE_TESTS = ROOT / "tests/test_ui_pdic_restore_controller.py"

app = APP.read_text(encoding="utf-8")
controller = CONTROLLER.read_text(encoding="utf-8")
export_tests = EXPORT_TESTS.read_text(encoding="utf-8")

# ---- app.py: route shared PDIC restore primitives through a low-level module ----
import_anchor = "from .models import (\n    AppSettings, Entry as WordEntry, PolygonRegion, ProjectState, project_page_images,\n    natural_text_key, read_noncomment_lines, resolve_wordslist_path, resolved_tesseract_language,\n)\n"
assert import_anchor in app
service_import = import_anchor + "from .pdic_restore import (\n    build_page_lookup as _build_words_page_lookup,\n    parse_merged_pdic_text as _parse_merged_pdic_text,\n    resolve_page_token as _resolve_words_page_token,\n    write_pdic_atomic as _write_pdic_atomic,\n)\n"
app = app.replace(import_anchor, service_import, 1)

lookup_start = app.index("def _build_words_page_lookup(")
lookup_end = app.index("def _parse_words_of_pages_text(", lookup_start)
lookup_block = app[lookup_start:lookup_end]
assert "def _resolve_words_page_token(" in lookup_block
assert "numeric_candidates" in lookup_block
app = app[:lookup_start] + app[lookup_end:]

restore_helpers_start = app.index("def _parse_merged_pdic_text(")
restore_helpers_end = app.index("def _page_word_mapping_text(", restore_helpers_start)
restore_helpers = app[restore_helpers_start:restore_helpers_end]
assert "def _write_pdic_atomic(" in restore_helpers
assert "os.replace(temp, target)" in restore_helpers
app = app[:restore_helpers_start] + app[restore_helpers_end:]

# ---- app.py: retain only the historical public wrapper and alias ----
method_start = app.index("    def restore_from_pdic_backup(self) -> None:\n")
method_end = app.index("    def restore_from_merged_pdic(self) -> None:\n", method_start)
restore_body = app[method_start:method_end]
for required in (
    'messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=self)',
    "indices = self.selected_page_indices()",
    'title="选择备份的PDIC 备份 文本"',
    'self._flush_deferred_page_save()',
    'settings_snapshot = replace(self.settings)',
    'read_text_detected(source)',
    '_parse_merged_pdic_text(text_data, page_stems)',
    'derive_nominal_geometry(width, height, settings_snapshot)',
    '_write_pdic_atomic(pdic_path(page), entries, width, pages_meta[index])',
    'self._clear_word_fill_checks_for_indices(completed_indices, persist=True)',
    'foreground_page_edit=False',
):
    assert required in restore_body, required
wrapper = (
    "    def restore_from_pdic_backup(self) -> None:\n"
    "        self._export_controller_for_call().restore_from_pdic_backup()\n\n"
)
app = app[:method_start] + wrapper + app[method_end:]

# ---- low-level restore module ----
service = '''from __future__ import annotations

"""Low-level PDIC backup restore primitives.

This module owns deterministic page-token resolution, merged-PDIC parsing and
one-page atomic publication.  It deliberately contains no Tk/UI orchestration;
controllers decide scope, confirmation, batch lifetime and refresh behavior.
"""

import os
from pathlib import Path
import re

from .formats import write_pdic
from .models import Entry as WordEntry


def build_page_lookup(
    page_stems: list[str],
) -> tuple[dict[str, str], dict[int, str], dict[int, str]]:
    """Build O(1) exact/numeric/suffix lookup tables for project page stems."""
    exact: dict[str, str] = {}
    numeric_candidates: dict[int, list[str]] = {}
    suffix_candidates: dict[int, list[str]] = {}
    for stem in page_stems:
        exact[stem.casefold()] = stem
        if stem.isdigit():
            numeric_candidates.setdefault(int(stem), []).append(stem)
        match = re.search(r"(\\d+)$", stem)
        if match:
            suffix_candidates.setdefault(int(match.group(1)), []).append(stem)
    numeric = {
        number: values[0]
        for number, values in numeric_candidates.items()
        if len(values) == 1
    }
    suffix = {
        number: values[0]
        for number, values in suffix_candidates.items()
        if len(values) == 1
    }
    return exact, numeric, suffix


def resolve_page_token(
    token: str,
    page_stems: list[str],
    lookup: tuple[dict[str, str], dict[int, str], dict[int, str]] | None = None,
) -> str | None:
    """Resolve one legacy page token without guessing ambiguous numeric suffixes."""
    cleaned = Path(str(token).strip()).stem.strip()
    if not cleaned:
        return None
    exact, numeric, suffix = lookup or build_page_lookup(page_stems)
    hit = exact.get(cleaned.casefold())
    if hit:
        return hit
    if cleaned.isdigit():
        number = int(cleaned)
        hit = numeric.get(number)
        if hit:
            return hit
        return suffix.get(number)
    return None


def parse_merged_pdic_text(
    text: str,
    page_stems: list[str],
) -> tuple[dict[str, list[WordEntry]], dict[str, int]]:
    """Parse a whole-dictionary PDIC backup into independent per-page entries."""
    mapping: dict[str, list[WordEntry]] = {stem: [] for stem in page_stems}
    lookup = build_page_lookup(page_stems)
    matched = 0
    unmatched = 0
    nonblank = 0
    for line_no, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        nonblank += 1
        fields = raw.split("#")
        if len(fields) < 8:
            raise ValueError(
                f"整体 PDIC 第 {line_no} 行字段不足 8 个，不是有效 PDIC 记录"
            )
        try:
            x = int(float(fields[1]))
            y = int(float(fields[2]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"整体 PDIC 第 {line_no} 行坐标无效") from exc
        page = resolve_page_token(fields[5], page_stems, lookup)
        if page is None:
            unmatched += 1
            continue
        mapping[page].append(
            WordEntry(
                word=str(fields[0]),
                x=x,
                y=y,
                current_page=page,
                previous_page=str(fields[6] or "@"),
                next_page=str(fields[7] or "@"),
            )
        )
        matched += 1
    if nonblank == 0:
        raise ValueError("整体 PDIC 文件为空，没有可用于恢复的记录。")
    if matched == 0:
        raise ValueError(
            "整体 PDIC 中没有任何记录能对应当前项目页面，请核对是否选择了正确文件。"
        )
    return mapping, {
        "records": nonblank,
        "matched": matched,
        "unmatched": unmatched,
    }


def write_pdic_atomic(
    target: Path,
    entries: list[WordEntry],
    image_width: int,
    pages: tuple[str, str, str],
) -> None:
    """Atomically replace one page PDIC so stop/crash never leaves a half file."""
    temp = target.with_name(f".{target.name}.restore.tmp")
    try:
        write_pdic(temp, entries, image_width, pages)
        os.replace(temp, target)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass
'''

# ---- ExportController: own the destructive action boundary, not the low-level format ----
controller = controller.replace("import os\n", "import os\nimport threading\n", 1)
controller = controller.replace(
    "from datetime import datetime\n",
    "from dataclasses import replace\nfrom datetime import datetime\n",
    1,
)
controller = controller.replace(
    "from tkinter import messagebox\n",
    "from tkinter import filedialog, messagebox\n",
    1,
)
controller = controller.replace(
    "from typing import Any\n\n",
    "from typing import Any\n\nfrom PIL import Image\n\n",
    1,
)
controller = controller.replace(
    "from ...formats import pdic_path, read_picdic_index_records\n",
    "from ...formats import pdic_path, read_picdic_index_records\n"
    "from ...page_sections import read_page_sections\n"
    "from ...pdic_restore import parse_merged_pdic_text, write_pdic_atomic\n",
    1,
)
controller = controller.replace(
    "from ...processing import export_ocred, import_ocred\n",
    "from ...processing import (\n"
    "    derive_nominal_geometry, export_ocred, import_ocred,\n"
    "    sort_entries_reading_order,\n"
    ")\n",
    1,
)
controller = controller.replace(
    "from ...project_storage import exports_root, qt_root\n",
    "from ...project_storage import exports_root, qt_root\n"
    "from ...text_encoding import read_text_detected\n",
    1,
)
assert "    def restore_from_pdic_backup(self) -> None:" not in controller
restore_method = r'''

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
'''
controller = controller.rstrip() + restore_method + "\n"

# ---- update the Phase 4R source-shape test to the new boundary ----
old_test_start = export_tests.index(
    "def test_backup_pdic_wiring_keeps_restore_outside_phase4r() -> None:\n"
)
next_test = export_tests.find("\ndef ", old_test_start + 5)
old_test_end = len(export_tests) if next_test < 0 else next_test + 1
new_test = '''def test_export_controller_wiring_owns_backup_and_restore_after_phase4s() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/export.py"
    ).read_text(encoding="utf-8")

    backup_start = app.index("    def backup_pdic(self) -> None:")
    restore_start = app.index("    def restore_from_pdic_backup(self) -> None:", backup_start)
    alias_start = app.index("    def restore_from_merged_pdic(self) -> None:", restore_start)
    backup_block = app[backup_start:restore_start]
    restore_block = app[restore_start:alias_start]
    assert "self._export_controller_for_call().backup_pdic()" in backup_block
    assert "self._export_controller_for_call().restore_from_pdic_backup()" in restore_block
    assert "_start_batch_task" not in backup_block
    assert "_start_batch_task" not in restore_block
    assert "    def backup_pdic(self) -> None:" in controller
    assert "    def restore_from_pdic_backup(self) -> None:" in controller
    assert "    def restore_from_merged_pdic(self) -> None:" in app
    assert 'self.restore_from_pdic_backup()' in app[alias_start:]
    assert '("备份PDIC", self.backup_pdic)' in app
    assert '("恢复PDIC", self.restore_from_pdic_backup)' in app
'''
export_tests = export_tests[:old_test_start] + new_test + export_tests[old_test_end:]

restore_tests = r'''from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from picture_capture.models import AppSettings, Entry
from picture_capture.pdic_restore import (
    build_page_lookup,
    parse_merged_pdic_text,
    resolve_page_token,
    write_pdic_atomic,
)
import picture_capture.pdic_restore as restore_module
import picture_capture.ui.controllers.export as export_module
from picture_capture.ui.controllers.export import ExportController


class _Var:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value) -> None:
        self.values.append(str(value))


class _Opened:
    def __init__(self, size=(100, 200)) -> None:
        self.size = size

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class _RestoreApp:
    def __init__(self, root: Path, pages: list[Path]) -> None:
        self.project = SimpleNamespace(root=root, images=pages)
        self.current_page = pages[0] if pages else None
        self.image = object() if pages else None
        self.current_index = 0
        self._batch_active = False
        self.settings = AppSettings()
        self.status_var = _Var()
        self.batch_text_var = _Var()
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []
        self.batch = None
        self.start_result = True
        self.indices = list(range(len(pages)))

    def selected_page_indices(self):
        self.calls.append(("selected",))
        return list(self.indices)

    def _flush_deferred_page_save(self) -> None:
        self.calls.append(("flush",))

    def _sync_entry_editor_texts(self) -> None:
        self.calls.append(("sync",))

    def save_pdic(self, *, silent: bool, sync_editors: bool) -> None:
        self.calls.append(("save", silent, sync_editors))

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))

    def pages_tuple(self, index: int):
        self.calls.append(("pages_tuple", index))
        pages = self.project.images
        return (
            pages[index].stem,
            pages[index - 1].stem if index > 0 else "@",
            pages[index + 1].stem if index + 1 < len(pages) else "@",
        )

    def _start_batch_task(self, title, items, worker, done, **kwargs):
        self.batch = (title, list(items), worker, done, kwargs)
        self.calls.append(("start_batch", title, tuple(items)))
        return self.start_result

    def _clear_word_fill_checks_for_indices(self, indices, *, persist: bool) -> None:
        self.calls.append(("clear_checks", tuple(sorted(indices)), persist))

    def _update_page_row(self, index: int) -> None:
        self.calls.append(("update_row", index))

    def _schedule_page_cell_overlay_refresh(self) -> None:
        self.calls.append(("refresh_overlay",))

    def load_page(self, index: int) -> None:
        self.calls.append(("load_page", index))


def _patch_restore_dialogs(monkeypatch, source: Path, *, confirm: bool = True) -> None:
    monkeypatch.setattr(export_module.filedialog, "askopenfilename", lambda **_kwargs: str(source))
    monkeypatch.setattr(export_module.messagebox, "askyesno", lambda *_args, **_kwargs: confirm)


def test_restore_missing_project_preserves_dialog(monkeypatch, tmp_path) -> None:
    page = tmp_path / "001.jpg"
    app = _RestoreApp(tmp_path, [page])
    app.project = None
    dialogs: list[tuple] = []
    monkeypatch.setattr(
        export_module.messagebox,
        "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).restore_from_pdic_backup()

    assert dialogs == [("尚未打开", "请先打开包含扫描图片的项目目录。", app)]
    assert app.batch is None


def test_restore_batch_active_preserves_dialog(monkeypatch, tmp_path) -> None:
    page = tmp_path / "001.jpg"
    app = _RestoreApp(tmp_path, [page])
    app._batch_active = True
    dialogs: list[tuple] = []
    monkeypatch.setattr(
        export_module.messagebox,
        "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).restore_from_pdic_backup()

    assert dialogs == [("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", app)]
    assert app.batch is None


def test_restore_cancelled_picker_does_not_prepare(monkeypatch, tmp_path) -> None:
    page = tmp_path / "001.jpg"
    app = _RestoreApp(tmp_path, [page])
    monkeypatch.setattr(export_module.filedialog, "askopenfilename", lambda **_kwargs: "")

    ExportController(app).restore_from_pdic_backup()

    assert app.calls == [("selected",)]
    assert app.batch is None


def test_restore_preparation_failure_uses_exact_error(monkeypatch, tmp_path) -> None:
    page = tmp_path / "001.jpg"
    source = tmp_path / "backup.txt"
    app = _RestoreApp(tmp_path, [page])
    _patch_restore_dialogs(monkeypatch, source)
    problem = OSError("save failed")

    def fail_save(*, silent: bool, sync_editors: bool) -> None:
        app.calls.append(("save", silent, sync_editors))
        raise problem

    app.save_pdic = fail_save
    ExportController(app).restore_from_pdic_backup()

    assert app.errors == [("PDIC 备份 恢复准备失败", problem)]
    assert app.batch is None


def test_restore_worker_parse_once_atomic_page_commit_and_done_refresh(monkeypatch, tmp_path) -> None:
    pages = [tmp_path / "001.jpg", tmp_path / "002.jpg"]
    source = tmp_path / "backup.txt"
    app = _RestoreApp(tmp_path, pages)
    _patch_restore_dialogs(monkeypatch, source)

    first = Entry(word="alpha", x=10, y=20, current_page="001")
    mapping = {"001": [first], "002": []}
    stats = {"records": 2, "matched": 1, "unmatched": 1}
    parse_calls: list[tuple] = []
    write_calls: list[tuple] = []
    geometry = object()

    monkeypatch.setattr(
        export_module,
        "read_text_detected",
        lambda path: (parse_calls.append(("read", path)) or ("backup-data", "utf-8")),
    )
    monkeypatch.setattr(
        export_module,
        "parse_merged_pdic_text",
        lambda text, stems: (
            parse_calls.append(("parse", text, tuple(stems))) or (mapping, stats)
        ),
    )
    monkeypatch.setattr(export_module.Image, "open", lambda _page: _Opened())
    monkeypatch.setattr(export_module, "derive_nominal_geometry", lambda w, h, settings: geometry)
    monkeypatch.setattr(export_module, "read_page_sections", lambda page: [page.stem])

    def sort_entries(entries, got_geometry, sections):
        assert got_geometry is geometry
        assert sections in (["001"], ["002"])
        return list(entries)

    monkeypatch.setattr(export_module, "sort_entries_reading_order", sort_entries)
    monkeypatch.setattr(
        export_module,
        "write_pdic_atomic",
        lambda target, entries, width, page_links: write_calls.append(
            (target, list(entries), width, page_links)
        ),
    )

    ExportController(app).restore_from_pdic_backup()

    assert app.calls[:6] == [
        ("selected",),
        ("flush",),
        ("sync",),
        ("save", True, False),
        ("pages_tuple", 0),
        ("pages_tuple", 1),
    ]
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "恢复PDIC"
    assert items == [0, 1]
    assert kwargs["foreground_page_edit"] is False
    assert kwargs["item_label"](1) == "002.jpg"
    assert app.batch_text_var.values == ["恢复PDIC：准备读取备份文件 0/2"]
    assert app.status_var.values == [
        "正在后台解析PDIC 备份 并逐页覆盖重建：共 2 页；进度按页面更新，可暂停或停止。"
    ]

    result0 = worker(0, 1, 2)
    result1 = worker(1, 2, 2)
    assert parse_calls == [
        ("read", source),
        ("parse", "backup-data", ("001", "002")),
    ]
    assert result0 == {
        "index": 0,
        "records": 1,
        "empty": False,
        "source_records": 2,
        "source_matched": 1,
        "source_unmatched": 1,
    }
    assert result1["empty"] is True
    assert len(write_calls) == 2
    assert write_calls[0][0] == pages[0].with_suffix(".pdic")
    assert write_calls[0][1][0] is not first
    assert write_calls[0][1][0].word == "alpha"
    assert write_calls[1][1] == []

    done(2, 2, False, [result0, result1], None)
    assert ("clear_checks", (0, 1), True) in app.calls
    assert ("update_row", 0) in app.calls and ("update_row", 1) in app.calls
    assert ("refresh_overlay",) in app.calls
    assert ("load_page", 0) in app.calls
    assert app.status_var.values[-1] == (
        "PDIC 备份 恢复完成：2/2 页，重建 1 条；空页 1 页；源文件有 1 条记录未对应当前项目页面"
    )


def test_restore_stopped_status_and_error_done_noop(monkeypatch, tmp_path) -> None:
    pages = [tmp_path / "001.jpg"]
    source = tmp_path / "backup.txt"
    app = _RestoreApp(tmp_path, pages)
    _patch_restore_dialogs(monkeypatch, source)
    monkeypatch.setattr(export_module, "read_text_detected", lambda _path: ("x", "utf-8"))
    monkeypatch.setattr(
        export_module,
        "parse_merged_pdic_text",
        lambda _text, _stems: ({"001": []}, {"records": 1, "matched": 1, "unmatched": 0}),
    )
    monkeypatch.setattr(export_module.Image, "open", lambda _page: _Opened())
    monkeypatch.setattr(export_module, "derive_nominal_geometry", lambda *_args: object())
    monkeypatch.setattr(export_module, "read_page_sections", lambda _page: [])
    monkeypatch.setattr(export_module, "sort_entries_reading_order", lambda entries, *_args: entries)
    monkeypatch.setattr(export_module, "write_pdic_atomic", lambda *_args: None)

    ExportController(app).restore_from_pdic_backup()
    _, _, worker, done, _ = app.batch
    result = worker(0, 1, 1)
    done(1, 1, True, [result], None)
    assert app.status_var.values[-1] == (
        "PDIC 备份 恢复已停止：完成 1/1 页，重建 0 条；空页 1 页"
    )
    before = list(app.calls)
    before_status = list(app.status_var.values)
    done(0, 1, False, [], RuntimeError("worker failed"))
    assert app.calls == before
    assert app.status_var.values == before_status


def test_restore_start_false_does_not_publish_running_status(monkeypatch, tmp_path) -> None:
    page = tmp_path / "001.jpg"
    source = tmp_path / "backup.txt"
    app = _RestoreApp(tmp_path, [page])
    app.start_result = False
    _patch_restore_dialogs(monkeypatch, source)

    ExportController(app).restore_from_pdic_backup()

    assert app.batch is not None
    assert app.batch_text_var.values == []
    assert app.status_var.values == []


def test_page_token_resolution_preserves_zero_padding_and_ambiguity() -> None:
    stems = ["0001", "book0002", "scan0003", "other0003"]
    lookup = build_page_lookup(stems)
    assert resolve_page_token("0001", stems, lookup) == "0001"
    assert resolve_page_token("1", stems, lookup) == "0001"
    assert resolve_page_token("2", stems, lookup) == "book0002"
    assert resolve_page_token("3", stems, lookup) is None
    assert resolve_page_token("book0002.jpg", stems, lookup) == "book0002"


def test_parse_merged_pdic_preserves_match_counts_and_page_isolation() -> None:
    text = (
        "alpha#10#20#0#0#001#@#002\n"
        "ignored#30#40#0#0#999#001#@\n"
        "beta#50#60#0#0#002#001#@\n"
    )
    mapping, stats = parse_merged_pdic_text(text, ["001", "002"])
    assert [entry.word for entry in mapping["001"]] == ["alpha"]
    assert [entry.word for entry in mapping["002"]] == ["beta"]
    assert stats == {"records": 3, "matched": 2, "unmatched": 1}


def test_parse_merged_pdic_rejects_empty_malformed_and_no_match() -> None:
    import pytest

    with pytest.raises(ValueError, match="文件为空"):
        parse_merged_pdic_text("\n", ["001"])
    with pytest.raises(ValueError, match="字段不足 8 个"):
        parse_merged_pdic_text("broken#line", ["001"])
    with pytest.raises(ValueError, match="没有任何记录能对应"):
        parse_merged_pdic_text("word#1#2#0#0#999#@#@", ["001"])


def test_write_pdic_atomic_uses_restore_temp_and_replace(monkeypatch, tmp_path) -> None:
    target = tmp_path / "001.pdic"
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def fake_write(path: Path, _entries, _width, _pages) -> None:
        path.write_text("complete", encoding="utf-8")

    def tracked_replace(source, destination) -> None:
        replace_calls.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(restore_module, "write_pdic", fake_write)
    monkeypatch.setattr(restore_module.os, "replace", tracked_replace)
    write_pdic_atomic(target, [], 100, ("001", "@", "@"))

    assert target.read_text(encoding="utf-8") == "complete"
    assert replace_calls == [(tmp_path / ".001.pdic.restore.tmp", target)]
    assert not (tmp_path / ".001.pdic.restore.tmp").exists()


def test_restore_wiring_keeps_app_wrapper_alias_and_ui_binding() -> None:
    root = Path(__file__).parents[1]
    app = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        root / "src/picture_capture/ui/controllers/export.py"
    ).read_text(encoding="utf-8")
    start = app.index("    def restore_from_pdic_backup(self) -> None:")
    end = app.index("    def restore_from_merged_pdic(self) -> None:", start)
    block = app[start:end]
    assert "self._export_controller_for_call().restore_from_pdic_backup()" in block
    assert "filedialog.askopenfilename" not in block
    assert "_start_batch_task" not in block
    assert "    def restore_from_pdic_backup(self) -> None:" in controller
    assert '("恢复PDIC", self.restore_from_pdic_backup)' in app
    assert "self.restore_from_pdic_backup()" in app[end:]
    assert "def _parse_merged_pdic_text(" not in app
    assert "def _write_pdic_atomic(" not in app
    assert "parse_merged_pdic_text as _parse_merged_pdic_text" in app
    assert "write_pdic_atomic as _write_pdic_atomic" in app
'''

APP.write_text(app.rstrip() + "\n", encoding="utf-8")
CONTROLLER.write_text(controller.rstrip() + "\n", encoding="utf-8")
SERVICE.write_text(service.rstrip() + "\n", encoding="utf-8")
EXPORT_TESTS.write_text(export_tests.rstrip() + "\n", encoding="utf-8")
RESTORE_TESTS.write_text(restore_tests.rstrip() + "\n", encoding="utf-8")
