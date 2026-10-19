"""Issue #562: crop/overlay helpers have one physical canonical owner."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
OWNERS = {
    "crop_logging": "crop/logging.py",
    "crop_plan_formatting": "crop/plan_formatting.py",
    "crop_preview_display_settings": "crop/preview_display_settings.py",
    "crop_preview_labels": "crop/preview_labels.py",
    "overlay_layout_helpers": "ui/overlay_layout_helpers.py",
    "overlay_line_anchor": "ui/overlay_line_anchor.py",
    "overlay_opacity": "ui/overlay_opacity.py",
}


def test_real_crop_overlay_package_ownership_no_root_shims():
    for old, canonical in OWNERS.items():
        assert (ROOT / canonical).is_file(), canonical
        assert not (ROOT / (old + ".py")).exists(), old


def test_no_stale_production_imports_of_removed_crop_overlay_modules():
    forbidden = set(OWNERS)
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
                    # Resolve relative imports from the current package. A
                    # canonical sibling such as ui.overlay_line_anchor is valid.
                    parent_parts = path.parent.relative_to(ROOT).parts
                    keep = len(parent_parts) + 1 - node.level
                    resolved = (*parent_parts[:max(0, keep)], *module.split("."))
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
