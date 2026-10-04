from __future__ import annotations

import ast
from pathlib import Path

from picture_capture.ui.settings import window as settings_window


ROOT = Path(__file__).resolve().parents[1]


def test_settings_window_module_has_no_reverse_app_dependency() -> None:
    source = Path(settings_window.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_settings_window_extraction_keeps_dialog_wrappers_and_controller_boundary() -> None:
    app = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    helper = (
        ROOT / "src" / "picture_capture" / "ui" / "settings" / "window.py"
    ).read_text(encoding="utf-8")

    settings_start = app.index("class SettingsDialog")
    settings_end = app.index("class ReviewWindow", settings_start)
    settings = app[settings_start:settings_end]

    for method, helper_name in (
        ("_configure_settings_appearance_styles", "configure_settings_appearance_styles"),
        ("refresh_appearance", "refresh_appearance"),
        ("select_tab", "select_tab"),
    ):
        assert f"def {method}(" in settings
        assert f"_settings_window_ui.{helper_name}(" in settings

    assert '"PC.Settings.TNotebook.Tab"' not in settings
    assert '"PC.Settings.TNotebook.Tab"' in helper
    assert "appearance_palette(dialog.parent.appearance_mode)" in helper
    assert "dialog.parent._apply_current_appearance(dialog)" in helper
    assert "dialog.notebook.select(tab)" in helper

    open_start = app.index("    def open_settings(")
    open_end = app.index("\n    def ", open_start + 10)
    open_settings = app[open_start:open_end]
    assert "existing.select_tab(initial_tab)" in open_settings
