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


def test_open_review_is_refused_while_project_load_worker_is_active():
    from picture_capture.ui import main_dialog_lifecycle

    calls = []
    settings = SimpleNamespace(
        review_main_show_ocr_choices=True,
        review_main_show_ocr_background=True,
    )
    app = SimpleNamespace(
        _ui_worker_key_active=lambda key: key == "project-load",
        status_var=_Var(),
        guard=lambda: True,
        entries=[object()],
        review_window=None,
        _sync_entry_editor_texts=lambda: calls.append("sync"),
        settings=settings,
        quick_bool_vars={},
        redraw=lambda: calls.append("redraw"),
    )

    def make_review(_parent):
        calls.append("construct")
        return object()

    main_dialog_lifecycle.open_review(
        app,
        deps={"tk": SimpleNamespace(TclError=RuntimeError), "ReviewWindow": make_review},
    )

    assert calls == [], (
        "ReviewWindow opened while project-load was already in flight"
    )
    assert settings.review_main_show_ocr_choices is True
    assert settings.review_main_show_ocr_background is True
    assert "项目正在加载" in app.status_var.value
