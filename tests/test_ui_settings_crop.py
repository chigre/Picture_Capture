from __future__ import annotations

import ast
from pathlib import Path

from picture_capture.ui.settings import crop as settings_crop


ROOT = Path(__file__).resolve().parents[1]


def test_settings_crop_module_has_no_reverse_app_dependency() -> None:
    source = Path(settings_crop.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_settings_crop_extraction_keeps_dialog_wrappers_and_save_boundary() -> None:
    app = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    helper = (
        ROOT / "src" / "picture_capture" / "ui" / "settings" / "crop.py"
    ).read_text(encoding="utf-8")

    settings_start = app.index("class SettingsDialog")
    settings_end = app.index("class ReviewWindow", settings_start)
    settings = app[settings_start:settings_end]

    for method, helper_name in (
        ("_crop_nonnegative_int", "crop_nonnegative_int"),
        ("_build_crop_settings_tab", "build_crop_settings_tab"),
        ("_crop_settings_payload", "crop_settings_payload"),
        ("_save_integrated_crop_settings", "save_integrated_crop_settings"),
    ):
        assert f"def {method}(" in settings
        assert f"_settings_crop_ui.{helper_name}(" in settings

    for field in (
        "general_top_y",
        "general_bottom_y",
        "entry_left_padding_x",
        "entry_right_padding_x",
        "integrate_illustrations",
        "polygon_margin",
        "parallel_workers",
    ):
        assert f'"{field}"' in helper

    assert '(crop_tab, "切图")' in settings
    assert '"crop": crop_tab' in settings
    assert "self._save_integrated_crop_settings()" in settings
    assert "CropSettingsDialog.CONFIG_NAME" in helper
    assert "CROP_SETTINGS_VERSION" in helper
    assert "SOURCE_COORDINATE_SPACE" in helper
