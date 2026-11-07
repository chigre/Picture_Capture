from __future__ import annotations

"""Batch OCR UI orchestration for pages with existing PDIC markers.

The detection controller retains its stable public method and live global
patchpoints. This owner handles scope selection, user confirmation, pending
editor flush, worker scheduling and completion UI. Actual page decoding,
OCR and OCRed/PDIC publication remain in ocr.batch_existing_entries.
"""

from dataclasses import replace
from typing import Any, Callable, Mapping

from .batch_ocr_completion import complete_existing_pdic_batch


def run_existing_pdic_batch(
    app: Any,
    *,
    dependencies: Callable[[], Mapping[str, Any]],
) -> None:
    """Run the original batch OCR action with live controller dependencies."""
    if not app.project or app._batch_active:
        return
    if not app._guard_transformed_geometry("批量 OCR"):
        return
    project = app.project
    current = dependencies()
    indices = [
        i
        for i, page in enumerate(project.images)
        if current["read_pdic"](current["pdic_path"](page))
    ]
    if not indices:
        app.status_var.set("没有含 PDIC 词条的页面可执行批量 OCR")
        return
    if not current["messagebox"].askyesno(
        "批量 OCR",
        f"将对 {len(indices)} 个已有 PDIC 的页面执行 OCR。\n\n"
        "处理期间可暂停或停止；当前页会先完整处理并保存。继续？",
        parent=app,
    ):
        return
    # A nested native confirmation dialog can pump the Tk event loop. Do not
    # commit the new project's editor if the original project was replaced.
    if app.project is not project:
        return

    # Preserve the newest visible text before a worker claims this page.
    if callable(getattr(app, "save_pdic", None)):
        app._sync_entry_editor_texts()
        app.save_pdic(silent=True, sync_editors=False)
    settings = replace(app.settings)
    rules = current["load_replace_rules"](
        current["replace_rules_path"](project.root)
    )
    pages_info = {i: app.pages_tuple(i) for i in indices}

    def worker(index: int, _position: int, _total: int):
        live = dependencies()
        return live["process_existing_pdic_page"](
            project.images[index], index, project.root,
            settings, rules, pages_info[index],
            deps={
                "read_pdic": live["read_pdic"],
                "pdic_path": live["pdic_path"],
                "Image": live["Image"],
                "normalize_page_rgb": live["normalize_page_rgb"],
                "effective_page_settings": live["effective_page_settings"],
                "page_template_analysis_image": live["page_template_analysis_image"],
                "read_page_sections": live["read_page_sections"],
                "sort_entries_reading_order": live["sort_entries_reading_order"],
                "derive_geometry": live["derive_geometry"],
                "ocr_entries": live["ocr_entries"],
                "qt_root": live["qt_root"],
                "export_ocred": live["export_ocred"],
                "write_pdic": live["write_pdic"],
            },
        )

    def done(completed, total_pages, stopped, results, error):
        return complete_existing_pdic_batch(
            app,
            project=project,
            completed=completed,
            total_pages=total_pages,
            stopped=stopped,
            results=results,
            error=error,
        )

    app._start_batch_task(
        "批量 OCR",
        indices,
        worker,
        done,
        item_label=lambda i: project.images[i].name,
        foreground_page_edit=True, allow_pdic_edits=True,
    )
