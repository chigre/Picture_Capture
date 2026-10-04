from __future__ import annotations

import ast
from pathlib import Path

from picture_capture.ui.settings import project as settings_project


ROOT = Path(__file__).resolve().parents[1]


def test_settings_project_module_has_no_reverse_app_dependency() -> None:
    source = Path(settings_project.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_settings_project_extraction_keeps_dialog_wrapper_and_shared_language_contract() -> None:
    app = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    helper = (
        ROOT / "src" / "picture_capture" / "ui" / "settings" / "project.py"
    ).read_text(encoding="utf-8")

    settings_start = app.index("class SettingsDialog")
    settings_end = app.index("class ReviewWindow", settings_start)
    settings = app[settings_start:settings_end]

    assert "def _build_project_details_tab(" in settings
    assert "_settings_project_ui.build_project_details_tab(" in settings
    assert "language_codes=PROJECT_LANGUAGE_CODES" in settings
    assert "language_from_ocr=project_language_from_ocr" in settings

    assert "PROJECT_LANGUAGE_CODES = (" in app
    assert "def project_language_from_ocr(" in app
    assert 'text="词典项目详情"' in helper
    assert 'text="索引语言："' in helper
    assert 'text="内容语言："' in helper
    assert '"dictionary_body_page_range"' in helper
    assert "language_from_ocr(str(ocr_var.get()))" in helper
