"""R4.2: a live ReviewWindow owns the project session until it closes."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from picture_capture import app as gui
from picture_capture.ui import project_session_workflow as workflow


class _Var:
    def __init__(self):
        self.value = ""
        self.writes = []

    def set(self, value):
        self.value = value
        self.writes.append(value)


def test_project_switch_is_refused_while_review_window_is_alive(tmp_path):
    calls = []
    old_root = tmp_path / "old-project"
    new_root = tmp_path / "new-project"
    app = SimpleNamespace(
        _batch_active=False,
        _ui_worker_key_active=lambda _key: False,
        _preprocess_mode_active=lambda: False,
        project=SimpleNamespace(root=old_root),
        current_page=None,
        status_var=_Var(),
        review_window=SimpleNamespace(winfo_exists=lambda: 1),
        _flush_deferred_page_save=lambda: calls.append("flush"),
        canvas=SimpleNamespace(winfo_width=lambda: 700),
        appearance_mode="light",
        _start_ui_worker=lambda *args, **kwargs: calls.append(("worker", args, kwargs)),
    )
    deps = replace(
        gui._project_session_deps(),
        has_legacy_project_data=lambda _root: False,
        is_managed_project=lambda _root: True,
    )

    workflow._load_project(app, deps, new_root)

    assert calls == [], (
        "project loading started while a live ReviewWindow still owned the old session"
    )
    assert "关闭" in app.status_var.value
    assert "校对" in app.status_var.value


def test_same_project_reopen_remains_noop_with_live_review_window(tmp_path):
    calls = []
    app = SimpleNamespace(
        _batch_active=False,
        _ui_worker_key_active=lambda _key: False,
        _preprocess_mode_active=lambda: False,
        project=SimpleNamespace(root=tmp_path),
        current_page=None,
        status_var=_Var(),
        review_window=SimpleNamespace(winfo_exists=lambda: 1),
        _flush_deferred_page_save=lambda: calls.append("flush"),
        canvas=SimpleNamespace(winfo_width=lambda: 700),
        appearance_mode="light",
        _start_ui_worker=lambda *args, **kwargs: calls.append(("worker", args, kwargs)),
    )
    deps = replace(
        gui._project_session_deps(),
        has_legacy_project_data=lambda _root: False,
        is_managed_project=lambda _root: True,
    )

    workflow._load_project(app, deps, tmp_path)

    assert calls == []
    assert "已经打开" in app.status_var.value
