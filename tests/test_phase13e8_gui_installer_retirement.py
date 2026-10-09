"""Phase 13E8: GUI bootstrap no longer installs global Layout primitive hooks."""
from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_gui_bootstrap_uses_explicit_composition_without_layout_installers():
    source = (ROOT / "bootstrap" / "gui.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [name.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
               for name in node.names]
    assert "install_robust_line_starts" not in imports
    assert "install_physical_indent_inference" not in imports
    assert "install_robust_line_starts()" not in source
    assert "install_physical_indent_inference()" not in source
    assert "core_services = build_core_services()" in source


def test_spawn_compatibility_installer_is_not_deleted_by_gui_cutover():
    source = (ROOT / "processing.py").read_text(encoding="utf-8")
    assert "def _ensure_layout_runtime()" in source
    assert "install_robust_line_starts()" in source
    assert "install_physical_indent_inference()" in source
