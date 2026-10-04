from __future__ import annotations

"""User-action orchestration for current-page OCR text import/export.

The controller owns only the stable UI action boundary. The ``.OCRed`` format
implementation remains in ``processing`` and project path policy remains in
``project_storage`` so this refactor does not change persisted data semantics.
"""

from typing import Any

from ...processing import export_ocred, import_ocred
from ...project_storage import qt_root


class ExportController:
    """Coordinate current-page text import/export without owning file formats."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def export_text(self) -> None:
        app = self.app
        if not app.guard():
            return
        export_ocred(
            qt_root(app.project.root) / f"{app.current_page.stem}.OCRed",
            [entry.word for entry in app._ordered_entries_reading_order()],
        )
        app.status_var.set("当前文本已导出")

    def import_text(self) -> None:
        app = self.app
        if not app.guard():
            return
        path = qt_root(app.project.root) / f"{app.current_page.stem}.OCRed"
        try:
            texts = import_ocred(path)
            if len(texts) != len(app.entries):
                raise ValueError(
                    f"文本 {len(texts)} 行，画线 {len(app.entries)} 条，数量不一致"
                )
            for entry, text in zip(app._ordered_entries_reading_order(), texts):
                entry.word = text
            app.redraw()
            app.status_var.set("当前文本已导入")
        except Exception as exc:
            app.show_error("导入失败", exc)
