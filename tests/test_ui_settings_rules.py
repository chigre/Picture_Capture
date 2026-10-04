from __future__ import annotations

import ast
from pathlib import Path

from picture_capture.ui.settings import rules as settings_rules


ROOT = Path(__file__).resolve().parents[1]


def test_settings_rules_module_has_no_reverse_app_dependency() -> None:
    source = Path(settings_rules.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_settings_rules_extraction_keeps_dialog_wrappers_and_behavior_boundary() -> None:
    app = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    helper = (
        ROOT / "src" / "picture_capture" / "ui" / "settings" / "rules.py"
    ).read_text(encoding="utf-8")

    settings_start = app.index("class SettingsDialog")
    settings_end = app.index("class ReviewWindow", settings_start)
    settings = app[settings_start:settings_end]

    for method, helper_name in (
        ("_rules_path", "rules_path"),
        ("load_rules_editor", "load_rules_editor"),
        ("restore_default_rules", "restore_default_rules"),
        ("import_rules", "import_rules"),
        ("export_rules", "export_rules"),
    ):
        assert f"def {method}(" in settings
        assert f"_settings_rules_ui.{helper_name}(" in settings

    assert 'title="导入词头规则"' not in settings
    assert 'title="导入词头规则"' in helper
    assert 'title="导出词头规则"' in helper
    assert "parse_headword_filter_rules(" in helper
    assert "headword_filter_rules_path(" in helper
