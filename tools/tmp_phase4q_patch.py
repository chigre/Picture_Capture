from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/picture_capture/app.py"
CONTROLLER = ROOT / "src/picture_capture/ui/controllers/export.py"
TESTS = ROOT / "tests/test_ui_export_controller.py"

app = APP.read_text(encoding="utf-8")
controller = CONTROLLER.read_text(encoding="utf-8")
tests = TESTS.read_text(encoding="utf-8")

method_start = "    def export_picdic_index(self) -> None:\n"
next_method = "    def backup_pdic(self) -> None:\n"
assert app.count(method_start) == 1
start = app.index(method_start)
end = app.index(next_method, start)
old_block = app[start:end]
for required in (
    'self.status_var.set("已有批量任务正在运行，请结束后再导出PicDic索引。")',
    'self._flush_deferred_page_save()',
    'self._sync_entry_editor_texts()',
    'self.save_pdic(silent=True, sync_editors=False)',
    'read_picdic_index_records(pdic_path(page), fallback_page=page.stem)',
    'os.replace(temp, target)',
    'self._start_batch_task(',
    'refresh_page_quality=False',
):
    assert required in old_block, required
assert app.count("read_picdic_index_records") == 2

wrapper = (
    "    def export_picdic_index(self) -> None:\n"
    "        self._export_controller_for_call().export_picdic_index()\n\n"
)
app = app[:start] + wrapper + app[end:]
old_formats_import = (
    "from .formats import pdic_path, read_pdic, read_ppp, write_pdic, write_ppp, "
    "write_text_atomic, read_picdic_index_records\n"
)
new_formats_import = (
    "from .formats import pdic_path, read_pdic, read_ppp, write_pdic, write_ppp, "
    "write_text_atomic\n"
)
assert old_formats_import in app
app = app.replace(old_formats_import, new_formats_import, 1)
assert "read_picdic_index_records" not in app

assert "    def export_picdic_index(self) -> None:" not in controller
controller = controller.replace(
    '"""User-action orchestration for text import/export and PicDic package builds.\n',
    '"""User-action orchestration for text import/export and PicDic outputs.\n',
    1,
)
old_stdlib = "from tkinter import messagebox\nfrom typing import Any\n"
new_stdlib = (
    "import os\n"
    "from datetime import datetime\n"
    "from pathlib import Path\n"
    "from tkinter import messagebox\n"
    "from typing import Any\n"
)
assert old_stdlib in controller
controller = controller.replace(old_stdlib, new_stdlib, 1)
old_local = (
    "from ...picdic import PicDicBuildCancelled, build_picdic_package\n"
    "from ...processing import export_ocred, import_ocred\n"
    "from ...project_storage import qt_root\n"
)
new_local = (
    "from ...formats import pdic_path, read_picdic_index_records\n"
    "from ...picdic import PicDicBuildCancelled, build_picdic_package\n"
    "from ...processing import export_ocred, import_ocred\n"
    "from ...project_storage import exports_root, qt_root\n"
)
assert old_local in controller
controller = controller.replace(old_local, new_local, 1)

index_method = r'''

    def export_picdic_index(self) -> None:
        """Export a project-wide four-column text index from saved PDIC records.

        The persisted PDIC coordinates are passed through unchanged. Large
        projects are streamed through a temporary file and atomically published
        only after the batch finishes successfully.
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
'''
controller = controller.rstrip() + index_method + "\n"

old_phase4p_assertions = (
    '    assert "    def export_picdic_index(self) -> None:" in app\n'
    '    assert "    def export_picdic_index(self) -> None:" not in controller\n'
)
new_phase4q_assertions = (
    '    assert "    def export_picdic_index(self) -> None:" in app\n'
    '    assert "    def export_picdic_index(self) -> None:" in controller\n'
)
assert old_phase4p_assertions in tests
tests = tests.replace(old_phase4p_assertions, new_phase4q_assertions, 1)

extra_tests = r'''

class _IndexApp:
    def __init__(self, root: Path, pages: list[Path]) -> None:
        self.project = SimpleNamespace(root=root, images=pages)
        self.current_page = pages[0] if pages else Path("page001.jpg")
        self.image = object()
        self._batch_active = False
        self.status_var = _StatusVar()
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []
        self.save_error: Exception | None = None
        self.batch = None

    def _flush_deferred_page_save(self) -> None:
        self.calls.append(("flush",))

    def _sync_entry_editor_texts(self) -> None:
        self.calls.append(("sync",))

    def save_pdic(self, silent: bool = False, sync_editors: bool = True) -> None:
        self.calls.append(("save_pdic", silent, sync_editors))
        if self.save_error is not None:
            raise self.save_error

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))

    def _start_batch_task(self, title, items, worker, done, **kwargs):
        self.calls.append(("start_batch", title, list(items), kwargs))
        self.batch = (title, list(items), worker, done, kwargs)
        return True


def _prepare_index_files(tmp_path: Path, names=("001.jpg", "002.jpg")):
    pages = [tmp_path / name for name in names]
    for page in pages:
        page.with_suffix(".pdic").write_text("placeholder", encoding="utf-8")
    return pages


def test_export_picdic_index_missing_project_contract(monkeypatch, tmp_path) -> None:
    app = _IndexApp(tmp_path, [])
    app.project = None
    dialogs: list[tuple] = []
    monkeypatch.setattr(
        export_module.messagebox, "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).export_picdic_index()

    assert dialogs == [("尚未打开", "请先打开包含扫描图片的项目目录。", app)]
    assert app.calls == []
    assert app.batch is None


def test_export_picdic_index_batch_active_preserves_exact_status(tmp_path) -> None:
    pages = _prepare_index_files(tmp_path, ("001.jpg",))
    app = _IndexApp(tmp_path, pages)
    app._batch_active = True

    ExportController(app).export_picdic_index()

    assert app.status_var.values == ["已有批量任务正在运行，请结束后再导出PicDic索引。"]
    assert app.calls == []
    assert app.batch is None


def test_export_picdic_index_prepare_failure_preserves_error_contract(tmp_path) -> None:
    pages = _prepare_index_files(tmp_path, ("001.jpg",))
    app = _IndexApp(tmp_path, pages)
    problem = OSError("save failed")
    app.save_error = problem

    ExportController(app).export_picdic_index()

    assert app.calls == [("flush",), ("sync",), ("save_pdic", True, False)]
    assert app.errors == [("导出PicDic索引失败", problem)]
    assert app.batch is None


def test_export_picdic_index_no_saved_pdic_shows_existing_info(monkeypatch, tmp_path) -> None:
    pages = [tmp_path / "001.jpg"]
    app = _IndexApp(tmp_path, pages)
    dialogs: list[tuple] = []
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(
        export_module.messagebox, "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).export_picdic_index()

    assert app.calls == [("flush",), ("sync",), ("save_pdic", True, False)]
    assert dialogs == [("导出PicDic索引", "当前项目没有可导出的 PDIC 文件。", app)]
    assert app.batch is None


def test_export_picdic_index_streams_and_atomically_publishes(monkeypatch, tmp_path) -> None:
    pages = _prepare_index_files(tmp_path)
    app = _IndexApp(tmp_path, pages)
    output = tmp_path / "output"
    output.mkdir()
    dialogs: list[tuple] = []
    records_by_stem = {
        "001": ["uno\t10.00\t20.00\t001", "due\t11.00\t21.00\t001"],
        "002": [],
    }
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module, "exports_root", lambda _root: output)
    monkeypatch.setattr(
        export_module, "read_picdic_index_records",
        lambda path, fallback_page="": list(records_by_stem[path.stem]),
    )
    monkeypatch.setattr(
        export_module.messagebox, "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).export_picdic_index()

    assert app.calls[:3] == [("flush",), ("sync",), ("save_pdic", True, False)]
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "导出PicDic索引"
    assert items == pages
    assert kwargs["item_label"](pages[0]) == "001.jpg"
    assert kwargs["refresh_page_quality"] is False
    assert list(output.iterdir()) == []

    assert worker(pages[0], 1, 2) == 2
    assert worker(pages[1], 2, 2) == 0
    temps = list(output.glob(".PicDic_index_*.txt.tmp"))
    assert len(temps) == 1
    done(2, 2, False, [2, 0], None)

    assert not list(output.glob(".*.tmp"))
    targets = list(output.glob("PicDic_index_*.txt"))
    assert len(targets) == 1
    assert targets[0].read_text(encoding="utf-8") == (
        "uno\t10.00\t20.00\t001\n"
        "due\t11.00\t21.00\t001\n"
    )
    assert app.status_var.values == [
        f"PicDic索引导出完成：{targets[0].name}｜1 页｜2 条"
    ]
    assert dialogs == [(
        "导出PicDic索引",
        f"已生成：\n{targets[0]}\n\n共 1 个有记录页面，2 条索引。\n"
        "格式：WORD\\txx.xx%\\tyy.yy%\\tpage",
        app,
    )]


def test_export_picdic_index_stop_removes_temp_and_keeps_no_partial_output(monkeypatch, tmp_path) -> None:
    pages = _prepare_index_files(tmp_path)
    app = _IndexApp(tmp_path, pages)
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module, "exports_root", lambda _root: output)
    monkeypatch.setattr(
        export_module, "read_picdic_index_records",
        lambda _path, fallback_page="": [f"word\t1.00\t2.00\t{fallback_page}"],
    )

    ExportController(app).export_picdic_index()
    assert app.batch is not None
    worker, done = app.batch[2], app.batch[3]
    assert worker(pages[0], 1, 2) == 1
    done(1, 2, True, [1], None)

    assert list(output.iterdir()) == []
    assert app.status_var.values == [
        "PicDic索引导出已停止：完成 1/2 页，未生成不完整索引。"
    ]
    assert app.errors == []


def test_export_picdic_index_error_removes_temp_without_completion_status(monkeypatch, tmp_path) -> None:
    pages = _prepare_index_files(tmp_path, ("001.jpg",))
    app = _IndexApp(tmp_path, pages)
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module, "exports_root", lambda _root: output)
    monkeypatch.setattr(
        export_module, "read_picdic_index_records",
        lambda _path, fallback_page="": ["word\t1.00\t2.00\t001"],
    )

    ExportController(app).export_picdic_index()
    assert app.batch is not None
    worker, done = app.batch[2], app.batch[3]
    worker(pages[0], 1, 1)
    done(0, 1, False, [], RuntimeError("worker failed"))

    assert list(output.iterdir()) == []
    assert app.status_var.values == []
    assert app.errors == []


def test_export_picdic_index_publish_failure_cleans_temp_and_reports(monkeypatch, tmp_path) -> None:
    pages = _prepare_index_files(tmp_path, ("001.jpg",))
    app = _IndexApp(tmp_path, pages)
    output = tmp_path / "output"
    output.mkdir()
    problem = OSError("replace failed")
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module, "exports_root", lambda _root: output)
    monkeypatch.setattr(
        export_module, "read_picdic_index_records",
        lambda _path, fallback_page="": ["word\t1.00\t2.00\t001"],
    )
    monkeypatch.setattr(export_module.os, "replace", lambda *_args: (_ for _ in ()).throw(problem))

    ExportController(app).export_picdic_index()
    assert app.batch is not None
    worker, done = app.batch[2], app.batch[3]
    worker(pages[0], 1, 1)
    done(1, 1, False, [1], None)

    assert list(output.iterdir()) == []
    assert app.status_var.values == []
    assert app.errors == [("导出PicDic索引失败", problem)]


def test_export_picdic_index_wiring_keeps_app_wrapper_and_format_boundaries() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/export.py"
    ).read_text(encoding="utf-8")
    imports = app[: app.index("class PictureCaptureApp")]

    start = app.index("    def export_picdic_index(self) -> None:")
    end = app.index("    def backup_pdic(self) -> None:", start)
    block = app[start:end]
    assert "self._export_controller_for_call().export_picdic_index()" in block
    assert "_start_batch_task" not in block
    assert "read_picdic_index_records" not in block
    assert "read_picdic_index_records" not in imports
    assert "from ...formats import pdic_path, read_picdic_index_records" in controller
    assert "from ...project_storage import exports_root, qt_root" in controller
    assert "    def export_picdic_index(self) -> None:" in controller
    assert "os.replace(temp, target)" in controller
    assert '("导出PicDic索引", self.export_picdic_index)' in app
'''

assert "class _IndexApp:" not in tests
tests = tests.rstrip() + extra_tests + "\n"

APP.write_text(app, encoding="utf-8")
CONTROLLER.write_text(controller, encoding="utf-8")
TESTS.write_text(tests, encoding="utf-8")
