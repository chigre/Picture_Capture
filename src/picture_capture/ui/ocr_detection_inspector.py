"""Read-only visual audit of the final saved OCR and ordinary-fusion decisions.

Only the provenance-validated final-decisions sidecar is authoritative. Never
associate a candidate by nearest XY or re-run recognition to populate this UI.
"""
from __future__ import annotations

from typing import Any
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

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


def preview_markers(report: dict[str, Any]) -> list[tuple[int, int, str]]:
    """Only saved final coordinates are plotted; no nearest-candidate inference."""
    points: list[tuple[int, int, str]] = []
    for candidate in report.get("candidate_decisions") or []:
        if not candidate.get("final_selected"):
            continue
        x, y = candidate.get("final_source_x"), candidate.get("final_source_y")
        if x is None or y is None:
            continue
        try:
            points.append((int(x), int(y), str(candidate.get("final_status", "unknown"))))
        except (TypeError, ValueError):
            pass
    for row in report.get("final_only") or []:
        try:
            points.append((int(row["x"]), int(row["y"]), "unlinked"))
        except (KeyError, TypeError, ValueError):
            pass
    return points


def _draw_saved_markers(canvas: tk.Canvas, app: Any, report: dict[str, Any], window: tk.Toplevel) -> None:
    """An image-aligned, purely local inspection view; never redraw app canvas."""
    source = getattr(app, "image", None)
    if source is None or not isinstance(source, Image.Image):
        return
    thumb = source.copy()
    try:
        thumb.thumbnail((490, 530), Image.Resampling.LANCZOS)
        size = thumb.size
        photo = ImageTk.PhotoImage(thumb, master=window)
    finally:
        thumb.close()
    window._ocr_decision_preview_photo = photo  # retain Tk image lifetime
    canvas.configure(width=size[0], height=size[1], scrollregion=(0, 0, *size))
    canvas.create_image(0, 0, image=photo, anchor="nw")
    scale_x, scale_y = size[0] / source.width, size[1] / source.height
    colors = {"retained": "#00ae55", "moved_by_post_ocr": "#fd6a13", "unlinked": "#2b65e8"}
    for x, y, provenance in preview_markers(report):
        if not (0 <= x < source.width and 0 <= y < source.height):
            continue
        px, py = x * scale_x, y * scale_y
        color = colors.get(provenance, "#9950d0")
        canvas.create_line(max(0, px - 18), py, min(size[0], px + 18), py,
                           fill=color, width=2)
        canvas.create_oval(px - 3, py - 3, px + 3, py + 3,
                           outline=color, fill="#ffffff", width=2)


def show_ocr_decision_inspector(app: Any) -> None:
    """Inspect the actual saved PDIC; if stale/missing, explain without guessing."""
    parent = getattr(app, "root", None) or app
    window = tk.Toplevel(parent)
    window.title("OCR画线／融合画线 · 最终决策可视化（只读）")
    window.geometry("1280x690")
    body = ttk.Frame(window, padding=12)
    body.pack(fill="both", expand=True)
    ttk.Label(
        body, text="只读取已保存的 OCR 决策；与当前 PDIC/OCR 缓存不一致时禁止展示旧证据。",
        wraplength=950,
    ).pack(anchor="w", pady=(0, 8))
    status = tk.StringVar(value="")
    ttk.Label(body, textvariable=status, wraplength=950).pack(anchor="w", pady=(0, 8))
    content = ttk.Frame(body)
    content.pack(fill="both", expand=True)
    table_panel = ttk.Frame(content)
    table_panel.pack(side="left", fill="both", expand=True)
    preview_panel = ttk.Frame(content)
    preview_panel.pack(side="right", fill="both", padx=(12, 0))
    ttk.Label(preview_panel, text="最终已保存画线（只读）\n绿色：OCR保留  橙色：后处理移动  蓝色：独立最终词条",
              justify="left").pack(anchor="w", pady=(0, 6))
    preview_canvas = tk.Canvas(preview_panel, background="#f2f2f2", highlightthickness=0)
    preview_canvas.pack(fill="both", expand=True)
    tree = ttk.Treeview(
        table_panel, columns=("id", "status", "word", "coord", "reason"),
        show="headings", selectmode="browse",
    )
    for col, heading, width in (
        ("id", "候选ID/来源", 200), ("status", "最终处理", 115),
        ("word", "PDIC词条", 175), ("coord", "原图 X,Y", 110),
        ("reason", "识别/后处理原因", 335),
    ):
        tree.heading(col, text=heading)
        tree.column(col, width=width, stretch=col in {"word", "reason"})
    scroll = ttk.Scrollbar(table_panel, orient="vertical", command=tree.yview)
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
    _draw_saved_markers(preview_canvas, app, data, window)
