from __future__ import annotations

"""UI completion boundary for existing-PDIC batch OCR tasks.

A batch is bound to the project object captured at scheduling time. Workers
may finish writing their original project's PDIC/OCRed files after the user
opens another project, but stale callbacks must not reload that different
project's page or replace its visible status.
"""

from typing import Any


def complete_existing_pdic_batch(
    app: Any,
    *,
    project: Any,
    completed: int,
    total_pages: int,
    stopped: bool,
    results: list[Any],
    error: BaseException | None,
) -> None:
    """Publish progress only while the originating project is still active."""
    if error is not None or app.project is not project:
        return

    count = sum(int(value or 0) for value in results)
    if not getattr(app, "_batch_foreground_pages", False):
        app.load_page(app.current_index, skip_current_save=True)
    if stopped:
        app.status_var.set(
            f"批量 OCR 已停止：完成 {completed}/{total_pages} 页，共 {count} 个词条"
        )
    else:
        app.status_var.set(f"批量 OCR 完成：{count} 个词条")
