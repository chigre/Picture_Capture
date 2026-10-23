"""Issue #562: one GUI project center, project load and page session owner."""
from __future__ import annotations

from dataclasses import fields
import inspect
import subprocess
import sys

from picture_capture import app as app_module
from picture_capture.ui import project_session_workflow as owner


def test_project_session_owner_does_not_import_giant_tk_app():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ui.project_session_workflow import ProjectSessionDeps
assert 'picture_capture.app' not in sys.modules
assert 'picture_capture.paddle_headwords_core' not in sys.modules
assert 'paddle' not in sys.modules
assert len(ProjectSessionDeps.__dataclass_fields__) == 30
"""], check=True)


def test_runtime_module_policies_and_tk_hooks_remain_patchable(monkeypatch):
    names = {f.name for f in fields(owner.ProjectSessionDeps)}
    assert len(names) == 30
    assert {
        "ProjectController", "ProjectState", "STORAGE_DIRNAME",
        "load_recent_projects", "recent_project_stub_details",
        "remove_recent_project", "set_recent_project_pinned",
        "touch_recent_project", "is_managed_project", "migrate_legacy_project",
        "read_pdic", "read_ppp", "read_page_sections",
        "normalize_page_rgb", "normalize_appearance_mode",
        "themed_display_image", "tk", "ttk", "messagebox", "ImageTk",
    } <= names
    deps = app_module._project_session_deps()
    assert deps.ProjectController is app_module.ProjectController
    assert deps.read_pdic is app_module.read_pdic
    replacement = lambda *args, **kwargs: []
    monkeypatch.setattr(app_module, "load_recent_projects", replacement)
    assert app_module._project_session_deps().load_recent_projects is replacement


def test_all_nine_original_methods_keep_signatures_and_static_tooltip():
    cls = app_module.PictureCaptureApp
    expected = {
        "open_recent_project": ["self"],
        "_attach_tooltip": ["widget", "message"],
        "_project_controller_for_call": ["self"],
        "_choose_new_project_image_suffix": ["self", "root"],
        "open_project": ["self"],
        "_load_project": [
            "self", "root", "requested_suffix", "target_page", "target_index",
            "target_view_scale", "launch_profile_setup", "parameter_template_root",
        ],
        "on_page_select": ["self", "_event"],
        "_request_page_load": [
            "self", "index", "reset_zoom", "current_already_saved", "force",
        ],
        "load_page": [
            "self", "index", "reset_zoom", "preloaded", "skip_current_save",
        ],
    }
    for name, arguments in expected.items():
        assert list(inspect.signature(getattr(cls, name)).parameters) == arguments
    assert isinstance(inspect.getattr_static(cls, "_attach_tooltip"), staticmethod)
    assert cls.open_recent_project.__doc__.startswith("Show recent projects")
    assert cls._load_project.__doc__.startswith("Prepare project files")


def test_recent_project_center_and_static_tooltip_forward_exact_arguments(monkeypatch):
    captured = []
    def center(self, deps):
        captured.append(("center", self, deps))
    def tooltip(deps, widget, message):
        captured.append(("tooltip", deps, widget, message))
    monkeypatch.setattr(owner, "open_recent_project", center)
    monkeypatch.setattr(owner, "_attach_tooltip", tooltip)
    app_instance = object()
    app_module.PictureCaptureApp.open_recent_project(app_instance)
    app_module.PictureCaptureApp._attach_tooltip(object(), "sample")
    assert captured[0][0:2] == ("center", app_instance)
    assert isinstance(captured[0][2], owner.ProjectSessionDeps)
    assert captured[1][0] == "tooltip"
    assert isinstance(captured[1][1], owner.ProjectSessionDeps)
    assert captured[1][3] == "sample"


def test_project_loader_keeps_all_restart_and_restoration_params(monkeypatch):
    called = {}
    def load(self, deps, *args, **kwargs):
        called.update(self=self, deps=deps, args=args, kwargs=kwargs)
    monkeypatch.setattr(owner, "_load_project", load)
    app_instance = object()
    root = object()
    template = object()
    app_module.PictureCaptureApp._load_project(
        app_instance, root, requested_suffix=".tif", target_page="p42",
        target_index=41, target_view_scale=1.75,
        launch_profile_setup=True, parameter_template_root=template,
    )
    assert called["self"] is app_instance
    assert isinstance(called["deps"], owner.ProjectSessionDeps)
    assert called["args"] == (root,)
    assert called["kwargs"] == {
        "requested_suffix": ".tif", "target_page": "p42",
        "target_index": 41, "target_view_scale": 1.75,
        "launch_profile_setup": True, "parameter_template_root": template,
    }


def test_page_load_preserves_preloaded_payload_and_skip_save(monkeypatch):
    called = {}
    def load(self, deps, *args, **kwargs):
        called.update(self=self, deps=deps, args=args, kwargs=kwargs)
    monkeypatch.setattr(owner, "load_page", load)
    app_instance = object()
    preloaded = {"marker": "source"}
    app_module.PictureCaptureApp.load_page(
        app_instance, 5, reset_zoom=True,
        preloaded=preloaded, skip_current_save=True,
    )
    assert called["self"] is app_instance
    assert called["args"] == (5,)
    assert called["kwargs"] == {
        "reset_zoom": True, "preloaded": preloaded,
        "skip_current_save": True,
    }


def test_page_request_forwards_all_navigation_policy_switches(monkeypatch):
    marker = object()
    def request(self, deps, *args, **kwargs):
        assert (args, kwargs) == ((7,), {
            "reset_zoom": True,
            "current_already_saved": True,
            "force": True,
        })
        return marker
    monkeypatch.setattr(owner, "_request_page_load", request)
    assert app_module.PictureCaptureApp._request_page_load(
        object(), 7, reset_zoom=True, current_already_saved=True, force=True
    ) is marker
