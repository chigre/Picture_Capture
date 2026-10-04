from __future__ import annotations

"""User-action orchestration for current-page crop workflows.

Phase 4I intentionally moves only the stable ``split_lines_current`` entry
seam. Crop geometry and file generation remain in ``processing`` and project
path policy remains in ``project_storage``. The runtime-installed
``split_single_lines_selected_scope`` path is deliberately outside this
controller until the later runtime-patch cleanup milestone.
"""

from dataclasses import replace
from typing import Any

from ...processing import append_crop_log, split_single_lines
from ...project_storage import qt_root


class CropController:
    """Coordinate current-page single-line crop export without owning algorithms."""

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
