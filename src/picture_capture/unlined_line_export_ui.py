from __future__ import annotations

"""Main-window action for exporting Layout rows without current PDIC markers."""

from functools import wraps
import queue
import threading
import traceback
from typing import Any, Iterable
import tkinter as tk
from tkinter import messagebox, ttk

from .postproduction_single_line_runtime import _snapshot_scope
from .single_line_parallel import configured_single_line_workers
from .unlined_export_filter_settings import load_unlined_filter_settings
from .unlined_line_export import UnlinedPageResult, run_unlined_export


_BUTTON_TEXT = "未画线行导出"
_LEFT_NEIGHBOR_TEXT = "单行切图"


def _walk_widgets(root: tk.Misc) -> Iterable[tk.Misc]:
    for child in root.winfo_children():
        yield child
        yield from _walk_widgets(child)


def _widget_text(widget: tk.Misc) -> str:
    try:
        return str(widget.cget("text") or "")
    except (tk.TclError, AttributeError):
        return ""


def _find_single_line_button(app: Any) -> tk.Misc | None:
    direct = getattr(app, "_pc_single_line_crop_button", None)
    if direct is not None:
        return direct
    for widget in _walk_widgets(app):
        if isinstance(widget, (ttk.Button, tk.Button)) and _widget_text(widget) == _LEFT_NEIGHBOR_TEXT:
            return widget
    return None


def _copy_button_presentation(target: tk.Misc) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for name in ("style", "width", "takefocus"):
        try:
            value = target.cget(name)
        except (tk.TclError, AttributeError):
            continue
        if value not in (None, ""):
            options[name] = value
    return options


def _pack_after(button: tk.Misc, target: tk.Misc) -> None:
    info = target.pack_info()
    options: dict[str, Any] = {"after": target}
    for name in ("side", "fill", "expand", "anchor", "padx", "pady", "ipadx", "ipady"):
        value = info.get(name)
        if value not in (None, ""):
            options[name] = value
    button.pack(**options)


def _grid_after(button: tk.Misc, target: tk.Misc) -> None:
    parent = target.master
    info = target.grid_info()
    row = int(info.get("row", 0))
    column = int(info.get("column", 0))
    span = max(1, int(info.get("columnspan", 1)))
    insert_column = column + span

    siblings: list[tuple[int, tk.Misc]] = []
    for widget in parent.grid_slaves(row=row):
        if widget is target:
            continue
        try:
            widget_column = int(widget.grid_info().get("column", 0))
        except (tk.TclError, TypeError, ValueError):
            continue
        if widget_column >= insert_column:
            siblings.append((widget_column, widget))
    for widget_column, widget in sorted(siblings, key=lambda item: item[0], reverse=True):
        widget.grid_configure(column=widget_column + span)

    options: dict[str, Any] = {
        "row": row,
        "column": insert_column,
        "columnspan": span,
        "rowspan": max(1, int(info.get("rowspan", 1))),
    }
    for name in ("sticky", "padx", "pady", "ipadx", "ipady"):
        value = info.get(name)
        if value not in (None, ""):
            options[name] = value
    button.grid(**options)


def _insert_button(app: Any) -> tk.Misc | None:
    if getattr(app, "_pc_unlined_export_button", None) is not None:
        return app._pc_unlined_export_button
    target = _find_single_line_button(app)
    if target is None:
        return None
    button = ttk.Button(
        target.master,
        text=_BUTTON_TEXT,
        command=app.export_unlined_rows_selected_scope,
        **_copy_button_presentation(target),
    )
    manager = str(target.winfo_manager() or "")
    try:
        if manager == "pack":
            _pack_after(button, target)
        elif manager == "grid":
            _grid_after(button, target)
        else:
            button.pack(side="left", after=target)
    except tk.TclError:
        button.destroy()
        return None
    app._pc_unlined_export_button = button
    try:
        app._attach_tooltip(
            button,
            "将【选定范围】内 Layout 已恢复、但当前 PDIC 没有横线的文字行导出到 QT/PSW_UNLINED。"
            "可在【设置中心 → 切图】启用【未画线行导出过滤 → 空白】只检查近空白候选；"
            "不以 entry/body 角色决定是否导出，并复用按页合并和切图并行进程设置。",
        )
    except Exception:
        pass
    return button


def _set_job_button_state(app: Any, active: bool) -> None:
    """Disable both related exporters while either output job is active."""
    for name in ("_pc_unlined_export_button", "_pc_single_line_crop_button"):
        button = getattr(app, name, None)
        if button is None:
            continue
        try:
            button.configure(state="disabled" if active else "normal")
        except tk.TclError:
            pass


def _status(app: Any, text: str) -> None:
    try:
        app.status_var.set(text)
    except Exception:
        pass


def _worker(project_root, images, indices, settings, events) -> None:
    try:
        def progress(
            completed: int,
            total: int,
            result: UnlinedPageResult,
            workers: int,
        ) -> None:
            events.put(("progress", (completed, total, result, workers)))

        result = run_unlined_export(
            project_root,
            images,
            indices,
            settings,
            progress,
        )
        events.put(("done", result))
    except Exception as exc:
        events.put(("error", (exc, traceback.format_exc())))


def _start_unlined_export(app: Any) -> None:
    if bool(getattr(app, "_pc_unlined_export_active", False)):
        _status(app, "未画线行导出正在进行中。")
        return
    if bool(getattr(app, "_pc_single_line_crop_active", False)):
        _status(app, "单行切图正在进行中，请结束后再导出未画线行。")
        return
    if bool(getattr(app, "_batch_active", False)):
        _status(app, "已有批量任务正在运行，请结束后再导出未画线行。")
        return

    snapshot = _snapshot_scope(app)
    if snapshot is None:
        return
    project_root, images, indices, settings = snapshot
    events: "queue.Queue[tuple[str, Any]]" = queue.Queue()
    token = object()
    app._pc_unlined_export_active = True
    app._pc_unlined_export_token = token
    _set_job_button_state(app, True)

    workers = max(1, min(configured_single_line_workers(project_root), len(indices)))
    worker_text = "串行" if workers <= 1 else f"并行×{workers}"
    filter_enabled, filter_blank, blank_threshold = load_unlined_filter_settings(project_root)
    filter_text = (
        f"；仅近空白≤{blank_threshold:g}%墨迹"
        if filter_enabled and filter_blank
        else ""
    )
    _status(
        app,
        f"未画线行导出：准备分析 {len(indices)} 页（{worker_text}{filter_text}）…",
    )

    thread = threading.Thread(
        target=_worker,
        args=(project_root, images, indices, settings, events),
        name="picture-capture-unlined-line-export",
        daemon=True,
    )
    app._pc_unlined_export_thread = thread
    thread.start()

    def poll() -> None:
        if getattr(app, "_pc_unlined_export_token", None) is not token:
            return
        finished = False
        try:
            while True:
                kind, payload = events.get_nowait()
                if kind == "progress":
                    completed, total, result, worker_count = payload
                    parallel = "" if worker_count <= 1 else f"，并行×{worker_count}"
                    if result.physical_reliable:
                        merged = "，按页合并" if result.merged else ""
                        filter_stats = ""
                        if filter_enabled and filter_blank:
                            filter_stats = (
                                f"，近空白 {result.blank_rows} 行，过滤掉 {result.filtered_out_rows} 行"
                            )
                        _status(
                            app,
                            f"未画线行导出：{completed}/{total} {result.filename} "
                            f"（Layout {result.layout_rows} 行，未画线 {result.unlined_rows} 行"
                            f"{filter_stats}，有效输出 {result.exported_images} 张{merged}{parallel}）",
                        )
                    else:
                        _status(
                            app,
                            f"未画线行导出：{completed}/{total} {result.filename}（Layout 不可靠，已跳过{parallel}）",
                        )
                elif kind == "done":
                    pages, unlined, exported, unreliable, output_dir, merged, worker_count = payload
                    parallel = "串行" if worker_count <= 1 else f"并行×{worker_count}"
                    mode = "；按页合并" if merged else ""
                    filtered = (
                        f"；空白过滤≤{blank_threshold:g}%墨迹"
                        if filter_enabled and filter_blank
                        else ""
                    )
                    skipped = f"；Layout不可靠跳过 {unreliable} 页" if unreliable else ""
                    _status(
                        app,
                        f"未画线行导出完成：{pages} 页，发现 {unlined} 个未画线行，"
                        f"输出 {exported} 张{filtered}{mode}{skipped}；{parallel}；保存到 {output_dir}",
                    )
                    finished = True
                elif kind == "error":
                    exc, details = payload
                    _status(app, "未画线行导出失败。")
                    try:
                        messagebox.showerror(
                            "未画线行导出失败",
                            f"{exc}\n\n{details}",
                            parent=app,
                        )
                    except tk.TclError:
                        pass
                    finished = True
        except queue.Empty:
            pass

        if finished:
            app._pc_unlined_export_active = False
            _set_job_button_state(app, False)
            return
        try:
            app.after(80, poll)
        except tk.TclError:
            app._pc_unlined_export_active = False

    app.after(80, poll)


def install_unlined_line_export_ui(app_module: Any) -> None:
    """Insert 【未画线行导出】 immediately to the right of 【单行切图】."""
    app_class = app_module.PictureCaptureApp
    if bool(getattr(app_class, "_pc_unlined_line_export_installed", False)):
        return

    def export_unlined_rows_selected_scope(self) -> None:
        _start_unlined_export(self)

    app_class.export_unlined_rows_selected_scope = export_unlined_rows_selected_scope

    original_init = app_class.__init__

    @wraps(original_init)
    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _insert_button(self)

    app_class.__init__ = wrapped_init
    app_class._pc_unlined_line_export_installed = True


__all__ = ["install_unlined_line_export_ui"]
