"""Round 78: an old OCR batch must never reload the newly opened project."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.models import AppSettings
from picture_capture.ui.batch_ocr_completion import complete_existing_pdic_batch
from picture_capture.ui.batch_ocr_flow import run_existing_pdic_batch


class Status:
    def __init__(self, value="unchanged"):
        self.value = value

    def set(self, value):
        self.value = value


class App:
    def __init__(self, root: Path):
        self.project = SimpleNamespace(root=root, images=[root / "first.png"])
        self.settings = AppSettings()
        self.status_var = Status()
        self.current_index = 0
        self._batch_active = False
        self._batch_foreground_pages = False
        self.calls = []
        self.batch = None

    def _guard_transformed_geometry(self, name):
        self.calls.append(("geometry", name))
        return True

    def _sync_entry_editor_texts(self):
        self.calls.append(("editor-sync",))

    def save_pdic(self, **kwargs):
        self.calls.append(("save", kwargs))

    def pages_tuple(self, index):
        return (str(index), "@", "@")

    def _start_batch_task(self, name, indices, worker, done, **kwargs):
        self.calls.append(("schedule", name, indices, kwargs))
        self.batch = (worker, done)

    def load_page(self, index, *, skip_current_save):
        self.calls.append(("reload", index, skip_current_save))


@pytest.mark.parametrize("foreground", [False, True])
@pytest.mark.parametrize("stopped", [False, True])
def test_stale_batch_completion_does_not_reopen_or_update_new_project(
    tmp_path, foreground, stopped,
):
    app = App(tmp_path)
    original = app.project
    app.project = SimpleNamespace(
        root=tmp_path / "new", images=[tmp_path / "new" / "first.png"],
    )
    app._batch_foreground_pages = foreground
    complete_existing_pdic_batch(
        app, project=original, completed=1, total_pages=2,
        stopped=stopped, results=[2], error=None,
    )
    assert not any(call[0] == "reload" for call in app.calls)
    assert app.status_var.value == "unchanged"


def test_stale_batch_failure_never_mutates_current_project(tmp_path):
    app = App(tmp_path)
    original = app.project
    app.project = SimpleNamespace(root=tmp_path / "other")
    complete_existing_pdic_batch(
        app, project=original, completed=0, total_pages=1,
        stopped=False, results=[], error=RuntimeError("OCR failed"),
    )
    assert app.calls == []
    assert app.status_var.value == "unchanged"


@pytest.mark.parametrize(
    ("foreground", "stopped", "expected"),
    [
        (False, False, "批量 OCR 完成：5 个词条"),
        (True, False, "批量 OCR 完成：5 个词条"),
        (False, True, "批量 OCR 已停止：完成 1/2 页，共 5 个词条"),
        (True, True, "批量 OCR 已停止：完成 1/2 页，共 5 个词条"),
    ],
)
def test_current_project_completion_preserves_foreground_and_status(
    tmp_path, foreground, stopped, expected,
):
    app = App(tmp_path)
    app._batch_foreground_pages = foreground
    complete_existing_pdic_batch(
        app, project=app.project, completed=1, total_pages=2,
        stopped=stopped, results=[2, None, 3], error=None,
    )
    assert app.status_var.value == expected
    reloads = [call for call in app.calls if call[0] == "reload"]
    assert reloads == ([] if foreground else [("reload", 0, True)])


def test_project_switch_during_confirmation_cannot_save_new_editor(tmp_path):
    app = App(tmp_path)
    original = app.project

    def switch_project(_title, _message, *, parent):
        assert parent is app
        app.project = SimpleNamespace(
            root=tmp_path / "new", images=[tmp_path / "new" / "first.png"],
        )
        return True

    def dependencies():
        return {
            "read_pdic": lambda _path: ["entry"],
            "pdic_path": lambda page: page.with_suffix(".PDIC"),
            "messagebox": SimpleNamespace(askyesno=switch_project),
        }

    run_existing_pdic_batch(app, dependencies=dependencies)
    assert app.project is not original
    assert app.calls == [("geometry", "批量 OCR")]
    assert app.batch is None
    assert app.status_var.value == "unchanged"


def test_batch_workflow_has_project_identity_checks_at_both_ui_boundaries():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture/ui"
    flow = (root / "batch_ocr_flow.py").read_text(encoding="utf-8")
    completion = (root / "batch_ocr_completion.py").read_text(encoding="utf-8")
    assert "if app.project is not project:" in flow
    assert "if error is not None or app.project is not project:" in completion
    assert "return complete_existing_pdic_batch(" in flow
    assert "foreground_page_edit=True, allow_pdic_edits=True," in flow
