from __future__ import annotations

"""Batch OCR UI orchestration for pages with existing PDIC markers.

The detection controller retains its stable public method and live global
patchpoints. This owner handles scope selection, user confirmation, pending
editor flush, worker scheduling and completion UI. Actual page decoding,
OCR and OCRed/PDIC publication remain in ocr.batch_existing_entries.
"""

from dataclasses import replace
from typing import Any, Callable, Mapping


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
    current = dependencies()
    indices = [
        i
        for i, page in enumerate(app.project.images)
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

    # Preserve the newest visible text before a worker claims this page.
    if callable(getattr(app, "save_pdic", None)):
        app._sync_entry_editor_texts()
        app.save_pdic(silent=True, sync_editors=False)
    project = app.project
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
        if error is not None:
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

    app._start_batch_task(
        "批量 OCR",
        indices,
        worker,
        done,
        item_label=lambda i: project.images[i].name,
        foreground_page_edit=True, allow_pdic_edits=True,
    )
