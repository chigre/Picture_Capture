from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = (
    "FIELDS",
    "PROFILE_FIELD_GROUPS",
    "PROFILE_CHECKS",
    "FIELD_GROUPS",
    "CHECK_GROUPS",
    "OCR_LANGUAGES",
    "SETTING_LABELS",
    "SETTING_HELP",
    "COMMON_FIELDS",
    "NORMAL_COMMON_FIELDS",
    "NORMAL_ADVANCED_FIELDS",
    "OCR_COMMON_FIELDS",
    "OCR_ADVANCED_FIELDS",
    "DISPLAY_FIELDS",
    "PROJECT_RUNTIME_FIELDS",
    "EXPERT_FIELDS",
    "SETTING_UNITS",
    "SETTING_SPIN",
    "SETTING_HELP_IMAGES",
    "SETTING_CHOICES",
    "CHECK_HELP",
    "NORMAL_CHECKS",
    "OCR_COMMON_CHECKS",
    "OCR_ADVANCED_CHECKS",
    "DISPLAY_STYLE_CHECKS",
    "DISPLAY_CHECKS",
)


def test_settings_schema_is_ui_free_and_complete() -> None:
    schema = ROOT / "src" / "picture_capture" / "ui" / "settings" / "schema.py"
    source = schema.read_text(encoding="utf-8")

    assert "tkinter" not in source
    assert "picture_capture.app" not in source
    for name in SCHEMA_NAMES:
        assert f"{name} =" in source


def test_settings_dialog_uses_same_schema_objects_before_runtime_extensions() -> None:
    names = repr(SCHEMA_NAMES)
    code = (
        "from picture_capture.app import SettingsDialog; "
        "from picture_capture.ui.settings import schema; "
        f"names={names}; "
        "assert all(getattr(SettingsDialog, n) is getattr(schema, n) for n in names)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_settings_dialog_keeps_metadata_compatibility_aliases_in_app() -> None:
    app_source = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert "from .ui.settings import schema as _settings_schema" in app_source
    for name in SCHEMA_NAMES:
        assert f"    {name} = _settings_schema.{name}" in app_source
