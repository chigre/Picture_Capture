from __future__ import annotations

"""User-action orchestration for stable crop workflows.

Crop geometry and file generation remain in ``processing`` and project path
policy remains in ``project_storage``. Crop-settings UI and illustration actions
remain outside this controller. The selected-scope single-line action is explicit
here, while its temporary Tk worker/poll scheduler remains runtime-owned.
"""

from dataclasses import replace
from typing import Any

from ...formats import pdic_path, read_pdic, read_ppp
from ...postproduction_single_line_runtime import start_single_line_export
from ...processing import (
    append_crop_log,
    split_single_lines,
    split_whole_entries,
    split_whole_entries_job,
)
from ...project_storage import ppp_read_path_for_image, qt_root


class CropController:
    """Coordinate stable crop exports without owning crop algorithms."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def split_single_lines_selected_scope(self) -> None:
        """Start selected-scope single-line export through the retained Tk scheduler."""
        start_single_line_export(self.app)

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
            )
            append_crop_log(project.root, records)
            return len(records)

        def done(_completed, _total, stopped, results, error):
            if error is None and not stopped and results:
                app.status_var.set(f"已导出 {int(results[-1] or 0)} 张词条整体图")

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
                app.status_var.set(f"批量整体切图完成：{count} 张")

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

        app.save_pdic(silent=True)
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
                app.status_var.set(f"词条切图完成：{completed} 页，共 {count} 张")

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
