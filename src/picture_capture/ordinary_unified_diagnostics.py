"""Unified, candidate-level ordinary drawing evidence report.

Pure post-processing of the SAME traced Layout and detection stages used by
the diagnostic GUI. No classification, thresholds, Entry objects, PDIC files,
or GUI settings are changed. A shadow assessment is deliberately advisory:
it cannot add or remove an automatic separator.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


SCHEMA = "picture-capture-ordinary-evidence-v2"
STAGE_DESCRIPTIONS = {
    "layout_role_materialization": "Layout entry 行转换为候选线",
    "oversized_fragment_veto": "大字内部碎片重复线过滤",
    "coherent_separator_y_refinement": "Layout 初始候选页面级 Y 偏移修正（前置）",
    "bracketed_headword_recovery": "【】词头恢复和来源升级",
    "page_template_section_filter": "Profile/SECTION 区域过滤",
    "anomalous_final_visual_consistency": "异常批量视觉复核",
    "proven_bracket_body_continuation": "括号词头相邻正文误线复核",
    "blank_before_proven_head": "已确认词头之前空白误线复核",
    "final_y_coordinates_locked": "最终候选 Y 坐标确认（不额外平移）",
    "final_reading_order": "最终按阅读顺序排序",
}


def _marker_key(marker: dict[str, Any]) -> tuple[int, int, str]:
    return (
        int(marker.get("x", 0)),
        int(marker.get("y", 0)),
        str(marker.get("source", "") or ""),
    )


def _row_for_marker(
    rows: list[dict[str, Any]], marker: dict[str, Any],
    tolerance: float,
) -> dict[str, Any] | None:
    """Best *proximity* association, with explicit tolerance and no guessing."""
    x, y, _source = _marker_key(marker)
    options = [
        (abs(y - int(row["source_y"])), abs(x - int(row["source_x"])), row)
        for row in rows
        if abs(x - int(row["source_x"])) <= tolerance
        and abs(y - int(row["source_y"])) <= tolerance
    ]
    if not options:
        return None
    options.sort(key=lambda item: (item[0], item[1], item[2]["id"]))
    return options[0][2]


def _row_for_large_head_glyph(
    rows: list[dict[str, Any]],
    glyph: dict[str, Any],
    tolerance: float,
) -> dict[str, Any] | None:
    """Associate printed glyphs by column and ROW Y, not left glyph X.

    A verified oversized glyph can start 30-60 px inside a column while
    its final separator is intentionally anchored on the column boundary.
    Comparing its glyph-left X to the separator X falsely reports a missing
    line. The Layout physical-row ID and the canonical row-top are both
    recorded by the same inference, so that is the correct diagnostic key.

    This remains a spatial association, never evidence that the glyph caused
    the final line. Reject unmatched or different-column rows explicitly.
    """
    box = glyph.get("canonical_box") or ()
    if len(box) < 2:
        return None
    column = int(glyph.get("column", -1))
    top = int(box[1])
    matches = [
        row for row in rows
        if int(row.get("column", -1)) == column
        and abs(int(row.get("canonical_y0", -1000000)) - top)
        <= tolerance
    ]
    if not matches:
        return None
    return min(
        matches,
        key=lambda row: (
            abs(int(row["canonical_y0"]) - top),
            str(row["id"]),
        ),
    )


def _candidate_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "column": int(row["column"]),
        "source_anchor": [int(row["source_x"]), int(row["source_y"])],
        "physical_row": dict(row),
        "evidence": [],
        "detector_matches": [],
        "stage_trace": [],
        "final_entries": [],
        "issues": [],
        "shadow_assessment": {},
    }


def _append_evidence(
    candidate: dict[str, Any], name: str, origin: str, strength: str,
    description: str,
) -> None:
    if any(item["type"] == name for item in candidate["evidence"]):
        return
    candidate["evidence"].append({
        "type": name, "origin": origin, "strength": strength,
        "description": description,
    })


def _shadow_assessment(item: dict[str, Any]) -> dict[str, Any]:
    """Safe diagnostic recommendation, never an automatic output action."""
    final = bool(item["final_entries"])
    types = {entry["type"] for entry in item["evidence"]}
    issues = list(item["issues"])
    if issues:
        label = "review_conflict"
        reason = "；".join(issues)
    elif "verified_bracket" in types or "verified_large_head" in types:
        label = "supported_headword"
        reason = "已记录独立视觉词头证据"
    elif "layout_entry" in types and final:
        label = "baseline_headword"
        reason = "Layout词头证据及最终自动线一致"
    elif item["physical_row"] and item["physical_row"].get("role") == "body":
        label = "body"
        reason = "物理行被标为正文；没有冲突证据"
    else:
        label = "uncertain"
        reason = "现有可观测证据不足以单独确认"
    return {
        "label": label, "reason": reason,
        "would_change_output": False,
        "note": "仅供诊断；不会自动增删PDIC线，不能当作人工真值",
    }


def compose_ordinary_evidence_report(
    layout_snapshot: dict[str, Any],
    candidates: list[dict[str, Any]],
    pipeline_stages: list[dict[str, Any]],
    role_transitions: list[dict[str, Any]],
    final_lines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Join layout/visual/pipeline outputs into one inspectable candidate index.

    The physical line IDs are stable within the current page. Source coordinate
    matches are labelled as *spatial proximity*, not proof of causal origin.
    """
    row_height = max(8.0, float(layout_snapshot.get("ordinary_line_height", 0) or 0))
    match_tolerance = max(10.0, min(27.0, row_height * .85))
    rows = list(layout_snapshot.get("physical_rows", []) or [])
    rows.sort(key=lambda r: (
        int(r["column"]), int(r["source_y"]), str(r["id"]),
    ))
    indexed: dict[str, dict[str, Any]] = {
        str(row["id"]): _candidate_from_row(row) for row in rows
    }
    extra_by_key: dict[tuple[int, int], str] = {}

    def locate(marker: dict[str, Any]) -> dict[str, Any]:
        row = _row_for_marker(rows, marker, match_tolerance)
        if row is not None:
            return indexed[str(row["id"])]
        # Unmatched separator proposals are still first-class candidates.
        x, y, _source = _marker_key(marker)
        key = (x, y)
        previous = extra_by_key.get(key)
        if previous is not None:
            return indexed[previous]
        column_index = min(
            range(len(layout_snapshot.get("columns", []) or [])),
            key=lambda k: abs(x - int(layout_snapshot["columns"][k]["left"])),
        ) if layout_snapshot.get("columns") else -1
        identifier = f"U{len(extra_by_key)+1:04d}"
        extra_by_key[key] = identifier
        indexed[identifier] = {
            "id": identifier, "column": int(column_index),
            "source_anchor": [x, y],
            "physical_row": None,
            "evidence": [], "detector_matches": [],
            "stage_trace": [], "final_entries": [],
            "issues": [], "shadow_assessment": {},
        }
        return indexed[identifier]

    # Physical row roles are recorded as existing observations, never inferred
    # from the final separator positions or from automatic PDIC saves.
    for row in rows:
        target = indexed[str(row["id"])]
        role = str(row.get("role", "unknown"))
        if role == "entry":
            _append_evidence(
                target, "layout_entry", "physical_layout", "moderate",
                "物理行最终Layout角色为entry",
            )
        elif role == "body":
            _append_evidence(
                target, "layout_body", "physical_layout", "moderate",
                "物理行最终Layout角色为body",
            )
        target["indent_measurement"] = {
            "raw": float(row.get("first_x", 0)),
            "corrected": float(row.get("corrected_first_x", 0)),
        }

    stage_names: list[str] = []
    all_stage_markers: list[dict[str, Any]] = []
    for stage in pipeline_stages:
        stage_name = str(stage.get("stage", "unknown"))
        stage_names.append(stage_name)
        seen: set[str] = set()
        for marker in stage.get("entries", []) or []:
            target = locate(marker)
            marker_data = {
                "stage": stage_name,
                "x": int(marker.get("x", 0)),
                "y": int(marker.get("y", 0)),
                "source": str(marker.get("source", "") or ""),
                "issue_type": str(marker.get("issue_type", "") or ""),
            }
            identity = target["id"]
            if identity in seen:
                # Preserve multiple candidates on one physical row rather
                # than overwriting evidence with the last matched proposal.
                continue
            seen.add(identity)
            target["stage_trace"].append(marker_data)
            all_stage_markers.append(marker_data)
            source = marker_data["source"]
            if "ordinary_bracket_pair" in source:
                _append_evidence(
                    target, "verified_bracket", stage_name, "strong",
                    "当前阶段输出线含已核实的印刷括号证据",
                )
            if ("large_head" in source or
                    bool(marker.get("oversized", False))):
                _append_evidence(
                    target, "large_head_marker", stage_name, "moderate",
                    "当前阶段输出线携带大字来源或尺寸标记",
                )
    for target in indexed.values():
        trace = target["stage_trace"]
        target["first_seen_stage"] = trace[0]["stage"] if trace else None
        target["last_seen_stage"] = trace[-1]["stage"] if trace else None
        target["stage_count"] = len(trace)

    for idx, marker in enumerate(final_lines):
        actual = locate(marker)
        actual["final_entries"].append({
            "index": idx, "x": int(marker.get("x", 0)),
            "y": int(marker.get("y", 0)),
            "source": str(marker.get("source", "") or ""),
        })

    for idx, glyph in enumerate(candidates):
        if str(glyph.get("status", "")) == "split_parent":
            continue
        x0, y0, x1, y1 = map(int, glyph.get("source_box", (0, 0, 0, 0)))
        if not (x1 > x0 and y1 > y0):
            continue
        # Match a large printed glyph to the SAME Layout physical row using
        # its canonical column/Y, not its left-most pixel X. A final line at
        # column-left and a glyph 30-40px to its right are the same row.
        physical = _row_for_large_head_glyph(rows, glyph, match_tolerance)
        if physical is not None:
            target = indexed[str(physical["id"])]
            association = "same_column_canonical_row_start_proximity"
        else:
            anchor = {"x": x0, "y": y0, "source": "large_head_candidate"}
            target = locate(anchor)
            association = "nearest_printed_row_or_source_anchor"
        matched = {
            "index": idx + 1,
            "status": str(glyph.get("status", "unknown")),
            "source_box": [x0, y0, x1, y1],
            "height_ratio": float(glyph.get("height_ratio", 0) or 0),
            "detector_output": bool(glyph.get("detector_output", False)),
            "association": association,
        }
        target["detector_matches"].append(matched)
        if matched["status"] == "accepted" and matched["detector_output"]:
            _append_evidence(
                target, "verified_large_head", "large_head_detector",
                "strong", "正式大字检测器返回通过的行首字形",
            )

    transition_events: list[dict[str, Any]] = []
    for change in role_transitions:
        after = change.get("after") or change.get("before")
        if not isinstance(after, dict):
            continue
        column = int(after.get("column", -1))
        cy = int(after.get("canonical_y", 0))
        matched = next(
            (
                row for row in rows
                if int(row["column"]) == column
                and int(row["canonical_y0"]) == cy
            ), None,
        )
        event = {
            "stage": str(change.get("stage", "unknown")),
            "before": change.get("before"),
            "after": change.get("after"),
            "candidate_id": matched["id"] if matched else None,
        }
        transition_events.append(event)
        if matched is not None:
            target = indexed[str(matched["id"])]
            target.setdefault("role_transitions", []).append(event)

    # A separate, non-authoritative context pass audits the contradiction
    # most often seen on real dictionary pages: a body-indented continuation
    # was assigned entry after an otherwise bracket-confirmed headword.
    # The actual role, candidate list and final PDIC remain untouched.
    columns = list(layout_snapshot.get("columns", []) or [])
    for item in indexed.values():
        physical = item.get("physical_row")
        if physical is None:
            continue
        index = int(item["column"])
        if not 0 <= index < len(columns):
            continue
        column = columns[index]
        body = column.get("body_mode")
        modes = list(column.get("entry_modes", []) or [])
        if (
            not isinstance(body, dict)
            or int(body.get("support", 0)) < 4
            or not any(int(mode.get("support", 0)) >= 4 for mode in modes)
        ):
            continue
        strong_modes = [
            mode for mode in modes if int(mode.get("support", 0)) >= 4
        ]
        entry_center = min(float(mode["center"]) for mode in strong_modes)
        body_center = float(body["center"])
        diff = body_center - entry_center
        if diff <= max(14.0, row_height * .70):
            continue
        corrected = float(physical.get("corrected_first_x", 0))
        if corrected >= entry_center + .62 * diff:
            _append_evidence(
                item, "physical_body_indent", "per_column_indent",
                "moderate", "本行真实行首位于重复正文缩进带",
            )
        elif corrected <= entry_center + .35 * diff:
            _append_evidence(
                item, "physical_entry_indent", "per_column_indent",
                "moderate", "本行真实行首位于重复词条起始带",
            )

    by_column: dict[int, list[dict[str, Any]]] = {}
    for item in indexed.values():
        by_column.setdefault(int(item["column"]), []).append(item)
    for group in by_column.values():
        group.sort(key=lambda item: item["source_anchor"][1])
        for index, item in enumerate(group):
            types = {e["type"] for e in item["evidence"]}
            if "physical_body_indent" not in types or index == 0:
                continue
            y = item["source_anchor"][1]
            previous = group[index - 1]
            gap = y - previous["source_anchor"][1]
            prev_types = {e["type"] for e in previous["evidence"]}
            if (
                .8 * row_height <= gap <= 1.7 * row_height
                and "verified_bracket" in prev_types
            ):
                _append_evidence(
                    item, "post_bracket_continuation",
                    "physical_context", "moderate",
                    "紧接已确认括号词头的正文缩进续行候选",
                )

    for target in indexed.values():
        types = {item["type"] for item in target["evidence"]}
        physical = target["physical_row"]
        has_final = bool(target["final_entries"])
        if "layout_entry" in types and not has_final:
            target["issues"].append("layout_entry_without_final_line")
        if has_final and physical is None:
            target["issues"].append("final_line_without_matched_physical_row")
        if (
            has_final and physical is not None
            and str(physical.get("role", "")) == "body"
            and not ({"verified_bracket", "verified_large_head"} & types)
        ):
            target["issues"].append("final_line_on_body_without_strong_visual_proof")
        if "verified_large_head" in types and not has_final:
            target["issues"].append("accepted_large_head_without_final_line")
        if (
            has_final
            and "physical_body_indent" in types
            and not ({"verified_bracket", "verified_large_head"} & types)
        ):
            target["issues"].append("final_line_contradicts_body_indent")
        if has_final and "post_bracket_continuation" in types:
            target["issues"].append("possible_post_bracket_body_continuation")
        target["shadow_assessment"] = _shadow_assessment(target)
        target["has_final_line"] = has_final

    ordered = sorted(
        indexed.values(),
        key=lambda item: (
            item["column"], item["source_anchor"][1],
            item["source_anchor"][0], item["id"],
        ),
    )
    issues = [
        {"candidate_id": item["id"], "column": item["column"],
         "source_anchor": item["source_anchor"], "codes": list(item["issues"])}
        for item in ordered if item["issues"]
    ]
    return {
        "schema": SCHEMA,
        "matching_policy": {
            "coordinate_space": "source_image_px",
            "tolerance_px": match_tolerance,
            "causality": "spatial association only",
            "warning": "物理行/候选/线之间靠坐标匹配；邻近不等于由该证据生成",
        },
        "stage_definitions": {
            name: STAGE_DESCRIPTIONS.get(name, name) for name in stage_names
        },
        "registry": ordered,
        "review_queue": issues,
        "role_transitions": transition_events,
        "summary": {
            "physical_rows": len(rows),
            "candidates_total": len(ordered),
            "final_lines": len(final_lines),
            "visual_large_head_candidates": len(candidates),
            "review_items": len(issues),
            "issue_types": dict(Counter(
                code for item in issues for code in item["codes"]
            )),
            "shadow_assessment": dict(Counter(
                item["shadow_assessment"]["label"] for item in ordered
            )),
        },
        "policy": {
            "execution": "shadow_diagnostics_only",
            "production_output_changed": False,
            "ground_truth_available": False,
        },
    }


__all__ = [
    "SCHEMA", "STAGE_DESCRIPTIONS", "compose_ordinary_evidence_report",
]
