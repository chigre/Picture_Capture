"""Physical selected-page Y-refinement and existing-marker OCR workflows.

Y workers remain read-only; guarded PDIC publication belongs to the foreground
parent coordinator. OCR over existing markers preserves their count/coordinates
and all manually chosen text. Do not import the Tk application shell.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SelectedMarkerActionsDeps:
    replace: object
    messagebox: object
    guard_ocr_action_selection: object
    read_pdic: object
    pdic_path: object
    load_replace_rules: object
    replace_rules_path: object
    headword_filter_rules_path: object
    HEADWORD_FILTER_RULES_FILENAME: object
    PROFILE_FILENAME: object
    Image: object
    normalize_page_rgb: object
    read_page_sections: object
    ocr_existing_entry_words_from_markers: object
    write_pdic: object
    export_ocred: object
    qt_root: object

def refine_lines_selected_scope(self, deps: SelectedMarkerActionsDeps, *, fixed_half_gutter: bool = False) -> None:
    """Align all saved PDIC markers near proven first-row ink without OCR."""
    replace = deps.replace
    messagebox = deps.messagebox
    if not self.guard() or not self.apply_quick_settings(show_status=False):
        return
    if self._batch_active:
        self.status_var.set("已有批量任务正在运行，请结束后再精修画线。")
        return
    try:
        indices = self.selected_page_indices()
    except Exception as exc:
        self.show_error("页面范围无效", exc)
        return
    if not indices:
        return

    first = self.project.images[indices[0]].name
    last = self.project.images[indices[-1]].name
    if not messagebox.askyesno(
        "精修Y（固定半栏距）" if fixed_half_gutter else "精修画线",
        f"精修所选 {len(indices)} 页：\n"
        f"{first}" + (f" → {last}" if len(indices) > 1 else "") +
        ("\n\n快速模式：临时填白插图，使用固定栏宽及两侧半栏距；不做逐页版式识别。\n"
         if fixed_half_gutter else "\n\n请先去设置中心的精修Y调整参数。\n") +
        "全部已有画线（含人工线）参与精修，不会新增或删除画线；"
        "在首行上缘附近寻找整栏空白Y；无安全位置则保留旧线。继续？",
        parent=self,
    ):
        return

    try:
        self._flush_deferred_page_save()
        self._sync_entry_editor_texts()
        self.save_pdic(silent=True, sync_editors=False)
    except Exception as exc:
        self.show_error("精修画线准备失败", exc)
        return

    project = self.project
    pages = list(project.images)
    settings = replace(self.settings)
    settings.paddle_refine_separator_y = True
    from ..refinement.parallel import (
        configured_refine_workers, refinement_uses_page_layout,
        refine_page_job, commit_refined_page_result,
    )
    workers = configured_refine_workers(
        len(indices), settings=settings, fixed_half_gutter=fixed_half_gutter,
        cache_pages=tuple((pages[i], i) for i in indices),
    )

    def job_builder(index: int, _position: int, _total: int):
        return (str(pages[index]), settings, index, fixed_half_gutter,
                workers > 1 and refinement_uses_page_layout(settings)
                and not fixed_half_gutter)

    def page_owned(index: int) -> bool:
        with self._batch_state_lock:
            return self._batch_page_states.get(int(index)) == "processing"

    def save_result(index: int, computed):
        return commit_refined_page_result(index, computed, page_owned)

    def done(completed, total, stopped, results, error) -> None:
        if error is not None:
            return
        moved = sum(int((row or {}).get("moved", 0)) for row in results)
        skipped = [row for row in results if (row or {}).get("skipped")]
        uncertain = sum(int((row or {}).get("unverified", 0)) for row in results)
        max_delta = max(
            [int((row or {}).get("max_delta", 0)) for row in results] or [0]
        )
        parts = [f"移动 {moved} 条", f"最大允许位移 {max_delta}px",
                 f"计算进程 {workers}"]
        if uncertain:
            parts.append(f"{uncertain} 条未确认全栏空白")
        if skipped:
            parts.append(f"跳过 {len(skipped)} 页")
            parts.append("；".join(
                f"{row['page']}: {str(row.get('reason', ''))[:70]}"
                for row in skipped[:3]
            ))
        if stopped:
            parts.insert(0, f"提前停止 {completed}/{total} 页")
        self.status_var.set("精修画线完成：" + "；".join(parts))

    self._start_parallel_batch_task(
        "精修画线", indices, refine_page_job, job_builder, save_result, done,
        item_label=lambda i: pages[i].name,
        max_workers=workers, respect_cpu_workers=True,
        foreground_page_edit=True, allow_pdic_edits=True,
        isolate_worker=True,
    )

def ocr_ordinary_lines_text_selected_scope(self, deps: SelectedMarkerActionsDeps) -> None:
    """OCR text for existing ordinary markers without changing geometry."""
    guard_ocr_action_selection = deps.guard_ocr_action_selection
    read_pdic = deps.read_pdic
    pdic_path = deps.pdic_path
    messagebox = deps.messagebox
    replace = deps.replace
    load_replace_rules = deps.load_replace_rules
    replace_rules_path = deps.replace_rules_path
    headword_filter_rules_path = deps.headword_filter_rules_path
    HEADWORD_FILTER_RULES_FILENAME = deps.HEADWORD_FILTER_RULES_FILENAME
    PROFILE_FILENAME = deps.PROFILE_FILENAME
    Image = deps.Image
    normalize_page_rgb = deps.normalize_page_rgb
    read_page_sections = deps.read_page_sections
    ocr_existing_entry_words_from_markers = deps.ocr_existing_entry_words_from_markers
    write_pdic = deps.write_pdic
    export_ocred = deps.export_ocred
    qt_root = deps.qt_root
    if not guard_ocr_action_selection(self):
        return
    if not self.guard() or not self.apply_quick_settings(show_status=False):
        return
    if self._batch_active:
        self.status_var.set("已有批量任务正在运行，请结束后再执行普通画线后OCR文字。")
        return
    if not self._guard_transformed_geometry("普通画线后OCR文字"):
        return
    try:
        indices = self.selected_page_indices()
    except Exception as exc:
        self.show_error("页面范围无效", exc)
        return
    if not indices:
        return

    existing = [
        index for index in indices
        if read_pdic(pdic_path(self.project.images[index]))
    ]
    if not existing:
        self.status_var.set("所选范围没有已有画线可执行OCR文字识别")
        return

    if len(existing) > 1 and not messagebox.askyesno(
        "普通画线后OCR文字",
        f"将对 {len(existing)} 个已有画线的页面逐条调用共享 OCR 通道。\n\n"
        "重新 OCR 并覆盖已有的自动 OCR 文本；明确人工选定的词条保留；"
        "不会新增、删除或移动任何画线。继续？",
        parent=self,
    ):
        return

    try:
        self._flush_deferred_page_save()
        self._sync_entry_editor_texts()
        self.save_pdic(silent=True, sync_editors=False)
    except Exception as exc:
        self.show_error("普通画线后OCR文字准备失败", exc)
        return

    project = self.project
    settings = replace(self.settings)
    rules = load_replace_rules(replace_rules_path(project.root))
    filter_path = headword_filter_rules_path(
        project.root, HEADWORD_FILTER_RULES_FILENAME
    )
    profile_path = filter_path.parent / PROFILE_FILENAME
    pages_info = {i: self.pages_tuple(i) for i in existing}

    def worker(index: int, _position: int, _total: int):
        page = project.images[index]
        entries = read_pdic(pdic_path(page))
        original_count = len(entries)
        original_coords = [(int(entry.x), int(entry.y)) for entry in entries]
        protected_words = {
            (int(entry.x), int(entry.y)): str(entry.word or "")
            for entry in entries
            if bool(entry.manually_selected)
        }
        with Image.open(page) as opened:
            image = normalize_page_rgb(opened)
        sections = read_page_sections(page)
        updated, stats = ocr_existing_entry_words_from_markers(
            image,
            entries,
            settings,
            rules,
            profile_page_index=index,
            page_sections=sections,
            profile_path=profile_path,
            only_blank=False,
        )
        if len(updated) != original_count:
            raise RuntimeError(
                f"{page.name} OCR文字前后画线数变化："
                f"{original_count} → {len(updated)}"
            )
        if [(int(entry.x), int(entry.y)) for entry in updated] != original_coords:
            raise RuntimeError(f"{page.name} OCR文字意外修改了画线坐标")
        for entry in updated:
            key = (int(entry.x), int(entry.y))
            if key in protected_words and str(entry.word or "") != protected_words[key]:
                raise RuntimeError(f"{page.name} OCR文字意外覆盖了人工选定文本")
        write_pdic(pdic_path(page), updated, image.width, pages_info[index])
        export_ocred(
            qt_root(project.root) / f"{page.stem}.OCRed",
            [entry.word for entry in updated],
        )
        return {"index": int(index), **stats}

    def done(completed, total, stopped, results, error):
        if error is not None:
            return
        if self.current_index in existing and not self._batch_foreground_pages:
            self.load_page(self.current_index, skip_current_save=True)
        filled = sum(int((row or {}).get("filled", 0)) for row in results)
        large = sum(int((row or {}).get("large", 0)) for row in results)
        regular = sum(int((row or {}).get("regular", 0)) for row in results)
        failed = sum(int((row or {}).get("failed", 0)) for row in results)
        skipped = sum(
            int((row or {}).get("skipped_existing", 0))
            + int((row or {}).get("skipped_manual", 0))
            for row in results
        )
        prefix = (
            f"普通画线后OCR文字已停止：{completed}/{total} 页"
            if stopped
            else f"普通画线后OCR文字完成：{completed}/{total} 页"
        )
        self.status_var.set(
            f"{prefix}；OCR 覆盖/识别 {filled} 条"
            f"（普通框 {regular}，大字框 {large}）"
            f"；未识别 {failed} 条；保留人工选定 {skipped} 条"
        )

    self._start_batch_task(
        "普通画线后OCR文字",
        existing,
        worker,
        done,
        item_label=lambda index: project.images[index].name,
        foreground_page_edit=True, allow_pdic_edits=True,
    )

