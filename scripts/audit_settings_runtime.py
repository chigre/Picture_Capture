"""Repository-wide static audit of persisted AppSettings and decision literals.

Usage: python scripts/audit_settings_runtime.py --out docs/audits/generated
Reads every Python module under src/picture_capture, without importing GUI/OCR.
Reports are heuristic: dynamic getattr, variable aliases and UI builders still
require runtime validation. Never label a heuristic absence an unused setting.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "picture_capture"
SCHEMA = PACKAGE / "ui" / "settings" / "schema.py"
MODELS = PACKAGE / "models.py"


def field_defaults():
    tree = ast.parse(MODELS.read_text(encoding="utf-8"))
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AppSettings"]
    if len(classes) != 1:
        raise RuntimeError("Cannot identify unique AppSettings class")
    fields = {}
    for node in classes[0].body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            fields[node.target.id] = ast.unparse(node.value) if node.value else None
    return fields


def schema_locations(fields):
    tree = ast.parse(SCHEMA.read_text(encoding="utf-8"))
    groups = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            if name not in {
                "FIELDS", "COMMON_FIELDS", "NORMAL_COMMON_FIELDS", "NORMAL_ADVANCED_FIELDS",
                "OCR_COMMON_FIELDS", "OCR_ADVANCED_FIELDS", "DISPLAY_FIELDS",
                "PROJECT_RUNTIME_FIELDS", "EXPERT_FIELDS", "SEPARATOR_Y_FIELDS",
                "SEPARATOR_Y_CHECKS", "NORMAL_CHECKS", "OCR_COMMON_CHECKS",
                "OCR_ADVANCED_CHECKS", "PROFILE_FIELD_GROUPS", "PROFILE_CHECKS",
                "ILLUSTRATION_CHECKS", "DISPLAY_STYLE_CHECKS", "DISPLAY_CHECKS",
                "CHECK_GROUPS", "FIELD_GROUPS",
            }:
                continue
            refs = {n.value for n in ast.walk(node.value) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            for field in fields:
                if field in refs:
                    groups.setdefault(field, set()).add(name)
    return {name: sorted(values) for name, values in groups.items()}


def scan_reads_writes(fields):
    references = {name: {"reads": [], "writes": []} for name in fields}
    literals = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        try:
            source_text = path.read_text(encoding="utf-8")
            tree = ast.parse(source_text)
        except (SyntaxError, UnicodeError) as exc:
            literals.append({"file": relative, "line": 0, "kind": "parse_error", "expression": str(exc)})
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in fields:
                action = "writes" if isinstance(node.ctx, (ast.Store, ast.Del)) else "reads"
                references[node.attr][action].append(f"{relative}:{node.lineno}")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and node.args[1].value in fields:
                    references[node.args[1].value]["reads"].append(f"{relative}:{node.lineno}")
            elif isinstance(node, ast.Compare):
                # Literal numerical thresholds in comparisons in detection/analysis code.
                if not any(key in relative for key in (
                    "ordinary", "layout", "paddle", "ocr", "separator",
                    "image_utils", "ink_safe", "physical", "illustration",
                )):
                    continue
                nums = [x for x in ast.walk(node) if isinstance(x, ast.Constant)
                        and type(x.value) in (int, float) and x.value not in (0, 1)]
                if not nums:
                    continue
                parent = ast.get_source_segment(source_text, node) or ""
                if len(parent) > 230:
                    parent = parent[:227] + "..."
                literals.append({
                    "file": relative, "line": node.lineno,
                    "kind": "numeric_comparison", "expression": parent,
                })
    return references, literals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "audits" / "generated")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    fields = field_defaults()
    groups = schema_locations(fields)
    refs, literals = scan_reads_writes(fields)
    rows = []
    for name, default in fields.items():
        evidence = refs[name]
        rows.append({
            "name": name,
            "default": default,
            "settings_center_groups": ";".join(groups.get(name, ())),
            "source_reads_count": len(evidence["reads"]),
            "source_writes_count": len(evidence["writes"]),
            "source_read_sites": ";".join(evidence["reads"][:80]),
            "source_write_sites": ";".join(evidence["writes"][:40]),
            "persistence": "AppSettings.to_json/from_json; check project migrations",
            "runtime_status": "not_executed_static_evidence_only",
        })
    with (args.out / "appsettings_field_matrix.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (args.out / "hardcoded_threshold_candidates.json").write_text(
        json.dumps(literals, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    summary = {
        "all_appsettings_fields": len(rows),
        "with_schema_group": sum(bool(row["settings_center_groups"]) for row in rows),
        "without_schema_group": [row["name"] for row in rows if not row["settings_center_groups"]],
        "numeric_comparison_candidates": len(literals),
        "limitations": [
            "AppSettings includes internal/profile/storage fields, not all require UI",
            "UI built through custom modules may not reference schema group",
            "AST attribute sites can refer to other objects having the same property name",
            "numeric literals include mathematical/safety conditions, not all tunable",
            "dynamic attribute names and nested scripts may escape this static scan",
            "runtime verification of GUI, subprocesses and PDIC parity is separate",
        ],
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k not in ("without_schema_group", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
