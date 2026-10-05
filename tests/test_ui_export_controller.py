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
    assert "    def export_picdic_index(self) -> None:" not in controller
