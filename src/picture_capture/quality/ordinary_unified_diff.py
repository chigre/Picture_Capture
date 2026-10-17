"""Compare two exported unified ordinary Layout diagnostics, offline.

Uses only source-image coordinates and explicit line/role/candidate observations.
Avoids treating auto-baseline/PDIC as human truth. The older v1 big-head
diagnostic JSON format is accepted for backward comparison.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "picture-capture-ordinary-evidence-diff-v1"


def _point(line: dict[str, Any]) -> tuple[int, int]:
    return int(line["x"]), int(line["y"])


def _line_matches(
    earlier: list[dict[str, Any]],
    later: list[dict[str, Any]],
    tolerance: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    proposals = []
    for i, old in enumerate(earlier):
        for j, new in enumerate(later):
            dx = abs(_point(old)[0] - _point(new)[0])
            dy = abs(_point(old)[1] - _point(new)[1])
            if dx <= tolerance and dy <= tolerance:
                proposals.append((dy, dx, i, j))
    proposals.sort()
    seen_old: set[int] = set()
    seen_new: set[int] = set()
    matched = []
    for _dy, _dx, i, j in proposals:
        if i in seen_old or j in seen_new:
            continue
        seen_old.add(i)
        seen_new.add(j)
        matched.append({
            "before": dict(earlier[i]),
            "after": dict(later[j]),
            "shift_x": _point(later[j])[0] - _point(earlier[i])[0],
            "shift_y": _point(later[j])[1] - _point(earlier[i])[1],
        })
    removed = [dict(entry) for i, entry in enumerate(earlier) if i not in seen_old]
    added = [dict(entry) for j, entry in enumerate(later) if j not in seen_new]
    return matched, removed, added


def _physical_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    layout = report.get("layout_snapshot", {})
    return list(layout.get("physical_rows", []) or [])


def _role_changes(before: dict[str, Any], after: dict[str, Any],
                  tolerance: int) -> list[dict[str, Any]]:
    older = _physical_rows(before)
    newer = _physical_rows(after)
    seen: set[int] = set()
    changes = []
    for prior in older:
        options = [
            (abs(int(prior["source_y"]) - int(row["source_y"])), j, row)
            for j, row in enumerate(newer)
            if j not in seen and int(prior["column"]) == int(row["column"])
            and abs(int(prior["source_y"]) - int(row["source_y"])) <= tolerance
        ]
        if not options:
            continue
        _dist, j, new = min(options, key=lambda item: (item[0], item[1]))
        seen.add(j)
        old_role, new_role = prior.get("role"), new.get("role")
        old_source, new_source = prior.get("entry_source"), new.get("entry_source")
        if old_role != new_role or old_source != new_source:
            changes.append({
                "before_y": int(prior["source_y"]),
                "after_y": int(new["source_y"]),
                "column": int(prior["column"]),
                "before_role": old_role, "after_role": new_role,
                "before_source": old_source, "after_source": new_source,
            })
    return changes


def compare_ordinary_diagnostics(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    tolerance_px: int = 12,
) -> dict[str, Any]:
    if tolerance_px < 0:
        raise ValueError("tolerance_px must be nonnegative")
    earlier_page = before.get("page_index")
    later_page = after.get("page_index")
    if (
        earlier_page is not None and later_page is not None
        and int(earlier_page) != int(later_page)
    ):
        raise ValueError("两份诊断不是同一个 page_index，禁止比较")
    hash_before = str(before.get("image_sha256") or "")
    hash_after = str(after.get("image_sha256") or "")
    if hash_before and hash_after and hash_before != hash_after:
        raise ValueError("源图内容SHA256不一致，禁止比较不同扫描页面")
    size_before = tuple(before.get("image_size", ()) or ())
    size_after = tuple(after.get("image_size", ()) or ())
    if size_before and size_after and size_before != size_after:
        raise ValueError(
            "不能直接比较不同原图尺寸；请先导出同一原图坐标系的诊断"
        )

    earlier = list(before.get("final_lines", []) or [])
    later = list(after.get("final_lines", []) or [])
    matched, removed, added = _line_matches(earlier, later, tolerance_px)
    role_changed = _role_changes(before, after, tolerance_px)
    old_review = before.get("review_queue", []) or []
    new_review = after.get("review_queue", []) or []
    before_head = before.get("summary", {}) or {}
    after_head = after.get("summary", {}) or {}
    old_unified = (before.get("unified_report") or {}).get("summary", {}) or {}
    new_unified = (after.get("unified_report") or {}).get("summary", {}) or {}
    result = {
        "schema": SCHEMA,
        "same_image_size": not size_before or not size_after
                           or size_before == size_after,
        "image_size": list(size_after or size_before),
        "image_sha256_checked": bool(hash_before and hash_after),
        "same_page_index_checked": earlier_page is not None and later_page is not None,
        "tolerance_px": tolerance_px,
        "matched_lines": matched,
        "removed_lines": removed,
        "added_lines": added,
        "layout_role_changes": role_changed,
        "counts": {
            "before_lines": len(earlier),
            "after_lines": len(later),
            "matched": len(matched),
            "removed": len(removed), "added": len(added),
            "shifted": sum(
                item["shift_x"] != 0 or item["shift_y"] != 0
                for item in matched
            ),
            "layout_role_changes": len(role_changed),
            "before_review": len(old_review),
            "after_review": len(new_review),
            "before_accepted_large_heads": int(before_head.get("accepted", 0)),
            "after_accepted_large_heads": int(after_head.get("accepted", 0)),
            "before_registry_rows": int(old_unified.get("candidates_total", 0)),
            "after_registry_rows": int(new_unified.get("candidates_total", 0)),
        },
        "ground_truth": "not_provided",
        "interpretation": (
            "匹配只比较线坐标；并不能证明新增/删除哪一条是正确的。"
            "必须使用人工审核边界才能计算Precision/Recall/F1。"
        ),
    }
    return result


__all__ = ["SCHEMA", "compare_ordinary_diagnostics"]
