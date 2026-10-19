"""Opt-in, read-only snapshots of the *production* Layout decision sequence.

No source images, PIL objects, Entry objects or mutable Layout instances are
retained. Snapshots are plain Python values in source-image coordinates. This
module has no Tk imports and cannot change detection or save project files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PARAMETERS = (
    "columns", "start_y", "bottom_y", "manual_x", "column_width",
    "gutter", "character_height", "row_padding",
)


def _plain_parameters(value: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    if value is None:
        return result
    for name in PARAMETERS:
        try:
            candidate = getattr(value, name)
            if candidate is not None:
                result[name] = int(candidate)
        except (AttributeError, TypeError, ValueError, OverflowError):
            pass
    return result


def _source_point(layout: Any, x: float, y: float) -> tuple[int, int]:
    try:
        return tuple(int(v) for v in layout.transform.canonical_to_source_point(
            int(round(x)), int(round(y)), layout.source_size,
        ))
    except (AttributeError, TypeError, ValueError):
        # Explicit fallback only for synthetic/test Layout objects without a
        # transform. Real product Layouts always provide canonical_to_source.
        return int(round(x)), int(round(y))


def diff_rows(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare physical row *keys*, not recycled Python object IDs."""
    old = {item["id"]: item for item in before}
    new = {item["id"]: item for item in after}
    changes: list[dict[str, Any]] = []
    for key in sorted(set(old) | set(new)):
        previous, current = old.get(key), new.get(key)
        if previous is None:
            changes.append({"id": key, "kind": "added", "before": None,
                            "after": current["role"]})
        elif current is None:
            changes.append({"id": key, "kind": "removed", "before": previous["role"],
                            "after": None})
        elif previous["role"] != current["role"]:
            changes.append({"id": key, "kind": "role", "before": previous["role"],
                            "after": current["role"]})
    return changes


@dataclass
class LayoutStepTrace:
    """Retains only geometry and small row dictionaries, never image buffers."""

    stages: list[dict[str, Any]] = field(default_factory=list)
    _last_rows: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def add_note(self, key: str, title: str, description: str,
                 *, details: dict[str, Any] | None = None,
                 candidates: list[dict[str, Any]] | None = None) -> None:
        self.stages.append({
            "key": key, "title": title, "description": description,
            "details": dict(details or {}), "columns": [], "lanes": [], "rows": [], "changes": [], "candidates": [dict(x) for x in (candidates or ())],
        })

    def add_policy(self, estimate: Any, used: Any,
                   applied: dict[str, int]) -> None:
        if estimate is not None:
            self.add_note("raw_estimate", "自动版面候选",
                          "自动检测器的原始建议；尚未按 Profile 和逐字段开关采用。",
                          details={
                              "raw": _plain_parameters(estimate),
                              "method": str(getattr(estimate, "method", "")),
                              "confidence": getattr(estimate, "confidence", None),
                          })
        else:
            self.add_note("raw_estimate", "自动版面候选",
                          "当前未启用逐页自动参数检测；没有原始自动候选。")
        self.add_note("effective_parameters", "最终采用的版面参数",
                      "以下是本次实际计算所用的 Project/Profile 参数及自动采用项。",
                      details={
                          "used": _plain_parameters(used),
                          "applied": dict(applied),
                      })

    def add_projection_stages(
        self, column_runs: list[dict[str, Any]], layout: Any, *,
        pass_count: int,
    ) -> None:
        """Replay the FINAL real policy projection pass in source coordinates.

        Early seed/reference passes are used to choose line scale and body
        extent; only the last body-bounded pass actually feeds LayoutLine.
        No pixels, image copies, or fabricated recomputations are retained.
        """
        if not column_runs:
            self.add_note(
                "projection_unavailable", "物理行投影阶段未记录",
                "当前 Layout 使用的不是可追踪的物理投影原语；"
                "不能根据最终物理行伪造连接或拆分历史。",
            )
            return

        gap_candidates: list[dict[str, Any]] = []
        split_candidates: list[dict[str, Any]] = []
        per_column: list[dict[str, Any]] = []

        for item in column_runs:
            evidence = item["evidence"]
            left = int(item["left"])
            right = left + int(item["strip_width"])
            top = int(item["top"])
            column = int(item["column"])

            def rectangle(y0: int, y1: int) -> list[int]:
                # The projector samples only the leading text strip of each
                # column, not the whole column/word bounding box.
                start = _source_point(layout, left, top + int(y0))
                stop = _source_point(layout, right, top + int(y1))
                return [*start, *stop]

            def record(
                target: list[dict[str, Any]], kind: str, values: Any,
                message: str, *,
                extra: dict[str, Any] | None = None,
            ) -> None:
                for y0, y1 in values:
                    target.append({
                        "status": kind,
                        "column": column + 1,
                        "source_box": rectangle(y0, y1),
                        "canonical_y": [int(top+y0), int(top+y1)],
                        "reason": message,
                        **(extra or {}),
                    })

            record(gap_candidates, "raw_band", evidence["original_runs"],
                   "达到投影墨迹阈值、尚未连接的原始连续墨迹带")
            record(gap_candidates, "connected_band", evidence["connected_runs"],
                   "原始墨迹带经过允许的短空白行连接之后的结果")
            record(gap_candidates, "bridged_gap", evidence["bridged_gaps"],
                   "原始墨迹间的短空白段，被投影算法连接（没有修改图像像素）")
            record(split_candidates, "connected_band", evidence["connected_runs"],
                   "拆分前的连续墨迹带")
            record(split_candidates, "retained_row", evidence["final_runs"],
                   "本次投影实际输出的逻辑行段；仍需经过后续物理行特征筛选")
            record(split_candidates, "ignored_short", evidence["ignored_short"],
                   "高度小于行高下限，投影未保留")
            for event in evidence["valley_splits"]:
                at = int(event["at_y"])
                record(split_candidates, "split_valley", [(at, at+1)],
                       "过高墨迹带在真实墨迹密度低谷处拆分",
                       extra={
                           "parent_y": list(event["parent"]),
                           "valley_ink": event["valley_ink"],
                           "limit": event["limit"],
                       })
            for event in evidence["logical_slots"]:
                record(split_candidates, "fallback_slot", event["slots"],
                       "未能用明显墨迹谷分开，按高度约束生成的逻辑槽位",
                       extra={"parent_y": list(event["parent"])})

            per_column.append({
                "column": column + 1,
                "sample_strip_width": int(item["strip_width"]),
                "configured_column_width": int(item.get("column_width", item["strip_width"])),
                "requested_width_percent": float(item.get("requested_percent", 42.0)),
                "effective_width_percent": round(
                    100.0 * int(item["strip_width"])
                    / max(1, int(item.get("column_width", item["strip_width"]))),
                    2,
                ),
                "projection_threshold": evidence["threshold"],
                "row_height_reference": evidence["reference_height"],
                "gap_limit_px": evidence["max_gap_px"],
                "raw_bands": len(evidence["original_runs"]),
                "connected_bands": len(evidence["connected_runs"]),
                "bridged_gaps": len(evidence["bridged_gaps"]),
                "valley_splits": len(evidence["valley_splits"]),
                "logical_slots": sum(len(e["slots"]) for e in evidence["logical_slots"]),
                "short_rejected": len(evidence["ignored_short"]),
                "output_rows": len(evidence["final_runs"]),
            })

        shared = {
            "projection_pass_count": int(pass_count),
            "shown_pass": "最后一轮：已确定正文范围及行高先验",
            "columns": per_column,
            "sample_domain": "每栏行首采样条带，不是全栏笔画连通或图像膨胀",
        }
        self.add_note(
            "projection_gap_bridge", "墨迹投影与短间隙连接",
            "从真实的行首条带墨迹投影得到原始带；只连接阈值以内的"
            "连续空白扫描行，不改变图像像素。橙色表示实际连接的间隙。",
            details=shared,
            candidates=gap_candidates,
        )
        self.add_note(
            "projection_tall_split", "过高墨迹带拆分与逻辑行恢复",
            "从刚才连接的墨迹带中，按真实墨迹谷拆分过高带；"
            "仍未分开的过高带可能按行高生成逻辑槽位。"
            "绿色为输出行，紫色为墨迹谷拆分，黄色为逻辑槽位。",
            details=shared,
            candidates=split_candidates,
        )

    def add_layout(self, key: str, title: str, description: str,
                   layout: Any, *, details: dict[str, Any] | None = None,
                   candidates: list[dict[str, Any]] | None = None,
                   provisional_no_indent: bool = False) -> None:
        """Freeze source-aligned rectangles at exactly one production boundary."""
        top = int(getattr(layout, "body_top", 0))
        bottom = int(getattr(layout, "body_bottom", 0))
        columns: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        lanes: list[dict[str, Any]] = []
        for col_index, col in enumerate(getattr(layout, "columns", ()) or ()):
            left = int(getattr(col, "left", 0))
            right = int(getattr(col, "right", left))
            p0 = _source_point(layout, left, top)
            p1 = _source_point(layout, right, bottom)
            columns.append({"index": col_index, "source_start": list(p0),
                            "source_end": list(p1), "left": left,
                            "right": right, "top": top, "bottom": bottom})
            # Indent modes are measured in local column X coordinates.
            # Copy their evidence without retaining the mutable mode objects.
            for lane_index, mode in enumerate(getattr(col, "indent_modes", ()) or ()):
                center = float(getattr(mode, "center", 0) or 0)
                tolerance = float(getattr(mode, "tolerance", 0) or 0)
                lane_top = _source_point(layout, left + center, top)
                lane_bottom = _source_point(layout, left + center, bottom)
                lanes.append({
                    "id": f"C{col_index+1}-L{lane_index+1}",
                    "column": col_index, "center": center,
                    "tolerance": tolerance,
                    "support": int(getattr(mode, "support", 0) or 0),
                    "role": ("unclassified" if provisional_no_indent else
                             str(getattr(mode, "role", "unknown"))),
                    "raw_provisional_role": str(getattr(mode, "role", "unknown")),
                    "source_line": [*lane_top, *lane_bottom],
                })
            for line in getattr(col, "lines", ()) or ():
                y0 = top + int(getattr(line, "y0", 0))
                y1 = top + int(getattr(line, "y1", 0))
                p0 = _source_point(layout, left, y0)
                p1 = _source_point(layout, right, y1)
                row_id = f"C{col_index+1}-Y{y0}-{y1}"
                rows.append({
                    "id": row_id, "column": col_index,
                    "source_box": [p0[0], p0[1], p1[0], p1[1]],
                    "canonical_y": y0,
                    "role": ("unclassified" if provisional_no_indent else
                             str(getattr(line, "role", "unknown"))),
                    "raw_provisional_role": str(getattr(line, "role", "unknown")),
                    "first_x": float(getattr(line, "first_x", 0) or 0),
                })
        changes = diff_rows(self._last_rows, rows) if self._last_rows else []
        self.stages.append({
            "key": key, "title": title, "description": description,
            "details": dict(details or {}),
            "provisional_no_indent": bool(provisional_no_indent),
            "columns": columns, "lanes": lanes, "rows": rows, "changes": changes,
            "candidates": [dict(item) for item in (candidates or ())],
        })
        self._last_rows = rows

    def adopt_unshown_role_baseline(self, layout: Any) -> None:
        """Update row-diff baseline after a mandatory but non-semantic reset.

        In explicit no-indent mode, the Page Design provisional roles must be
        cleared to 'body' so downstream independent detectors have a neutral
        starting state. That administrative normalization is intentionally not
        a user-visible stage; without resetting the baseline here, the next
        visual-check stage would falsely claim 140 role promotions.
        """
        before = len(self.stages)
        self.add_layout(
            "__internal_neutral_baseline__", "内部中性角色初始化",
            "无明显缩进：仅将物理行的历史临时标签归零，不参与词头推断。",
            layout,
        )
        self.stages.pop()
        assert len(self.stages) == before

    def add_entries(
        self, stage: dict[str, Any], *, description: str,
    ) -> None:
        """Freeze *actual* ordinary-drawing marker states, including provenance.

        Position-only diffs miss upgrades to ordinary_bracket_pair at the same
        coordinates. Keep those separate from physical-row role changes.
        """
        markers = [dict(item) for item in stage.get("entries", [])]
        earlier = next((
            item["entries"] for item in reversed(self.stages)
            if "entries" in item
        ), [])
        old = {(m["x"], m["y"]): m for m in earlier}
        new = {(m["x"], m["y"]): m for m in markers}
        changes = []
        for anchor in sorted(set(old) | set(new)):
            before, after = old.get(anchor), new.get(anchor)
            if before is None:
                kind = "added"
            elif after is None:
                kind = "removed"
            elif (before.get("source"), before.get("issue_type"), before.get("oversized")) != (
                after.get("source"), after.get("issue_type"), after.get("oversized")
            ):
                kind = "provenance_changed"
            else:
                continue
            changes.append({
                "x": anchor[0], "y": anchor[1], "kind": kind,
                "before": dict(before) if before else None,
                "after": dict(after) if after else None,
            })
        details = {
            k: v for k, v in stage.items()
            if k not in {"stage", "entries", "added", "removed", "candidates"}
        }
        self.stages.append({
            "key": stage["stage"], "title": description,
            "description": "来自 processing.detect_entries 真实普通画线阶段；"
                           "红点为当前画线候选，绿圈为新增或证据升级，橙叉为删除。",
            "details": details, "columns": [], "lanes": [], "rows": [],
            "changes": [], "candidates": [
                dict(item) for item in stage.get("candidates", [])
            ], "entries": markers,
            "entry_changes": changes,
        })

    def history_for_entry(self, x: int, y: int) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        previous = None
        for stage in self.stages:
            if "entries" not in stage:
                continue
            item = next((m for m in stage["entries"]
                         if m["x"] == x and m["y"] == y), None)
            state = str(item["source"]) if item else "absent"
            if state != previous:
                history.append({"stage": stage["title"], "role": state})
                previous = state
        return history

    def history_for_row(self, row_id: str) -> list[dict[str, str]]:
        """Chronological role history from frozen, *actual* Layout stage data."""
        history: list[dict[str, str]] = []
        prior: str | None = None
        for stage in self.stages:
            if not stage["rows"]:
                continue
            current = next((r for r in stage["rows"] if r["id"] == row_id), None)
            role = current["role"] if current is not None else "absent"
            if role != prior:
                history.append({
                    "stage": stage["title"], "role": role,
                    "reason": stage["description"],
                })
                prior = role
            if stage.get("provisional_no_indent") and current is not None:
                # A no-indent page has an invisible, *mandatory* administrative
                # role reset before actual visual evidence. Show it in a
                # clicked row's history so 'unclassified -> body' cannot be
                # falsely attributed to symbol evidence, without making it a
                # numbered, interactive Layout inference stage.
                history.append({
                    "stage": "内部中性角色初始化（非词头识别步骤）",
                    "role": "body",
                    "reason": "无明显缩进：清除 Page Design 临时词头标签；"
                              "物理行全部以中性 body 开始，不能据缩进推断词条。",
                })
                prior = "body"
        return history

    def final_roles(self) -> list[tuple[str, str]]:
        return [(row["id"], row["role"]) for row in self._last_rows]
