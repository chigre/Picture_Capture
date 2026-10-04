from __future__ import annotations

import ast
from pathlib import Path

from picture_capture.ui.settings import profile as settings_profile


ROOT = Path(__file__).resolve().parents[1]


def test_settings_profile_module_has_no_reverse_app_dependency() -> None:
    source = Path(settings_profile.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_settings_profile_extraction_keeps_dialog_wrappers_and_behavior_boundary() -> None:
    app = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    helper = (
        ROOT / "src" / "picture_capture" / "ui" / "settings" / "profile.py"
    ).read_text(encoding="utf-8")

    settings_start = app.index("class SettingsDialog")
    settings_end = app.index("class ReviewWindow", settings_start)
    settings = app[settings_start:settings_end]

    for method, helper_name in (
        ("_build_profile_tab", "build_profile_tab"),
        ("_build_profile_choice_labels", "build_profile_choice_labels"),
        ("_profile_label_for_key", "profile_label_for_key"),
        ("_profile_display_name", "profile_display_name"),
        ("_sync_custom_profile_name_state", "sync_custom_profile_name_state"),
        ("_on_custom_profile_name_changed", "on_custom_profile_name_changed"),
        ("_current_profile_key", "current_profile_key"),
        ("_refresh_profile_summary", "refresh_profile_summary"),
        ("_coerce_profile_var", "coerce_profile_var"),
        ("_refresh_profile_status", "refresh_profile_status"),
        ("_apply_profile_defaults_to_vars", "apply_profile_defaults_to_vars"),
        ("_on_profile_selected", "on_profile_selected"),
        ("restore_profile_defaults", "restore_profile_defaults"),
        ("_on_profile_language_changed", "on_profile_language_changed"),
        ("_sync_layout_semantics", "sync_layout_semantics"),
        ("_refresh_sort_choices", "refresh_sort_choices"),
        ("_toggle_custom_sort_state", "toggle_custom_sort_state"),
    ):
        assert f"def {method}(" in settings
        assert f"_settings_profile_ui.{helper_name}(" in settings

    assert "self.profile_canvas = profile_canvas" not in settings
    assert "dialog.profile_canvas = profile_canvas" in helper
    assert "profile_scrollbar" in helper
    assert 'text="自定义结构名称："' in helper

    assert "profiles = list(available_dictionary_profiles())" not in settings
    assert "profiles = list(available_dictionary_profiles())" in helper
    assert "profile_effective_settings(" in helper
    assert "language_effective_settings(" in helper
    assert "available_profile_labels(" in helper
