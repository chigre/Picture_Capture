"""Phase 13B final gate: primitive consumers use explicit operation objects.

Keep the historical hook assignments in their known compatibility implementations
until Phase 13E, but reject new direct reads in migrated consumers.
"""
from __future__ import annotations

import ast
from pathlib import Path

from picture_capture import dictionary_page_design as base


PACKAGE = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
MIGRATED = (
    "dictionary_page_layout_policy.py",
    "dictionary_page_design_refined.py",
    "page_x_registration.py",
    "layout_column_drift.py",
)
MUTABLE_HOOKS = frozenset((
    "_line_runs", "_line_feature", "_indent_modes", "_assign_indent_semantics",
))
FUNCTIONS_WITH_OPS = {
    "dictionary_page_layout_policy.py": (
        "resolve_page_layout_policy",
        "infer_dictionary_page_layout",
        "detect_entries_from_page_design",
    ),
    "dictionary_page_design_refined.py": ("_guard_band_entries",),
    "page_x_registration.py": ("_line_family_candidate", "register_page_manual_x"),
    "layout_column_drift.py": (
        "remeasure_layout_indents_from_ink", "finalize_layout_column_drift",
    ),
}


def test_layout_consumers_do_not_read_mutable_page_design_hooks():
    for name in MIGRATED:
        tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
        direct_reads = [
            node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "base"
            and node.attr in MUTABLE_HOOKS
            and isinstance(node.ctx, ast.Load)
        ]
        assert not direct_reads, (name, direct_reads)


def test_migrated_layout_boundaries_expose_optional_ops():
    for name, functions in FUNCTIONS_WITH_OPS.items():
        tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
        definitions = {
            node.name: node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for function in functions:
            node = definitions[function]
            parameters = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            assert "ops" in {param.arg for param in parameters}, (name, function)


def test_raw_layout_ops_remain_distinct_from_runtime_hook_snapshot(monkeypatch):
    original = base.current_layout_ops()
    def sentinel(*args, **kwargs):
        return []
    monkeypatch.setattr(base, "_line_runs", sentinel)
    assert base.current_layout_ops().line_runs is sentinel
    assert base.RAW_LAYOUT_OPS.line_runs is not sentinel
    assert original.line_runs is not sentinel
