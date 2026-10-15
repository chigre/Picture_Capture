"""Read-only visual audit of the final saved OCR and ordinary-fusion decisions.

Only the provenance-validated final-decisions sidecar is authoritative. Never
associate a candidate by nearest XY or re-run recognition to populate this UI.
"""
from __future__ import annotations

from typing import Any
import tkinter as tk
from tkinter import ttk

from ..formats import pdic_path
from ..ocr_final_decisions import load_current_final_decisions
from ..project_storage import ocr_cache_root


def summary_and_rows(report: dict[str, Any]) -> tuple[str, list[tuple[str, str, str, str, str]]]:
    stats = report.get("summary") or {}
    summary = (
        f"OCR候选 {int(stats.get('ocr_candidates', 0))}  ·  "
        f"最终PDIC {int(stats.get('final_markers', 0))}  ·  "
        f"确切对应 {int(stats.get('linked', 0))}  ·  "
        f"独立/未关联 {int(stats.get('unmatched_final', 0))}  ·  "
        f"删除 {int(stats.get('post_ocr_removed', 0))}  ·  "
        f"移动 {int(stats.get('post_ocr_moved', 0))}"
    )
    status_names = {
        "retained": "OCR保留",
        "removed_after_ocr": "后处理删除",
        "moved_by_post_ocr": "后处理移动",
        "rejected": "OCR拒绝",
    }
    rows: list[tuple[str, str, str, str, str]] = []
    for candidate in report.get("candidate_decisions") or []:
        status = str(candidate.get("final_status", "unknown"))
        x, y = candidate.get("final_source_x"), candidate.get("final_source_y")
        coords = f"{x}, {y}" if x is not None and y is not None else "—"
        rows.append((
            str(candidate.get("candidate_id", "") or "无候选ID"),
            status_names.get(status, status),
            str(candidate.get("final_word") or "—"),
            coords,
            str(candidate.get("ocr_decision_reason") or "—"),
        ))
    for final in report.get("final_only") or []:
        rows.append((
            "非唯一OCR来源", "独立最终词条", str(final.get("word") or "—"),
            f"{final.get('x')}, {final.get('y')}",
            str(final.get("reason") or "未能唯一关联"),
        ))
    return summary, rows


def show_ocr_decision_inspector(app: Any) -> None:
    """Inspect the actual saved PDIC; if stale/missing, explain without guessing."""
    parent = getattr(app, "root", None) or app
    window = tk.Toplevel(parent)
    window.title("OCR画线／融合画线 · 最终决策可视化（只读）")
    window.geometry("1000x630")
    body = ttk.Frame(window, padding=12)
    body.pack(fill="both", expand=True)
    ttk.Label(
        body, text="只读取已保存的 OCR 决策；与当前 PDIC/OCR 缓存不一致时禁止展示旧证据。",
        wraplength=950,
    ).pack(anchor="w", pady=(0, 8))
    status = tk.StringVar(value="")
    ttk.Label(body, textvariable=status, wraplength=950).pack(anchor="w", pady=(0, 8))
    tree = ttk.Treeview(
        body, columns=("id", "status", "word", "coord", "reason"),
        show="headings", selectmode="browse",
    )
    for col, heading, width in (
        ("id", "候选ID/来源", 200), ("status", "最终处理", 115),
        ("word", "PDIC词条", 175), ("coord", "原图 X,Y", 110),
        ("reason", "识别/后处理原因", 335),
    ):
        tree.heading(col, text=heading)
        tree.column(col, width=width, stretch=col in {"word", "reason"})
    scroll = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    page = getattr(app, "current_page", None)
    project = getattr(app, "project", None)
    if page is None or project is None:
        status.set("尚未打开项目/页面。")
        return
    cache = ocr_cache_root(project.root) / f"{page.stem}.json"
    try:
        data = load_current_final_decisions(cache, pdic_path(page))
    except (OSError, ValueError, TypeError):
        data = None
    if data is None:
        status.set("当前页尚无有效的最终 OCR/融合决策记录，或 PDIC/OCR 缓存已发生变化。请重新运行对应画线再查看；不使用过期坐标猜测。")
        return
    summary, rows = summary_and_rows(data)
    status.set(summary)
    for row in rows:
        tree.insert("", "end", values=row)
