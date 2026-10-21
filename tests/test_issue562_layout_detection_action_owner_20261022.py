"""Issue #562: Layout detection GUI callbacks have a single physical UI owner."""
from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE / "src" / "picture_capture"


def test_layout_detection_actions_physical_ui_owner_and_gui_entry_wiring():
    assert not (ROOT / "layout_detection_actions.py").exists()
    expected = ROOT / "ui" / "layout_detection_actions.py"
    assert expected.is_file()
    assert importlib.util.find_spec("picture_capture.layout_detection_actions") is None
    module = importlib.import_module("picture_capture.ui.layout_detection_actions")
    assert Path(module.__file__).resolve() == expected.resolve()
    assert callable(module.detect_layout_current)
    assert callable(module.detect_layout_consistency_selected)
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "from .ui.layout_detection_actions import (" in app
    assert "from .layout_detection_actions import" not in app


def test_gui_action_migration_has_no_retired_module_imports():
    retired = "layout_detection_actions"
    for section in ("src", "tests", "scripts"):
        for path in (BASE / section).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    assert not any(alias.name == "picture_capture." + retired for alias in node.names), (path, node.lineno)
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    assert mod != "picture_capture." + retired, (path, node.lineno)
                    if node.level and mod == retired:
                        raise AssertionError((path, node.lineno))
                    if mod in ("", "picture_capture"):
                        assert not any(alias.name == retired for alias in node.names), (path, node.lineno)
