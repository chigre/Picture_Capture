"""Main Tk page PDIC save, editor snapshot and autosave lifecycle.

Keeps original transaction quarantine, deferred snapshot and batch page ownership
invariants. The public app methods inject patched IO/Tk collaborators at call time.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import Entry as WordEntry
    import tkinter as tk

def _ordered_entries_reading_order(self, *, deps: dict[str, Any]) -> list[WordEntry]:
    """Return entries in reading order without mutation."""
    sort_entries_reading_order = deps["sort_entries_reading_order"]
    image = self.__dict__.get("image")
    entries = list(self.__dict__.get("entries") or [])
    settings = self.__dict__.get("settings")
    if image is None or settings is None or not entries:
        return entries
    return sort_entries_reading_order(
        entries, self._get_cached_display_geometry(), self.page_sections,
    )

def _sort_entries_reading_order(self, *, deps: dict[str, Any]) -> None:
    """Keep manual and OCR entries in one geometry-based reading order."""
    entries = self.__dict__.get("entries")
    if entries is None:
        return
    entries[:] = self._ordered_entries_reading_order()

def pages_tuple(self, index: int | None = None, *, deps: dict[str, Any]) -> tuple[str, str, str]:
    assert self.project
    i = self.current_index if index is None else index
    current = self.project.images[i].stem
    previous = self.project.images[i - 1].stem if i > 0 else "@"
    following = self.project.images[i + 1].stem if i + 1 < len(self.project.images) else "@"
    return current, previous, following

def save_pdic(self, silent: bool = False, sync_editors: bool = True, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    pdic_path = deps["pdic_path"]
    write_pdic = deps["write_pdic"]
    if not self.project or not self.current_page or self.image is None: return
    if self.__dict__.get("_batch_active", False) and not self._can_save_current_during_batch_navigation():
        return
    from ..proofreading.transactions import _recovery_path
    if _recovery_path(self.current_page).exists():
        raise RuntimeError("Unresolved R3 transaction; refusing PDIC save")
    if self.__dict__.get("_deferred_save_uncertain", False):
        raise RuntimeError("R3 PDIC write outcome uncertain; reload/recover before saving")
    # Commit live state; cancel any older queued checkbox snapshot.
    deferred_job = self.__dict__.get("_deferred_save_job")
    if deferred_job is not None:
        try:
            self.after_cancel(deferred_job)
        except tk.TclError:
            pass
    self.__dict__["_deferred_save_job"] = None
    # Keep the queued snapshot until the actual PDIC publication succeeds.
    from ..proofreading.save_safety import protect_app_pdic_commit
    with protect_app_pdic_commit(self):
        # Review edits bypass stale main-canvas editor values.
        if sync_editors:
            self._sync_entry_editor_texts()
        self._sort_entries_reading_order()
        changed = write_pdic(pdic_path(self.current_page), self.entries, self.image.width, self.pages_tuple())
    self.__dict__["_deferred_save_snapshot"] = None
    self.__dict__["_deferred_save_page"] = None
    self.__dict__["_deferred_save_uncertain"] = False
    self._last_pdic_write_changed = changed
    self._flush_pending_manual_override()
    self._flush_proofreading_candidate_evidence()
    self._flush_proofreading_add_evidence()
    if changed:
        self._refresh_word_fill_check_from_line_count(self.current_index, len(self.entries), persist=True)
        self._update_page_row(self.current_index)
    if not silent: self.status_var.set(f"已保存 {pdic_path(self.current_page).name}" if changed else "内容无变化，无需保存")

def _sync_entry_editor_texts(self, *, deps: dict[str, Any]) -> None:
    """Commit editor values to the exact Entry objects they were created for."""
    tk = deps["tk"]
    active_ids = {id(entry) for entry in self.entries}
    for editor, entry in self.entry_editor_bindings:
        if id(entry) not in active_ids:
            continue
        try:
            entry.word = editor.get().strip()
        except tk.TclError:
            # A redraw may already have destroyed the old widget.
            continue

def toggle_autosave(self, *, deps: dict[str, Any]) -> None:
    if self.autosave_job:
        self.after_cancel(self.autosave_job)
        self.autosave_job = None
    if self.autosave_var.get():
        delay = max(1, round(self.settings.batch_interval * 1000))
        self.autosave_job = self.after(delay, self.autosave_tick)

def autosave_tick(self, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    self.autosave_job = None
    if not self.autosave_var.get():
        return
    try:
        # Autosave PDIC only for editable batch pages; never autosave PPP
        # while a background batch owns the current page.
        if self._batch_active and not self._can_save_current_during_batch_navigation():
            return
        if self.project and self.current_page:
            self._last_pdic_write_changed = False
            review = self.review_window
            review_saved = False
            if review is not None:
                try:
                    if review.winfo_exists():
                        review_saved = bool(review.autosave_commit())
                    else:
                        self.review_window = None
                except tk.TclError:
                    self.review_window = None
            if not review_saved:
                self.save_pdic(silent=True)
            polygon_changed = False if self._batch_active else self._save_normalized_ppp()
            if self._last_pdic_write_changed or polygon_changed:
                self.status_var.set("已自动保存")
    except (OSError, RuntimeError, ValueError) as exc:
        # In particular, never fall back to stale main-canvas buffers when
        # ReviewWindow's PDIC transaction failed.
        self.status_var.set(f"自动保存失败，校对修改仍保留：{exc}")
    finally:
        # Failed I/O must not silently disable the next autosave tick.
        self.toggle_autosave()


# Page navigation and SECTION durability, without changing PDIC/PPP formats.

def _save_current_page_files(self, *, sync_editors: bool = True, deps: dict[str, Any]) -> tuple[Path, Path] | None:
    pdic_path = deps["pdic_path"]
    """Persist all editable artifacts for the currently displayed page.

    Page navigation must commit both the visible headword editors (.pdic)
    and illustration polygons (.ppp) before another page replaces them.
    """
    if not self.project or not self.current_page or self.image is None:
        return None
    self.save_pdic(silent=True, sync_editors=sync_editors)
    ppp = self._ppp_write_path(self.current_page)
    self._save_normalized_ppp()
    self._update_page_row(self.current_index)
    return pdic_path(self.current_page), ppp

def _save_current_page_by_mode(self, *, sync_editors: bool = True, deps: dict[str, Any]) -> Path | None:
    pdic_path = deps["pdic_path"]
    """ save current page by mode."""
    if not self.project or not self.current_page or self.image is None:
        return None
    if self.__dict__.get("_batch_active", False) and not self._can_save_current_during_batch_navigation():
        self.status_var.set("后台任务运行中：当前页只读，避免覆盖处理结果。")
        return None
    from ..illustration.profile import effective_page_kind
    if effective_page_kind(self.settings, self.current_page) == "illustrated":
        return None
    if self.polygon_draw_var.get() and not getattr(self, "_batch_allow_pdic_edits", False):
        target = self._ppp_write_path(self.current_page)
        self._save_normalized_ppp()
        self._update_page_row(self.current_index)
        return target
    self.save_pdic(silent=True, sync_editors=sync_editors)
    return pdic_path(self.current_page)

def save_current_page(self, *, deps: dict[str, Any]) -> None:
    if not self.guard():
        return
    try:
        saved = self._save_current_page_by_mode()
        if saved is not None:
            mode = "插图" if self.polygon_draw_var.get() else "画线"
            self.status_var.set(f"已保存当前页（{mode}）：{saved.name}")
    except Exception as exc:
        self.show_error("保存当前页失败", exc)

def _persist_current_page_sections(self, *, deps: dict[str, Any]) -> None:
    LayoutTransform = deps["LayoutTransform"]
    write_page_sections = deps["write_page_sections"]
    """Save explicit SECTION bounds without touching PDIC/PPP."""
    if self.current_page is None or self.image is None:
        return
    transform = LayoutTransform(
        str(getattr(self.settings, "layout_transform", "identity") or "identity")
    )
    canonical_width, canonical_height = transform.canonical_size(self.image.size)
    write_page_sections(
        self.current_page,
        list(self.page_sections),
        canonical_width=canonical_width,
        canonical_height=canonical_height,
        layout_transform=transform.kind,
    )
