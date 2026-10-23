"""#562 preprocessing GUI workflow physical owner and compatibility checks."""
from __future__ import annotations

from dataclasses import fields
import inspect
import subprocess
import sys
from types import SimpleNamespace

from PIL import Image

from picture_capture import app as app_module
from picture_capture.ui import preprocess_workflow as owner


class Var:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


def test_preprocess_ui_owner_import_is_independent_of_app_tk_and_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ui.preprocess_workflow import PreprocessUiDeps
assert 'picture_capture.app' not in sys.modules
assert 'picture_capture.paddle_headwords_core' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_exact_24_instance_and_static_preprocess_methods_still_on_app():
    names = [
        "_preprocess_mode_active", "_preprocess_config",
        "_preprocess_export_config", "_preprocess_export_settings_changed",
        "_preprocess_settings_changed", "_set_workspace_preprocess_locked",
        "_preprocess_blocking_window_name", "toggle_preprocess_mode",
        "_set_preprocess_mode", "_default_preprocess_corner_quad",
        "edit_preprocess_corners", "reset_preprocess_corners",
        "_preprocess_result_for_page", "_set_current_preprocess_status",
        "analyze_preprocess_current", "analyze_preprocess_selected",
        "show_preprocess_diagnostics", "promote_preprocessed_working_images",
        "jump_preprocess_review", "_preprocess_analysis_for_export",
        "export_preprocess_previews", "export_preprocess_images",
        "_get_preprocess_display_photo", "_redraw_preprocess_preview",
    ]
    for name in names:
        assert name in app_module.PictureCaptureApp.__dict__
        assert hasattr(owner, name)
    assert isinstance(
        app_module.PictureCaptureApp.__dict__["_default_preprocess_corner_quad"],
        staticmethod,
    )
    assert list(inspect.signature(
        app_module.PictureCaptureApp.analyze_preprocess_current
    ).parameters) == ["self", "silent"]
    assert list(inspect.signature(
        app_module.PictureCaptureApp._set_preprocess_mode
    ).parameters) == ["self", "active", "analyze"]
    assert list(inspect.signature(
        app_module.PictureCaptureApp._preprocess_analysis_for_export
    ).parameters) == [
        "self", "project", "page", "settings", "safety",
        "auto_deskew", "geometry_mode",
    ]


def test_preprocess_gui_globals_resolve_original_live_patch_points(monkeypatch):
    names = {f.name for f in fields(owner.PreprocessUiDeps)}
    assert len(names) == 42
    assert {
        "analyze_preprocess_path", "load_preprocess_analysis",
        "save_preprocess_analysis", "save_processed_page",
        "promote_processed_pages", "save_manual_perspective_quad",
        "load_manual_perspective_quad", "geometry_corrected_image",
        "preprocess_result_summary", "overlay_excluded_regions",
        "messagebox", "tk", "ttk", "ImageTk",
    } <= names
    func = lambda *args: None
    monkeypatch.setattr(app_module, "analyze_preprocess_path", func)
    deps = app_module._preprocess_ui_deps()
    assert deps.analyze_preprocess_path is func
    assert deps.messagebox is app_module.messagebox


def test_preprocess_mode_gate_and_config_use_original_widget_variables():
    app = SimpleNamespace(
        preprocess_mode_var=Var(True),
        preprocess_safety_var=Var("28"),
        preprocess_geometry_var=Var("自动透视"),
        preprocess_auto_deskew_var=Var(False),
        settings=SimpleNamespace(preprocess_safety_margin_px=20),
    )
    assert app_module.PictureCaptureApp._preprocess_mode_active(app) is True
    assert app_module.PictureCaptureApp._preprocess_config(app) == (
        28, False, "perspective"
    )
    app.preprocess_safety_var = Var("bad")
    assert app_module.PictureCaptureApp._preprocess_config(app)[0] == 20
    app.preprocess_mode_var = Var(False)
    assert not app_module.PictureCaptureApp._preprocess_mode_active(app)


def test_original_static_corner_quad_stays_bounded_by_image():
    image = Image.new("RGB", (400, 300), "white")
    try:
        points = app_module.PictureCaptureApp._default_preprocess_corner_quad(image)
        assert len(points) == 8
        assert points[0] >= 0 and points[1] >= 0
        assert points[2] < 400 and points[5] < 300
        assert points[0] < points[2] and points[1] < points[5]
    finally:
        image.close()


def test_instance_adapter_forwards_original_gui_self_and_user_event(monkeypatch):
    captured = {}
    sentinel = object()
    def spy(instance, deps, event=None):
        captured.update(instance=instance, deps=deps, event=event)
        return sentinel
    monkeypatch.setattr(owner, "_preprocess_settings_changed", spy)
    app = object()
    event = object()
    result = app_module.PictureCaptureApp._preprocess_settings_changed(app, event)
    assert result is sentinel
    assert captured["instance"] is app and captured["event"] is event
    assert captured["deps"].save_processed_page is app_module.save_processed_page


def test_export_preprocess_callback_returns_leaf_result(monkeypatch):
    value = object()
    monkeypatch.setattr(owner, "export_preprocess_images", lambda instance, deps: value)
    assert app_module.PictureCaptureApp.export_preprocess_images(object()) is value
