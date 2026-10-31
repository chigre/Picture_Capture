"""Physical owner for focused review scan, crop batching and Tk row painting.

Live app patchpoints captured at dispatch; no imports from the heavyweight app.
Worker scheduling, cancel serials, cache contents and Tk-thread behavior unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING

from ..proofreading.review_timing import ReviewTimingSession
from ..proofreading.focused_crop_source_fingerprint import (
    focused_crop_source_witness, focused_save_source_from_crop_witness,
    verify_focused_save_source,
)

if TYPE_CHECKING:
    import tkinter as tk
    from pathlib import Path
    from PIL import Image
    from ..models import AppSettings, Entry as WordEntry


@dataclass(frozen=True)
class FocusedFilterDeps:
    """Original app-level bindings captured separately for each operation."""
    ReviewWindow: object
    messagebox: object
    _focused_review_character_tokens: object
    read_pdic: object
    pdic_path: object
    ocr_cache_root: object
    json: object
    _focused_review_is_single_character: object
    _candidate_for_entry_from_list: object
    _candidate_word_for_ocr_source: object
    _review_similarity_key: object
    replace: object
    normalize_page_rgb: object
    _review_crop_context: object
    sort_entries_reading_order: object
    read_page_sections: object
    column_index: object
    _review_line_box: object
    review_auto_fit_zoom: object
    Image: object
    _format_layout_percent: object
    tk: object
    ttk: object
    ImageTk: object
    resolve_content_font_family: object
    _review_editor_font_size: object
    _entry_font_spec: object
    themed_display_image: object
    _apply_focused_review_page_updates: object


def _record_focused_timing(
    self, session: ReviewTimingSession | None,
    stage: str, elapsed: float | None, count: int = 1,
) -> None:
    """Record in Tk callback only, and only for the still-active scan epoch."""
    if (
        session is None or elapsed is None
        or getattr(self, "_focused_timing_session", None) is not session
        or getattr(self, "_filter_scan_serial", None) != session.epoch
        or not getattr(self, "_filter_rows_active", False)
    ):
        return
    if session.add(stage, elapsed, count, epoch=session.epoch):
        var = getattr(self, "focused_timing_summary_var", None)
        if var is not None:
            var.set(session.label)


def run_focused_filter(self, deps: FocusedFilterDeps) -> None:
    """Render the first batch early, then stream and pre-render later batches."""
    messagebox = deps.messagebox
    _focused_review_character_tokens = deps._focused_review_character_tokens
    read_pdic = deps.read_pdic
    pdic_path = deps.pdic_path
    ocr_cache_root = deps.ocr_cache_root
    json = deps.json
    _focused_review_is_single_character = deps._focused_review_is_single_character
    _candidate_for_entry_from_list = deps._candidate_for_entry_from_list
    _candidate_word_for_ocr_source = deps._candidate_word_for_ocr_source
    _review_similarity_key = deps._review_similarity_key
    project = self.parent.project
    if project is None:
        return
    # Re-filter may destroy visible editor rows. Refuse *before* modifying
    # persisted settings, even when the new checkbox differs from this epoch.
    if getattr(self, "_filter_rows_active", False) and (
        self._filter_save_running or self._filter_pending_changes
    ):
        self.parent.status_var.set("请先完成重点校对修改保存，再重新筛选。")
        return
    try:
        # Reuse the main-window 【指定】 parser exactly. This preserves
        # filename-number matching, leading zeroes, mixed comma ranges and
        # all accepted hyphen/tilde variants without a second parser.
        indices = self.parent._parse_page_spec(
            self.focused_page_range_var.get()
        )
    except Exception as exc:
        messagebox.showerror("筛选条件无效", str(exc), parent=self)
        return

    include_mismatch = bool(self.focused_include_mismatch_var.get())
    include_chars = bool(self.focused_include_characters_var.get())
    exclude_single = bool(self.focused_exclude_single_var.get())
    exclude_reference = bool(self.focused_exclude_reference_var.get())
    # The queue option is fixed for this scan epoch; toggling the checkbox
    # never reorders visible editors or changes the in-flight worker.
    risk_queue_enabled = bool(self.focused_risk_priority_var.get())
    timing_var = getattr(self, "focused_timing_var", None)
    timing_enabled = bool(timing_var.get()) if timing_var is not None else False
    tokens = _focused_review_character_tokens(self.focused_characters_var.get())
    if include_chars and not tokens:
        messagebox.showinfo(
            "特定字符为空",
            "已勾选【含特定字符】，请先输入至少一个字符。",
            parent=self,
        )
        return

    # A rejected first scan must not persist options or erase single-page
    # edits. ReviewWindow paints its first crop asynchronously; R3 forbids a
    # save until the real page/Entry/sidecar source snapshot has rendered.
    # Never bypass R3 merely to make an early filter click succeed.
    if not getattr(self, "_filter_rows_active", False):
        current_page = getattr(self.parent, "current_page", None)
        if (
            current_page is None
            or getattr(self, "_rendered_page_stem", "") != current_page.stem
        ):
            self.parent.status_var.set(
                "本页校对尚未加载完成，请待词条显示后重新筛选。"
            )
            return
    try:
        int(self.focused_batch_size_var.get().strip())
    except (ValueError, TypeError, AttributeError):
        messagebox.showerror(
            "筛选条件无效", "单批显示数量必须是整数。", parent=self
        )
        return
    if not getattr(self, "_filter_rows_active", False):
        try:
            saved = self.save(redraw_main=False)
        except (RuntimeError, OSError, ValueError):
            # Source mismatch, recovery marker and file-write failures belong
            # to R3. Keep the current editing surface and its settings as-is.
            self.parent.status_var.set(
                "本页保存失败或来源未通过验证，筛选已取消；请核对后重试。"
            )
            return
        if saved is False:
            self.parent.status_var.set(
                "本页校对尚未保存完成，筛选已取消。"
            )
            return
    # Persist filter options only after a successful R3-protected save,
    # valid options and no outstanding focused human edit.
    try:
        self._persist_focused_filter_settings()
    except Exception as exc:
        messagebox.showerror("筛选条件无效", str(exc), parent=self)
        return
    self.review_mode_var.set("filter")
    self._filter_rows_active = True
    self._set_filter_navigation(True)
    self.parent._invalidate_ui_worker(self._review_render_worker_key)
    # An old initial scan or prefetched crop must not publish in a new epoch.
    self.parent._invalidate_ui_worker(f"focused-filter-scan-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-scan-rest-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-render-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-prefetch-{id(self)}")
    self._filter_render_serial += 1
    self._filter_batch_render_cache.clear()
    self._filter_prefetch_key = None
    self._filter_scan_complete = False
    # An aborted remainder is not a completed scan. Keep already-rendered
    # source batches editable; the unfinished tail is never offered as final.
    self._filter_scan_failed = False
    self.filtered_targets = []
    self.filtered_batch_index = 0
    self._clear_review_workspace("正在快速筛选首批…")
    self.filter_batch_var.set("正在筛选首批…")
    self._filter_scan_serial += 1
    serial = self._filter_scan_serial
    timing_session = ReviewTimingSession(epoch=serial) if timing_enabled else None
    self._focused_timing_session = timing_session
    summary_var = getattr(self, "focused_timing_summary_var", None)
    if summary_var is not None:
        summary_var.set(timing_session.label if timing_session is not None else "")

    pages = list(project.images)
    project_root = project.root
    reference_words = set(self.parent._project_words) if exclude_reference else set()
    y_tolerance = max(
        6, round(max(1, int(self.parent.settings.character_height)) * 0.55)
    )
    ocr_compare_key = self.OCR_COMPARE_LABEL_TO_KEY.get(
        self.review_ocr_compare_var.get(), "fusion"
    )
    first_batch_size = self._focused_batch_size()

    def scan_page(
        page_index: int, sample: dict[str, float] | None = None,
    ) -> tuple[list[dict], bool]:
        """Fast filter pass using only PDIC and OCR JSON, never page pixels."""
        page = pages[page_index]
        entries = read_pdic(pdic_path(page))
        if not entries:
            return [], False

        candidates: list[dict] = []
        missing_ocr = False
        cache = ocr_cache_root(project_root) / f"{page.stem}.json"
        if cache.exists():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    candidates = [
                        row for row in payload.get("review_candidates", [])
                        if isinstance(row, dict)
                    ]
            except Exception:
                candidates = []
        elif include_mismatch:
            missing_ocr = True

        targets: list[dict] = []
        has_positive_filter = include_mismatch or include_chars
        for entry in entries:
            word = str(entry.word or "").strip()
            if exclude_single and _focused_review_is_single_character(word):
                continue
            if exclude_reference and word in reference_words:
                continue

            candidate = _candidate_for_entry_from_list(
                entry, candidates, y_tolerance=y_tolerance
            )
            ocr_words = {
                source: _candidate_word_for_ocr_source(candidate, source)
                for source in ("fusion", "paddle", "tesseract", "lens")
            }
            ocr_word = ocr_words.get(ocr_compare_key, "")
            mismatch = bool(
                include_mismatch
                and ocr_word
                and _review_similarity_key(word)
                != _review_similarity_key(ocr_word)
            )
            matched_tokens = tuple(
                token for token in tokens if token and token in word
            ) if include_chars else ()
            if has_positive_filter and not mismatch and not matched_tokens:
                continue

            reasons: list[str] = []
            if mismatch:
                reasons.append(f"OCR不匹配（OCR结果：{ocr_word}）")
            if matched_tokens:
                reasons.append("含字符：" + "、".join(matched_tokens))
            if not has_positive_filter:
                reasons.append("符合排除条件后的剩余词条")
            targets.append({
                "page_index": int(page_index),
                "page_name": page.name,
                "page_stem": page.stem,
                # Filled from reading-order geometry only when the row is
                # actually rendered; this keeps the scan path image-free.
                "column_number": 1,
                "sequence_number": 0,
                "x": int(entry.x),
                "y": int(entry.y),
                "original_word": word,
                "current_word": word,
                "ocr_source_key": ocr_compare_key,
                "ocr_word": ocr_word,
                "ocr_words": ocr_words,
                "reasons": tuple(reasons),
            })
        if risk_queue_enabled and targets:
            risk_start = perf_counter() if sample is not None else None
            from ..proofreading.review_risk_snapshot import prioritized_focused_page_targets
            targets = prioritized_focused_page_targets(
                targets, project_root=project_root, page=page,
                cache_path=cache, pdic_path=pdic_path(page), enabled=True,
            )
            if risk_start is not None:
                sample["risk"] += perf_counter() - risk_start
                sample["risk_pages"] += 1
        return targets, missing_ocr

    first_sample = {"scan": 0.0, "risk": 0.0, "pages": 0, "risk_pages": 0}

    def first_worker():
        started = perf_counter() if timing_session is not None else None
        targets: list[dict] = []
        pages_without_ocr = 0
        next_position = len(indices)
        for position, page_index in enumerate(indices):
            page_targets, missing_ocr = scan_page(
                page_index, first_sample if timing_session is not None else None
            )
            targets.extend(page_targets)
            pages_without_ocr += int(missing_ocr)
            if started is not None:
                first_sample["pages"] += 1
            # Stop at a page boundary as soon as one complete UI batch is
            # available. Later pages are streamed in batch-sized chunks.
            if len(targets) >= first_batch_size:
                next_position = position + 1
                break
        if started is not None:
            first_sample["scan"] = perf_counter() - started
        return targets, pages_without_ocr, next_position

    def start_remaining_scan(
        start_position: int, pages_without_ocr: int, initial_count: int,
    ) -> None:
        if start_position >= len(indices):
            self._filter_scan_complete = True
            self._update_filter_batch_indicator()
            extra = (
                f"；{pages_without_ocr} 页无 OCR 缓存"
                if include_mismatch and pages_without_ocr else ""
            )
            self.parent.status_var.set(
                f"筛选完成：{len(indices)} 页共 {len(self.filtered_targets)} 条{extra}"
            )
            self._update_title()
            self._schedule_filter_next_batch_preload()
            return

        # If the previous page crossed a batch boundary, keep its overflow.
        # Scan only until the next complete batch is available, then hand
        # that batch back to the UI immediately so its crops can pre-render.
        remainder = int(initial_count) % first_batch_size
        needed_for_next = first_batch_size - remainder if remainder else first_batch_size

        remaining_sample = {"scan": 0.0, "risk": 0.0, "pages": 0, "risk_pages": 0}

        def remaining_worker():
            started = perf_counter() if timing_session is not None else None
            additions: list[dict] = []
            missing_total = pages_without_ocr
            next_position = len(indices)
            for position in range(start_position, len(indices)):
                page_index = indices[position]
                page_targets, missing_ocr = scan_page(
                    page_index, remaining_sample if timing_session is not None else None
                )
                additions.extend(page_targets)
                missing_total += int(missing_ocr)
                if started is not None:
                    remaining_sample["pages"] += 1
                if len(additions) >= needed_for_next:
                    next_position = position + 1
                    break
            if started is not None:
                remaining_sample["scan"] = perf_counter() - started
            return additions, missing_total, next_position

        def remaining_done(payload) -> None:
            if (
                serial != self._filter_scan_serial
                or not getattr(self, "_filter_rows_active", False)
            ):
                return
            additions, missing_total, next_position = payload
            _record_focused_timing(
                self, timing_session, "scan",
                remaining_sample["scan"] if timing_session else None,
                int(remaining_sample["pages"]),
            )
            _record_focused_timing(
                self, timing_session, "risk",
                remaining_sample["risk"] if timing_session else None,
                int(remaining_sample["risk_pages"]),
            )
            had_available = self._filter_available_target_count()
            self.filtered_targets.extend(additions)
            self._filter_scan_complete = next_position >= len(indices)
            available_now = self._filter_available_target_count()
            self._update_filter_batch_indicator()
            self._update_title()

            if self._filter_scan_complete:
                extra = (
                    f"；{missing_total} 页无 OCR 缓存"
                    if include_mismatch and missing_total else ""
                )
                self.parent.status_var.set(
                    f"筛选完成：{len(indices)} 页共 {len(self.filtered_targets)} 条{extra}"
                )
            else:
                self.parent.status_var.set(
                    f"后台筛选中：已扫描 {next_position}/{len(indices)} 页，"
                    f"当前命中 {len(self.filtered_targets)} 条"
                )

            if had_available <= 0 < available_now:
                self.filtered_batch_index = 0
                self._request_filter_batch_render()
            else:
                self._schedule_filter_next_batch_preload()

            if not self._filter_scan_complete:
                start_remaining_scan(
                    next_position, missing_total, len(self.filtered_targets)
                )

        def remaining_failed(_exc, _detail) -> None:
            if (
                serial != self._filter_scan_serial
                or not getattr(self, "_filter_rows_active", False)
            ):
                return
            # Only fully scanned batches may remain available; no failed
            # chunk is published and no visible human edit is discarded.
            # Do not surface exception strings containing project paths.
            self._filter_scan_failed = True
            self._update_filter_batch_indicator()
            # Keep the explicit terminal label for older ReviewWindow
            # integrations that override the indicator helper.
            self.filter_batch_var.set("后续筛选中断（仅已就绪批次）")
            self.parent.status_var.set(
                "后续页面筛选失败，结果不完整；已就绪批次保留，"
                "未扫描页面不计入结果，请检查后重新筛选。"
            )

        self.parent._start_ui_worker(
            f"focused-filter-scan-rest-{id(self)}",
            remaining_worker, remaining_done, remaining_failed,
        )

    def first_done(payload) -> None:
        if (
            serial != self._filter_scan_serial
            or not getattr(self, "_filter_rows_active", False)
        ):
            return
        targets, pages_without_ocr, next_position = payload
        _record_focused_timing(
            self, timing_session, "scan",
            first_sample["scan"] if timing_session else None, int(first_sample["pages"]),
        )
        _record_focused_timing(
            self, timing_session, "risk",
            first_sample["risk"] if timing_session else None,
            int(first_sample["risk_pages"]),
        )
        self.filtered_targets = list(targets)
        self.filtered_batch_index = 0
        self._filter_scan_complete = next_position >= len(indices)
        self._update_title()

        if self.filtered_targets:
            if self._filter_scan_complete:
                extra = (
                    f"；{pages_without_ocr} 页无 OCR 缓存"
                    if include_mismatch and pages_without_ocr else ""
                )
                self.parent.status_var.set(
                    f"筛选完成：{len(indices)} 页共 {len(self.filtered_targets)} 条{extra}"
                )
            else:
                self.parent.status_var.set(
                    f"首批已就绪：已扫描 {next_position}/{len(indices)} 页，"
                    f"当前命中 {len(self.filtered_targets)} 条；后台准备下一批…"
                )
            self._request_filter_batch_render()
        elif self._filter_scan_complete:
            self._request_filter_batch_render()
        else:
            self._clear_review_workspace("首段暂无命中，正在继续筛选…")

        if not self._filter_scan_complete:
            start_remaining_scan(
                next_position, pages_without_ocr, len(self.filtered_targets)
            )

    def failed(_exc, _detail) -> None:
        # Keep the explicit serial comparison recognizable to existing
        # source-level integration guards, then check active Tk mode.
        if serial != self._filter_scan_serial:
            return
        if not getattr(self, "_filter_rows_active", False):
            return
        # The first scan did not publish even one trustworthy batch. An
        # exception is never a successful/complete scan, and raw worker
        # errors can contain private local source paths.
        self._filter_scan_failed = True
        self._filter_scan_complete = False
        self.filtered_targets = []
        self._update_filter_batch_indicator()
        # Older test/GUI adapters may override the indicator helper; the
        # first-batch terminal label must still be visible in that case.
        self.filter_batch_var.set("筛选中断（无完整批次）")
        self._clear_review_workspace(
            "首批筛选失败，结果未建立；请检查页面数据后重新筛选。"
        )
        self.parent.status_var.set(
            "首批筛选失败，结果不完整；未显示任何筛选词条，请检查后重试。"
        )
        messagebox.showerror(
            "重点筛选失败", "首批页面无法完成筛选；请检查后重新筛选。", parent=self
        )

    self.parent._start_ui_worker(
        f"focused-filter-scan-{id(self)}", first_worker, first_done, failed
    )

def _focused_batch_size(self, deps: FocusedFilterDeps) -> int:
    try:
        return max(1, min(500, int(self.focused_batch_size_var.get().strip())))
    except ValueError:
        return 40

def _filter_available_target_count(self, deps: FocusedFilterDeps) -> int:
    """Expose only complete batches while the background scan is unfinished."""
    total = len(self.filtered_targets)
    if self._filter_scan_complete:
        return total
    batch_size = self._focused_batch_size()
    return (total // batch_size) * batch_size

def _update_filter_batch_indicator(self, deps: FocusedFilterDeps) -> None:
    if getattr(self, "_filter_scan_failed", False):
        self.filter_batch_var.set(
            "筛选中断（无完整批次）"
            if self._filter_available_target_count() <= 0
            else "后续筛选中断（仅已就绪批次）"
        )
        return
    available_total = self._filter_available_target_count()
    if available_total <= 0:
        self.filter_batch_var.set(
            "0 / 0" if self._filter_scan_complete else "正在准备下一批…"
        )
        return
    batch_size = self._focused_batch_size()
    batch_count = max(1, (available_total + batch_size - 1) // batch_size)
    batch_index = max(0, min(batch_count - 1, int(self.filtered_batch_index)))
    start = batch_index * batch_size
    end = min(available_total, start + batch_size)
    total_text = str(available_total) if self._filter_scan_complete else f"{available_total}+"
    self.filter_batch_var.set(
        f"第 {batch_index + 1}/{batch_count} 批 · "
        f"{start + 1}-{end} / {total_text}"
    )

def _filter_batch_snapshot(self, deps: FocusedFilterDeps, batch_index: int):
    """Capture all Tk-derived values before a filter-batch worker starts."""
    replace = deps.replace
    project = self.parent.project
    if project is None:
        return None
    available_total = self._filter_available_target_count()
    batch_size = self._focused_batch_size()
    start = int(batch_index) * batch_size
    if start < 0 or start >= available_total:
        return None
    end = min(available_total, start + batch_size)
    targets = [dict(target) for target in self.filtered_targets[start:end]]
    pages = list(project.images)
    settings = replace(self.parent.settings)
    viewer_width = max(1, int(self.parent.canvas.winfo_width()))
    available_width = max(240, self._review_image_area_width())
    review_zoom_auto = bool(self.review_zoom_auto)
    review_zoom = max(0.01, float(self.review_zoom))
    target_signature = tuple(
        (
            int(target["page_index"]),
            int(target["x"]),
            int(target["y"]),
            str(target.get("original_word") or ""),
        )
        for target in targets
    )
    # A prefetched crop from a previous image/PDIC/SECTION revision must
    # never be reused just because the source XY, text or Tk zoom is the same.
    # Use actual source bytes, not mutable size/mtime metadata. This is a
    # volatile readback, not an OS-level multi-file atomic snapshot.
    try:
        source_witness = focused_crop_source_witness(pages, targets)
    except (OSError, ValueError, IndexError):
        return None
    render_signature = (
        target_signature,
        repr(settings),
        viewer_width,
        available_width,
        review_zoom_auto,
        None if review_zoom_auto else round(review_zoom, 6),
        source_witness,
    )
    cache_key = (int(batch_index), render_signature)
    return (
        cache_key, targets, pages, settings, viewer_width, available_width,
        review_zoom, review_zoom_auto,
    )

def _prepare_filter_batch_payload(
    deps: FocusedFilterDeps,
    targets: list[dict], pages: list[Path], settings: AppSettings,
    viewer_width: int, available_width: int, review_zoom: float,
    review_zoom_auto: bool,
) -> tuple[list[Image.Image], float, list[tuple[int, int]]]:
    """Build filter crops off Tk so a prefetched batch can display immediately."""
    read_pdic = deps.read_pdic
    pdic_path = deps.pdic_path
    normalize_page_rgb = deps.normalize_page_rgb
    _review_crop_context = deps._review_crop_context
    sort_entries_reading_order = deps.sort_entries_reading_order
    read_page_sections = deps.read_page_sections
    column_index = deps.column_index
    _review_line_box = deps._review_line_box
    review_auto_fit_zoom = deps.review_auto_fit_zoom
    Image = deps.Image
    raw_crops: list[Image.Image] = []
    display_meta: list[tuple[int, int]] = []
    page_cache: dict[int, tuple[Image.Image, object, list[WordEntry]]] = {}
    for target in targets:
        page_index = int(target["page_index"])
        if page_index not in page_cache:
            page = pages[page_index]
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            review_settings, geometry = _review_crop_context(
                image, settings, viewer_width, page_index,
            )
            ordered = sort_entries_reading_order(
                read_pdic(pdic_path(page)), geometry, read_page_sections(page)
            )
            page_cache[page_index] = (image, (review_settings, geometry), ordered)
        image, context, ordered = page_cache[page_index]
        review_settings, geometry = context
        matches = [
            i for i, entry in enumerate(ordered)
            if int(entry.x) == int(target["x"])
            and int(entry.y) == int(target["y"])
        ]
        if len(matches) > 1:
            preferred = [
                i for i in matches
                if str(ordered[i].word) == str(target.get("original_word") or "")
            ]
            matches = preferred or matches
        if len(matches) != 1:
            raw_crops.append(
                Image.new("RGB", (max(40, available_width // 2), 36), "white")
            )
            display_meta.append((
                int(target.get("column_number", 1) or 1),
                int(target.get("sequence_number", 0) or 0),
            ))
            continue
        row = matches[0]
        entry = ordered[row]
        try:
            column_number = column_index(
                int(entry.x), geometry, int(entry.y)
            ) + 1
        except Exception:
            column_number = 1
        display_meta.append((int(column_number), int(row + 1)))
        next_entry = ordered[row + 1] if row + 1 < len(ordered) else None
        box = _review_line_box(
            entry, geometry, image, review_settings, next_entry
        )
        raw_crops.append(image.crop(box).convert("RGB"))

    effective_zoom = max(0.01, float(review_zoom))
    if review_zoom_auto and raw_crops:
        widest = max(crop.width for crop in raw_crops)
        effective_zoom = review_auto_fit_zoom(
            widest, available_width, 0.99
        )
    crops = [
        crop.resize(
            (
                max(1, round(crop.width * effective_zoom)),
                max(1, round(crop.height * effective_zoom)),
            ),
            Image.Resampling.LANCZOS,
        )
        for crop in raw_crops
    ]
    return crops, effective_zoom, display_meta

def _cache_filter_batch_payload(self, deps: FocusedFilterDeps, cache_key: tuple[int, tuple], payload: tuple) -> None:
    self._filter_batch_render_cache.pop(cache_key, None)
    self._filter_batch_render_cache[cache_key] = payload
    while len(self._filter_batch_render_cache) > 4:
        oldest = next(iter(self._filter_batch_render_cache))
        self._filter_batch_render_cache.pop(oldest, None)

def _apply_filter_batch_payload(
    self, deps: FocusedFilterDeps, batch_index: int, cache_key: tuple[int, tuple], payload: tuple,
) -> bool:
    _format_layout_percent = deps._format_layout_percent
    if (
        not getattr(self, "_filter_rows_active", False)
        or int(self.filtered_batch_index) != int(batch_index)
    ):
        return False
    snapshot = self._filter_batch_snapshot(batch_index)
    if snapshot is None or snapshot[0] != cache_key:
        # Neither a late prefetch nor a cached payload owns a changed source.
        # Do not clear the current editors or discard an unsaved human edit.
        status = getattr(self.parent, "status_var", None)
        if status is not None:
            status.set("本批裁剪来源或显示条件已变化，旧预览已拒绝；请核对后重新筛选。")
        return False
    _key, _targets_copy, _pages, _settings, _viewer_width, _available_width, _zoom, _auto = snapshot
    batch_size = self._focused_batch_size()
    start = int(batch_index) * batch_size
    end = min(self._filter_available_target_count(), start + batch_size)
    targets = self.filtered_targets[start:end]

    crops, effective_zoom, display_meta = payload
    if len(crops) != len(targets) or len(display_meta) != len(targets):
        return False
    # The accepted crop (not a later save-time disk read) is the source of
    # truth for a subsequently edited row. Bind only image and SECTION: PDIC
    # necessarily changes after a successful human correction.
    source_witness = cache_key[1][-1]
    for target, (column_number, sequence_number) in zip(targets, display_meta):
        target["column_number"] = int(column_number)
        target["sequence_number"] = int(sequence_number)
        target["_focused_save_source_witness"] = focused_save_source_from_crop_witness(
            source_witness, int(target["page_index"])
        )
    if self.review_zoom_auto:
        self.review_zoom = max(0.01, float(effective_zoom))
        self.review_zoom_var.set(f"自动 {_format_layout_percent(self.review_zoom * 100.0)}%")
    self._update_filter_batch_indicator()
    self._render_filter_batch(targets, crops)
    self._reset_rows_scroll_top()
    self._schedule_filter_next_batch_preload()
    return True

def _schedule_filter_next_batch_preload(self, deps: FocusedFilterDeps) -> None:
    """Prepare N+1 while the user proofreads N."""
    if not getattr(self, "_filter_rows_active", False):
        return
    next_index = int(self.filtered_batch_index) + 1
    snapshot = self._filter_batch_snapshot(next_index)
    if snapshot is None:
        return
    (
        cache_key, targets, pages, settings, viewer_width, available_width,
        review_zoom, review_zoom_auto,
    ) = snapshot
    if cache_key in self._filter_batch_render_cache:
        return
    if self._filter_prefetch_key == cache_key:
        return
    self._filter_prefetch_key = cache_key
    worker_key = f"focused-filter-prefetch-{id(self)}"
    scan_epoch = getattr(self, "_filter_scan_serial", None)
    timing_session = getattr(self, "_focused_timing_session", None)
    crop_seconds = [None]

    ReviewWindow = deps.ReviewWindow

    def worker(
        local_targets=targets, local_pages=pages, local_settings=settings,
        local_viewer_width=viewer_width, local_available_width=available_width,
        local_review_zoom=review_zoom, local_review_zoom_auto=review_zoom_auto,
    ):
        started = perf_counter() if timing_session is not None else None
        result = ReviewWindow._prepare_filter_batch_payload(
            local_targets, local_pages, local_settings,
            local_viewer_width, local_available_width,
            local_review_zoom, local_review_zoom_auto,
        )
        if started is not None:
            crop_seconds[0] = perf_counter() - started
        return result

    def done(payload, local_key=cache_key, local_index=next_index) -> None:
        if scan_epoch != getattr(self, "_filter_scan_serial", None):
            return
        _record_focused_timing(self, timing_session, "crop", crop_seconds[0])
        if self._filter_prefetch_key == local_key:
            self._filter_prefetch_key = None
        if not getattr(self, "_filter_rows_active", False):
            return
        self._cache_filter_batch_payload(local_key, payload)
        # If the user clicked 【下一批】 while this worker was still running,
        # complete that navigation immediately from the freshly built cache.
        if int(self.filtered_batch_index) == int(local_index):
            self._apply_filter_batch_payload(local_index, local_key, payload)

    def failed(_exc, _detail, local_key=cache_key) -> None:
        if scan_epoch != getattr(self, "_filter_scan_serial", None):
            return
        # Prefetch is optional. Let a later navigation retry the batch,
        # without publishing raw paths from a stale/failed crop worker.
        if self._filter_prefetch_key == local_key:
            self._filter_prefetch_key = None

    self.parent._start_ui_worker(
        worker_key, worker, done, failed,
    )

def change_filter_batch(self, deps: FocusedFilterDeps, delta: int) -> None:
    if not self._filter_rows_active or not self.filtered_targets:
        return
    available_total = self._filter_available_target_count()
    if available_total <= 0:
        return
    batch_size = self._focused_batch_size()
    batch_count = max(1, (available_total + batch_size - 1) // batch_size)
    requested = self.filtered_batch_index + int(delta)
    target = max(0, min(batch_count - 1, requested))
    if target == self.filtered_batch_index:
        if int(delta) > 0 and getattr(self, "_filter_scan_failed", False):
            self.parent.status_var.set(
                "后续筛选已中断，请重新筛选以处理尚未扫描的页面。"
            )
        elif int(delta) > 0 and not self._filter_scan_complete:
            self.parent.status_var.set("下一批仍在后台筛选与预生成，请继续校对当前批次。")
            self._schedule_filter_next_batch_preload()
        return
    self._flush_focused_changes_now()
    if self._filter_save_running or self._filter_pending_changes:
        # A background writer being scheduled does not mean the original
        # batch's human corrections have reached PDIC. Preserve its visible
        # editors on write failure/uncertainty instead of losing the source
        # batch as soon as the worker starts.
        self.parent.status_var.set(
            "筛选校对修改尚未保存完成，暂不能切换下一批。"
        )
        return
    self.filtered_batch_index = target
    self._request_filter_batch_render()

def _request_filter_batch_render(self, deps: FocusedFilterDeps) -> None:
    if not getattr(self, "_filter_rows_active", False):
        return
    available_total = self._filter_available_target_count()
    if available_total <= 0:
        if getattr(self, "_filter_scan_failed", False):
            self.filter_batch_var.set("筛选中断（无完整批次）")
            self._clear_review_workspace("筛选失败，结果不完整；请重新筛选。")
        elif self._filter_scan_complete:
            self.filter_batch_var.set("0 / 0")
            self._clear_review_workspace("当前条件没有筛选出词条。")
        else:
            self.filter_batch_var.set("正在准备下一批…")
            self._clear_review_workspace("正在后台筛选下一批…")
        return

    batch_size = self._focused_batch_size()
    batch_count = max(1, (available_total + batch_size - 1) // batch_size)
    self.filtered_batch_index = max(
        0, min(batch_count - 1, int(self.filtered_batch_index))
    )
    self._update_filter_batch_indicator()
    self._set_filter_navigation(True)
    snapshot = self._filter_batch_snapshot(self.filtered_batch_index)
    if snapshot is None:
        # A disappeared/unreadable image, PDIC or SECTION is not a valid
        # crop. Never silently retain another batch's thumbnail as this one.
        self.parent.status_var.set(
            "当前批次的原图、PDIC 或 SECTION 无法核验；请检查来源后重新筛选。"
        )
        if not self._filter_save_running and not self._filter_pending_changes:
            self._clear_review_workspace("裁剪来源不可核验，未生成本批预览。")
        return
    (
        cache_key, targets, pages, settings, viewer_width, available_width,
        review_zoom, review_zoom_auto,
    ) = snapshot

    self._filter_render_serial += 1
    serial = self._filter_render_serial
    scan_epoch = getattr(self, "_filter_scan_serial", None)
    timing_session = getattr(self, "_focused_timing_session", None)
    crop_seconds = [None]
    cached = self._filter_batch_render_cache.get(cache_key)
    if cached is not None:
        self._apply_filter_batch_payload(
            self.filtered_batch_index, cache_key, cached
        )
        return

    if self._filter_prefetch_key == cache_key:
        self._clear_review_workspace("下一批已在后台预生成，即将显示…")
        return

    self._clear_review_workspace("正在异步生成本批切词行…")

    ReviewWindow = deps.ReviewWindow

    def worker(
        local_targets=targets, local_pages=pages, local_settings=settings,
        local_viewer_width=viewer_width, local_available_width=available_width,
        local_review_zoom=review_zoom, local_review_zoom_auto=review_zoom_auto,
    ):
        started = perf_counter() if timing_session is not None else None
        result = ReviewWindow._prepare_filter_batch_payload(
            local_targets, local_pages, local_settings,
            local_viewer_width, local_available_width,
            local_review_zoom, local_review_zoom_auto,
        )
        if started is not None:
            crop_seconds[0] = perf_counter() - started
        return result

    def done(payload, local_index=int(self.filtered_batch_index), local_key=cache_key) -> None:
        if (
            serial != self._filter_render_serial
            or scan_epoch != getattr(self, "_filter_scan_serial", None)
            or not getattr(self, "_filter_rows_active", False)
        ):
            return
        _record_focused_timing(self, timing_session, "crop", crop_seconds[0])
        self._cache_filter_batch_payload(local_key, payload)
        self._apply_filter_batch_payload(local_index, local_key, payload)

    def failed(_exc, _detail) -> None:
        if (
            serial != self._filter_render_serial
            or scan_epoch != getattr(self, "_filter_scan_serial", None)
            or not getattr(self, "_filter_rows_active", False)
        ):
            return
        # A crop failure cannot mutate the next scan's workspace or
        # disclose a private page path through the ReviewWindow status.
        self._clear_review_workspace(
            "本批切词行生成失败；请检查页面数据后重试。"
        )
        self.parent.status_var.set(
            "本批裁剪未能生成，请检查源文件后重试。"
        )

    self.parent._start_ui_worker(
        f"focused-filter-render-{id(self)}", worker, done, failed
    )

def _render_filter_batch(
    self, deps: FocusedFilterDeps, targets: list[dict], crops: list[Image.Image],
) -> None:
    Image = deps.Image
    tk = deps.tk
    ttk = deps.ttk
    ImageTk = deps.ImageTk
    resolve_content_font_family = deps.resolve_content_font_family
    _review_editor_font_size = deps._review_editor_font_size
    _entry_font_spec = deps._entry_font_spec
    themed_display_image = deps.themed_display_image
    for child in self.rows.winfo_children():
        child.destroy()
    self.filter_vars = []
    self.filter_editors = []
    self.filter_thumbnails = []
    self._filter_current_batch_targets = list(targets)
    if not targets:
        self._clear_review_workspace("当前批次为空。")
        return

    family = resolve_content_font_family(
        self, self.parent.settings.review_entry_font_family,
        self.parent.settings.ocr_language,
    )
    font_size = _review_editor_font_size(self.parent.settings)
    font_spec = _entry_font_spec(
        family, font_size,
        self.parent.settings.review_entry_font_bold,
        self.parent.settings.review_entry_font_italic,
    )
    reference_words = set(self.parent._project_words)
    for index, target in enumerate(targets):
        row = ttk.Frame(
            self.rows, padding=(6, 4), style="PCR.Surface.TFrame"
        )
        row.grid(row=index, column=0, sticky="ew", padx=4, pady=(2, 5))
        row.columnconfigure(0, weight=1)

        header = ttk.Frame(row, style="PCR.Surface.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        reason = "；".join(str(value) for value in target.get("reasons", ())) or "—"
        ttk.Label(
            header,
            text=(
                f"{target['page_name']} | 第{int(target.get('column_number', 1))}栏 | "
                f"序号 {int(target.get('sequence_number', index + 1))} | 原因：{reason}"
            ),
            style="PCR.Header.TLabel",
        ).pack(side="left")

        crop = crops[index] if index < len(crops) else Image.new("RGB", (320, 36), "white")
        photo = ImageTk.PhotoImage(
            themed_display_image(crop, self.parent.appearance_mode)
        )
        self.filter_thumbnails.append(photo)
        ttk.Label(
            row, image=photo, style="PCR.Crop.TLabel",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 2))

        value = str(target.get("current_word", target.get("original_word", "")))
        variable = tk.StringVar(value=value)
        self.filter_vars.append(variable)
        editor_bg, editor_fg, selection_bg, selection_fg = (
            self._review_membership_colors(value in reference_words)
        )
        editor_row = ttk.Frame(row, style="PCR.Surface.TFrame")
        editor_row.grid(row=2, column=0, sticky="ew")
        editor = tk.Entry(
            editor_row, textvariable=variable, font=font_spec,
            bg=editor_bg, foreground=editor_fg, insertbackground=editor_fg,
            selectbackground=selection_bg, selectforeground=selection_fg,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=editor_bg, highlightcolor=editor_bg,
        )
        editor._pc_skip_classic_appearance = True
        editor.pack(
            side="left", fill="x", expand=True,
            ipady=max(0, int(self.parent.settings.review_entry_vertical_padding)),
        )
        ttk.Button(
            editor_row, text="填充OCR结果",
            command=lambda i=index: self._fill_filter_ocr_result(i),
            style="PCR.Compact.TButton",
        ).pack(side="right", padx=(5, 0))
        self.filter_editors.append(editor)

        def commit_bound_filter_var(
            *_trace_args, i=index, expected_var=variable, expected_target=target,
        ) -> None:
            # A Tk StringVar write captures paste, cut, replacement and IME
            # commits even when the platform emits no KeyRelease. An old
            # variable may still outlive a batch redraw: never reuse its
            # row index for a newly rendered page/XY owner.
            if (
                not getattr(self, "_filter_rows_active", False)
                or i >= len(self.filter_vars)
                or self.filter_vars[i] is not expected_var
                or i >= len(self._filter_current_batch_targets)
                or self._filter_current_batch_targets[i] is not expected_target
            ):
                return
            self._commit_filter_editor_value(i)

        variable.trace_add("write", commit_bound_filter_var)
        editor.bind("<FocusIn>", lambda _event, i=index: self._set_filter_active(i))
        editor.bind("<KeyRelease>", lambda event, i=index: self._on_filter_key(event, i))
        editor.bind("<FocusOut>", lambda _event, callback=commit_bound_filter_var: callback())
        editor.bind("<Return>", lambda _event, i=index: self._focus_filter_index(i + 1))
        editor.bind("<Up>", lambda _event, i=index: self._focus_filter_index(i - 1))
        editor.bind("<Down>", lambda _event, i=index: self._focus_filter_index(i + 1))
        editor.bind("<MouseWheel>", self.scroll_rows)
        editor.bind("<Button-4>", lambda e: self.scroll_rows_linux(-1))
        editor.bind("<Button-5>", lambda e: self.scroll_rows_linux(1))
    self.rows.columnconfigure(0, weight=1)
    self.filter_active_local_index = 0
    if self.filter_editors:
        self.filter_editors[0].focus_set()


def _persist_focused_filter_settings(self, deps: FocusedFilterDeps) -> None:
    """Validate first; never partially change settings on invalid input."""
    settings = self.parent.settings
    include_mismatch = bool(self.focused_include_mismatch_var.get())
    include_chars = bool(self.focused_include_characters_var.get())
    exclude_single = bool(self.focused_exclude_single_var.get())
    exclude_reference = bool(self.focused_exclude_reference_var.get())
    characters = self.focused_characters_var.get().strip()
    # Older adapter/test owners legitimately lack these optional Tk controls.
    priority_var = getattr(self, "focused_risk_priority_var", None)
    capture_var = getattr(self, "focused_risk_capture_var", None)
    timing_var = getattr(self, "focused_timing_var", None)
    risk_enabled = (
        bool(priority_var.get()) if priority_var is not None
        else bool(getattr(settings, "focused_review_risk_queue_enabled", False))
    )
    capture_enabled = (
        bool(capture_var.get()) if capture_var is not None
        else bool(getattr(settings, "focused_review_risk_witness_capture", False))
    )
    timing_enabled = (
        bool(timing_var.get()) if timing_var is not None
        else bool(getattr(settings, "focused_review_timing_enabled", False))
    )
    try:
        batch_size = int(self.focused_batch_size_var.get().strip())
    except ValueError as exc:
        raise ValueError("单批显示数量必须是整数。") from exc
    validated_size = max(1, min(500, batch_size))
    settings.focused_review_include_ocr_mismatch = include_mismatch
    settings.focused_review_include_characters = include_chars
    settings.focused_review_exclude_single_character = exclude_single
    settings.focused_review_exclude_reference_words = exclude_reference
    settings.focused_review_characters = characters
    settings.focused_review_risk_queue_enabled = risk_enabled
    settings.focused_review_risk_witness_capture = capture_enabled
    settings.focused_review_timing_enabled = timing_enabled
    settings.focused_review_batch_size = validated_size
    self.focused_batch_size_var.set(str(validated_size))
    self.parent.save_settings()


def _set_filter_active(self, deps: FocusedFilterDeps, index: int) -> None:
    # Keep the active row stable while batch widgets are repainted.
    # A stale row index must never become the active selection.
    if 0 <= int(index) < len(getattr(self, "filter_editors", [])):
        self.filter_active_local_index = int(index)


def _focus_filter_index(self, deps: FocusedFilterDeps, index: int) -> str:
    tk = deps.tk
    editors = getattr(self, "filter_editors", [])
    if editors:
        target = max(0, min(len(editors) - 1, int(index)))
        self.filter_active_local_index = target
        editors[target].focus_set()
        editors[target].icursor("end")
        try:
            self.canvas.yview_moveto(
                max(0.0, min(1.0, target / max(1, len(editors) - 1)))
            )
        except tk.TclError:
            pass
    return "break"


def _filter_ocr_word(self, deps: FocusedFilterDeps, target: dict) -> str:
    key = self.OCR_COMPARE_LABEL_TO_KEY.get(
        self.review_ocr_compare_var.get(), "fusion"
    )
    words = target.get("ocr_words") or {}
    if not isinstance(words, dict):
        return ""
    return str(words.get(key) or "").strip()


def _fill_filter_ocr_result(self, deps: FocusedFilterDeps, index: int) -> None:
    if not (0 <= index < len(getattr(self, "filter_vars", []))):
        return
    target = self._filter_current_batch_targets[index]
    ocr_word = self._filter_ocr_word(target)
    if not ocr_word:
        source = self.review_ocr_compare_var.get()
        self.parent.status_var.set(f"当前词条没有 {source} 结果可填充")
        return
    self.filter_vars[index].set(ocr_word)
    self.filter_editors[index].focus_set()
    self.filter_editors[index].icursor("end")
    self._commit_filter_editor_value(index)


def _commit_filter_editor_value(self, deps: FocusedFilterDeps, index: int) -> None:
    tk = deps.tk
    if not (0 <= index < len(getattr(self, "filter_vars", []))):
        return
    target = self._filter_current_batch_targets[index]
    editor = self.filter_editors[index]
    value = self.filter_vars[index].get().strip()
    current = str(
        target.get("current_word", target.get("original_word", ""))
    ).strip()
    if value == current:
        # StringVar.trace_add already committed this exact editor value.
        # A later KeyRelease / FocusOut must not reschedule an extra writer.
        return
    target["current_word"] = value
    in_reference = value in set(self.parent._project_words)
    color = "#b3fddd" if in_reference else "#fce5e8"
    try:
        editor.configure(
            bg=color, foreground="#111827", insertbackground="#111827",
            highlightbackground=color, highlightcolor=color,
        )
    except tk.TclError:
        pass
    self._queue_focused_change(target, value)


def _on_filter_key(self, deps: FocusedFilterDeps, event: tk.Event, index: int) -> None:
    tk = deps.tk
    if not (0 <= index < len(getattr(self, "filter_vars", []))):
        return
    self._set_filter_active(index)
    char = getattr(event, "char", "")
    editor = self.filter_editors[index]
    if self.replace_digits.get() and char in self.DIGIT_KEYS:
        replacement = self.digit_map_vars[self.DIGIT_KEYS.index(char)].get()
        if replacement:
            pos = editor.index("insert")
            text = editor.get()
            start = max(0, pos - 1)
            editor.delete(0, "end")
            editor.insert(0, text[:start] + replacement + text[pos:])
            editor.icursor(start + len(replacement))
    self._commit_filter_editor_value(index)


def _queue_focused_change(self, deps: FocusedFilterDeps, target: dict, value: str) -> None:
    tk = deps.tk
    page_index = int(target["page_index"])
    key = (int(target["x"]), int(target["y"]))
    original = str(target.get("original_word") or "")
    clean = (
        str(value or "").replace("\r", " ").replace("\n", " ")
        .replace("#", "＃").strip()
    )
    target["current_word"] = clean
    if clean == original:
        page_changes = self._filter_pending_changes.get(page_index)
        if page_changes is not None:
            page_changes.pop(key, None)
            if not page_changes:
                self._filter_pending_changes.pop(page_index, None)
    else:
        change = {
            "page_index": page_index,
            "x": key[0], "y": key[1],
            "original_word": original,
            "new_word": clean,
        }
        # Never fabricate source ownership from the disk at save time:
        # a hidden external file change after crop display must be detected.
        source_witness = target.get("_focused_save_source_witness")
        if source_witness is not None:
            change["_focused_save_source_witness"] = source_witness
        self._filter_pending_changes.setdefault(page_index, {})[key] = change
    if self._filter_save_job is not None:
        try:
            self.after_cancel(self._filter_save_job)
        except tk.TclError:
            pass
    self._filter_save_job = self.after(160, self._flush_focused_changes)


def _flush_focused_changes_now(self, deps: FocusedFilterDeps) -> None:
    tk = deps.tk
    if self._filter_save_job is not None:
        try:
            self.after_cancel(self._filter_save_job)
        except tk.TclError:
            pass
        self._filter_save_job = None
    self._flush_focused_changes()


def _flush_focused_changes(self, deps: FocusedFilterDeps) -> None:
    messagebox = deps.messagebox
    _apply_focused_review_page_updates = deps._apply_focused_review_page_updates
    self._filter_save_job = None
    if self._filter_save_running or not self._filter_pending_changes:
        return
    project = self.parent.project
    if project is None:
        return
    snapshot = {
        page_index: list(changes.values())
        for page_index, changes in self._filter_pending_changes.items()
        if changes
    }
    if not snapshot:
        return
    self._filter_pending_changes.clear()
    self._filter_save_running = True
    pages = list(project.images)
    timing_session = getattr(self, "_focused_timing_session", None)
    save_seconds = [None]

    def restore_unwritten(committed: set[tuple[int, int, int]]) -> bool:
        """Requeue only unsaved snapshot entries, without erasing newer edits.

        A second edit at the same source page/XY can arrive while the writer
        is running. That newer pending value owns the coordinate. A revert
        to the original text also takes precedence over an old snapshot.
        """
        visible_targets = {
            (int(target["page_index"]), int(target["x"]), int(target["y"])): target
            for target in getattr(self, "filtered_targets", ())
        }
        recovered = False
        for page_index, changes in snapshot.items():
            for change in changes:
                x, y = int(change["x"]), int(change["y"])
                point = (int(page_index), x, y)
                row_key = (x, y)
                if point in committed:
                    continue
                if row_key in self._filter_pending_changes.get(page_index, {}):
                    # An in-flight edit is newer than the failed write.
                    continue
                target = visible_targets.get(point)
                if (
                    target is not None and "current_word" in target
                    and str(target["current_word"]).strip()
                    == str(change.get("original_word") or "").strip()
                ):
                    # An explicit user reversion supersedes the old snapshot.
                    continue
                self._filter_pending_changes.setdefault(page_index, {})[row_key] = change
                recovered = True
        return recovered

    def worker():
        started = perf_counter() if timing_session is not None else None
        saved: list[tuple[int, int, int, str]] = []
        conflicts: list[str] = []
        # Preflight every page before any PDIC write: a stale page among
        # several edited pages must not allow a partial first-page save.
        # Actual ReviewWindow filter mode has _filter_rows_active=True.
        # Keep legacy standalone helper/mock ABI intact outside filter mode.
        if getattr(self, "_filter_rows_active", False):
            for page_index, changes in sorted(snapshot.items()):
                expected = changes[0].get("_focused_save_source_witness")
                if expected is None or any(
                    change.get("_focused_save_source_witness") != expected
                    for change in changes
                ):
                    raise RuntimeError(
                        "筛选校对缺少一致的原图与 SECTION 来源证明，拒绝保存"
                    )
                verify_focused_save_source(pages[page_index], expected)
        for page_index, changes in sorted(snapshot.items()):
            page_saved, page_conflicts = _apply_focused_review_page_updates(
                pages[page_index], pages, page_index, changes
            )
            saved.extend(page_saved)
            conflicts.extend(page_conflicts)
        if started is not None:
            save_seconds[0] = perf_counter() - started
        return saved, conflicts

    def done(payload) -> None:
        self._filter_save_running = False
        saved, conflicts = payload
        _record_focused_timing(
            self, timing_session, "save", save_seconds[0], len(saved),
        )
        saved_map = {
            (int(page_index), int(x), int(y)): str(word)
            for page_index, x, y, word in saved
        }
        for target in self.filtered_targets:
            key = (
                int(target["page_index"]), int(target["x"]), int(target["y"])
            )
            if key in saved_map:
                target["original_word"] = saved_map[key]
        # Pending edits made while this worker was running must use the new
        # on-disk word as their ambiguity guard on the next serialized write.
        for page_index, changes in self._filter_pending_changes.items():
            for key, change in changes.items():
                saved_word = saved_map.get((int(page_index), int(key[0]), int(key[1])))
                if saved_word is not None:
                    change["original_word"] = saved_word

        # If a user returned a row to its pre-write original while this
        # worker was running, the old queue legitimately became empty.
        # Once the older snapshot *successfully* commits, that user's
        # reversion is now a new change relative to the committed PDIC.
        # Preserve any separately queued newer edit as the stronger owner.
        for target in self.filtered_targets:
            point = (
                int(target["page_index"]), int(target["x"]), int(target["y"])
            )
            saved_word = saved_map.get(point)
            if saved_word is None or "current_word" not in target:
                continue
            page_index, x, y = point
            current_word = (
                str(target["current_word"] or "")
                .replace("\r", " ").replace("\n", " ")
                .replace("#", "＃").strip()
            )
            row_key = (x, y)
            queued = self._filter_pending_changes.get(page_index, {}).get(row_key)
            if queued is not None:
                # A newer, serialized edit already owns the page/XY.
                # Drop only a redundant edit to precisely the saved text.
                if (
                    str(queued.get("new_word") or "") == saved_word
                    and current_word == saved_word
                ):
                    changes = self._filter_pending_changes[page_index]
                    changes.pop(row_key, None)
                    if not changes:
                        self._filter_pending_changes.pop(page_index, None)
            elif current_word != saved_word:
                # Reversion during an in-flight save becomes a fresh edit
                # relative to the just-published PDIC. Reuse the accepted
                # crop's image/SECTION provenance; do not mint new proof
                # from disk in the save-completion callback.
                replacement = {
                    "page_index": page_index,
                    "x": x, "y": y,
                    "original_word": saved_word,
                    "new_word": current_word,
                }
                source_witness = target.get("_focused_save_source_witness")
                if source_witness is not None:
                    replacement["_focused_save_source_witness"] = source_witness
                # A missing witness still fails closed in the next worker.
                self._filter_pending_changes.setdefault(page_index, {})[row_key] = replacement

        # The writer returns no saved rows for a page with source-coordinate
        # conflicts. Never drop that page's original human corrections or
        # overwrite edits made after this snapshot was dispatched.
        recovered = restore_unwritten(set(saved_map))
        if conflicts:
            # A pending close request must not survive a failed/conflicted
            # write and silently close after some unrelated later autosave.
            self._filter_close_after_save = False

        current_index = int(self.parent.current_index)
        current_saved = {
            (x, y): word
            for page_index, x, y, word in saved
            if int(page_index) == current_index
        }
        if current_saved:
            saved_entries = []
            for entry in self.parent.entries:
                value = current_saved.get((int(entry.x), int(entry.y)))
                if value is not None:
                    entry.word = value
                    entry.confidence = None
                    entry.ocr_source = "manual"
                    entry.final_engine = "manual"
                    entry.manually_selected = True
                    saved_entries.append(entry)
            # Filtered writes finish off-thread. The main window retains its
            # own Tk editor buffers; ordinary page navigation would otherwise
            # copy the stale buffer over the newly committed PDIC Entry.word.
            # Reconcile only saved, live Entry object identities.
            from ..proofreading.main_editor_sync import reconcile_main_editors_after_review
            reconcile_main_editors_after_review(self.parent, saved_entries)

        if conflicts:
            messagebox.showwarning(
                "部分筛选词条未保存",
                "以下词条的 PDIC 坐标已变化或存在歧义，因此未写入：\n\n"
                + "\n".join(conflicts[:20])
                + ("\n…" if len(conflicts) > 20 else ""),
                parent=self,
            )
        self.parent.status_var.set(
            f"筛选校对已保存 {len(saved)} 条修改"
            + (f"；{len(conflicts)} 条冲突" if conflicts else "")
        )
        if self._filter_pending_changes and not conflicts and not recovered:
            # Newer edits after a successful write can be serialized next.
            self._filter_save_job = self.after(1, self._flush_focused_changes)
        elif self._filter_close_after_save and not self._filter_pending_changes:
            self._filter_close_after_save = False
            self._finish_close_review()

    def failed(_exc, _detail) -> None:
        self._filter_save_running = False
        self._filter_close_after_save = False
        # Restore unsaved work for explicit retry, never overwrite a later
        # edit or an explicit reversion made while the worker was running.
        restore_unwritten(set())
        # Worker exceptions/tracebacks can contain private project paths or
        # headwords. Do not echo them to stdout, status, or Tk error dialogs.
        # Keep the retry guidance generic and retain the human edit buffer.
        self.parent.status_var.set(
            "筛选校对保存失败：未确认写入的修改已保留，请检查后重试。"
        )
        messagebox.showerror(
            "筛选校对保存失败",
            "本次保存未完成；校对修改仍可核对或重试，请检查项目文件。",
            parent=self,
        )

    self.parent._start_ui_worker(
        f"focused-filter-save-{id(self)}",
        worker, done, failed, wait_on_close=True,
    )

