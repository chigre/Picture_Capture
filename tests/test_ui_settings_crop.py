from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from picture_capture.crop.settings import (
    SINGLE_LINE_MERGE_KEY,
    UNLINED_BLANK_INK_PERCENT_KEY,
    UNLINED_FILTER_BLANK_KEY,
    UNLINED_FILTER_ENABLED_KEY,
)
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
    assert "SINGLE_LINE_MERGE_KEY" in helper
    assert "save_merge_by_page(project_root, enabled)" in helper
    assert "UNLINED_FILTER_ENABLED_KEY" in helper
    assert "UNLINED_FILTER_BLANK_KEY" in helper
    assert "UNLINED_BLANK_INK_PERCENT_KEY" in helper
    assert "save_unlined_filter_settings(" in helper

    assert '(crop_tab, "切图")' in settings
    assert '"crop": crop_tab' in settings
    assert "self._save_integrated_crop_settings()" in settings
    assert "CropSettingsDialog.CONFIG_NAME" in helper
    assert "CROP_SETTINGS_VERSION" in helper
    assert "SOURCE_COORDINATE_SPACE" in helper



class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def test_integrated_crop_payload_owns_single_line_merge_flag() -> None:
    dialog = SimpleNamespace(
        crop_vars={
            "general_top_y": _Var("10"),
            "general_bottom_y": _Var("100"),
            "entry_left_padding_x": _Var("0"),
            "entry_right_padding_x": _Var("0"),
            "integrate_illustrations": _Var(True),
            "polygon_margin": _Var("0"),
            "parallel_workers": _Var("2"),
            SINGLE_LINE_MERGE_KEY: _Var(True),
            UNLINED_FILTER_ENABLED_KEY: _Var(True),
            UNLINED_FILTER_BLANK_KEY: _Var(True),
            UNLINED_BLANK_INK_PERCENT_KEY: _Var("1.2"),
        },
        _crop_specials={},
    )

    payload = settings_crop.crop_settings_payload(dialog)

    assert payload[SINGLE_LINE_MERGE_KEY] is True
    assert payload[UNLINED_FILTER_ENABLED_KEY] is True
    assert payload[UNLINED_FILTER_BLANK_KEY] is True
    assert payload[UNLINED_BLANK_INK_PERCENT_KEY] == 1.2
    assert payload["parallel_workers"] == 2
