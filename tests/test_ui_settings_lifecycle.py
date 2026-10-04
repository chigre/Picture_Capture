from __future__ import annotations

import ast
from pathlib import Path

from picture_capture.ui.settings import lifecycle as settings_lifecycle


ROOT = Path(__file__).resolve().parents[1]


def test_settings_lifecycle_module_has_no_reverse_app_dependency() -> None:
    source = Path(settings_lifecycle.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_settings_lifecycle_extraction_keeps_dialog_wrappers_and_save_boundary() -> None:
    app = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    helper = (
        ROOT / "src" / "picture_capture" / "ui" / "settings" / "lifecycle.py"
    ).read_text(encoding="utf-8")

    settings_start = app.index("class SettingsDialog")
    settings_end = app.index("class ReviewWindow", settings_start)
    settings = app[settings_start:settings_end]

    for method, helper_name in (
        ("_schedule_autosave", "schedule_autosave"),
        ("_run_autosave", "run_autosave"),
        ("_validate_settings_now", "validate_settings_now"),
        ("_close_validated", "close_validated"),
    ):
        assert f"def {method}(" in settings
        assert f"_settings_lifecycle_ui.{helper_name}(" in settings

    assert "def save(" in settings
    assert "dialog.save(close=False, show_errors=False)" in helper
    assert "dialog.save(close=False, show_errors=True)" in helper
    assert "dialog.save(close=True, show_errors=True)" in helper
    assert "dialog.after(450, dialog._run_autosave)" in helper
