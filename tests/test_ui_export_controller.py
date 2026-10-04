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
