from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import picture_capture.ui.controllers.export as export_module
from picture_capture.ui.controllers.export import ExportController


ROOT = Path(__file__).resolve().parents[1]


class _StatusVar:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class _App:
    def __init__(self) -> None:
        self.project = SimpleNamespace(root=Path("/project"))
        self.current_page = SimpleNamespace(stem="page001")
        self.entries = [object(), object()]
        self.ordered = [SimpleNamespace(word="second"), SimpleNamespace(word="first")]
        self.status_var = _StatusVar()
        self.guard_result = True
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []

    def guard(self) -> bool:
        self.calls.append(("guard",))
        return self.guard_result

    def _ordered_entries_reading_order(self):
        self.calls.append(("ordered",))
        return self.ordered

    def redraw(self) -> None:
        self.calls.append(("redraw",))

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))


def test_export_text_preserves_guard_path_reading_order_and_status(monkeypatch) -> None:
    app = _App()
    captured: list[tuple[Path, list[str]]] = []
    monkeypatch.setattr(export_module, "qt_root", lambda root: Path("/normalized/QT"))
    monkeypatch.setattr(
        export_module,
        "export_ocred",
        lambda path, texts: captured.append((path, list(texts))),
    )

    ExportController(app).export_text()

    assert captured == [(Path("/normalized/QT/page001.OCRed"), ["second", "first"])]
    assert app.calls == [("guard",), ("ordered",)]
    assert app.status_var.values == ["当前文本已导出"]


def test_export_text_guard_false_is_noop(monkeypatch) -> None:
    app = _App()
    app.guard_result = False
    monkeypatch.setattr(
        export_module,
        "export_ocred",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not export")),
    )

    ExportController(app).export_text()

    assert app.calls == [("guard",)]
    assert app.status_var.values == []


def test_import_text_preserves_path_order_assignment_redraw_and_status(monkeypatch) -> None:
    app = _App()
    paths: list[Path] = []
    monkeypatch.setattr(export_module, "qt_root", lambda root: Path("/normalized/QT"))

    def fake_import(path: Path) -> list[str]:
        paths.append(path)
        return ["uno", "dos"]

    monkeypatch.setattr(export_module, "import_ocred", fake_import)

    ExportController(app).import_text()

    assert paths == [Path("/normalized/QT/page001.OCRed")]
    assert [entry.word for entry in app.ordered] == ["uno", "dos"]
    assert app.calls == [("guard",), ("ordered",), ("redraw",)]
    assert app.status_var.values == ["当前文本已导入"]
    assert app.errors == []


def test_import_text_count_mismatch_uses_existing_error_contract(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(export_module, "qt_root", lambda root: Path("/normalized/QT"))
    monkeypatch.setattr(export_module, "import_ocred", lambda _path: ["only-one"])

    ExportController(app).import_text()

    assert app.calls == [("guard",)]
    assert app.status_var.values == []
    assert len(app.errors) == 1
    title, exc = app.errors[0]
    assert title == "导入失败"
    assert isinstance(exc, ValueError)
    assert str(exc) == "文本 1 行，画线 2 条，数量不一致"


def test_import_text_reader_failure_is_forwarded_without_redraw(monkeypatch) -> None:
    app = _App()
    problem = OSError("cannot read")
    monkeypatch.setattr(export_module, "qt_root", lambda root: Path("/normalized/QT"))
    monkeypatch.setattr(export_module, "import_ocred", lambda _path: (_ for _ in ()).throw(problem))

    ExportController(app).import_text()

    assert app.calls == [("guard",)]
    assert app.errors == [("导入失败", problem)]
    assert app.status_var.values == []


def test_export_controller_has_no_reverse_dependency_on_app_module() -> None:
    path = ROOT / "src/picture_capture/ui/controllers/export.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_export_controller_wiring_preserves_app_compatibility_methods() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controllers = (
        ROOT / "src/picture_capture/ui/controllers/__init__.py"
    ).read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/export.py"
    ).read_text(encoding="utf-8")

    imports = app[: app.index("class PictureCaptureApp")]
    assert "ExportController" in imports
    assert "self.export_controller = ExportController(self)" in app
    assert app.index("self.export_controller = ExportController(self)") < app.index("self._build_ui()")
    assert "def _export_controller_for_call(" in app
    assert 'self.__dict__.get("export_controller")' in app
    assert "def export_text(self)" in app
    assert "self._export_controller_for_call().export_text()" in app
    assert "def import_text(self)" in app
    assert "self._export_controller_for_call().import_text()" in app
    assert "from .export import ExportController" in controllers
    assert '"ExportController"' in controllers
    assert "class ExportController" in controller


class _StopEvent:
    def __init__(self) -> None:
        self.value = False
        self.queries = 0

    def is_set(self) -> bool:
        self.queries += 1
        return self.value


class _PicDicApp:
    def __init__(self) -> None:
        self.project = SimpleNamespace(root=Path("/project"))
        self.settings = SimpleNamespace(ocr_language="ita")
        self.status_var = _StatusVar()
        self._batch_active = False
        self._batch_stop_event = _StopEvent()
        self.guard_result = True
        self.save_error: Exception | None = None
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []
        self.batch = None

    def guard(self) -> bool:
        self.calls.append(("guard",))
        return self.guard_result

    def save_pdic(self, silent: bool = False) -> None:
        self.calls.append(("save_pdic", silent))
        if self.save_error is not None:
            raise self.save_error

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))

    def _start_batch_task(self, title, items, worker, done, **kwargs):
        self.calls.append(("start_batch", title, list(items), kwargs))
        self.batch = (title, list(items), worker, done, kwargs)
        return True


def test_build_picdic_guard_false_is_noop(monkeypatch) -> None:
    app = _PicDicApp()
    app.guard_result = False
    monkeypatch.setattr(
        export_module,
        "build_picdic_package",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not build")),
    )

    ExportController(app).build_picdic()

    assert app.calls == [("guard",)]
    assert app.status_var.values == []
    assert app.batch is None


def test_build_picdic_batch_active_preserves_exact_status_and_skips_save() -> None:
    app = _PicDicApp()
    app._batch_active = True

    ExportController(app).build_picdic()

    assert app.calls == [("guard",)]
    assert app.status_var.values == ["已有批量任务正在运行，请结束后再制作 PicDic。"]
    assert app.batch is None


def test_build_picdic_prepare_failure_uses_existing_error_contract() -> None:
    app = _PicDicApp()
    problem = OSError("cannot save")
    app.save_error = problem

    ExportController(app).build_picdic()

    assert app.calls == [("guard",), ("save_pdic", True)]
    assert app.errors == [("PicDic 制作准备失败", problem)]
    assert app.batch is None


def test_build_picdic_preserves_worker_batch_and_completion_contract(monkeypatch) -> None:
    app = _PicDicApp()
    built: list[tuple] = []
    dialogs: list[tuple] = []
    dsl = Path("/project/QT/PicDic/book.dsl")
    archive = Path("/project/QT/PicDic/book.dsl.files.zip")

    def fake_build(root, language, *, should_stop):
        built.append((root, language, should_stop))
        assert should_stop() is False
        return dsl, archive, 7, 9

    monkeypatch.setattr(export_module, "build_picdic_package", fake_build)
    monkeypatch.setattr(
        export_module.messagebox,
        "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).build_picdic()

    assert app.calls[0:2] == [("guard",), ("save_pdic", True)]
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "PicDic 制作"
    assert items == [Path("/project")]
    assert kwargs["item_label"](Path("/project")) == "生成 DSL 与图片包"
    assert kwargs["refresh_page_quality"] is False
    result = worker(Path("/project"), 1, 1)
    assert result == (dsl, archive, 7, 9)
    assert built[0][0:2] == (Path("/project"), "ita")
    assert app._batch_stop_event.queries == 1

    done(1, 1, False, [result], None)

    assert app.status_var.values == ["PicDic 制作完成：7 个词头，9 张图片"]
    assert dialogs == [(
        "PicDic 制作完成",
        f"词头：7\n图片：9\n\nDSL：book.dsl\n图片包：book.dsl.files.zip\n目录：{dsl.parent}",
        app,
    )]


def test_build_picdic_worker_keeps_cooperative_cancellation(monkeypatch) -> None:
    app = _PicDicApp()

    def cancel(*_args, **_kwargs):
        raise export_module.PicDicBuildCancelled()

    monkeypatch.setattr(export_module, "build_picdic_package", cancel)
    ExportController(app).build_picdic()
    assert app.batch is not None
    worker = app.batch[2]
    assert worker(Path("/project"), 1, 1) is None


def test_build_picdic_done_ignores_error_stop_and_empty_results(monkeypatch) -> None:
    app = _PicDicApp()
    dialogs: list[tuple] = []
    monkeypatch.setattr(
        export_module.messagebox,
        "showinfo",
        lambda *args, **kwargs: dialogs.append((args, kwargs)),
    )
    ExportController(app).build_picdic()
    assert app.batch is not None
    done = app.batch[3]

    done(0, 1, False, [], RuntimeError("failed"))
    done(0, 1, True, [(Path("a"), Path("b"), 1, 1)], None)
    done(0, 1, False, [], None)

    assert app.status_var.values == []
    assert dialogs == []


def test_build_picdic_wiring_moves_only_action_orchestration_to_export_controller() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/export.py"
    ).read_text(encoding="utf-8")
    imports = app[: app.index("class PictureCaptureApp")]

    start = app.index("    def build_picdic(self) -> None:")
    end = app.index("    def _order_key(", start)
    block = app[start:end]
    assert "self._export_controller_for_call().build_picdic()" in block
    assert "build_picdic_package" not in block
    assert "PicDicBuildCancelled" not in block
    assert "from .picdic import PicDicBuildCancelled, build_picdic_package" not in imports
    assert "from ...picdic import PicDicBuildCancelled, build_picdic_package" in controller
    assert "    def build_picdic(self) -> None:" in controller
    assert '("PicDic制作", self.build_picdic)' in app
    assert "    def export_picdic_index(self) -> None:" in app
    assert "    def export_picdic_index(self) -> None:" in controller

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
    assert "from ...formats import pdic_path, read_pdic, read_picdic_index_records" in controller
    assert "from ...project_storage import exports_root, qt_root" in controller
    assert "    def export_picdic_index(self) -> None:" in controller
    assert "os.replace(temp, target)" in controller
    assert '("导出PicDic索引", self.export_picdic_index)' in app


def _prepare_backup_files(tmp_path: Path, names=("001.jpg", "002.jpg")):
    pages = [tmp_path / name for name in names]
    for page in pages:
        page.with_suffix(".pdic").write_text("placeholder", encoding="utf-8")
    return pages


def test_backup_pdic_missing_project_contract(monkeypatch, tmp_path) -> None:
    app = _IndexApp(tmp_path, [])
    app.project = None
    dialogs: list[tuple] = []
    monkeypatch.setattr(
        export_module.messagebox, "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).backup_pdic()

    assert dialogs == [("尚未打开", "请先打开包含扫描图片的项目目录。", app)]
    assert app.calls == []
    assert app.batch is None


def test_backup_pdic_batch_active_preserves_exact_status(tmp_path) -> None:
    pages = _prepare_backup_files(tmp_path, ("001.jpg",))
    app = _IndexApp(tmp_path, pages)
    app._batch_active = True

    ExportController(app).backup_pdic()

    assert app.status_var.values == ["已有批量任务正在运行，请结束后再备份PDIC。"]
    assert app.calls == []
    assert app.batch is None


def test_backup_pdic_prepare_failure_preserves_error_contract(tmp_path) -> None:
    pages = _prepare_backup_files(tmp_path, ("001.jpg",))
    app = _IndexApp(tmp_path, pages)
    problem = OSError("save failed")
    app.save_error = problem

    ExportController(app).backup_pdic()

    assert app.calls == [("flush",), ("sync",), ("save_pdic", True, False)]
    assert app.errors == [("备份PDIC失败", problem)]
    assert app.batch is None


def test_backup_pdic_no_saved_pdic_shows_existing_info(monkeypatch, tmp_path) -> None:
    pages = [tmp_path / "001.jpg"]
    app = _IndexApp(tmp_path, pages)
    dialogs: list[tuple] = []
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(
        export_module.messagebox, "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).backup_pdic()

    assert app.calls == [("flush",), ("sync",), ("save_pdic", True, False)]
    assert dialogs == [("备份PDIC", "当前项目没有可备份的 PDIC 文件。", app)]
    assert app.batch is None


def test_backup_pdic_streams_filters_blank_lines_and_atomically_publishes(monkeypatch, tmp_path) -> None:
    pages = _prepare_backup_files(tmp_path)
    pages[0].with_suffix(".pdic").write_text("\ufeffuno\n\n due \n", encoding="utf-8")
    pages[1].with_suffix(".pdic").write_text("\n\ntre\n", encoding="utf-8")
    app = _IndexApp(tmp_path, pages)
    output = tmp_path / "output"
    output.mkdir()
    dialogs: list[tuple] = []
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module, "exports_root", lambda _root: output)
    monkeypatch.setattr(
        export_module.messagebox, "showinfo",
        lambda title, message, *, parent: dialogs.append((title, message, parent)),
    )

    ExportController(app).backup_pdic()

    assert app.calls[:3] == [("flush",), ("sync",), ("save_pdic", True, False)]
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "备份PDIC"
    assert items == pages
    assert kwargs["item_label"](pages[0]) == "001.jpg"
    assert kwargs["refresh_page_quality"] is False
    assert list(output.iterdir()) == []

    assert worker(pages[0], 1, 2) == 2
    assert worker(pages[1], 2, 2) == 1
    temps = list(output.glob(".all_pdic_backup_*.txt.tmp"))
    assert len(temps) == 1
    done(2, 2, False, [2, 1], None)

    assert not list(output.glob(".*.tmp"))
    targets = list(output.glob("all_pdic_backup_*.txt"))
    assert len(targets) == 1
    assert targets[0].read_text(encoding="utf-8") == "uno\n due \ntre\n"
    assert app.status_var.values == [
        f"PDIC备份完成：{targets[0].name}｜2 页｜3 条"
    ]
    assert dialogs == [(
        "备份PDIC",
        f"已生成：\n{targets[0]}\n\n包含 2 个有记录页面，共 3 条 PDIC。",
        app,
    )]


def test_backup_pdic_stop_removes_temp_and_never_publishes_partial_output(monkeypatch, tmp_path) -> None:
    pages = _prepare_backup_files(tmp_path, ("001.jpg",))
    pages[0].with_suffix(".pdic").write_text("word\n", encoding="utf-8")
    app = _IndexApp(tmp_path, pages)
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module, "exports_root", lambda _root: output)

    ExportController(app).backup_pdic()
    assert app.batch is not None
    _, _, worker, done, _ = app.batch
    assert worker(pages[0], 1, 1) == 1
    assert list(output.glob(".all_pdic_backup_*.txt.tmp"))

    done(1, 1, True, [1], None)

    assert not list(output.glob(".*.tmp"))
    assert not list(output.glob("all_pdic_backup_*.txt"))
    assert app.status_var.values == [
        "PDIC备份已停止：完成 1/1 页，未生成不完整备份。"
    ]


def test_backup_pdic_error_removes_temp_without_success_status(monkeypatch, tmp_path) -> None:
    pages = _prepare_backup_files(tmp_path, ("001.jpg",))
    pages[0].with_suffix(".pdic").write_text("word\n", encoding="utf-8")
    app = _IndexApp(tmp_path, pages)
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(export_module, "pdic_path", lambda page: page.with_suffix(".pdic"))
    monkeypatch.setattr(export_module, "exports_root", lambda _root: output)

    ExportController(app).backup_pdic()
    assert app.batch is not None
    _, _, worker, done, _ = app.batch
    assert worker(pages[0], 1, 1) == 1

    done(0, 1, False, [], RuntimeError("failed"))

    assert not list(output.glob(".*.tmp"))
    assert not list(output.glob("all_pdic_backup_*.txt"))
    assert app.status_var.values == []


def test_export_controller_wiring_owns_backup_and_restore_after_phase4s() -> None:
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
