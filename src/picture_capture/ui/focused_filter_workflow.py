"""Physical owner for focused review scan, crop batching and Tk row painting.

Live app patchpoints captured at dispatch; no imports from the heavyweight app.
Worker scheduling, cancel serials, cache contents and Tk-thread behavior unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from PIL import Image
    from ..models import AppSettings, Entry as WordEntry


@dataclass(frozen=True)
class FocusedFilterDeps:
    """Original app-level bindings captured separately for each operation."""
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
    try:
        # Reuse the main-window 【指定】 parser exactly. This preserves
        # filename-number matching, leading zeroes, mixed comma ranges and
        # all accepted hyphen/tilde variants without a second parser.
        indices = self.parent._parse_page_spec(
            self.focused_page_range_var.get()
        )
        self._persist_focused_filter_settings()
    except Exception as exc:
        messagebox.showerror("筛选条件无效", str(exc), parent=self)
        return

    include_mismatch = bool(self.focused_include_mismatch_var.get())
    include_chars = bool(self.focused_include_characters_var.get())
    exclude_single = bool(self.focused_exclude_single_var.get())
    exclude_reference = bool(self.focused_exclude_reference_var.get())
    tokens = _focused_review_character_tokens(self.focused_characters_var.get())
    if include_chars and not tokens:
        messagebox.showinfo(
            "特定字符为空",
            "已勾选【含特定字符】，请先输入至少一个字符。",
            parent=self,
        )
        return

    if not getattr(self, "_filter_rows_active", False):
        self.save(redraw_main=False)
    self.review_mode_var.set("filter")
    self._filter_rows_active = True
    self._set_filter_navigation(True)
    self.parent._invalidate_ui_worker(self._review_render_worker_key)
    self.parent._invalidate_ui_worker(f"focused-filter-scan-rest-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-render-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-prefetch-{id(self)}")
    self._filter_batch_render_cache.clear()
    self._filter_prefetch_key = None
    self._filter_scan_complete = False
    self.filtered_targets = []
    self.filtered_batch_index = 0
    self._clear_review_workspace("正在快速筛选首批…")
    self.filter_batch_var.set("正在筛选首批…")
    self._filter_scan_serial += 1
    serial = self._filter_scan_serial

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

    def scan_page(page_index: int) -> tuple[list[dict], bool]:
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
        return targets, missing_ocr

    def first_worker():
        targets: list[dict] = []
        pages_without_ocr = 0
        next_position = len(indices)
        for position, page_index in enumerate(indices):
            page_targets, missing_ocr = scan_page(page_index)
            targets.extend(page_targets)
            pages_without_ocr += int(missing_ocr)
            # Stop at a page boundary as soon as one complete UI batch is
            # available. Later pages are streamed in batch-sized chunks.
            if len(targets) >= first_batch_size:
                next_position = position + 1
                break
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

        def remaining_worker():
            additions: list[dict] = []
            missing_total = pages_without_ocr
            next_position = len(indices)
            for position in range(start_position, len(indices)):
                page_index = indices[position]
                page_targets, missing_ocr = scan_page(page_index)
                additions.extend(page_targets)
                missing_total += int(missing_ocr)
                if len(additions) >= needed_for_next:
                    next_position = position + 1
                    break
            return additions, missing_total, next_position

        def remaining_done(payload) -> None:
            if (
                serial != self._filter_scan_serial
                or not getattr(self, "_filter_rows_active", False)
            ):
                return
            additions, missing_total, next_position = payload
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

        def remaining_failed(exc, detail) -> None:
            if detail:
                print(detail)
            if serial != self._filter_scan_serial:
                return
            self.parent.status_var.set(f"后续页面筛选失败：{exc}")

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

    def failed(exc, detail) -> None:
        if detail:
            print(detail)
        if serial != self._filter_scan_serial:
            return
        self._filter_scan_complete = True
        self.filter_batch_var.set("筛选失败")
        self._clear_review_workspace(f"筛选失败：{exc}")
        messagebox.showerror("重点筛选失败", str(exc), parent=self)

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
    render_signature = (
        target_signature,
        repr(settings),
        viewer_width,
        available_width,
        review_zoom_auto,
        None if review_zoom_auto else round(review_zoom, 6),
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
        return False
    _key, _targets_copy, _pages, _settings, _viewer_width, _available_width, _zoom, _auto = snapshot
    batch_size = self._focused_batch_size()
    start = int(batch_index) * batch_size
    end = min(self._filter_available_target_count(), start + batch_size)
    targets = self.filtered_targets[start:end]

    crops, effective_zoom, display_meta = payload
    if len(crops) != len(targets) or len(display_meta) != len(targets):
        return False
    for target, (column_number, sequence_number) in zip(targets, display_meta):
        target["column_number"] = int(column_number)
        target["sequence_number"] = int(sequence_number)
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

    def worker(
        local_targets=targets, local_pages=pages, local_settings=settings,
        local_viewer_width=viewer_width, local_available_width=available_width,
        local_review_zoom=review_zoom, local_review_zoom_auto=review_zoom_auto,
    ):
        return ReviewWindow._prepare_filter_batch_payload(
            local_targets, local_pages, local_settings,
            local_viewer_width, local_available_width,
            local_review_zoom, local_review_zoom_auto,
        )

    def done(payload, local_key=cache_key, local_index=next_index) -> None:
        if self._filter_prefetch_key == local_key:
            self._filter_prefetch_key = None
        if not getattr(self, "_filter_rows_active", False):
            return
        self._cache_filter_batch_payload(local_key, payload)
        # If the user clicked 【下一批】 while this worker was still running,
        # complete that navigation immediately from the freshly built cache.
        if int(self.filtered_batch_index) == int(local_index):
            self._apply_filter_batch_payload(local_index, local_key, payload)

    def failed(exc, detail, local_key=cache_key) -> None:
        if detail:
            print(detail)
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
        if int(delta) > 0 and not self._filter_scan_complete:
            self.parent.status_var.set("下一批仍在后台筛选与预生成，请继续校对当前批次。")
            self._schedule_filter_next_batch_preload()
        return
    self._flush_focused_changes_now()
    self.filtered_batch_index = target
    self._request_filter_batch_render()

def _request_filter_batch_render(self, deps: FocusedFilterDeps) -> None:
    if not getattr(self, "_filter_rows_active", False):
        return
    available_total = self._filter_available_target_count()
    if available_total <= 0:
        if self._filter_scan_complete:
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
        return
    (
        cache_key, targets, pages, settings, viewer_width, available_width,
        review_zoom, review_zoom_auto,
    ) = snapshot

    self._filter_render_serial += 1
    serial = self._filter_render_serial
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

    def worker(
        local_targets=targets, local_pages=pages, local_settings=settings,
        local_viewer_width=viewer_width, local_available_width=available_width,
        local_review_zoom=review_zoom, local_review_zoom_auto=review_zoom_auto,
    ):
        return ReviewWindow._prepare_filter_batch_payload(
            local_targets, local_pages, local_settings,
            local_viewer_width, local_available_width,
            local_review_zoom, local_review_zoom_auto,
        )

    def done(payload, local_index=int(self.filtered_batch_index), local_key=cache_key) -> None:
        if (
            serial != self._filter_render_serial
            or not getattr(self, "_filter_rows_active", False)
        ):
            return
        self._cache_filter_batch_payload(local_key, payload)
        self._apply_filter_batch_payload(local_index, local_key, payload)

    def failed(exc, detail) -> None:
        if detail:
            print(detail)
        if serial != self._filter_render_serial:
            return
        self._clear_review_workspace(f"本批切词行生成失败：{exc}")

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
        editor.bind("<FocusIn>", lambda _event, i=index: self._set_filter_active(i))
        editor.bind("<KeyRelease>", lambda event, i=index: self._on_filter_key(event, i))
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

