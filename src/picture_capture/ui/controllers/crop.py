from __future__ import annotations

"""User-action orchestration for stable crop workflows.

Crop geometry and file generation remain in ``processing`` and project path
policy remains in ``project_storage``. Crop-settings UI, unrelated batch or
selected-scope actions, and the runtime-installed ``split_single_lines_selected_scope``
path remain outside this controller phase.
"""

from dataclasses import replace
from typing import Any

from ...formats import pdic_path, read_pdic, read_ppp
from ...processing import append_crop_log, split_single_lines, split_whole_entries
from ...project_storage import ppp_read_path_for_image, qt_root


class CropController:
    """Coordinate stable crop exports without owning crop algorithms."""

    def __init__(self, app: Any) -> None:
        self.app = app

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
