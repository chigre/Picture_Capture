from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import picture_capture.ui.controllers.export as export_module
from picture_capture.ui.controllers.export import ExportController


class _Var:
    def __init__(self, value="current") -> None:
        self.value = value
        self.values: list[str] = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        self.values.append(value)


class _StopEvent:
    def __init__(self) -> None:
        self.value = False

    def is_set(self) -> bool:
        return self.value


class _App:
    def __init__(self, root: Path, pages: list[Path]) -> None:
        self.project = SimpleNamespace(root=root, images=pages)
        self.current_page = pages[0]
        self.image = object()
        self.settings = SimpleNamespace(name="settings")
        self._batch_active = False
        self._batch_stop_event = _StopEvent()
        self._ui_worker_active = []
        self.status_var = _Var("")
        self.page_range_var = _Var("current")
        self.page_range_spec_var = _Var("")
        self.batch = None
        self.ui_worker = None
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []

    def _save_current_page_by_mode(self) -> None:
        self.calls.append(("save-current",))

    def selected_page_indices(self):
        return list(range(len(self.project.images)))

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))

    def _start_batch_task(self, title, items, worker, done, **kwargs):
        self.batch = (title, list(items), worker, done, kwargs)
        return True

    def _start_ui_worker(self, *args, **kwargs):
        self.ui_worker = (args, kwargs)
        return True


def test_training_export_controller_preserves_staging_manifest_zip_and_scope(monkeypatch, tmp_path):
    pages = [tmp_path / "001.jpg", tmp_path / "002.jpg"]
    pages[0].with_suffix(".pdic").write_text("x", encoding="utf-8")
    app = _App(tmp_path, pages)
    dialogs: list[tuple] = []
    calls: list[tuple] = []

    monkeypatch.setattr(export_module, "replace", lambda settings: settings)
    monkeypatch.setattr(export_module, "training_exports_root", lambda root: root / "TrainingExports")
    monkeypatch.setattr(export_module.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(
        export_module, "show_training_export_complete",
        lambda parent, count, path: dialogs.append((parent, count, path)),
    )
    monkeypatch.setattr(
        export_module, "copy_project_context",
        lambda root, staging: calls.append(("context", root, staging)) or ["profile.json"],
    )
    monkeypatch.setattr(
        export_module, "export_training_page",
        lambda page, root, settings, staging, index: {"page": page.name, "index": index},
    )
    monkeypatch.setattr(
        export_module, "write_training_manifest",
        lambda staging, **kwargs: calls.append(("manifest", staging, kwargs)),
    )
    monkeypatch.setattr(
        export_module, "make_training_zip",
        lambda staging, target, *, should_stop: calls.append(("zip", staging, target, should_stop())),
    )

    ExportController(app).export_training_package()

    assert app.calls == [("save-current",)]
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "导出训练标记包"
    assert items[0] == "__prepare__"
    assert items[1] == 0
    assert items[-1] == "__finalize__"
    assert len(items) == 3
    assert kwargs["item_label"](0) == "001.jpg"

    prepared = worker("__prepare__", 1, 3)
    record = worker(0, 2, 3)
    final = worker("__finalize__", 3, 3)

    assert prepared == {"prepared": True}
    assert record == {"page": "001.jpg", "index": 0}
    assert "final_zip" in final
    assert any(row[0] == "context" for row in calls)
    assert any(row[0] == "manifest" for row in calls)
    assert any(row[0] == "zip" for row in calls)

    done(3, 3, False, [prepared, record, final], None)
    assert app.status_var.values[-1].startswith("训练标记包已导出：")
    assert dialogs[-1][0] is app
    assert dialogs[-1][1] == 1
    assert dialogs[-1][2] == Path(final["final_zip"])


def test_training_export_stopped_path_keeps_async_cleanup(monkeypatch, tmp_path):
    page = tmp_path / "001.jpg"
    page.with_suffix(".pdic").write_text("x", encoding="utf-8")
    app = _App(tmp_path, [page])
    monkeypatch.setattr(export_module, "replace", lambda settings: settings)
    monkeypatch.setattr(export_module, "training_exports_root", lambda root: root / "TrainingExports")
    monkeypatch.setattr(export_module.messagebox, "askyesno", lambda *a, **k: True)

    ExportController(app).export_training_package()
    assert app.batch is not None
    done = app.batch[3]
    done(1, 3, True, [], None)

    assert app.status_var.values[-1] == "训练标记包已停止；正在后台清理 staging…"
    assert app.ui_worker is not None
    args, kwargs = app.ui_worker
    assert str(args[0]).startswith("training-cleanup-")
    assert kwargs["wait_on_close"] is True


def test_current_training_export_composition_is_static_before_gui_bootstrap():
    import picture_capture.training_export as base
    import picture_capture.training_export_composed as composed

    assert base.TRAINING_EXPORT_FORMAT == "picture-capture-training-v2"
    assert composed.TRAINING_EXPORT_FORMAT == "picture-capture-training-v3"
    assert composed.export_training_page is not base.export_training_page
    assert composed.write_training_manifest is not base.write_training_manifest
    assert composed.export_training_page.__name__ == "export_training_page_with_understanding"
    assert composed.write_training_manifest.__name__ == "write_training_manifest_v3"
    assert export_module.export_training_page is composed.export_training_page
    assert export_module.write_training_manifest is composed.write_training_manifest


def test_phase5f_training_export_ownership_is_explicit():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")
    bootstrap = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    controller = (root / "src/picture_capture/ui/controllers/export.py").read_text(encoding="utf-8")
    compat = (root / "src/picture_capture/training_export_ui.py").read_text(encoding="utf-8")

    start = app.index("    def export_training_package(")
    end = app.index("\n    def show_help_dialog", start)
    wrapper = app[start:end]
    assert "self._export_controller_for_call().export_training_package()" in wrapper
    assert "copy_project_context" not in wrapper
    assert "make_training_zip" not in wrapper
    assert "PictureCaptureApp.export_training_package =" not in bootstrap
    assert "export_training_package_selected_range" not in bootstrap
    assert "training_export.export_training_page =" not in bootstrap
    assert "training_export.write_training_manifest =" not in bootstrap
    assert "training_export.TRAINING_EXPORT_FORMAT =" not in bootstrap
    assert "from ...training_export_composed import" in controller
    assert "from .training_export import (" not in compat
    assert "    def export_training_package(self) -> None:" in controller
    assert "app._start_batch_task(" in controller
    assert "app._start_ui_worker(" in controller
    assert "def export_training_package_selected_range(self) -> None:" in compat
    assert "_export_controller_for_call().export_training_package()" in compat
