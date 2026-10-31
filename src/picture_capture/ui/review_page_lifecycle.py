"""Physical ReviewWindow page workflow owner.

No import of the heavyweight app module; original Tk callback signatures remain.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from pathlib import Path
    from ..models import Entry as WordEntry
    from PIL import Image


@dataclass(frozen=True)
class ReviewPageDeps:
    """Original module bindings captured fresh on dispatch."""
    tk: object
    replace: object
    Image: object
    json: object
    threading: object
    Path: object
    ocr_cache_root: object
    ppp_read_path_for_image: object
    pdic_path: object
    read_pdic: object
    normalize_page_rgb: object
    effective_page_settings: object
    page_template_analysis_image: object
    derive_geometry: object
    read_page_sections: object
    sort_entries_reading_order: object
    read_ppp: object
    _review_crop_context: object
    _review_line_box: object
    settings_path: object

def _finish_close_review(self, deps: ReviewPageDeps) -> None:
    tk = deps.tk
    if self.parent.review_window is self:
        self.parent.review_window = None
    self._prefetch_closed = True
    self.parent._invalidate_ui_worker(self._review_render_worker_key)
    self.parent._invalidate_ui_worker(f"focused-filter-scan-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-scan-rest-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-render-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-prefetch-{id(self)}")
    self._filter_batch_render_cache.clear()
    self._filter_prefetch_key = None
    if self._filter_save_job is not None:
        try:
            self.after_cancel(self._filter_save_job)
        except tk.TclError:
            pass
        self._filter_save_job = None
    if self._review_auto_zoom_job is not None:
        try:
            self.after_cancel(self._review_auto_zoom_job)
        except tk.TclError:
            pass
        self._review_auto_zoom_job = None
    self._network_lookup_serial += 1
    if self._network_lookup_job is not None:
        try:
            self.after_cancel(self._network_lookup_job)
        except tk.TclError:
            pass
        self._network_lookup_job = None
    if self._network_poll_job is not None:
        try:
            self.after_cancel(self._network_poll_job)
        except tk.TclError:
            pass
        self._network_poll_job = None
    self._network_pending_serials.clear()
    with self._prefetch_lock:
        self._prefetched_pages.clear()
    self.parent.clear_review_entry_highlight()
    self.destroy()
    self.parent.redraw()


def _has_unreported_simplified_input(self) -> bool:
    """Detect live text edits even when Tk emits no KeyRelease/Paste callback.

    This is a read-only gate; the existing guarded commit performs the actual
    source binding, PDIC/manual and simplified-sidecar verification.
    A stale/destroyed row must never be rebound by a numeric index.
    """
    from .review_simplified_workflow import _owned_rendered_simplified_rows

    rows = _owned_rendered_simplified_rows(self)
    if rows is None:
        return False
    for index, _entry in enumerate(rows):
        actual = self.simplified_actual_values[index]
        manual = bool(self.simplified_manual_flags[index])
        original = self.vars[index].get().strip()
        expected = self._simplified_display_from_value(original, actual, manual)
        if self.simplified_vars[index].get().strip() != expected:
            return True
    return False


def autosave_commit(self, deps: ReviewPageDeps) -> bool:
    """Commit review edits for the shared main-window autosave timer."""
    if getattr(self, "_filter_rows_active", False):
        self._flush_focused_changes_now()
        return True
    if not self.parent.project or not self.parent.current_page:
        return False
    state = self.parent._foreground_batch_state(self.parent.current_index)
    if state == "processing":
        return True
    row_entries = self._bound_row_entries()
    word_dirty = any(
        i < len(row_entries) and self.vars[i].get().strip() != row_entries[i].word
        for i in range(min(len(self.vars), len(row_entries)))
    )
    current_stem = self.parent.current_page.stem
    simplified_dirty = (
        current_stem in self._simplified_dirty_pages
        or _has_unreported_simplified_input(self)
    )
    dirty = word_dirty or simplified_dirty
    if state == "pending" and dirty and not self.parent._claim_page_for_manual_edit():
        return True
    if not dirty:
        return True
    from .review_transaction_actions import capture_review_before, record_review_after
    transaction_before = capture_review_before(self)
    evidence_before = self._review_evidence_before_save()
    from ..proofreading.save_safety import protect_review_pdic_commit
    from ..proofreading.review_bundle import commit_review_bundle
    with protect_review_pdic_commit(self):
        self._commit_edits()
        commit_review_bundle(self, transaction_before)
        self.parent.settings.review_zoom_percent = self._stored_review_zoom_percent()
    self._review_evidence_after_save(evidence_before)
    record_review_after(self, transaction_before)
    return True


def _review_evidence_before_save(self, deps: ReviewPageDeps) -> list[WordEntry] | None:
    """Read the pre-edit on-disk PDIC only for explicit project-local opt-in."""
    pdic_path = deps.pdic_path
    read_pdic = deps.read_pdic
    if not bool(getattr(
        getattr(self.parent, "settings", None), "proofreading_event_capture", False
    )):
        return None
    page = getattr(self.parent, "current_page", None)
    if page is None or getattr(self.parent, "project", None) is None:
        return None
    self.__dict__["_review_evidence_source_fingerprints"] = None
    self.__dict__["_review_evidence_prior_pdic_sha256"] = None
    self.__dict__["_review_evidence_source_page"] = page
    try:
        from ..proofreading.events import sha256_file
        saved = pdic_path(page)
        prior_sha = sha256_file(saved)
        previous = read_pdic(saved)
        if prior_sha is None or sha256_file(saved) != prior_sha:
            return None
        self.__dict__["_review_evidence_prior_pdic_sha256"] = prior_sha
        from ..proofreading.capture import verified_ocr_preedit_fingerprints
        cache_fn = getattr(self.parent, "_paddle_cache_path", None)
        cache = cache_fn() if callable(cache_fn) else None
        self.__dict__["_review_evidence_source_fingerprints"] = (
            verified_ocr_preedit_fingerprints(cache, pdic_path(page))
        )
        return previous
    except (OSError, ValueError, TypeError):
        return None


def _review_evidence_after_save(self, deps: ReviewPageDeps, previous: list[WordEntry] | None) -> None:
    """Supplement a committed PDIC, never modify or roll back user edits."""
    if previous is None:
        return
    page = getattr(self.parent, "current_page", None)
    project = getattr(self.parent, "project", None)
    owned_page = self.__dict__.pop("_review_evidence_source_page", None)
    if page is None or project is None or page != owned_page:
        return
    try:
        from ..proofreading.capture import capture_saved_review_rename
        source = self.__dict__.pop("_review_evidence_source_fingerprints", None)
        prior_sha = self.__dict__.pop("_review_evidence_prior_pdic_sha256", None)
        capture_saved_review_rename(
            project_root=project.root, page=page, prior_pdic_entries=previous,
            source_fingerprints=source, prior_pdic_sha256=prior_sha,
        )
    except (OSError, ValueError, TypeError):
        self.parent.status_var.set(
            "校对内容已保存，但本地校对操作日志写入失败，请检查磁盘权限。"
        )


def save(self, deps: ReviewPageDeps, *, redraw_main: bool = True) -> bool:
    settings_path = deps.settings_path
    if getattr(self, "_filter_rows_active", False):
        self._flush_focused_changes_now()
        return not (self._filter_save_running or self._filter_pending_changes)
    state = self.parent._foreground_batch_state(self.parent.current_index)
    if state == "processing":
        self.parent.status_var.set("当前页正在后台处理，校对窗口保持只读，未写入 PDIC。")
        return False
    if state == "pending":
        row_entries = self._bound_row_entries()
        word_dirty = any(
            i < len(row_entries) and self.vars[i].get().strip() != row_entries[i].word
            for i in range(len(self.vars))
        )
        simplified_dirty = bool(
            self.parent.current_page and (
                self.parent.current_page.stem in self._simplified_dirty_pages
                or _has_unreported_simplified_input(self)
            )
        )
        dirty = word_dirty or simplified_dirty
        if not dirty:
            # Browsing a pending page must not accidentally reserve it.
            self.parent.settings.review_zoom_percent = self._stored_review_zoom_percent()
            return True
        if not self.parent._claim_page_for_manual_edit():
            return False
    from .review_transaction_actions import capture_review_before, record_review_after
    transaction_before = capture_review_before(self)
    evidence_before = self._review_evidence_before_save()
    from ..proofreading.save_safety import protect_review_pdic_commit
    from ..proofreading.review_bundle import commit_review_bundle
    with protect_review_pdic_commit(self):
        self._commit_edits()
        commit_review_bundle(self, transaction_before)
        self.parent.settings.review_zoom_percent = self._stored_review_zoom_percent()
    self._review_evidence_after_save(evidence_before)
    record_review_after(self, transaction_before)
    if self.parent.project:
        try:
            self.parent.settings.to_json(settings_path(self.parent.project.root))
        except OSError:
            pass
    if redraw_main:
        self.parent.redraw()
    return True


def _reset_rows_scroll_top(self, deps: ReviewPageDeps) -> None:
    """Return the proofreading crop/text viewport to its first row."""
    tk = deps.tk
    try:
        self.canvas.yview_moveto(0.0)
    except tk.TclError:
        return
    # render_rows() rebuilds row widgets and their final scrollregion is
    # established on idle; repeat once then so a previous page's scroll
    # position cannot be restored by the pending geometry update.
    def reset_after_layout() -> None:
        try:
            if self.canvas.winfo_exists():
                self.canvas.yview_moveto(0.0)
        except tk.TclError:
            pass
    self.after_idle(reset_after_layout)


def _prefetch_path_signature(deps: ReviewPageDeps, path: Path) -> tuple[bool, int, int]:
    try:
        stat = path.stat()
        return True, int(stat.st_size), int(stat.st_mtime_ns)
    except OSError:
        return False, 0, 0


def _page_prefetch_signature_for(cls, deps: ReviewPageDeps, project_root: Path, page: Path) -> tuple:
    json = deps.json
    ocr_cache_root = deps.ocr_cache_root
    ppp_read_path_for_image = deps.ppp_read_path_for_image
    pdic_path = deps.pdic_path
    cache = ocr_cache_root(project_root) / f"{page.stem}.json"
    ppp = ppp_read_path_for_image(page)
    return (
        cls._prefetch_path_signature(page),
        cls._prefetch_path_signature(pdic_path(page)),
        cls._prefetch_path_signature(ppp),
        cls._prefetch_path_signature(cache),
    )


def _page_prefetch_signature(self, deps: ReviewPageDeps, page: Path) -> tuple:
    project = self.parent.project
    if project is None:
        return ()
    return self._page_prefetch_signature_for(project.root, page)


def _review_prefetch_key(self, deps: ReviewPageDeps) -> tuple:
    # repr(AppSettings) intentionally includes every persisted geometry and
    # review option.  Invalidation is conservative: an unrelated setting
    # change may discard a prefetched crop, but a stale crop is never used.
    viewer_width = max(1, int(self.parent.canvas.winfo_width()))
    return (
        repr(self.parent.settings),
        round(float(self.review_zoom), 6),
        round(float(self.parent.view_scale), 6),
        viewer_width,
    )


def _take_prefetched_page(self, deps: ReviewPageDeps, index: int) -> dict | None:
    if not self.parent.project or not (0 <= index < len(self.parent.project.images)):
        return None
    with self._prefetch_lock:
        payload = self._prefetched_pages.pop(index, None)
    if payload is None:
        return None
    page = self.parent.project.images[index]
    if payload.get("project_root") != str(self.parent.project.root):
        return None
    if payload.get("signature") != self._page_prefetch_signature(page):
        return None
    return payload


def _schedule_adjacent_preload(self, deps: ReviewPageDeps) -> None:
    replace = deps.replace
    Image = deps.Image
    json = deps.json
    threading = deps.threading
    Path = deps.Path
    ocr_cache_root = deps.ocr_cache_root
    ppp_read_path_for_image = deps.ppp_read_path_for_image
    pdic_path = deps.pdic_path
    read_pdic = deps.read_pdic
    normalize_page_rgb = deps.normalize_page_rgb
    effective_page_settings = deps.effective_page_settings
    page_template_analysis_image = deps.page_template_analysis_image
    derive_geometry = deps.derive_geometry
    read_page_sections = deps.read_page_sections
    sort_entries_reading_order = deps.sort_entries_reading_order
    read_ppp = deps.read_ppp
    _review_crop_context = deps._review_crop_context
    _review_line_box = deps._review_line_box
    project = self.parent.project
    if project is None or self.parent.current_index < 0 or self.parent.image is None:
        return
    # Capture every Tk-derived value on the UI thread. The worker below
    # touches only filesystem/PIL/pure-Python geometry functions.
    settings_snapshot = replace(self.parent.settings)
    review_zoom = max(0.01, float(self.review_zoom))
    view_scale = float(self.parent.view_scale)
    viewer_width = max(1, int(self.parent.canvas.winfo_width()))
    review_key = self._review_prefetch_key()
    project_root = str(project.root)
    anchor_index = int(self.parent.current_index)
    targets = [
        i for i in (anchor_index - 1, anchor_index + 1)
        if 0 <= i < len(project.images)
    ]
    for index in targets:
        page = project.images[index]
        signature = self._page_prefetch_signature(page)
        with self._prefetch_lock:
            cached = self._prefetched_pages.get(index)
            if cached is not None and cached.get("signature") == signature and cached.get("review_key") == review_key:
                continue
            if index in self._prefetch_inflight:
                continue
            self._prefetch_inflight.add(index)

        def worker(
            page_index=index, page_path=page, expected_signature=signature,
            local_settings=settings_snapshot, local_review_zoom=review_zoom,
            local_view_scale=view_scale, local_viewer_width=viewer_width,
            local_review_key=review_key, local_project_root=project_root,
            local_ppp_path=ppp_read_path_for_image(page),
            local_anchor_index=anchor_index,
        ) -> None:
            payload = None
            try:
                with Image.open(page_path) as opened:
                    image = normalize_page_rgb(opened)
                entries = read_pdic(pdic_path(page_path))
                effective_settings = effective_page_settings(
                    local_settings, image.size, page_index,
                )
                analysis_image = page_template_analysis_image(
                    image, effective_settings, page_index,
                )
                geometry = derive_geometry(analysis_image, effective_settings)
                sections = read_page_sections(page_path)
                entries = sort_entries_reading_order(entries, geometry, sections)
                polygons = read_ppp(local_ppp_path)
                cache_path = ocr_cache_root(Path(local_project_root)) / f"{page_path.stem}.json"
                ocr_payload: dict = {}
                if cache_path.exists():
                    try:
                        loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                        if isinstance(loaded, dict):
                            ocr_payload = loaded
                    except Exception:
                        ocr_payload = {}

                review_settings, review_geometry = _review_crop_context(
                    image, local_settings, local_viewer_width, page_index
                )
                review_crops: list[Image.Image] = []
                for row, entry in enumerate(entries):
                    next_entry = entries[row + 1] if row + 1 < len(entries) else None
                    box = _review_line_box(entry, review_geometry, image, review_settings, next_entry)
                    crop = image.crop(box).convert("RGB")
                    crop = crop.resize(
                        (
                            max(1, round(crop.width * local_review_zoom)),
                            max(1, round(crop.height * local_review_zoom)),
                        ),
                        Image.Resampling.LANCZOS,
                    )
                    review_crops.append(crop)

                display_size = (
                    max(1, round(image.width * local_view_scale)),
                    max(1, round(image.height * local_view_scale)),
                )
                display_image = image.resize(display_size, Image.Resampling.LANCZOS)
                # A file rewritten while it was being prefetched is rejected
                # rather than exposing a mixed old/new page snapshot.
                if expected_signature == self._page_prefetch_signature_for(
                    Path(local_project_root), page_path,
                ):
                    payload = {
                        "project_root": local_project_root,
                        "index": page_index,
                        "signature": expected_signature,
                        "review_key": local_review_key,
                        "image": image,
                        "entries": entries,
                        "polygons": polygons,
                        "ocr_payload": ocr_payload,
                        "review_crops": review_crops,
                        "display_size": display_size,
                        "display_image": display_image,
                        "view_scale": local_view_scale,
                    }
            except Exception:
                payload = None
            finally:
                with self._prefetch_lock:
                    self._prefetch_inflight.discard(page_index)
                    if payload is not None and not self._prefetch_closed:
                        self._prefetched_pages[page_index] = payload
                        # Keep memory bounded to nearby pages even if the
                        # user navigates rapidly back and forth.
                        while len(self._prefetched_pages) > 4:
                            stale = max(
                                self._prefetched_pages,
                                key=lambda i: abs(i - local_anchor_index),
                            )
                            self._prefetched_pages.pop(stale, None)

        threading.Thread(
            target=worker, name=f"ReviewPrefetch-{page.stem}", daemon=True
        ).start()


def change_page(self, deps: ReviewPageDeps, delta: int) -> None:
    if getattr(self, "_filter_rows_active", False):
        self.change_filter_batch(delta)
        return
    target = self.parent.current_index + delta
    # Commit review edits without repainting the page we are about to leave.
    # The parent is told that the current PDIC has already been saved, which
    # also prevents stale main-canvas Entry widgets from overwriting the
    # newer proofreading text during navigation.
    if self.save(redraw_main=False) is False:
        return
    preloaded = self._take_prefetched_page(target)
    self.parent.change_page(
        delta, preloaded=preloaded, current_already_saved=True, async_allowed=False
    )

