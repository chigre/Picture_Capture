"""Unified Layout, large-head and final-line evidence overlay.

The page's ordinary candidate registry is generated ONCE by the same read-only
snapshot used for JSON export. This overlay only paints canvas primitives and
offers click-to-inspect provenance; it never calls a detector with changed
thresholds or mutates AppSettings, PDIC or Entry records.
"""
from __future__ import annotations

from typing import Any

_TAG = "ordinary-unified-evidence-overlay"
_COLORS = {
    "review_conflict": "#d97706",
    "supported_headword": "#168342",
    "baseline_headword": "#168342",
    "body": "#2563eb",
    "uncertain": "#71717a",
}
_ISSUES = {
    "layout_entry_without_final_line": "Layout 判 entry，但最后没有画线",
    "final_line_without_matched_physical_row": "最终画线没有匹配到物理行",
    "final_line_on_body_without_strong_visual_proof": "最终线对应 body，但没有独立强视觉证据",
    "accepted_large_head_without_final_line": "大字候选通过，最终没有邻近分隔线",
    "final_line_contradicts_body_indent": "最终线与可靠的正文缩进带相矛盾",
    "possible_post_bracket_body_continuation": "疑似括号词头后的正文续行",
}


def format_candidate_detail(row: dict[str, Any]) -> str:
    physical = row.get("physical_row")
    source_x, source_y = row.get("source_anchor", [0, 0])
    evidence = row.get("evidence", [])
    final_lines = row.get("final_entries", [])
    stages = row.get("stage_trace", [])
    transitions = row.get("role_transitions", [])
    issues = row.get("issues", [])
    shadow = row.get("shadow_assessment", {})
    lines = [
        f"候选 ID：{row.get('id')} / C{int(row.get('column', -1))+1}",
        f"源图起点：({source_x}, {source_y})",
        (
            f"物理行：{physical.get('role','unknown')}"
            f" / first_x={physical.get('first_x')}"
            f" / corrected={physical.get('corrected_first_x')}"
            if physical else "物理行：未匹配（可能是括号/视觉补画）"
        ),
        f"最终自动线：{len(final_lines)} 条",
        f"只读影子判定：{shadow.get('label','unknown')}",
        f"原因：{shadow.get('reason','无')}",
        "注意：此判断不会改变最终画线，不是人工标注。",
        "",
        "证据：",
    ]
    lines.extend(
        "  " + e.get("type", "?") + " / " + e.get("strength", "?")
        + " / " + e.get("origin", "?")
        for e in evidence
    )
    if not evidence:
        lines.append("  无已知独立证据")
    lines.append("大字候选：")
    lines.extend(
        f"  H{int(g.get('index',0)):03d}: {g.get('status')} "
        f"(高度比 {float(g.get('height_ratio',0)):.2f})"
        for g in row.get("detector_matches", [])
    )
    if not row.get("detector_matches"):
        lines.append("  无邻近大字候选")
    lines.append("阶段输出位置：")
    lines.extend(
        f"  {s.get('stage')}: ({s.get('x')},{s.get('y')})"
        f" [{s.get('source') or 'unknown'}]"
        for s in stages
    )
    if not stages:
        lines.append("  无")
    if transitions:
        lines.append("角色变化：")
        lines.extend(
            f"  {change.get('stage')}: "
            f"{(change.get('before') or {}).get('role','—')} → "
            f"{(change.get('after') or {}).get('role','—')}"
            for change in transitions
        )
    if final_lines:
        lines.append(
            "最终线：" + ", ".join(
                f"({entry['x']},{entry['y']})[{entry.get('source','')}]"
                for entry in final_lines
            )
        )
    if issues:
        lines.append("需要复核：")
        lines.extend("  " + _ISSUES.get(issue, issue) for issue in issues)
    lines.append("注：多来源坐标关联仅是空间邻近，不代表因果。")
    return "\n".join(lines)


def draw_unified_candidate_overlay(
    app: Any, *, layout_enabled: bool,
) -> None:
    """Paint provenance markers on the very same registry exported as JSON."""
    canvas = getattr(app, "canvas", None)
    if canvas is None:
        return
    try:
        canvas.delete(_TAG)
    except Exception:
        return
    if not layout_enabled or getattr(app, "image", None) is None:
        return
    from .large_head_visualization_ui import get_large_head_debug_snapshot

    try:
        snapshot = get_large_head_debug_snapshot(app)
        report = snapshot.get("unified_report", {})
        registry = report.get("registry", [])
        summary = report.get("summary", {})
        if not registry:
            return
    except Exception as exc:
        canvas.create_text(
            12, 24, anchor="nw",
            text=f"统一候选审计不可用：{type(exc).__name__}",
            fill="#b91c1c", tags=(_TAG,),
        )
        return

    scale = float(getattr(app, "view_scale", 1.0) or 1.0)
    density_var = getattr(app, "_layout_display_density_var", None)
    density = str(density_var.get()) if density_var is not None else "详细"
    # Screen-space rectangles prevent dense candidate labels from colliding.
    # If two rows are very close at low zoom, alternate their label lanes.
    occupied: dict[int, list[tuple[float, float, float, float]]] = {}
    for row in registry:
        x, y = (int(v) for v in row["source_anchor"])
        # Keep tiny click-targets outside printed text; the existing Layout
        # strips still convey roles, these marks show output and conflicts.
        shadow = row.get("shadow_assessment", {})
        label = str(shadow.get("label", "uncertain"))
        has_final = bool(row.get("has_final_line", False))
        flagged = bool(row.get("issues"))
        if density == "简洁":
            # Only show genuinely suspicious decisions. Hundreds of green
            # markers otherwise obscure the actual scanned dictionary.
            if not flagged:
                continue
        elif not (flagged or has_final or (
            row.get("physical_row") and
            row["physical_row"].get("role") == "entry"
        )):
            continue
        color = _COLORS.get(label, "#71717a")
        # Original version painted a 6px box at (source_x-22)*zoom.
        # Column 1 commonly starts at x=0-20; those icons disappeared to the
        # left of the image and shrank below clickability when zoomed out.
        # These 16-20 SCREEN-pixel markers remain visible at every zoom.
        pos_x = max(26.0, x * scale + 14.0)
        pos_y = max(10.0, y * scale)
        radius = 10.0 if flagged else 8.0
        symbol = canvas.create_rectangle(
            pos_x-radius, pos_y-radius, pos_x+radius, pos_y+radius,
            outline=color, fill="#fff7ed" if flagged else color,
            width=3 if flagged else 1,
            tags=(_TAG,),
        )
        if flagged:
            symbol_label = canvas.create_text(
                pos_x, pos_y,
                text="!", anchor="center", fill="#9a3412",
                font=("TkDefaultFont", 11, "bold"),
                tags=(_TAG,),
            )

        def show(_event: Any, record: dict[str, Any] = row) -> str:
            from .ordinary_layout_inspector import show_unified_layout_inspector
            show_unified_layout_inspector(
                app, candidate_id=str(record["id"]),
            )
            # Never let a diagnostic click also trigger the canvas editor.
            return "break"

        canvas.tag_bind(symbol, "<Button-1>", show)
        if flagged:
            canvas.tag_bind(symbol_label, "<Button-1>", show)

        # Match the inspector's ID exactly (e.g. C02-R008). A small opaque
        # label sits immediately to the RIGHT of each marker; its text and
        # background are both clickable, rather than just the tiny square.
        identifier = str(row.get("id", "") or "")
        if identifier:
            col_index = int(row.get("column", -1))
            left0 = pos_x + radius + 4.0
            height = 17.0
            # TkFixedFont 8 is approximately 7px per ASCII character on
            # Windows/macOS; extra padding prevents clipping with fallback.
            width = max(38.0, len(identifier) * 7.3 + 10.0)
            top = pos_y - height / 2.0
            prior = occupied.setdefault(col_index, [])
            label_left = left0
            for lane in range(5):
                attempt_left = left0 + lane * (width + 7.0)
                attempt = (
                    attempt_left, attempt_left + width,
                    top, top + height,
                )
                if not any(
                    attempt[0] < other[1] + 3 and
                    attempt[1] > other[0] - 3 and
                    attempt[2] < other[3] + 2 and
                    attempt[3] > other[2] - 2
                    for other in prior
                ):
                    label_left = attempt_left
                    break
            # Keep the box attached to the corresponding glyph marker even
            # when the second label lane is needed; no Y reassignment.
            badge = canvas.create_rectangle(
                label_left, top, label_left + width, top + height,
                fill="#fff1df" if flagged else "#edf7f0",
                outline=color, width=1,
                tags=(_TAG,),
            )
            text_id = canvas.create_text(
                label_left + 5.0, pos_y,
                text=identifier, anchor="w",
                fill="#713f12" if flagged else "#14532d",
                font=("TkFixedFont", 8),
                tags=(_TAG,),
            )
            canvas.tag_bind(badge, "<Button-1>", show)
            canvas.tag_bind(text_id, "<Button-1>", show)
            prior.append((label_left, label_left + width, top, top + height))

    # Counters and verbose candidate statistics belong ONLY in the
    # independent inspector and copyable Layout panel, never over the scan.

__all__ = ["draw_unified_candidate_overlay", "format_candidate_detail"]
