"""A usable, page-level Layout evidence inspector.

The inspector reads exactly the same cached unified report as JSON export and
the overlay. It is a session-only diagnostic view, never a PDIC editor.
"""
from __future__ import annotations

from typing import Any


_FILTERS = (
    "待复核（优先）",
    "全部候选",
    "最终自动线",
    "Layout词头",
    "大字候选",
)


def _filtered_registry(
    registry: list[dict[str, Any]], mode: str,
) -> list[dict[str, Any]]:
    if mode == _FILTERS[0]:
        return [item for item in registry if item.get("issues")]
    if mode == _FILTERS[2]:
        return [item for item in registry if item.get("final_entries")]
    if mode == _FILTERS[3]:
        return [item for item in registry
                if (item.get("physical_row") or {}).get("role") == "entry"]
    if mode == _FILTERS[4]:
        return [item for item in registry if item.get("detector_matches")]
    return list(registry)


def _row_values(row: dict[str, Any]) -> tuple[str, ...]:
    pos = row.get("source_anchor", [0, 0])
    physical = row.get("physical_row") or {}
    issues = row.get("issues") or []
    evidence = row.get("evidence") or []
    from .ordinary_unified_visualization import _ISSUES
    return (
        str(row.get("id", "")),
        str(int(row.get("column", -1)) + 1),
        str(int(pos[1])),
        str(physical.get("role", "—")),
        "是" if row.get("final_entries") else "否",
        " · ".join(str(item.get("type", "")) for item in evidence) or "—",
        "；".join(_ISSUES.get(issue, issue) for issue in issues) if issues else "—",
    )


def focus_layout_candidate(app: Any, row: dict[str, Any]) -> bool:
    """Scroll to the actual source-image position and highlight it visibly."""
    canvas = getattr(app, "canvas", None)
    picture = getattr(app, "image", None)
    if canvas is None or picture is None:
        return False
    scale = max(0.01, float(getattr(app, "view_scale", 1.0) or 1.0))
    sx, sy = (float(value) for value in row.get("source_anchor", [0, 0]))
    source_x, source_y = sx * scale, sy * scale
    tag = "ordinary-layout-inspector-highlight"
    try:
        canvas.delete(tag)
        viewport_h = max(1.0, float(canvas.winfo_height()))
        viewport_w = max(1.0, float(canvas.winfo_width()))
        total_h = max(viewport_h, float(picture.height) * scale)
        total_w = max(viewport_w, float(picture.width) * scale)
        canvas.yview_moveto(max(
            0.0, min(1.0,
                     (source_y - viewport_h / 2) /
                     max(1.0, total_h - viewport_h)),
        ))
        canvas.xview_moveto(max(
            0.0, min(1.0,
                     (source_x - viewport_w / 3) /
                     max(1.0, total_w - viewport_w)),
        ))
        # The rectangle is display-pixel sized, even at a reduced zoom level.
        left = max(1.0, source_x - 15.0)
        top = max(1.0, source_y - 15.0)
        canvas.create_rectangle(
            left, top, source_x + 33.0, source_y + 33.0,
            outline="#d97706", width=3, dash=(7, 4),
            tags=(tag,),
        )
        canvas.tag_raise(tag)
        return True
    except Exception:
        return False


def show_unified_layout_inspector(
    app: Any, *, candidate_id: str | None = None,
) -> None:
    """Open a readable, searchable per-candidate audit panel.

    The view never recalculates thresholds or modifies Layout, settings,
    saved PDIC, or the automatic baseline.
    """
    import tkinter as tk
    from tkinter import ttk, messagebox

    from .large_head_visualization_ui import (
        export_large_head_debug_json, get_large_head_debug_snapshot,
    )
    from .ordinary_unified_visualization import format_candidate_detail

    try:
        snapshot = get_large_head_debug_snapshot(app)
        report = snapshot.get("unified_report", {})
        registry = list(report.get("registry", []) or [])
        summary = dict(report.get("summary", {}) or {})
        if not report:
            raise RuntimeError(snapshot.get("message") or "统一Layout数据不可用")
    except Exception as exc:
        messagebox.showerror(
            "Layout 诊断不可用", str(exc),
            parent=getattr(app, "root", None),
        )
        return

    existing = getattr(app, "_ordinary_layout_inspector_window", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.destroy()
        except Exception:
            pass

    parent = getattr(app, "root", None)
    dialog = tk.Toplevel(parent)
    app._ordinary_layout_inspector_window = dialog
    dialog.title(f"Layout 候选与最终画线审计 — 第{int(getattr(app,'current_index',0))+1}页")
    dialog.geometry("1100x660")
    dialog.minsize(780, 460)
    dialog.transient(parent)
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(2, weight=1)

    headline = (
        f"物理行 {summary.get('physical_rows', 0)}    "
        f"候选 {summary.get('candidates_total', 0)}    "
        f"最终自动线 {summary.get('final_lines', 0)}    "
        f"需复核 {summary.get('review_items', 0)}"
    )
    ttk.Label(
        dialog, text=headline, font=("TkDefaultFont", 11, "bold"),
    ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 5))

    actions = ttk.Frame(dialog)
    actions.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
    ttk.Label(actions, text="筛选").pack(side="left")
    filter_var = tk.StringVar(value=_FILTERS[0] if summary.get("review_items") else _FILTERS[1])
    mode_box = ttk.Combobox(
        actions, state="readonly", width=17,
        values=_FILTERS, textvariable=filter_var,
    )
    mode_box.pack(side="left", padx=(5, 12))
    ttk.Label(
        actions, text="点击一行查看证据；双击定位扫描图（源图坐标）",
    ).pack(side="left", padx=(0, 12))
    ttk.Button(
        actions, text="导出同一份 JSON",
        command=lambda: export_large_head_debug_json(app),
    ).pack(side="right")

    content = ttk.Panedwindow(dialog, orient="horizontal")
    content.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 10))
    left = ttk.Frame(content)
    right = ttk.Frame(content)
    content.add(left, weight=3)
    content.add(right, weight=2)

    left.columnconfigure(0, weight=1)
    left.rowconfigure(0, weight=1)
    columns = ("id", "col", "y", "role", "final", "evidence", "issues")
    table = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
    for key, heading, width in (
        ("id", "候选 ID", 90), ("col", "栏", 42), ("y", "Y", 64),
        ("role", "Layout", 65), ("final", "有最终线", 76),
        ("evidence", "证据", 230), ("issues", "待复核原因", 260),
    ):
        table.heading(key, text=heading)
        table.column(key, width=width, anchor="w", stretch=key in {"evidence", "issues"})
    table.tag_configure("review", foreground="#9a3412")
    table.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(left, orient="vertical", command=table.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    table.configure(yscrollcommand=scroll.set)

    right.columnconfigure(0, weight=1)
    right.rowconfigure(0, weight=1)
    detail = tk.Text(right, wrap="word", state="disabled", width=41, height=20)
    detail.grid(row=0, column=0, sticky="nsew", padx=(8, 0))
    detail_scroll = ttk.Scrollbar(right, orient="vertical", command=detail.yview)
    detail_scroll.grid(row=0, column=1, sticky="ns")
    detail.configure(yscrollcommand=detail_scroll.set)

    by_id = {str(row["id"]): row for row in registry}

    def selection() -> dict[str, Any] | None:
        chosen = table.selection()
        return by_id.get(str(chosen[0])) if chosen else None

    def show_details(_event: Any = None) -> None:
        item = selection()
        message = format_candidate_detail(item) if item is not None else "请选择一个候选"
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        detail.insert("1.0", message)
        detail.configure(state="disabled")

    def locate(_event: Any = None) -> None:
        item = selection()
        if item is not None:
            focus_layout_candidate(app, item)

    def refill(_event: Any = None) -> None:
        previous = table.selection()
        wanted = str(previous[0]) if previous else candidate_id
        table.delete(*table.get_children())
        for item in _filtered_registry(registry, filter_var.get()):
            name = str(item["id"])
            table.insert(
                "", "end", iid=name, values=_row_values(item),
                tags=("review",) if item.get("issues") else (),
            )
        displayed = table.get_children()
        if displayed:
            chosen = wanted if wanted in displayed else displayed[0]
            table.selection_set(chosen)
            table.focus(chosen)
            table.see(chosen)
        show_details()

    mode_box.bind("<<ComboboxSelected>>", refill)
    table.bind("<<TreeviewSelect>>", show_details)
    table.bind("<Double-1>", locate)
    ttk.Button(
        actions, text="定位选中候选", command=locate,
    ).pack(side="right", padx=(0, 8))
    if candidate_id and candidate_id in by_id:
        match = by_id[candidate_id]
        if match.get("issues"):
            filter_var.set(_FILTERS[0])
        else:
            filter_var.set(_FILTERS[1])
    refill()
    dialog.protocol(
        "WM_DELETE_WINDOW",
        lambda: (setattr(app, "_ordinary_layout_inspector_window", None),
                 dialog.destroy()),
    )


def add_unified_layout_inspector_controls(app: Any, section: Any) -> None:
    """Add an explicit inspector button to the legacy non-compact panel."""
    from tkinter import ttk
    from .layout_visualization_ui_v3 import _next_grid_row

    if getattr(app, "_ordinary_layout_inspector_button", None) is not None:
        return
    button = ttk.Button(
        section, text="查看Layout候选/异常",
        command=lambda: show_unified_layout_inspector(app),
    )
    button.grid(
        row=_next_grid_row(section), column=0,
        columnspan=4, sticky="w", pady=(3, 0),
    )
    app._ordinary_layout_inspector_button = button


__all__ = [
    "show_unified_layout_inspector", "focus_layout_candidate",
    "add_unified_layout_inspector_controls", "_filtered_registry", "_row_values",
]
