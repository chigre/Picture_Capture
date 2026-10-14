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

# These are *actual* SettingsDialog groups, not arbitrary occurrences of
# field names in the schema. A field may appear in several task-specific pages.
GROUP_TO_PATH = {
    "COMMON_FIELDS": "设置中心/常用/版面参数",
    "NORMAL_COMMON_FIELDS": "设置中心/普通画线/常用",
    "NORMAL_ADVANCED_FIELDS": "设置中心/普通画线/高级（折叠）",
    "NORMAL_CHECKS": "设置中心/普通画线/行为",
    "OCR_COMMON_FIELDS": "设置中心/OCR画线/常用",
    "OCR_COMMON_CHECKS": "设置中心/OCR画线/行为",
    "OCR_ADVANCED_FIELDS": "设置中心/OCR画线/高级（折叠）",
    "OCR_ADVANCED_CHECKS": "设置中心/OCR画线/高级（折叠）",
    "SEPARATOR_Y_FIELDS": "设置中心/横线Y精修/参数",
    "SEPARATOR_Y_CHECKS": "设置中心/横线Y精修/行为",
    "DISPLAY_FIELDS": "设置中心/显示与校对/参数",
    "DISPLAY_STYLE_CHECKS": "设置中心/显示与校对/外观",
    "DISPLAY_CHECKS": "设置中心/显示与校对/行为",
    "PROJECT_RUNTIME_FIELDS": "设置中心/项目与批量/运行",
    "EXPERT_FIELDS": "设置中心/高级/版面与后端",
    "ILLUSTRATION_CHECKS": "设置中心/插图/行为",
    "ILLUSTRATION_DETECTION_FIELDS": "设置中心/插图/自动识别",
    "ILLUSTRATION_APPEARANCE_FIELDS": "设置中心/插图/外观",
    "PROFILE_FIELD_GROUPS": "设置中心/Project Profile/参数",
    "PROFILE_CHECKS": "设置中心/Project Profile/行为",
    # Deprecated/indirect registries are retained as *reference* evidence,
    # but cannot alone be taken as proof of a visible user control.
}
REGISTRY_ONLY = {
    "FIELDS", "FIELD_GROUPS", "CHECK_GROUPS",
}
PRODUCTION_RUNTIME_PREFIX = "src/picture_capture/"
PERSISTENCE_REGRESSION = (
    "tests/test_settings_runtime_audit_20261015.py::"
    "test_every_appsettings_value_roundtrips_through_json"
)
TARGETED_RUNTIME_TESTS = {
    "separator_y_ink_safe_max_fraction":
        "tests/test_ink_safe_separator_20261014.py::test_white_gap_thresholds_are_actually_consumed_by_shared_refiner",
    "separator_y_ink_safe_ink_threshold":
        "tests/test_ink_safe_separator_20261014.py::test_white_gap_search_fraction_and_grayscale_threshold_affect_runtime",
    "separator_y_ink_safe_existing_ink_ratio":
        "tests/test_ink_safe_separator_20261014.py::test_existing_ink_ratio_controls_whether_previously_safe_line_is_moved",
    "separator_y_ink_safe_gap_ink_ratio":
        "tests/test_ink_safe_separator_20261014.py::test_candidate_gap_ink_ratio_controls_three_row_acceptance",
}


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
                "ILLUSTRATION_APPEARANCE_FIELDS", "ILLUSTRATION_DETECTION_FIELDS",
            }:
                continue
            refs = {n.value for n in ast.walk(node.value) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            for field in fields:
                if field in refs:
                    groups.setdefault(field, set()).add(name)
    return {name: sorted(values) for name, values in groups.items()}


def schema_help_keys():
    """Literal help metadata can be checked without importing Tk."""
    tree = ast.parse(SCHEMA.read_text(encoding="utf-8"))
    found = {"SETTING_HELP": set(), "CHECK_HELP": set()}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id not in found:
                continue
            if isinstance(node.value, ast.Dict):
                found[target.id].update(
                    key.value for key in node.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                )
    return found


def user_ui_path(groups_for_field, field_name=None):
    paths = [GROUP_TO_PATH[name] for name in groups_for_field if name in GROUP_TO_PATH]
    if field_name == "crop_parallel_workers":
        paths.append("设置中心/切图/并行处理（自定义控件）")
    if paths:
        return ";".join(sorted(set(paths))), "static_schema_location"
    if any(name in REGISTRY_ONLY for name in groups_for_field):
        return "", "registry_only_not_proven_visible"
    return "", "no_schema_location_check_custom_ui"


def source_runtime_refs(field_reads):
    """Exclude static definition and widget-binding references from runtime list."""
    return [location for location in field_reads
            if location.startswith(PRODUCTION_RUNTIME_PREFIX)
            and not location.startswith("src/picture_capture/ui/")
            and not location.startswith("src/picture_capture/models.py:")
            and not location.startswith("src/picture_capture/app_settings_migrations.py:")]


def classified_candidates(literals, fields):
    """Classify heuristic *review candidates*; do not assert a hardcode is a bug."""
    keys = set(fields)
    decision_terms = ("threshold", "ratio", "fraction", "tolerance", "confidence",
                      "score", "min_", "max_", "support", "distance", "margin",
                      "ink", "gap", "radius", "width", "height")
    for item in literals:
        expr = item.get("expression", "")
        meaningful = any(token in expr.lower() for token in decision_terms)
        existing = sorted(
            name for name in keys
            if re.search(r"\b" + re.escape(name) + r"\b", expr)
        )
        yield {**item,
               "existing_settings_mentioned": existing,
               "triage": ("review_candidate_no_direct_settings"
                          if meaningful and not existing
                          else "review_candidate_existing_settings_or_guard"),
               "reviewed": False}


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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                positional = list(node.args.defaults)
                kw_defaults = list(node.args.kw_defaults)
                for name, default in zip(
                    [arg.arg for arg in node.args.args[-len(positional):]] if positional else [],
                    positional,
                ):
                    if isinstance(default, ast.Constant) and type(default.value) in (int, float):
                        if re.search(r"(threshold|ratio|tolerance|fraction|confidence|score|margin)", name):
                            literals.append({
                                "file": relative, "line": node.lineno,
                                "kind": "numeric_function_default",
                                "expression": f"{node.name}({name}={default.value!r})",
                            })
                for arg, default in zip(node.args.kwonlyargs, kw_defaults):
                    if isinstance(default, ast.Constant) and type(default.value) in (int, float):
                        if re.search(r"(threshold|ratio|tolerance|fraction|confidence|score|margin)", arg.arg):
                            literals.append({
                                "file": relative, "line": node.lineno,
                                "kind": "numeric_keyword_default",
                                "expression": f"{node.name}(*, {arg.arg}={default.value!r})",
                            })
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
    help_keys = schema_help_keys()
    threshold_review = list(classified_candidates(literals, fields))
    rows = []
    for name, default in fields.items():
        evidence = refs[name]
        ui_path, ui_evidence = user_ui_path(groups.get(name, ()), name)
        live_reads = source_runtime_refs(evidence["reads"])
        rows.append({
            "name": name,
            "default": default,
            "settings_center_groups": ";".join(groups.get(name, ())),
            "settings_center_path": ui_path,
            "ui_evidence": ui_evidence,
            "dedicated_help": name in help_keys["SETTING_HELP"] or name in help_keys["CHECK_HELP"],
            "gui_save_mechanism": ("SettingsDialog.save -> setattr -> AppSettings.to_json"
                                   if ui_path else "custom UI / project editor / internal: review"),
            "load_mechanism": "AppSettings.from_json -> migrate_app_settings_payload",
            "persistence_runtime_test": PERSISTENCE_REGRESSION,
            "targeted_algorithm_runtime_test": TARGETED_RUNTIME_TESTS.get(name, ""),
            "runtime_static_read_count": len(live_reads),
            "runtime_static_read_sites": ";".join(live_reads[:80]),
            "source_reads_count": len(evidence["reads"]),
            "source_writes_count": len(evidence["writes"]),
            "source_read_sites": ";".join(evidence["reads"][:80]),
            "source_write_sites": ";".join(evidence["writes"][:40]),
            "persistence": "AppSettings.to_json/from_json; check project migrations",
            "runtime_status": (
                "targeted_behavior_test"
                if name in TARGETED_RUNTIME_TESTS else (
                    "static_candidates_only_runtime_test_required"
                    if live_reads else "no_simple_static_runtime_read_review_dynamic_access"
                )
            ),
        })
    with (args.out / "appsettings_field_matrix.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (args.out / "hardcoded_threshold_candidates.json").write_text(
        json.dumps(threshold_review, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # Two-stage triage: arbitrary numeric constants can be guards, not tuning
    # knobs. Keep every detection literal as evidence without turning all
    # arithmetic constants into user-facing configuration.
    (args.out / "threshold_triage_summary.json").write_text(
        json.dumps({
            "review_candidates_without_direct_field": sum(
                item["triage"] == "review_candidate_no_direct_settings"
                for item in threshold_review
            ),
            "resolved_experimental_white_gap_thresholds": [
                "separator_y_ink_safe_max_fraction",
                "separator_y_ink_safe_ink_threshold",
                "separator_y_ink_safe_existing_ink_ratio",
                "separator_y_ink_safe_gap_ink_ratio",
            ],
            "classification_note": (
                "Heuristic review queue; not a list of confirmed bugs. "
                "Mathematical invariants, imaging safety and library limits "
                "must not be automatically exposed as controls."
            ),
        }, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {
        "all_appsettings_fields": len(rows),
        "with_schema_group": sum(bool(row["settings_center_groups"]) for row in rows),
        "visible_settings_center_path": sum(bool(row["settings_center_path"]) for row in rows),
        "with_static_runtime_read": sum(bool(row["runtime_static_read_count"]) for row in rows),
        "with_dedicated_schema_help": sum(bool(row["dedicated_help"]) for row in rows),
        "threshold_candidates_requiring_review": sum(
            item["triage"] == "review_candidate_no_direct_settings"
            for item in threshold_review
        ),
        "without_schema_group": [row["name"] for row in rows if not row["settings_center_groups"]],
        "numeric_comparison_candidates": len(literals),
        "limitations": [
            "AppSettings includes internal/profile/storage fields, not all require UI",
            "UI built through custom modules may not reference schema group",
            "AST attribute sites can refer to other objects having the same property name",
            "numeric literals include mathematical/safety conditions, not all tunable",
            "dynamic attribute names and nested scripts may escape this static scan",
            "runtime verification of GUI, subprocesses and PDIC parity is separate",
            "Field persistence is dataclass JSON by default; migration and UI-specific save paths require runtime checks",
            "Every threshold candidate is heuristic until manually triaged",
        ],
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k not in ("without_schema_group", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
