"""Current-page OCR batch, source-pixel PDIC/OCRed write and UI completion.

Only the existing batch worker performs OCR/file IO; GUI updates stay in the
existing batch dispatcher callback on the Tk main thread.
"""
from __future__ import annotations
from typing import Any

def ocr_current(self, *, deps: dict[str, Any]) -> None:
    replace = deps["replace"]
    replace_rules_path = deps["replace_rules_path"]
    qt_root = deps["qt_root"]
    OCR_ENGINE_LABELS = deps["OCR_ENGINE_LABELS"]
    load_replace_rules = deps["load_replace_rules"]
    Image = deps["Image"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    ocr_entries = deps["ocr_entries"]
    export_ocred = deps["export_ocred"]
    write_pdic = deps["write_pdic"]
    pdic_path = deps["pdic_path"]
    """Backward-compatible current-page OCR, executed off the Tk thread."""
    if self._batch_active:
        self.status_var.set("后台画线任务运行中，暂不启动前台 OCR；可进行人工文本校对。")
        return
    if not self.guard() or not self.entries:
        return
    if not self._guard_transformed_geometry("OCR"):
        return

    project = self.project
    page = self.current_page
    page_index = int(self.current_index)
    settings = replace(self.settings)
    ordered_entries = [replace(entry) for entry in self._ordered_entries_reading_order()]
    page_sections = list(self.page_sections)
    pages_meta = self.pages_tuple(page_index)
    rules_path = replace_rules_path(project.root)
    ocred_path = qt_root(project.root) / f"{page.stem}.OCRed"
    engine_name = OCR_ENGINE_LABELS.get(settings.ocr_engine, settings.ocr_engine)

    def worker(_item, _position: int, _total: int):
        rules = load_replace_rules(rules_path)
        with Image.open(page) as opened:
            image = normalize_page_rgb(opened)
        texts = ocr_entries(
            image, ordered_entries, settings, rules,
            profile_page_index=page_index, page_sections=page_sections,
        )
        for entry, text in zip(ordered_entries, texts):
            entry.word = text
        export_ocred(ocred_path, texts)
        write_pdic(pdic_path(page), ordered_entries, image.width, pages_meta)
        return texts

    def done(_completed, _total, stopped, results, error):
        if error is not None or stopped or not results:
            return
        if self.project is not project or self.current_page != page:
            return
        texts = list(results[-1])
        current = self._ordered_entries_reading_order()
        if len(current) == len(texts):
            for entry, text in zip(current, texts):
                entry.word = text
            self.redraw()
        else:
            self._request_page_load(
                page_index, current_already_saved=True, force=True,
            )
        self.status_var.set(f"{engine_name} OCR 完成：{len(texts)} 个词条")

    self._start_batch_task(
        "当前页 OCR", [page_index], worker, done,
        item_label=lambda _item: page.name,
    )
