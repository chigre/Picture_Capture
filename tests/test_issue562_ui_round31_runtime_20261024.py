"""Round 31: GUI threading, quick settings, Paddle diagnostics and button API contracts."""
from __future__ import annotations

import ast
import inspect
import queue
from pathlib import Path
from types import SimpleNamespace

from picture_capture import app as gui
from picture_capture.ui import (
    background_job_runtime, quick_settings_sync,
    paddle_environment_report, main_action_buttons,
)


def test_round31_leaf_owners_and_old_app_api():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(root.glob("*.py"))) == 10
    owners = {
        "background_job_runtime.py": {"start_ui_worker", "poll_ui_worker_queue"},
        "quick_settings_sync.py": {"sync_quick_settings_impl"},
        "paddle_environment_report.py": {"paddle_environment_text_impl"},
        "main_action_buttons.py": {"sidebar_action_button_impl", "footer_action_button_impl"},
    }
    for filename, names in owners.items():
        file = root / "ui" / filename
        tree = ast.parse(file.read_text(encoding="utf-8"))
        assert {n.name for n in tree.body if isinstance(n, ast.FunctionDef)} == names
        assert not any(isinstance(n, (ast.ClassDef, ast.Assign, ast.AnnAssign)) for n in tree.body)
        assert not (root / filename).exists()
    expected = {
        "_start_ui_worker": ["self", "key", "worker", "on_done", "on_error", "wait_on_close"],
        "_poll_ui_worker_queue": ["self"],
        "sync_quick_settings": ["self"],
        "_paddle_environment_text": ["self", "settings"],
        "_sidebar_action_button": ["self", "parent", "text", "command", "role"],
        "_footer_action_button": ["self", "parent", "text", "command", "role"],
    }
    for name, args in expected.items():
        method = getattr(gui.PictureCaptureApp, name)
        assert method.__module__ == "picture_capture.app"
        assert list(inspect.signature(method).parameters) == args


def test_round31_legacy_entrypoints_pass_current_globals(monkeypatch):
    seen = []
    def spy(label):
        def impl(owner, *args, deps, **kwargs):
            seen.append((label, owner, args, kwargs, deps))
            return label
        return impl
    monkeypatch.setattr(background_job_runtime, "start_ui_worker", spy("start"))
    monkeypatch.setattr(background_job_runtime, "poll_ui_worker_queue", spy("poll"))
    monkeypatch.setattr(quick_settings_sync, "sync_quick_settings_impl", spy("sync"))
    monkeypatch.setattr(paddle_environment_report, "paddle_environment_text_impl", spy("env"))
    monkeypatch.setattr(main_action_buttons, "sidebar_action_button_impl", spy("side"))
    monkeypatch.setattr(main_action_buttons, "footer_action_button_impl", spy("footer"))
    owner, parent = object(), object()
    assert gui.PictureCaptureApp._start_ui_worker(
        owner, "save", lambda: None, lambda result: None, wait_on_close=True,
    ) == "start"
    assert gui.PictureCaptureApp._poll_ui_worker_queue(owner) == "poll"
    assert gui.PictureCaptureApp.sync_quick_settings(owner) == "sync"
    assert gui.PictureCaptureApp._paddle_environment_text(owner) == "env"
    assert gui.PictureCaptureApp._sidebar_action_button(owner, parent, "按钮", None) == "side"
    assert gui.PictureCaptureApp._footer_action_button(owner, parent, "完成", None, role="project") == "footer"
    assert [x[0] for x in seen] == ["start", "poll", "sync", "env", "side", "footer"]
    assert all(x[1] is owner for x in seen)
    assert seen[0][3]["wait_on_close"] is True
    assert seen[0][4]["threading"] is gui.threading
    assert seen[1][4]["queue"] is gui.queue
    assert seen[1][4]["tk"] is gui.tk
    assert seen[2][4]["_layout_pixels_to_percent"] is gui._layout_pixels_to_percent
    assert seen[3][4]["resolve_paddle_device"] is gui.resolve_paddle_device
    assert seen[4][4]["ttk"] is gui.ttk
    assert seen[5][4]["tk"] is gui.tk


def test_worker_generation_guards_and_deferred_ui_completion(monkeypatch):
    events = []
    class InlineThread:
        def __init__(self, *, target, name, daemon):
            assert daemon is True and name.startswith("PictureCapture-")
            self.target = target
        def start(self):
            self.target()

    app = SimpleNamespace(
        _ui_worker_shutdown=False,
        _ui_close_requested=False,
        _ui_worker_handlers={},
        _ui_worker_generations={},
        _ui_worker_active=set(),
        _ui_worker_close_wait=set(),
        _ui_worker_queue=queue.Queue(),
        _ui_worker_poll_job=None,
        after=lambda delay, callback: ("after", delay, callback),
    )
    app._poll_ui_worker_queue = lambda: None
    fake_threading = SimpleNamespace(Thread=InlineThread)
    first = background_job_runtime.start_ui_worker(
        app, "load", lambda: "result", events.append,
        wait_on_close=True,
        deps={"threading": fake_threading, "traceback": gui.traceback},
    )
    assert first == 1
    assert app._ui_worker_close_wait == {("load", 1)}
    assert app._ui_worker_queue.get_nowait()[:4] == ("done", "load", 1, "result")
    assert app._ui_worker_poll_job[1] == 40
    second = background_job_runtime.start_ui_worker(
        app, "load", lambda: "new result", events.append,
        deps={"threading": fake_threading, "traceback": gui.traceback},
    )
    assert second == 2 and app._ui_worker_generations["load"] == 2
    assert ("load", 1) not in app._ui_worker_handlers
    assert ("load", 2) in app._ui_worker_handlers
    assert events == []  # Tk completion must not run on worker thread


def test_quick_sync_resets_state_on_conversion_failure():
    class BadVar:
        def set(self, value):
            raise ValueError("conversion failed")
    app = SimpleNamespace(
        quick_vars={"columns": BadVar()},
        quick_bool_vars={}, quick_color_vars={},
        settings=SimpleNamespace(columns=2),
        _quick_syncing=False,
        _quick_geometry_edit_source=set(),
        _refresh_quick_coordinate_labels=lambda: None,
    )
    deps = {
        "LAYOUT_PERCENT_AXES": {},
        "_format_layout_percent": str,
        "_layout_pixels_to_percent": lambda *a: 0.0,
        "normalize_content_font_setting": str,
        "LENS_MODE_LABELS": {"off": "关"},
    }
    try:
        quick_settings_sync.sync_quick_settings_impl(app, deps=deps)
    except ValueError as exc:
        assert "conversion failed" in str(exc)
    else:
        raise AssertionError("expected widget setter error")
    assert app._quick_syncing is False
