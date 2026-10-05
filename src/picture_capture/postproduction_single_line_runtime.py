from __future__ import annotations

"""Batch single-line export for the main post-production action row.

The proofreading window already consumes the historical ``split_single_lines``
output in ``QT/PSW``.  This adapter exposes that same crop path on the main
window for the currently selected page range; it deliberately does not
reimplement line boxes or proofreading geometry.
"""

from dataclasses import replace
from pathlib import Path
import queue
import threading
import traceback
from typing import Any
import tkinter as tk
from tkinter import messagebox

from .ordinary_action_runtime import _apply_quick_settings_for_ordinary
from .single_line_parallel import (
    configured_single_line_workers,
    run_single_line_pages,
)


def _set_job_button_state(app: Any, active: bool) -> None:
    button = getattr(app, "_pc_single_line_crop_button", None)
    if button is None:
        return
    try:
        button.configure(state="disabled" if active else "normal")
    except tk.TclError:
        pass


def _status(app: Any, text: str) -> None:
    try:
        app.status_var.set(text)
    except Exception:
        pass


def _snapshot_scope(app: Any) -> tuple[Path, tuple[Path, ...], tuple[int, ...], Any] | None:
    if not app.guard():
        return None
    # Single-line export is OCR-independent. Reuse the ordinary-action settings
    # adapter so a project with every OCR engine disabled is still allowed to
    # apply current quick geometry before cropping.
    if not _apply_quick_settings_for_ordinary(app):
        return None

    save_current = getattr(app, "save_current_page", None)
    if callable(save_current):
        save_current()

    project = getattr(app, "project", None)
    if project is None:
        return None
    indices = tuple(int(index) for index in app.selected_page_indices())
    if not indices:
        _status(app, "单行切图：当前没有可处理的选定页面。")
        return None
    images = tuple(Path(path) for path in project.images)
    valid = tuple(index for index in indices if 0 <= index < len(images))
    if not valid:
        _status(app, "单行切图：选定范围内没有有效页面。")
        return None
    return Path(project.root), images, valid, replace(app.settings)


def _single_line_worker(
    project_root: Path,
    images: tuple[Path, ...],
    indices: tuple[int, ...],
    settings: Any,
    events: "queue.Queue[tuple[str, Any]]",
) -> None:
    try:
        def progress(
            completed: int,
            total: int,
            filename: str,
            count: int,
            merged: bool,
            workers: int,
        ) -> None:
            events.put((
                "progress",
                (completed, total, filename, count, merged, workers),
            ))

        result = run_single_line_pages(
            project_root,
            images,
            indices,
            settings,
            progress,
        )
        events.put(("done", result))
    except Exception as exc:
        events.put(("error", (exc, traceback.format_exc())))


def start_single_line_export(app: Any) -> None:
    if bool(getattr(app, "_pc_single_line_crop_active", False)):
        _status(app, "单行切图正在进行中。")
        return
    if bool(getattr(app, "_batch_active", False)):
        _status(app, "已有批量任务正在运行，请结束后再执行单行切图。")
        return

    snapshot = _snapshot_scope(app)
    if snapshot is None:
        return
    project_root, images, indices, settings = snapshot
    events: "queue.Queue[tuple[str, Any]]" = queue.Queue()
    token = object()
    app._pc_single_line_crop_active = True
    app._pc_single_line_crop_token = token
    _set_job_button_state(app, True)
    workers = max(1, min(configured_single_line_workers(project_root), len(indices)))
    worker_text = "串行" if workers <= 1 else f"并行×{workers}"
    _status(app, f"单行切图：准备处理 {len(indices)} 页（{worker_text}）…")

    worker = threading.Thread(
        target=_single_line_worker,
        args=(project_root, images, indices, settings, events),
        name="picture-capture-single-line-crop",
        daemon=True,
    )
    app._pc_single_line_crop_thread = worker
    worker.start()

    def poll() -> None:
        if getattr(app, "_pc_single_line_crop_token", None) is not token:
            return
        finished = False
        try:
            while True:
                kind, payload = events.get_nowait()
                if kind == "progress":
                    completed, total, filename, count, merged, worker_count = payload
                    suffix = "，已合并为 1 张" if merged else ""
                    parallel = "" if worker_count <= 1 else f"，并行×{worker_count}"
                    _status(
                        app,
                        f"单行切图：{completed}/{total} {filename}（{count} 行{suffix}{parallel}）",
                    )
                elif kind == "done":
                    pages, records, output_dir, merged, worker_count = payload
                    mode = "；每页已合并为 1 张图" if merged else ""
                    parallel = "串行" if worker_count <= 1 else f"并行×{worker_count}"
                    _status(
                        app,
                        f"单行切图完成：{pages} 页，共 {records} 行{mode}；{parallel}；已保存到 {output_dir}",
                    )
                    finished = True
                elif kind == "error":
                    exc, details = payload
                    _status(app, "单行切图失败。")
                    try:
                        messagebox.showerror(
                            "单行切图失败",
                            f"{exc}\n\n{details}",
                            parent=app,
                        )
                    except tk.TclError:
                        pass
                    finished = True
        except queue.Empty:
            pass

        if finished:
            app._pc_single_line_crop_active = False
            _set_job_button_state(app, False)
            return
        try:
            app.after(80, poll)
        except tk.TclError:
            app._pc_single_line_crop_active = False

    app.after(80, poll)


__all__ = [
    "start_single_line_export",
]
