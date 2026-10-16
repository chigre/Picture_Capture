"""Evidence-based bookmark marking for manually changed PDIC line positions.

Only an explicitly captured automated-drawing coordinate baseline is evidence
of changes. Missing baselines are *unknown*, never assumed unchanged.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import json

from .formats import pdic_path, read_pdic, write_text_atomic
from .project_storage import settings_path


def baseline_path(project_root: Path, page: Path) -> Path:
    return Path(project_root) / "data" / "line_baselines" / (page.stem + ".json")


def marker_positions(entries) -> list[list[int]]:
    return sorted([[int(entry.x), int(entry.y)] for entry in entries])


def record_original_lines(project_root: Path, page: Path, entries) -> None:
    """Store the automatic geometry immediately following a successful draw."""
    path = baseline_path(project_root, page)
    payload = {
        "format": 1, "page": page.name,
        "coordinates": marker_positions(entries),
    }
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False) + "\n")


def page_has_manual_line_difference(project_root: Path, page: Path) -> bool | None:
    """True/False for comparable pages; None for absent/invalid provenance."""
    path = baseline_path(project_root, page)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("format") != 1
            or data.get("page") != page.name):
        raise ValueError(f"Invalid original-line baseline for {page.name}")
    positions = data.get("coordinates")
    if (not isinstance(positions, list)
            or any(not isinstance(row, list) or len(row) != 2
                   or any(type(value) is not int for value in row)
                   for row in positions)):
        raise ValueError(f"Invalid original-line coordinates for {page.name}")
    saved = pdic_path(page)
    if not saved.is_file():
        return bool(positions)
    current = marker_positions(read_pdic(saved))
    return Counter(map(tuple, positions)) != Counter(map(tuple, current))


def modified_line_page_stems(project_root: Path, pages) -> tuple[set[str], int]:
    changed: set[str] = set()
    unknown = 0
    for page in pages:
        result = page_has_manual_line_difference(project_root, page)
        if result is None:
            unknown += 1
        elif result:
            changed.add(page.stem)
    return changed, unknown


def bookmark_modified_line_pages(app) -> None:
    """Replace bookmarks with pages whose stored automated lines differ."""
    from tkinter import messagebox

    if app.project is None or getattr(app, "_batch_active", False):
        app.status_var.set("请先打开项目，并等待画线或批处理任务结束。")
        return
    if app._preprocess_mode_active():
        app.status_var.set("预处理模式中不可修改书签。")
        return
    try:
        indices = app.selected_page_indices()
        if not indices:
            app.status_var.set("所选范围没有页面；书签未改变。")
            return
        pages = [app.project.images[i] for i in indices]
        changed, unknown = modified_line_page_stems(app.project.root, pages)
    except (ValueError, OSError, IndexError, TypeError) as exc:
        app.show_error("比较原始与人工画线失败；书签未改变", exc)
        return
    if unknown == len(pages):
        messagebox.showwarning(
            "标记线差异页",
            f"选定 {len(pages)} 页都没有可验证的原始画线基准。无法判断差异，已有书签保持不变。"
            "请在后续自动画线后再比较。",
            parent=app,
        )
        return
    warning = f"\n另有 {unknown} 页缺少原始基准，不参与判定。" if unknown else ""
    if not messagebox.askyesno(
        "标记线差异页",
        f"将清空现有所有书签，并仅在选定的 {len(pages)} 页中为 "
        f"{len(changed)} 个画线坐标已变化的页面添加书签。{warning}\n\n继续？",
        parent=app,
    ):
        return
    # Compute and validate everything before destructive replacement.
    app.settings.page_bookmarks = sorted(changed)
    app.project.settings.page_bookmarks = list(app.settings.page_bookmarks)
    app.settings.to_json(settings_path(app.project.root))
    for i in range(len(app.project.images)):
        app._update_page_row(i)
    app.status_var.set(
        f"画线差异书签已更新：标记 {len(changed)} 页；"
        f"无原始基准 {unknown} 页（未判定）"
    )
