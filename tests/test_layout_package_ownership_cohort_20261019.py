"""Issue #562: verify real Layout package ownership without compatibility shims."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
MIGRATED = (
    "layout_character_height",
    "layout_parameter_evidence",
    "layout_scale_experiment",
    "layout_step_trace",
    "layout_textbox_leading",
    "layout_column_drift",
    "layout_column_indent_recovery",
    "layout_line_start_refinement",
    "layout_local_indent_visualization",
    "layout_oversized_ink_continuation",
    "layout_illustration_mask",
    "layout_mask_source_guard",
    "layout_reliability",
    "layout_role_visual_consistency",
    "layout_verified_oversized_heads",
    "layout_visualization_readability",
    "layout_details_window",
    "layout_role_provenance",
    "layout_lane_summary_extension",
)


def test_layout_cohort_is_physical_and_root_modules_are_absent():
    for former in MIGRATED:
        canonical = ROOT / "layout" / (former.removeprefix("layout_") + ".py")
        assert canonical.is_file(), str(canonical)
        assert not (ROOT / (former + ".py")).exists(), former
    # Migrated historical role color owner is physical, not a root shim.
    assert not (ROOT / "layout_visualization_role_theme.py").exists()
    assert (ROOT / "layout/visualization_role_theme.py").is_file()


def test_no_static_or_dotted_dynamic_import_of_removed_layout_owners():
    forbidden = set(MIGRATED)
    violations = []
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("picture_capture.") and alias.name.split(".")[1] in forbidden:
                        violations.append((path, node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".")[-1] in forbidden:
                    violations.append((path, node.lineno, module))
                if module in {"", "picture_capture"}:
                    for alias in node.names:
                        if alias.name in forbidden:
                            violations.append((path, node.lineno, alias.name))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                for former in forbidden:
                    if node.value == "picture_capture." + former:
                        violations.append((path, node.lineno, node.value))
    assert not violations, violations[:30]
