"""Phase 13E completion gate: no normal product path may install Layout hooks."""
from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
INSTALLERS = {"install_robust_line_starts", "install_physical_indent_inference"}


def test_global_layout_install_calls_only_in_legacy_processing_shim():
    violations = []
    for path in PACKAGE.rglob("*.py"):
        relative = path.relative_to(PACKAGE).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for top in tree.body:
            # The explicit compatibility shim is intentionally retained for
            # existing direct callers; nothing in product execution calls it.
            if not isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(top):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                    continue
                if node.func.id not in INSTALLERS:
                    continue
                if (relative, top.name) != ("processing.py", "_ensure_layout_runtime"):
                    violations.append((relative, top.name, node.func.id))
    assert violations == []


def test_normal_processing_does_not_invoke_compatibility_shim():
    path = PACKAGE / "processing.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    owners = [node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == "_understand_page_current"]
    assert len(owners) == 1
    calls = [node.func.id for node in ast.walk(owners[0]) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name)]
    assert "_ensure_layout_runtime" not in calls


def test_gui_unlined_and_remaining_full_consumers_use_explicit_composition():
    files = {
        "bootstrap/gui.py": ("core_services = build_core_services()",),
        "unlined_physical_rows_resolver.py": ("infer_composed_physical_page_layout(",),
        "layout_core_understanding.py": ("infer_composed_physical_page_layout as infer_dictionary_page_layout",),
        "processing.py": ("understanding = understand_composed_page(",),
        "training_export_page_understanding.py": ("understanding = understand_composed_page(",),
        "profile_validation_modes.py": ("understanding = understand_composed_page(",),
        "training_export_v3.py": ("ops=explicit_physical_layout_ops()",),
    }
    for filename, needles in files.items():
        content = (PACKAGE / filename).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in content, (filename, needle)
    gui = (PACKAGE / "bootstrap/gui.py").read_text(encoding="utf-8")
    assert "install_robust_line_starts()" not in gui
    assert "install_physical_indent_inference()" not in gui
