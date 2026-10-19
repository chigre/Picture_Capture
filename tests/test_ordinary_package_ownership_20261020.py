"""Issue #562: ordinary evidence helpers have canonical package owners, not shims."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
MOVED = ["ordinary_cjk_large_heads", "ordinary_crossing_separator", "ordinary_final_visual_consistency", "ordinary_independent_indent_rescue", "ordinary_lane_polarity", "ordinary_layout_inspector", "ordinary_marker_ocr_text", "ordinary_oversized_head_guard", "ordinary_postprocess", "ordinary_secondary_recovery", "ordinary_symbol_evidence", "ordinary_unified_diagnostics", "ordinary_unified_visualization", "ordinary_vb_brightness", "ordinary_quick_settings"]


def test_ordinary_owners_exist_and_retired_roots_do_not():
    for old_name in MOVED:
        assert not (ROOT / (old_name + ".py")).exists(), old_name
        assert (ROOT / "ordinary" / (old_name.removeprefix("ordinary_") + ".py")).is_file(), old_name


def test_no_static_imports_from_removed_ordinary_roots():
    forbidden = set(MOVED)
    violations = []
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    if len(parts) > 1 and parts[0] == "picture_capture" and parts[1] in forbidden:
                        violations.append((str(path), node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    parent = path.parent.relative_to(ROOT).parts
                    keep = len(parent) + 1 - node.level
                    resolved = (*parent[:max(0, keep)], *module.split("."))
                else:
                    parts = module.split(".")
                    resolved = tuple(parts[1:] if parts[0] == "picture_capture" else parts)
                if resolved and resolved[0] in forbidden:
                    violations.append((str(path), node.lineno, module))
                if not module or module == "picture_capture":
                    for alias in node.names:
                        if alias.name in forbidden:
                            violations.append((str(path), node.lineno, alias.name))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in {"picture_capture." + old for old in forbidden}:
                    violations.append((str(path), node.lineno, node.value))
    assert not violations, violations[:30]
