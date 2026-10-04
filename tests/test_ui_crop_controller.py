from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import picture_capture.ui.controllers.crop as crop_module
from picture_capture.ui.controllers.crop import CropController


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class _Entry:
    word: str


@dataclass
class _Settings:
    marker: int = 1


class _StatusVar:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class _App:
    def __init__(self) -> None:
        self._batch_active = False
        self.project = SimpleNamespace(root=Path("/project"))
        self.current_page = Path("/pages/page001.png")
        self.current_index = 2
        self.entries = [_Entry("one"), _Entry("two")]
        self.settings = _Settings(marker=7)
        self.status_var = _StatusVar()
        self.guard_result = True
        self.geometry_result = True
        self.calls: list[tuple] = []
        self.batch: dict[str, object] | None = None

    def guard(self) -> bool:
        self.calls.append(("guard",))
        return self.guard_result

    def _guard_transformed_geometry(self, action: str) -> bool:
        self.calls.append(("guard_geometry", action))
        return self.geometry_result

    def _start_batch_task(self, label, items, worker, done, *, item_label) -> None:
        self.calls.append(("start_batch", label, list(items)))
        self.batch = {
            "label": label,
            "items": list(items),
            "worker": worker,
            "done": done,
            "item_label": item_label,
        }


def test_batch_active_short_circuits_before_guards() -> None:
    app = _App()
    app._batch_active = True

    CropController(app).split_lines_current()

    assert app.calls == []
    assert app.batch is None
    assert app.status_var.values == ["已有批量任务正在运行，请结束后再执行单行切图。"]


def test_guard_and_geometry_short_circuit_in_original_order() -> None:
    app = _App()
    app.guard_result = False

    CropController(app).split_lines_current()

    assert app.calls == [("guard",)]
    assert app.batch is None

    app = _App()
    app.geometry_result = False

    CropController(app).split_lines_current()

    assert app.calls == [("guard",), ("guard_geometry", "单行切图")]
    assert app.batch is None


def test_single_line_action_snapshots_current_page_and_starts_original_batch(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(crop_module, "qt_root", lambda root: Path("/normalized/QT"))

    CropController(app).split_lines_current()

    assert app.calls == [
        ("guard",),
        ("guard_geometry", "单行切图"),
        ("start_batch", "当前页单行切图", [2]),
    ]
    assert app.batch is not None
    assert app.batch["label"] == "当前页单行切图"
    assert app.batch["items"] == [2]
    assert app.batch["item_label"](object()) == "page001.png"


def test_worker_uses_snapshots_logs_records_and_returns_record_count(monkeypatch) -> None:
    app = _App()
    captured: dict[str, object] = {}
    records = [object(), object(), object()]
    monkeypatch.setattr(crop_module, "qt_root", lambda root: Path("/normalized/QT"))

    def fake_split(page, entries, settings, out_dir, *, profile_page_index):
        captured["page"] = page
        captured["entries"] = entries
        captured["settings"] = settings
        captured["out_dir"] = out_dir
        captured["page_index"] = profile_page_index
        return records

    logged: list[tuple[Path, list[object]]] = []
    monkeypatch.setattr(crop_module, "split_single_lines", fake_split)
    monkeypatch.setattr(
        crop_module,
        "append_crop_log",
        lambda root, rows: logged.append((root, list(rows))),
    )

    CropController(app).split_lines_current()
    assert app.batch is not None

    app.entries[0].word = "mutated"
    app.settings.marker = 99
    result = app.batch["worker"](2, 1, 1)

    assert result == 3
    assert captured == {
        "page": Path("/pages/page001.png"),
        "entries": [_Entry("one"), _Entry("two")],
        "settings": _Settings(marker=7),
        "out_dir": Path("/normalized/QT/PSW"),
        "page_index": 2,
    }
    assert captured["entries"] is not app.entries
    assert captured["settings"] is not app.settings
    assert logged == [(Path("/project"), records)]


def test_done_preserves_success_only_status_semantics() -> None:
    app = _App()
    CropController(app).split_lines_current()
    assert app.batch is not None
    done = app.batch["done"]

    done(1, 1, False, [5], None)
    assert app.status_var.values == ["已导出 5 张词条单行图"]

    app.status_var.values.clear()
    done(1, 1, True, [5], None)
    done(1, 1, False, [], None)
    done(1, 1, False, [5], RuntimeError("failed"))
    assert app.status_var.values == []


def test_crop_controller_has_no_reverse_dependency_on_app_module() -> None:
    path = ROOT / "src/picture_capture/ui/controllers/crop.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_crop_controller_wiring_preserves_app_compatibility_method() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controllers = (
        ROOT / "src/picture_capture/ui/controllers/__init__.py"
    ).read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/crop.py"
    ).read_text(encoding="utf-8")

    imports = app[: app.index("class PictureCaptureApp")]
    assert "CropController" in imports
    assert "self.crop_controller = CropController(self)" in app
    assert app.index("self.crop_controller = CropController(self)") < app.index("self._build_ui()")
    assert "def _crop_controller_for_call(" in app
    assert 'self.__dict__.get("crop_controller")' in app
    assert "def split_lines_current(self)" in app
    assert "self._crop_controller_for_call().split_lines_current()" in app
    assert "from .crop import CropController" in controllers
    assert '"CropController"' in controllers
    assert "class CropController" in controller


def test_phase4i_leaves_whole_entry_and_runtime_single_line_paths_untouched() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    runtime = (
        ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
    ).read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/crop.py"
    ).read_text(encoding="utf-8")

    assert "def split_whole_current(self)" in app
    assert "split_whole_current" not in controller
    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" in runtime
    assert "split_lines_current" not in runtime
    assert "split_single_lines_selected_scope" not in controller
