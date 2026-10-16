from __future__ import annotations

"""User-action orchestration for stable crop workflows.

Crop geometry and file generation remain in ``processing`` and project path
policy remains in ``project_storage``. Crop-settings UI and illustration actions
remain outside this controller. Selected-scope single-line and unlined-row export
actions are explicit here and use the app-owned parallel batch runner.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any
import tkinter as tk
import threading

from ... import unlined_line_export as unlined_export
from ...crop.export_output import normalize_project_crop_widths
from ...formats import pdic_path, read_pdic, read_ppp, write_ppp
from ...ordinary_quick_settings import _apply_quick_settings_for_ordinary
from ...processing import (
    append_crop_log,
    split_single_lines,
    split_whole_entries,
    split_whole_entries_job,
)
from ...project_storage import ppp_read_path_for_image, qt_root
from ...single_line_merge_settings import load_merge_by_page
from ...single_line_parallel import configured_single_line_workers, single_line_page_job
from ...unlined_export_filter_settings import load_unlined_filter_settings


def _width_report(app: Any, root: Path, config: dict) -> str:
    """Complete a batch with a stable project-wide entry width."""
    try:
        stats = normalize_project_crop_widths(root, config)
    except Exception as exc:
        app.show_error("切图宽度补齐失败", exc)
        return "；宽度补齐失败"
    if not stats["target_width"]:
        return ""
    suffix = (
        f'；目标宽度 {stats["target_width"]} px'
        f'，补齐词条 {stats["entries_padded"]}、插图 {stats["illustrations_padded"]} 张'
    )
    if stats["oversize"]:
        suffix += f'；超宽保留 {stats["oversize"]} 张'
    return suffix


def complete_crop_widths(app: Any, root: Path, config: dict, prefix: str) -> None:
    """Finish a crop in the background without blocking Tk on large PNG projects."""
    starter = getattr(app, "_start_ui_worker", None)
    if not callable(starter):
        app.status_var.set(prefix + _width_report(app, root, config))
        return

    cancel = threading.Event()
    app._crop_width_cancel_event = cancel
    progress = [0, 0]

    def progress_callback(done: int, total: int) -> None:
        progress[:] = [done, total]

    def worker():
        return normalize_project_crop_widths(
            root, config, progress=progress_callback, cancelled=cancel.is_set,
        )

    def finish(result) -> None:
        if getattr(app, "_crop_width_cancel_event", None) is cancel:
            app._crop_width_cancel_event = None
        app.batch_stop_button.configure(state="disabled")
        suffix = (
            f'；目标宽度 {result["target_width"]} px'
            f'，补齐词条 {result["entries_padded"]}、插图 {result["illustrations_padded"]} 张'
            if result["target_width"] else ""
        )
        app.status_var.set(prefix + suffix)
        app.after(1800, app._hide_batch_bar_if_idle)

    def failed(exc, detail) -> None:
        if getattr(app, "_crop_width_cancel_event", None) is cancel:
            app._crop_width_cancel_event = None
        app.batch_stop_button.configure(state="disabled")
        if isinstance(exc, InterruptedError):
            app.status_var.set(prefix + "；宽度标准化已取消，已完成的 PNG 保留")
        else:
            if detail:
                print(detail)
            app.show_error("切图宽度标准化失败", exc)
        app.after(1800, app._hide_batch_bar_if_idle)

    app.status_var.set(prefix + "；后台统一 PNG 宽度中（可停止）")
    app.batch_stop_button.configure(state="normal")
    token = starter(
        "crop-width-normalization", worker, finish, failed, wait_on_close=True,
    )
    if token == -1:
        cancel.set()
        app.batch_stop_button.configure(state="disabled")
        return

    def poll() -> None:
        active = getattr(app, "_ui_worker_key_active", None)
        if not callable(active) or not active("crop-width-normalization"):
            return
        app.batch_text_var.set(f"PNG 宽度标准化：{progress[0]}/{progress[1]} 张")
        app.after(250, poll)

    app.after(250, poll)


def _commit_current_entry_inputs(app: Any) -> bool:
    """Ensure disk PDIC matches visible edits before workers read page sidecars."""
    try:
        flush = getattr(app, "_flush_deferred_page_save", None)
        if callable(flush):
            flush()
        save = getattr(app, "save_pdic", None)
        if callable(save):
            save(silent=True)
        # Selected-range workers also read PPP from disk, not from app.polygons.
        page = getattr(app, "current_page", None)
        ppp_path = getattr(app, "_ppp_write_path", None)
        if page is not None and callable(ppp_path) and hasattr(app, "polygons"):
            sync_labels = getattr(app, "_sync_polygon_label_texts", None)
            if callable(sync_labels):
                sync_labels()
            write_ppp(ppp_path(page), app.polygons, page.stem)
        return True
    except Exception as exc:
        app.show_error("切图前保存当前词条失败", exc)
        return False


def _status(app: Any, text: str) -> None:
    try:
        app.status_var.set(text)
    except Exception:
        pass


def _set_button_state(app: Any, names: tuple[str, ...], active: bool) -> None:
    for name in names:
        button = getattr(app, name, None)
        if button is None:
            continue
        try:
            button.configure(state="disabled" if active else "normal")
        except tk.TclError:
            pass


def _set_job_button_state(app: Any, active: bool) -> None:
    """Preserve the main single-line action's historical button-state contract."""
    _set_button_state(app, ("_pc_single_line_crop_button",), active)


def _set_unlined_job_button_state(app: Any, active: bool) -> None:
    """Disable both related exporters while unlined-row export is active."""
    _set_button_state(
        app,
        ("_pc_unlined_export_button", "_pc_single_line_crop_button"),
        active,
    )


def _snapshot_scope(app: Any) -> tuple[Path, tuple[Path, ...], tuple[int, ...], Any] | None:
    if not app.guard():
        return None
    # Both selected-scope exporters are OCR-independent. Reuse the ordinary
    # action adapter so projects with all OCR engines disabled can still apply
    # current quick geometry before cropping/export.
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


class CropController:
    """Coordinate stable crop exports without owning crop algorithms."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def split_single_lines_selected_scope(self) -> None:
        """Export selected-page single lines through the shared app batch runner."""
        app = self.app
        if bool(getattr(app, "_batch_active", False)):
            _status(app, "已有批量任务正在运行，请结束后再执行单行切图。")
            return

        snapshot = _snapshot_scope(app)
        if snapshot is None:
            return
        project_root, images, indices, settings = snapshot
        output_dir = qt_root(project_root) / "PSW"
        output_dir.mkdir(parents=True, exist_ok=True)
        merge_by_page = load_merge_by_page(project_root)
        workers = max(1, min(configured_single_line_workers(project_root), len(indices)))
        worker_text = "串行" if workers <= 1 else f"并行×{workers}"
        _status(app, f"单行切图：准备处理 {len(indices)} 页（{worker_text}）…")
        _set_job_button_state(app, True)

        def job_builder(index: int, _position: int, _total: int):
            return (
                str(project_root),
                str(images[index]),
                int(index),
                settings,
                str(output_dir),
                bool(merge_by_page),
            )

        def consume_result(_index: int, result):
            _page_index, filename, records, merged = result
            append_crop_log(project_root, records)
            return filename, len(records), bool(merged)

        def done(completed, total_pages, stopped, results, error):
            _set_job_button_state(app, False)
            if error is not None:
                return
            record_count = sum(int(result[1]) for result in results)
            if stopped:
                _status(
                    app,
                    f"单行切图已停止：完成 {completed}/{total_pages} 页，共 {record_count} 行；{worker_text}",
                )
                return
            mode = "；每页已合并为 1 张图" if merge_by_page else ""
            _status(
                app,
                f"单行切图完成：{completed} 页，共 {record_count} 行{mode}；{worker_text}；已保存到 {output_dir}",
            )

        started = app._start_parallel_batch_task(
            "单行切图",
            indices,
            single_line_page_job,
            job_builder,
            consume_result,
            done,
            item_label=lambda index: images[index].name,
            max_workers=workers,
            allow_pdic_edits=True,
        )
        if not started:
            _set_job_button_state(app, False)


    def export_unlined_rows_selected_scope(self) -> None:
        """Export selected-page Layout rows without current PDIC markers."""
        app = self.app
        if bool(getattr(app, "_batch_active", False)):
            _status(app, "已有批量任务正在运行，请结束后再导出未画线行。")
            return

        snapshot = _snapshot_scope(app)
        if snapshot is None:
            return
        project_root, images, indices, settings = snapshot
        output_dir = qt_root(project_root) / unlined_export.OUTPUT_DIRNAME
        output_dir.mkdir(parents=True, exist_ok=True)
        merge_by_page = load_merge_by_page(project_root)
        filter_enabled, filter_blank, left_white_threshold = load_unlined_filter_settings(
            project_root
        )
        workers = max(1, min(configured_single_line_workers(project_root), len(indices)))
        worker_text = "串行" if workers <= 1 else f"并行×{workers}"
        filter_text = (
            f"；左侧连续白宽>{left_white_threshold:g}%"
            if filter_enabled and filter_blank
            else ""
        )
        _status(
            app,
            f"未画线行导出：准备分析 {len(indices)} 页（{worker_text}{filter_text}）…",
        )
        _set_unlined_job_button_state(app, True)

        def job_builder(index: int, _position: int, _total: int):
            return (
                str(project_root),
                str(images[index]),
                int(index),
                settings,
                bool(merge_by_page),
                bool(filter_enabled),
                bool(filter_blank),
                float(left_white_threshold),
            )

        def done(completed, total_pages, stopped, results, error):
            _set_unlined_job_button_state(app, False)
            if error is not None:
                return

            total_unlined = sum(int(result.unlined_rows) for result in results)
            total_exported = sum(int(result.exported_images) for result in results)
            unreliable = sum(
                1 for result in results if not bool(result.physical_reliable)
            )
            mode = "；按页合并" if merge_by_page else ""
            filtered = (
                f"；左侧连续白宽>{left_white_threshold:g}%"
                if filter_enabled and filter_blank
                else ""
            )
            skipped = f"；Layout不可靠跳过 {unreliable} 页" if unreliable else ""
            if stopped:
                _status(
                    app,
                    f"未画线行导出已停止：完成 {completed}/{total_pages} 页，"
                    f"发现 {total_unlined} 个未画线行，输出 {total_exported} 张"
                    f"{filtered}{mode}{skipped}；{worker_text}",
                )
                return
            _status(
                app,
                f"未画线行导出完成：{completed} 页，发现 {total_unlined} 个未画线行，"
                f"输出 {total_exported} 张{filtered}{mode}{skipped}；"
                f"{worker_text}；保存到 {output_dir}",
            )

        # Deliberately resolve the one-page worker through the module at action
        # time. GUI composition installs the physical-row fast path after app.py
        # (and therefore this controller) is imported; importing the function by
        # value here would freeze the pre-fast-path worker and regress performance.
        started = app._start_parallel_batch_task(
            "未画线行导出",
            indices,
            unlined_export.export_unlined_page_job,
            job_builder,
            on_done=done,
            item_label=lambda index: images[index].name,
            max_workers=workers,
            allow_pdic_edits=True,
        )
        if not started:
            _set_unlined_job_button_state(app, False)

    def split_lines_current(self) -> None:
        app = self.app
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再执行单行切图。")
            return
        if not app.guard():
            return
        if not app._guard_transformed_geometry("单行切图"):
            return

        project = app.project
        page = app.current_page
        page_index = int(app.current_index)
        entries = [replace(entry) for entry in app.entries]
        settings = replace(app.settings)
        out_dir = qt_root(project.root) / "PSW"

        def worker(_item, _position: int, _total: int):
            records = split_single_lines(
                page,
                entries,
                settings,
                out_dir,
                profile_page_index=page_index,
            )
            append_crop_log(project.root, records)
            return len(records)

        def done(_completed, _total, stopped, results, error):
            if error is None and not stopped and results:
                app.status_var.set(f"已导出 {int(results[-1] or 0)} 张词条单行图")

        app._start_batch_task(
            "当前页单行切图",
            [page_index],
            worker,
            done,
            item_label=lambda _item: page.name,
        )

    def split_whole_current(self) -> None:
        app = self.app
        if app._batch_active:
            app.status_var.set("已有批量任务正在运行，请结束后再执行整体切图。")
            return
        if not app.guard():
            return
        if not app._guard_transformed_geometry("整体切图"):
            return
        if not _commit_current_entry_inputs(app):
            return

        project = app.project
        page = app.current_page
        page_index = int(app.current_index)
        entries = [replace(entry) for entry in app.entries]
        polygons = list(app.polygons)
        settings = replace(app.settings)
        config = app._load_crop_settings()
        special = config.get("special_pages", {}).get(page.stem, {})
        top_y = int(special.get("top_y", config.get("general_top_y", settings.start_y)))
        bottom_y = int(special.get("bottom_y", config.get("general_bottom_y", 0)))
        entry_left = int(config.get("entry_left_padding_x", 0))
        entry_right = int(config.get("entry_right_padding_x", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        out_dir = qt_root(project.root) / "PWW"

        def worker(_item, _position: int, _total: int):
            records = split_whole_entries(
                page,
                entries,
                settings,
                out_dir,
                top_y=top_y,
                bottom_y=bottom_y,
                polygons=polygons,
                entry_left_padding=entry_left,
                entry_right_padding=entry_right,
                integrate_illustrations=integrate_illustrations,
                profile_page_index=page_index,
                **({"transparent_background": True} if config.get("entry_transparent_background", False) else {}),
            )
            append_crop_log(project.root, records)
            return len(records)

        def done(_completed, _total, stopped, results, error):
            if error is None and not stopped and results:
                complete_crop_widths(app, project.root, config,
                                     f"已导出 {int(results[-1] or 0)} 张词条整体图")

        app._start_batch_task(
            "当前页整体切图",
            [page_index],
            worker,
            done,
            item_label=lambda _item: page.name,
        )

    def batch_split_whole(self) -> None:
        app = self.app
        if not app.project or app._batch_active:
            return
        if not app._guard_transformed_geometry("批量整体切图"):
            return
        if not _commit_current_entry_inputs(app):
            return

        project = app.project
        settings = replace(app.settings)
        indices = list(range(len(project.images)))
        out_dir = qt_root(project.root) / "PWW"
        config = app._load_crop_settings()
        general_top = int(config.get("general_top_y", settings.start_y))
        general_bottom = int(config.get("general_bottom_y", 0))
        entry_left = int(config.get("entry_left_padding_x", 0))
        entry_right = int(config.get("entry_right_padding_x", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        specials = (
            config.get("special_pages", {})
            if isinstance(config.get("special_pages", {}), dict)
            else {}
        )

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            entries = read_pdic(pdic_path(page))
            polygons = read_ppp(ppp_read_path_for_image(page))
            special = (
                specials.get(page.stem, {})
                if isinstance(specials.get(page.stem, {}), dict)
                else {}
            )
            top_y = int(special.get("top_y", general_top))
            bottom_y = int(special.get("bottom_y", general_bottom))
            records = split_whole_entries(
                page,
                entries,
                settings,
                out_dir,
                top_y=top_y,
                bottom_y=bottom_y,
                polygons=polygons,
                entry_left_padding=entry_left,
                entry_right_padding=entry_right,
                integrate_illustrations=integrate_illustrations,
                profile_page_index=index,
                **({"transparent_background": True} if config.get("entry_transparent_background", False) else {}),
            )
            append_crop_log(project.root, records)
            return len(records)

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            count = sum(int(value or 0) for value in results)
            if stopped:
                app.status_var.set(
                    f"批量整体切图已停止：完成 {completed}/{total_pages} 页，共 {count} 张"
                )
            else:
                complete_crop_widths(app, project.root, config,
                                     f"批量整体切图完成：{count} 张")

        app._start_batch_task(
            "批量整体切图",
            indices,
            worker,
            done,
            item_label=lambda index: project.images[index].name,
        )

    def split_entries_selected_scope(self) -> None:
        """Export whole-entry crops for the selected page range."""
        app = self.app
        if not app.guard():
            return
        try:
            indices = app.selected_page_indices()
        except Exception as exc:
            app.show_error("页面范围无效", exc)
            return
        # Phase 4L intentionally fixes the one crop entry point that previously
        # skipped the same transformed-geometry safety gate used by the other
        # whole-entry crop actions. Keep range-validation behavior first, but do
        # not save or launch work when the geometry adapter is unsupported.
        if not app._guard_transformed_geometry("词条切图"):
            return

        if not _commit_current_entry_inputs(app):
            return
        project = app.project
        settings = replace(app.settings)
        config = app._load_crop_settings()
        out_dir = qt_root(project.root) / "PWW"
        general_top = int(config.get("general_top_y", settings.start_y))
        general_bottom = int(config.get("general_bottom_y", 0))
        entry_left = int(config.get("entry_left_padding_x", 0))
        entry_right = int(config.get("entry_right_padding_x", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        specials = (
            config.get("special_pages", {})
            if isinstance(config.get("special_pages", {}), dict)
            else {}
        )
        workers = int(config.get("parallel_workers", settings.crop_parallel_workers))

        def job_builder(index: int, _position: int, _total: int):
            page = project.images[index]
            special = (
                specials.get(page.stem, {})
                if isinstance(specials.get(page.stem, {}), dict)
                else {}
            )
            top_y = int(special.get("top_y", general_top))
            bottom_y = int(special.get("bottom_y", general_bottom))
            return (
                str(page),
                str(pdic_path(page)),
                settings,
                str(out_dir),
                top_y,
                bottom_y,
                str(ppp_read_path_for_image(page)),
                entry_left,
                entry_right,
                integrate_illustrations,
                index,
                bool(config.get("entry_transparent_background", False)),
                str(project.images[index - 1]) if index > 0 else None,
            )

        def consume_result(_index: int, records):
            append_crop_log(project.root, records)
            return len(records)

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            count = sum(int(value or 0) for value in results)
            if stopped:
                app.status_var.set(
                    f"词条切图已停止：完成 {completed}/{total_pages} 页，共导出 {count} 张"
                )
            else:
                complete_crop_widths(app, project.root, config,
                                     f"词条切图完成：{completed} 页，共 {count} 张")

        app._start_parallel_batch_task(
            "词条切图",
            indices,
            split_whole_entries_job,
            job_builder,
            consume_result,
            done,
            item_label=lambda index: project.images[index].name,
            max_workers=workers,
        )
