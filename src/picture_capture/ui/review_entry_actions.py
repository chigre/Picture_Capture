"""Physical ReviewWindow entry workflow owner.

No import of the heavyweight app module; original Tk callback signatures remain.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from ..models import Entry as WordEntry


@dataclass(frozen=True)
class ReviewEntryDeps:
    """Original module bindings captured fresh on dispatch."""
    tk: object
    messagebox: object
    read_pdic: object
    pdic_path: object
    simplified_entry_key: object
    sync_review_entry_classification: object

def set_active(self, deps: ReviewEntryDeps, index: int) -> None:
    sync_review_entry_classification = deps.sync_review_entry_classification
    self.active_index = index
    self._update_active_crop_preview(index)
    self._update_title()
    row_entries = self._bound_row_entries()
    candidate = self._candidate_for_entry(row_entries[index]) if 0 <= index < len(row_entries) else None
    self._show_ocr_options(candidate)
    if 0 <= index < len(row_entries):
        self.parent.highlight_review_entry(row_entries[index])
    if 0 <= index < len(self.vars):
        self.locate_reference_word(self.vars[index].get(), index)
        self._refresh_cc_simplified_comparison(index)
        self._schedule_network_lookup(self.vars[index].get())
    sync_review_entry_classification(self)


def _scroll_editor_into_view(self, deps: ReviewEntryDeps, index: int) -> None:
    tk = deps.tk
    if not (0 <= index < len(self.editors)):
        return
    try:
        self.update_idletasks()
        row_box = self.rows.grid_bbox(0, index * 2)
        if row_box and row_box[3] > 0:
            target_top = max(0, int(row_box[1]) - 6)
        else:
            target_top = max(0, self.editor_frames[index].winfo_y() - 40)
        target_bottom = self.editor_frames[index].winfo_y() + self.editor_frames[index].winfo_height() + 8
        view_top = float(self.canvas.canvasy(0))
        view_height = max(1, self.canvas.winfo_height())
        total_height = max(1, self.rows.winfo_reqheight())
        if target_top < view_top:
            self.canvas.yview_moveto(max(0.0, min(1.0, target_top / total_height)))
        elif target_bottom > view_top + view_height:
            new_top = max(0, target_bottom - view_height)
            self.canvas.yview_moveto(max(0.0, min(1.0, new_top / total_height)))
    except tk.TclError:
        pass


def focus_index(self, deps: ReviewEntryDeps, index: int) -> str:
    if 0 <= index < len(self.editors):
        self.editors[index].focus_set()
        self.editors[index].icursor("end")
        self.editors[index].xview_moveto(1.0)
        self._scroll_editor_into_view(index)
    return "break"


def on_key(self, deps: ReviewEntryDeps, event: tk.Event, index: int) -> None:
    char = getattr(event, "char", "")
    if self.replace_digits.get() and char in self.DIGIT_KEYS:
        replacement = self.digit_map_vars[self.DIGIT_KEYS.index(char)].get()
        if replacement:
            editor = self.editors[index]
            pos = editor.index("insert")
            text = editor.get()
            start = max(0, pos - 1)
            editor.delete(0, "end")
            editor.insert(0, text[:start] + replacement + text[pos:])
            editor.icursor(start + len(replacement))
    words = self.parent._project_words if self.parent.project else set()
    self._set_editor_membership_color(index, self.vars[index].get().strip() in words)
    self._refresh_simplified_for_index(index)
    self._refresh_editor_ocr_compare(index)
    if index == self.active_index:
        self._refresh_ocr_similarity_colors()
        self._refresh_cc_simplified_comparison(index)
        self.locate_reference_word(self.vars[index].get(), index)
        self._schedule_network_lookup(self.vars[index].get())


def _set_editor_membership_color(self, deps: ReviewEntryDeps, index: int, in_wordslist: bool) -> None:
    tk = deps.tk
    color, foreground, selection_bg, selection_fg = (
        self._review_membership_colors(in_wordslist)
    )
    if 0 <= index < len(self.editors):
        try:
            self.editors[index].configure(
                bg=color,
                disabledbackground=color,
                foreground=foreground,
                disabledforeground=foreground,
                insertbackground=foreground,
                selectbackground=selection_bg,
                selectforeground=selection_fg,
            )
        except tk.TclError:
            pass
    if 0 <= index < len(self.editor_frames):
        try:
            frame = self.editor_frames[index]
            current_border = str(frame.cget("highlightbackground"))
            mismatch_border = current_border.lower() == "#d32f2f"
            frame.configure(
                bg=color,
                highlightbackground=("#d32f2f" if mismatch_border else color),
                highlightcolor=("#d32f2f" if mismatch_border else color),
            )
        except tk.TclError:
            pass


def delete_review_entry(self, deps: ReviewEntryDeps, index: int) -> str:
    """Delete one proofreading row and mirror the deletion on the main page.

    The review window and main canvas share ``parent.entries``.  Commit all
    visible proofreading text before removing the selected Entry so deleting
    a middle row cannot shift later text onto the wrong headword.  Persist the
    PDIC immediately and redraw both views; the grave/backtick shortcut uses
    the same path as the visible [X] button.
    """
    read_pdic = deps.read_pdic
    pdic_path = deps.pdic_path
    simplified_entry_key = deps.simplified_entry_key
    row_entries = self._bound_row_entries()
    if not (0 <= int(index) < len(row_entries)):
        return "break"
    if not self.parent._claim_page_for_manual_edit():
        return "break"
    if str(getattr(row_entries[int(index)], "candidate_id", "") or ""):
        # Candidate deletion publishes disk before mutating Tk/Entry.
        from .review_candidate_delete_actions import delete_owned_review_candidate
        return delete_owned_review_candidate(self, int(index), row_entries)

    # Only explicitly enabled, project-local evidence capture. Save the
    # *previous on-disk* PDIC before mutating any shared Entry objects.
    capture_requested = bool(getattr(
        getattr(self.parent, "settings", None), "proofreading_event_capture", False
    ))
    prior_pdic_rows = None
    prior_ocr_fingerprints = None
    if capture_requested and self.parent.current_page is not None:
        try:
            prior_pdic_rows = read_pdic(pdic_path(self.parent.current_page))
            from ..proofreading.capture import verified_ocr_preedit_fingerprints
            cache_fn = getattr(self.parent, "_paddle_cache_path", None)
            cache = cache_fn() if callable(cache_fn) else None
            prior_ocr_fingerprints = verified_ocr_preedit_fingerprints(
                cache, pdic_path(self.parent.current_page),
            )
        except (OSError, ValueError, TypeError):
            prior_pdic_rows = None

    # Capture before mutating shared Entry objects or saving the PDIC.
    # OCR-linked deletion changes manual-selection ownership and will
    # intentionally be refused by the R3 transaction classifier.
    from .review_transaction_actions import capture_review_before, record_review_after
    transaction_before = capture_review_before(self)
    self._commit_edits()
    entry = row_entries[int(index)]
    deleted_identity = (str(entry.word), int(entry.x), int(entry.y))
    deleted_candidate_id = str(entry.candidate_id or "")
    candidate_id_unique = (
        bool(deleted_candidate_id)
        and sum(
            str(row.get("candidate_id", "")) == deleted_candidate_id
            for row in getattr(self.parent, "ocr_review_candidates", ())
            if isinstance(row, dict)
        ) == 1
    )
    simplified_key = simplified_entry_key(entry.x, entry.y)
    rendered_stem = getattr(self, "_rendered_page_stem", "")
    if rendered_stem and hasattr(self, "_simplified_page_cache"):
        self._simplified_page_records(rendered_stem).pop(simplified_key, None)
        self._simplified_dirty_pages.add(rendered_stem)

    if entry in self.parent.entries:
        self.parent.entries.remove(entry)
    self.parent._sort_entries_reading_order()
    self.parent.clear_review_entry_highlight()
    # Do not sync stale main-canvas Entry widgets back into the shared model:
    # the proofreading text above is the newest source of truth.
    self.parent.save_pdic(silent=True, sync_editors=False)
    capture_failed = False
    if prior_pdic_rows is not None:
        try:
            from ..proofreading.capture import capture_saved_review_deletion
            capture_saved_review_deletion(
                project_root=self.parent.project.root,
                page=self.parent.current_page,
                prior_pdic_entries=prior_pdic_rows,
                expected_deleted=deleted_identity,
                deleted_candidate_id=deleted_candidate_id,
                candidate_id_unique=candidate_id_unique,
                source_fingerprints=prior_ocr_fingerprints,
            )
        except (OSError, ValueError, TypeError):
            # PDIC and manual overrides were saved successfully. Evidence
            # errors must neither undo that save nor silently claim success.
            capture_failed = True
    if getattr(self, "_rendered_page_stem", "") and hasattr(self, "_simplified_page_cache"):
        self._persist_simplified_page(self._rendered_page_stem)
    # The soon-to-be-rebuilt ReviewWindow rows still reference the old
    # widgets; read the true saved parent.entries to classify this one
    # committed deletion, then rebuild widgets for the restored identities.
    record_review_after(self, transaction_before, allow_unbound=True)
    self.parent.redraw()

    next_index = min(int(index), max(0, len(self.parent.entries) - 1))
    deleted_word = entry.word or "（空白词条）"
    self.active_index = next_index if self.parent.entries else 0
    self._request_render_rows(focus_index=self.active_index)
    if not self.parent.entries:
        self._show_ocr_options(None)
        self._update_title()
    self.parent.status_var.set(
        f"已删除词条：{deleted_word}"
        + ("（本地操作日志保存失败，PDIC 已保存）" if capture_failed else "")
    )
    return "break"


def _save_digit_map(self, deps: ReviewEntryDeps) -> None:
    values = [var.get() for var in self.digit_map_vars]
    self.parent.settings.review_digit_map = values[:10]
    self.parent.save_settings()


def insert_char(self, deps: ReviewEntryDeps, char: str) -> None:
    if self._filter_rows_active and getattr(self, "filter_editors", []):
        index = max(
            0, min(
                len(self.filter_editors) - 1,
                int(getattr(self, "filter_active_local_index", 0)),
            )
        )
        editor = self.filter_editors[index]
        editor.insert("insert", char)
        self._on_filter_key(type("_Event", (), {"char": ""})(), index)
        return
    if self.editors and self.parent._claim_page_for_manual_edit():
        self.editors[self.active_index].insert("insert", char)
        self.on_key(type("_Event", (), {"char": ""})(), self.active_index)


def _selected_wordslist_global_index(self, deps: ReviewEntryDeps) -> int | None:
    local = self.word_selected_local_index
    if local is not None and 0 <= int(local) < len(self.word_window_indices):
        return self.word_window_indices[int(local)]
    return None


def use_selected_word(self, deps: ReviewEntryDeps, event: tk.Event | None = None) -> None:
    if event is not None:
        self.word_selected_local_index = self._word_list_local_index_from_event(event)
    source = self._selected_wordslist_global_index()
    words = self.parent.project.words if self.parent.project else []
    if source is None or source >= len(words) or not self.editors:
        return
    if not self.parent._claim_page_for_manual_edit():
        return
    index = self.active_index
    self.vars[index].set(words[source])
    self.on_key(type("_Event", (), {"char": ""})(), index)
    # A single click fills the active box but intentionally does not advance;
    # the user can verify the image/text pair before pressing Return.
    self.after_idle(lambda i=index: self.focus_index(i))


def fill_words(self, deps: ReviewEntryDeps) -> None:
    messagebox = deps.messagebox
    if self._effective_wordslist_locator_mode() == "sorted":
        messagebox.showinfo(
            "外部索引模式",
            "当前 wordslist 按外部排序索引定位。来自另一部词典时可能存在增词/漏词，"
            "因此不做连续批量填充；请单击参考词逐条填入。\n\n"
            "若该词表与当前词典逐条对应，请把定位模式改为“同源连续词表”。",
            parent=self,
        )
        return
    start = self._selected_wordslist_global_index()
    if start is None:
        messagebox.showinfo("请选择", "请先在右侧词表中选择起始词。", parent=self)
        return
    if not self.parent._claim_page_for_manual_edit():
        return
    words = self.parent.project.words if self.parent.project else []
    for offset in range(self.active_index, len(self.vars)):
        source = start + offset - self.active_index
        if source >= len(words):
            break
        old = self.vars[offset].get()
        if any(marker in old for marker in ("【", "|", "\\")):
            continue
        self.vars[offset].set(words[source])
        self._set_editor_membership_color(offset, True)
        self._refresh_simplified_for_index(offset)
    self._refresh_ocr_similarity_colors()

