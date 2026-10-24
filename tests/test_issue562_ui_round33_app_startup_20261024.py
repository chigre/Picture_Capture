"""Round 33: whole startup and resolved-appearance ownership without Tk changes."""
from __future__ import annotations

import ast
from pathlib import Path

from picture_capture import app as gui
from picture_capture.ui import main_app_initialization, appearance_resolution

BASE = Path(__file__).resolve().parents[1] / "src/picture_capture"


def _method(source: str, class_name: str, method_name: str):
    root = ast.parse(source)
    cls = next(n for n in root.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)


def test_original_startup_owner_and_live_dependencies():
    app = (BASE / "app.py").read_text(encoding="utf-8")
    init = (BASE / "ui/main_app_initialization.py").read_text(encoding="utf-8")
    constructor = _method(app, "PictureCaptureApp", "__init__")
    assert len(ast.get_source_segment(app, constructor).splitlines()) < 48
    assert 'super().__init__()' in ast.get_source_segment(app, constructor)
    assert '_main_app_initialization.initialize_main_app(' in ast.get_source_segment(app, constructor)
    assert "app_module_file" in init and "Path(app_module_file)" in init
    for token in ("self._batch_queue", "self._ui_worker_queue", "self._build_ui()",
                  "self._configure_global_appearance()", "self.restore_last_session",
                  "attach_nonbmp_unicode_input(self)"):
        assert token in init
    assert "self._build_ui()" not in ast.get_source_segment(app, constructor)


def test_tk_super_before_startup_delegate_and_live_globals(monkeypatch):
    calls = []
    def fake_tk_ctor(self):
        calls.append(("tk", self))
    def fake_initialize(self, *, deps):
        calls.append(("startup", self, deps))
    monkeypatch.setattr(gui.tk.Tk, "__init__", fake_tk_ctor)
    monkeypatch.setattr(main_app_initialization, "initialize_main_app", fake_initialize)
    obj = gui.PictureCaptureApp.__new__(gui.PictureCaptureApp)
    gui.PictureCaptureApp.__init__(obj)
    assert [c[0] for c in calls] == ["tk", "startup"]
    assert calls[0][1] is obj and calls[1][1] is obj
    deps = calls[1][2]
    assert deps["app_module_file"] == gui.__file__
    assert deps["tk"] is gui.tk
    assert deps["ImageTk"] is gui.ImageTk
    assert deps["SessionController"] is gui.SessionController
    assert deps["_parse_words_of_pages_text"] is gui._parse_words_of_pages_text
    assert deps["attach_nonbmp_unicode_input"] is gui.attach_nonbmp_unicode_input


def test_appearance_owner_preserves_live_palette_and_public_entrypoint(monkeypatch):
    app = (BASE / "app.py").read_text(encoding="utf-8")
    owner = (BASE / "ui/appearance_resolution.py").read_text(encoding="utf-8")
    method = ast.get_source_segment(app, _method(app, "PictureCaptureApp", "_apply_resolved_appearance"))
    assert "_appearance_resolution.apply_resolved_appearance(" in method
    assert "refresh_compact_header_buttons" in owner
    assert "refresh_compact_range_appearance" in owner
    assert "self._schedule_page_cell_overlay_refresh()" in owner
    assert "from .workspace_tools import" in owner
    captured = []
    def fake_owner(self, mode, *, deps):
        captured.append((self, mode, deps))
    monkeypatch.setattr(appearance_resolution, "apply_resolved_appearance", fake_owner)
    obj = gui.PictureCaptureApp.__new__(gui.PictureCaptureApp)
    gui.PictureCaptureApp._apply_resolved_appearance(obj, "dark")
    assert captured[0][0:2] == (obj, "dark")
    assert captured[0][2]["appearance_palette"] is gui.appearance_palette
    assert captured[0][2]["normalize_appearance_mode"] is gui.normalize_appearance_mode
