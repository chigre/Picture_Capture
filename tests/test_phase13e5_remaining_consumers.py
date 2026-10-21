"""Phase 13E5: both remaining full-understanding consumers use composition."""
from pathlib import Path
import ast

from picture_capture.layout import composition as layout_composition
from picture_capture.training import export_page_understanding as training


ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_training_diagnostics_binds_explicit_composed_service():
    assert training.understand_composed_page is layout_composition.understand_composed_page
    tree = ast.parse((ROOT / "training/export_page_understanding.py").read_text(encoding="utf-8"))
    calls = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "understand_composed_page" in calls
    assert "understand_page" not in calls


def test_profile_validation_uses_composed_service_inside_worker():
    tree = ast.parse((ROOT / "profile/validation_modes.py").read_text(encoding="utf-8"))
    imports = [alias.name for node in ast.walk(tree)
               if isinstance(node, ast.ImportFrom) and node.module == "layout_composition"
               for alias in node.names]
    calls = [n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "understand_composed_page" in imports
    assert "understand_composed_page" in calls
    assert "understand_page" not in calls
