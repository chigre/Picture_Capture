"""Independent, strictly diagnostic oversized-head overlay.

No PDIC edits, no settings mutation, no role/threshold changes. The optional
debug trace is collected by the exact production large-head detector.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .layout_visualization_ui import _layout_cache_key


_TAG = "large-head-diagnostics-overlay"
_COLORS = {
    "accepted": "#159447",
    "rejected_weak": "#c77d00",
    "rejected_row_front": "#d32f2f",
    "size_or_density": "#c77d00",
    "group_too_tall": "#d32f2f",
    "split_parent": "#64748b",
}
_REASONS = {
    "accepted": "通过形态、行首及强大字阈值",
    "rejected_weak": "形态和行首符合；高度不足以改变 Layout 角色",
    "rejected_row_front": "未通过行首/物理行匹配",
    "size_or_density": "未通过大字高度、宽度、宽高比或墨迹密度条件",
    "group_too_tall": "碎片组合过高，不能安全拆出独立大字",
    "split_parent": "原组合过大；已从栏首单字区域拆分独立候选",
}


def _cache_key(app: Any) -> tuple[Any, ...]:
    from .adaptive_denoise import DENOISE_ENV

    return (
        _layout_cache_key(app),
        repr(getattr(app, "settings", None)),
        repr(getattr(app, "page_sections", None)),
        os.environ.get(DENOISE_ENV, "auto"),
    )


def get_large_head_debug_snapshot(app: Any) -> dict[str, Any]:
    """Cache only the display-session report, not changed detection state."""
    key = _cache_key(app)
    existing = getattr(app, "_large_head_debug_snapshot", None)
    if (
        existing is not None
        and key == getattr(app, "_large_head_debug_snapshot_key", None)
    ):
        return existing
    from .large_head_visual_diagnostics import build_large_head_diagnostics

    result = build_large_head_diagnostics(
        app.image, app.settings,
        page_index=max(0, int(getattr(app, "current_index", 0))),
        page_sections=list(getattr(app, "page_sections", []) or []),
        source_image_path=getattr(app, "current_page", None),
    )
    app._large_head_debug_snapshot = result
    app._large_head_debug_snapshot_key = key
    return result


def _details(item: dict[str, Any], index: int) -> str:
    x0, y0, x1, y1 = item["source_box"]
    reference = max(1.0, float(item["reference_height"]))
    return (
        f"候选 H{index + 1:03d} / C{int(item['column']) + 1}\n"
        f"源图框: ({x0},{y0}) – ({x1},{y1})\n"
        f"墨迹宽高: {x1-x0} × {y1-y0} px\n"
        f"普通正文行高: {reference:.1f} px\n"
        f"高度比: {float(item['height_ratio']):.2f}\n"
        f"判定: {_REASONS.get(item['status'], item['status'])}\n"
        + (f"原组合框拆出: {int(item['recovered_count'])} 个字形\n"
           if "recovered_count" in item else "")
        + (f"原组合框坐标: {item['parent_source_box']}\n"
           if "parent_source_box" in item else "")
        + f"检测器实际输出: {'是' if item.get('detector_output') else '否'}\n"
        f"最近物理行角色: {item.get('layout_role','unknown')}\n"
        f"最近行证据: {item.get('layout_source','unknown')}\n"
        f"附近最终自动线: {len(item.get('nearby_final_lines', []))} 条\n"
        "说明：最终线按空间邻近匹配，不代表仅由本候选产生。"
    )


def draw_large_head_debug_overlay(app: Any) -> None:
    canvas = getattr(app, "canvas", None)
    if canvas is None:
        return
    try:
        canvas.delete(_TAG)
    except Exception:
        return
    var = getattr(app, "_large_head_visualization_var", None)
    if var is None or not bool(var.get()):
        return
    if getattr(app, "image", None) is None:
        return
    try:
        if bool(app.crop_preview_var.get()):
            return
    except Exception:
        pass

    try:
        snapshot = get_large_head_debug_snapshot(app)
    except Exception as exc:
        # The previous TypeName-only label concealed the actionable saved-PPP
        # error. Show the reason on canvas and keep the full text in status.
        reason = f"{type(exc).__name__}: {exc}"
        status = getattr(app, "status_var", None)
        if status is not None:
            status.set(f"大字头诊断不可用：{reason}")
        canvas.create_text(
            12, 12, anchor="nw", width=480,
            text=f"大字头诊断不可用：{reason[:200]}",
            fill="#c62828", tags=(_TAG,),
        )
        return

    scale = float(getattr(app, "view_scale", 1.0) or 1.0)
    for index, candidate in enumerate(snapshot["candidates"]):
        x0, y0, x1, y1 = candidate["source_box"]
        if x1 <= x0 or y1 <= y0:
            continue
        status = str(candidate["status"])
        color = _COLORS.get(status, "#666666")
        dashed = status != "accepted"
        rectangle = canvas.create_rectangle(
            x0*scale, y0*scale, x1*scale, y1*scale,
            fill="", outline=color,
            width=2 if status == "accepted" else 1,
            dash=(5, 3) if dashed else (),
            tags=(_TAG,),
        )
        # Candidate numbers only for strong/row-front cases; otherwise scans
        # with hundreds of small components would obscure printed text.
        if status in {"accepted", "rejected_row_front"}:
            canvas.create_text(
                (x0+2)*scale, max(0, y0-3)*scale, anchor="sw",
                text=f"H{index+1:03d}", fill=color,
                font=("TkDefaultFont", 8),
                tags=(_TAG,),
            )

        def show_details(_event: Any, row: dict[str, Any] = candidate, n: int = index):
            from tkinter import messagebox
            messagebox.showinfo(
                "大字头检测详情", _details(row, n),
                parent=getattr(app, "root", None),
            )

        canvas.tag_bind(rectangle, "<Button-1>", show_details)

        if status == "accepted":
            for line in candidate.get("nearby_final_lines", []):
                y = int(line["y"])
                lx = int(line["x"])
                canvas.create_line(
                    lx*scale, y*scale,
                    (lx+max(50, int(candidate["reference_height"]*2.0)))*scale,
                    y*scale,
                    fill="#2563eb", width=2, tags=(_TAG,),
                )

    summary = snapshot.get("summary", {})
    label = (
        f"大字候选 {len(snapshot['candidates'])}  "
        f"通过 {summary.get('accepted', 0)}  "
        f"弱证据 {summary.get('rejected_weak', 0)}  "
        f"非行首 {summary.get('rejected_row_front', 0)}\n"
        "绿=通过  黄=形态不足  红=非行首/过高  蓝=附近最终线（点击框查看详情）"
    )
    if not snapshot.get("enabled", False):
        label = str(snapshot.get("message") or "没有可用的大字头检测结果")
    canvas.create_text(
        12, 12, anchor="nw", text=label,
        fill="#177447", font=("TkDefaultFont", 9), tags=(_TAG,),
    )


def export_large_head_debug_json(app: Any) -> None:
    """User-triggered export shared by compact and quick display panels."""
    from tkinter import filedialog, messagebox

    if getattr(app, "image", None) is None:
        return
    try:
        snapshot = get_large_head_debug_snapshot(app)
    except Exception as exc:
        messagebox.showerror("大字头诊断", str(exc), parent=getattr(app, "root", None))
        return
    filename = filedialog.asksaveasfilename(
        title="导出统一Layout与普通画线诊断（不修改 PDIC）",
        defaultextension=".json",
        filetypes=[("JSON", "*.json")],
        parent=getattr(app, "root", None),
    )
    if not filename:
        return
    document = {
        "schema": snapshot.get("schema", "picture-capture-ordinary-evidence-v2"),
        "page_index": max(0, int(getattr(app, "current_index", 0))),
        "image_size": list(app.image.size),
        **snapshot,
    }
    try:
        Path(filename).write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        messagebox.showerror("导出失败", str(exc), parent=getattr(app, "root", None))



def compare_large_head_debug_json(app: Any) -> None:
    """Compare a selected older export to current unified Layout evidence."""
    from tkinter import filedialog, messagebox
    from .ordinary_unified_diff import compare_ordinary_diagnostics

    if getattr(app, "image", None) is None:
        return
    prior_filename = filedialog.askopenfilename(
        title="选择之前导出的Layout/大字头诊断 JSON",
        filetypes=[("JSON", "*.json")],
        parent=getattr(app, "root", None),
    )
    if not prior_filename:
        return
    try:
        previous = json.loads(Path(prior_filename).read_text(encoding="utf-8"))
        current = {
            "page_index": max(0, int(getattr(app, "current_index", 0))),
            "image_size": list(app.image.size),
            **get_large_head_debug_snapshot(app),
        }
        result = compare_ordinary_diagnostics(previous, current)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        messagebox.showerror(
            "诊断对比失败", str(exc),
            parent=getattr(app, "root", None),
        )
        return
    metrics = result["counts"]
    details = (
        f"旧自动线: {metrics['before_lines']}    新自动线: {metrics['after_lines']}\n"
        f"匹配: {metrics['matched']}    新增: {metrics['added']}    "
        f"消失: {metrics['removed']}    坐标偏移: {metrics['shifted']}\n"
        f"物理行角色变化: {metrics['layout_role_changes']}\n"
        f"大字检测通过: {metrics['before_accepted_large_heads']} → "
        f"{metrics['after_accepted_large_heads']}\n"
        f"待复核: {metrics['before_review']} → {metrics['after_review']}\n\n"
        "新增线 (最多10条): "
        + ", ".join(
            f"({line['x']},{line['y']})"
            for line in result["added_lines"][:10]
        )
        + "\n消失线 (最多10条): "
        + ", ".join(
            f"({line['x']},{line['y']})"
            for line in result["removed_lines"][:10]
        )
        + "\n\n注意：差异不代表新增/删除正确与否。"
        + "新旧必须属于同一原图尺寸及同一页面。"
    )
    messagebox.showinfo(
        "普通画线诊断对比（只读）",
        details, parent=getattr(app, "root", None),
    )


def add_large_head_debug_controls(app: Any, section: Any) -> None:
    """Add an opt-in overlay and explicit JSON export; never auto-write files."""
    if getattr(app, "_large_head_debug_toggle_widget", None) is not None:
        return
    from tkinter import ttk
    import tkinter as tk
    from .layout_visualization_ui_v3 import _next_grid_row

    var = tk.BooleanVar(value=False)
    app._large_head_visualization_var = var
    # Session-only display switch: never register in quick_bool_vars.
    # apply_quick_settings persists each quick_bool_vars key into AppSettings,
    # whose slotted schema deliberately has no debug-overlay setting.
    row = _next_grid_row(section)

    def toggle() -> None:
        app._large_head_debug_snapshot_key = None
        app._large_head_debug_snapshot = None
        app.redraw()

    checkbox = ttk.Checkbutton(
        section, text="显示大字头检测", variable=var, command=toggle,
    )
    checkbox.grid(row=row, column=0, columnspan=4, sticky="w", pady=(3, 0))
    app._large_head_debug_toggle_widget = checkbox
    try:
        app._attach_tooltip(
            checkbox,
            "只读检测诊断：标注大字候选框、失败原因、物理行角色和附近最终自动线。"
            "不改变检测阈值、画线或词条数据。",
        )
    except Exception:
        pass

    button = ttk.Button(
        section, text="导出统一Layout诊断 JSON",
        command=lambda: export_large_head_debug_json(app),
    )
    button.grid(row=row+1, column=0, columnspan=4, sticky="w", pady=(2, 0))
    app._large_head_debug_export_widget = button
    compare_button = ttk.Button(
        section, text="对比旧诊断 JSON",
        command=lambda: compare_large_head_debug_json(app),
    )
    compare_button.grid(
        row=row+2, column=0, columnspan=4, sticky="w", pady=(2, 0),
    )
    app._large_head_debug_compare_widget = compare_button


__all__ = [
    "add_large_head_debug_controls",
    "draw_large_head_debug_overlay",
    "get_large_head_debug_snapshot",
    "export_large_head_debug_json",
    "compare_large_head_debug_json",
]
