from __future__ import annotations

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
