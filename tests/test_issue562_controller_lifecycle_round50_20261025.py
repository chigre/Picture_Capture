"""Issue #562 Round 50: one lazy UI controller lifecycle owner with live patching."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import inspect

import pytest

from picture_capture import app as app_module
from picture_capture.ui import controller_lifecycle, project_session_workflow


def test_cache_reuses_existing_instance_and_does_not_eagerly_construct():
    calls = []
    class Fake:
        def __init__(self, parent, **kwargs):
            calls.append((parent, kwargs))
    app = SimpleNamespace()
    instance = controller_lifecycle.get_or_create_controller(app, "review_controller", Fake)
    assert app.review_controller is instance
    assert controller_lifecycle.get_or_create_controller(
        app, "review_controller", lambda *_args: pytest.fail("unexpected construction")
    ) is instance
    assert calls == [(app, {})]


def test_none_sentinel_constructor_kwargs_and_failure_atomicity():
    app = SimpleNamespace(headword_controller=None)
    history = []
    class Fake:
        def __init__(self, parent, *, parse_words_of_pages_text, fill_page_entries):
            history.append((parent, parse_words_of_pages_text, fill_page_entries))
    parser, fill = object(), object()
    instance = controller_lifecycle.get_or_create_controller(
        app, "headword_controller", Fake,
        parse_words_of_pages_text=parser, fill_page_entries=fill,
    )
    assert app.headword_controller is instance
    assert history == [(app, parser, fill)]
    empty = SimpleNamespace()
    def reject(parent):
        raise RuntimeError("failed to initialize")
    with pytest.raises(RuntimeError, match="failed to initialize"):
        controller_lifecycle.get_or_create_controller(empty, "crop_controller", reject)
    assert "crop_controller" not in empty.__dict__


@pytest.mark.parametrize("key,method,class_name", (
    ("canvas", "_canvas_controller_for_call", "CanvasController"),
    ("review", "_review_controller_for_call", "ReviewController"),
    ("detection", "_detection_controller_for_call", "DetectionController"),
    ("export", "_export_controller_for_call", "ExportController"),
    ("crop", "_crop_controller_for_call", "CropController"),
    ("illustration", "_illustration_controller_for_call", "IllustrationController"),
))
def test_app_wrappers_keep_live_class_patchpoints_and_stable_signature(
    monkeypatch, key, method, class_name,
):
    created = []
    class Fake:
        def __init__(self, parent):
            created.append(parent)
    monkeypatch.setattr(app_module, class_name, Fake)
    app = SimpleNamespace()
    callback = getattr(app_module.PictureCaptureApp, method)
    instance = callback(app)
    assert isinstance(instance, Fake)
    assert callback(app) is instance
    assert created == [app]
    assert app.__dict__[f"{key}_controller"] is instance
    assert list(inspect.signature(callback).parameters) == ["self"]


def test_headword_and_project_dependency_snapshots_are_not_frozen(monkeypatch):
    history = []
    class FakeHeadword:
        def __init__(self, parent, *, parse_words_of_pages_text, fill_page_entries):
            history.append(("headword", parent, parse_words_of_pages_text, fill_page_entries))
    parser, fill = object(), object()
    monkeypatch.setattr(app_module, "HeadwordController", FakeHeadword)
    monkeypatch.setattr(app_module, "_parse_words_of_pages_text", parser)
    monkeypatch.setattr(app_module, "_fill_page_entries", fill)
    app = SimpleNamespace()
    instance = app_module.PictureCaptureApp._headword_controller_for_call(app)
    assert app.headword_controller is instance
    assert history == [("headword", app, parser, fill)]
    assert app_module.PictureCaptureApp._headword_controller_for_call(app) is instance

    class FakeProject:
        def __init__(self, parent):
            history.append(("project", parent))
    project_app = SimpleNamespace()
    project = project_session_workflow._project_controller_for_call(
        project_app, SimpleNamespace(ProjectController=FakeProject)
    )
    assert project is project_app.project_controller
    assert project_session_workflow._project_controller_for_call(
        project_app, SimpleNamespace(
            ProjectController=lambda *_args: pytest.fail("unexpected reconstruction")
        ),
    ) is project
    assert history[-1] == ("project", project_app)


def test_owner_has_single_cache_implementation_and_no_reverse_ui_dependency():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture"
    lifecycle = (root / "ui/controller_lifecycle.py").read_text(encoding="utf-8")
    app = (root / "app.py").read_text(encoding="utf-8")
    project = (root / "ui/project_session_workflow.py").read_text(encoding="utf-8")
    assert "cache = app.__dict__" in lifecycle
    assert "controller = cache.get(cache_key)" in lifecycle
    assert "cache[cache_key] = controller" in lifecycle
    assert "picture_capture.app" not in lifecycle
    assert "import tkinter" not in lifecycle
    for key in (
        "canvas", "review", "detection", "export", "crop", "illustration", "headword"
    ):
        assert f'__dict__.get("{key}_controller")' not in app
    assert 'self.__dict__.get("project_controller")' not in project
