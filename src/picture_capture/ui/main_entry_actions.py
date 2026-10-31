"""Physical owner of main-canvas entry editing, OCR menus and aligned deletion."""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import tkinter as tk
    from ..models import Entry as WordEntry
    from .widgets.vertical_word import VerticalWordText

@dataclass(frozen=True)
class MainEntryActionsDeps:
    release_alpha_line_photos: object
    tk: object
    parameter_scale: object
    VerticalWordText: object
    resolve_wordslist_path: object
    _candidate_choice_rows: object
    _has_distinct_ocr_alternatives: object
    simplified_entry_key: object
    simplified_review_path_for_image: object
    read_simplified_records: object
    write_simplified_records: object


def _remove_entry_overlay(self, deps: MainEntryActionsDeps, entry: WordEntry) -> None:
    """Remove only the widgets/canvas items belonging to one headword row."""
    release_alpha_line_photos = deps.release_alpha_line_photos
    tk = deps.tk
    visuals = self.__dict__.get("_entry_visuals", {})
    record = visuals.pop(id(entry), None)
    if not record:
        return
    widgets = list(record.get("widgets") or [])
    canvas_items = list(record.get("canvas_items") or [])
    release_alpha_line_photos(self, canvas_items)
    for item in canvas_items:
        try:
            self.canvas.delete(item)
        except tk.TclError:
            pass
    for widget in widgets:
        try:
            widget.destroy()
        except tk.TclError:
            pass
        try:
            self.overlay_widgets.remove(widget)
        except ValueError:
            pass
    self.entry_editor_bindings = [
        (widget, bound_entry) for widget, bound_entry in self.entry_editor_bindings
        if bound_entry is not entry and widget not in widgets
    ]

def _entry_sequence_text(deps: MainEntryActionsDeps, index: int, total: int) -> str:
    """Format zero-based row numbers to one uniform width for the page."""
    width = max(1, len(str(max(1, int(total)))))
    return f"{int(index):0{width}d}"

def _refresh_entry_index_labels(self, deps: MainEntryActionsDeps) -> None:
    tk = deps.tk
    ordered = self._ordered_entries_reading_order()
    for index, entry in enumerate(ordered):
        record = self._entry_visuals.get(id(entry))
        widget = record.get("index_widget") if record else None
        if widget is not None:
            try:
                widget.configure(
                    text=self._entry_sequence_text(index, len(ordered)),
                    bg="#e6e6e6",
                    fg="#000000",
                )
            except tk.TclError:
                pass

def _update_entry_overlays_local(self, deps: MainEntryActionsDeps, *, removed: list[WordEntry] | None = None, added: list[WordEntry] | None = None,
) -> None:
    """Apply a checkbox edit without re-resizing the page or rebuilding all rows."""
    parameter_scale = deps.parameter_scale
    removed = removed or []
    added = added or []
    for entry in removed:
        self._remove_entry_overlay(entry)
    image = self.__dict__.get("image")
    hide_var = self.__dict__.get("hide_var")
    if image is None or (hide_var is not None and hide_var.get()):
        return
    # A pure removal needs no geometry recomputation at all: the deleted
    # row's canvas ids are already gone, and only the tiny numeric labels
    # need renumbering. This is the most common proofreading action.
    if not added:
        self._refresh_entry_index_labels()
        if self.cursor_canvas_xy is not None:
            self.draw_cursor_guides(*self.cursor_canvas_xy)
        else:
            self._set_idle_cursor_status()
        return
    geometry = self._get_cached_display_geometry()
    size = (
        max(1, round(image.width * self.view_scale)),
        max(1, round(image.height * self.view_scale)),
    )
    overlay_scale = self.view_scale / parameter_scale(image, self.settings)
    ordered = self._ordered_entries_reading_order()
    index_by_id = {id(entry): index for index, entry in enumerate(ordered)}
    for entry in added:
        if id(entry) in self._entry_visuals:
            continue
        self._draw_entry_overlay(
            entry, index_by_id.get(id(entry), 0), geometry, size, overlay_scale,
            processing_readonly=False,
        )
    self._refresh_entry_index_labels()
    self._apply_current_appearance(self.canvas)
    if self.cursor_canvas_xy is not None:
        self.draw_cursor_guides(*self.cursor_canvas_xy)
    else:
        self._set_idle_cursor_status()

def _confidence_bg(self, deps: MainEntryActionsDeps, confidence: float | None) -> str:
    if confidence is None:
        return "#eeeeee"
    if confidence >= 0.95:
        return "#c8e6c9"
    if confidence >= 0.90:
        return "#e8f5c8"
    if confidence >= 0.80:
        return "#fff3bf"
    if confidence >= 0.65:
        return "#ffe0b2"
    return "#ffcdd2"

def _style_entry_editor(self, deps: MainEntryActionsDeps, widget: tk.Entry | VerticalWordText, entry: WordEntry, displayed_word: str | None = None
) -> None:
    """Style a main-view headword editor by wordslist membership.

    Membership is intentionally encoded only by the outer border:
    words present in wordslist.txt keep the normal thin neutral border,
    while missing words receive a conspicuous red outline.  The optional
    ``displayed_word`` lets KeyRelease refresh the border before FocusOut
    commits the edit back to ``entry.word``.
    """
    VerticalWordText = deps.VerticalWordText
    tk = deps.tk
    bg, border, thickness = self._entry_overlay_style(entry, displayed_word)
    options = {
        "bg": bg,
        "highlightthickness": thickness,
        "highlightbackground": border,
        "highlightcolor": border,
    }
    if isinstance(widget, VerticalWordText):
        options["insertbackground"] = "#111111"
    else:
        options["disabledbackground"] = bg
    widget.configure(**options)
    # Sequence labels use a fixed light-gray background with black text so
    # row numbering stays visually stable regardless of marker/OCR colours.
    record = self.__dict__.get("_entry_visuals", {}).get(id(entry))
    index_control = record.get("index_widget") if record else None
    if index_control is not None:
        try:
            index_control.configure(bg="#e6e6e6", fg="#000000")
        except tk.TclError:
            pass
    delete_control = record.get("delete_widget") if record else None
    if delete_control is not None:
        try:
            delete_control.configure(
                bg="#9d042f", fg="#ffffff",
                activebackground="#9d042f", activeforeground="#ffffff",
            )
        except tk.TclError:
            pass

def _entry_overlay_style(self, deps: MainEntryActionsDeps, entry: WordEntry, displayed_word: str | None = None,
) -> tuple[str, str, int]:
    """Return the shared editor background and membership border."""
    resolve_wordslist_path = deps.resolve_wordslist_path
    word = entry.word if displayed_word is None else displayed_word
    in_wordlist = bool(word and word in self._project_words)
    bg = (
        self._confidence_bg(entry.confidence)
        if self._main_ocr_review_option_enabled("review_main_show_ocr_background")
        else self.settings.main_entry_default_color
    )
    project = getattr(self, "project", None)
    wordslist_exists = bool(getattr(self, "_project_words", set())) if project is None else False
    if project is not None:
        try:
            wordslist_exists = resolve_wordslist_path(
                project.root, self.settings.wordslist_path
            ).is_file()
        except OSError:
            wordslist_exists = False
    if not wordslist_exists:
        border = "#c7c7c7"
        thickness = 1
    elif in_wordlist:
        border = "#b0b0b0"
        thickness = 1
    else:
        border = "#d32f2f"
        thickness = 2
    return bg, border, thickness

def _candidate_for_entry(self, deps: MainEntryActionsDeps, entry: WordEntry) -> dict | None:
    """Find the OCR review candidate corresponding to a visible headword row."""
    if entry.candidate_id:
        for candidate in self.ocr_review_candidates:
            if str(candidate.get("candidate_id", "")) == entry.candidate_id:
                return candidate
    tolerance = max(6, round(self._quick_geometry_value("character_height") * 0.55))
    nearby: list[tuple[float, dict]] = []
    for candidate in self.ocr_review_candidates:
        try:
            dx = abs(int(candidate.get("source_x", entry.x)) - entry.x)
            dy = abs(int(candidate.get("source_y", entry.y)) - entry.y)
        except (TypeError, ValueError):
            continue
        if dx <= 20 and dy <= tolerance:
            nearby.append((dy + dx * 0.1, candidate))
    return min(nearby, key=lambda item: item[0])[1] if nearby else None

def _short_ocr_menu_word(deps: MainEntryActionsDeps, word: str, limit: int = 12) -> str:
    word = str(word).strip()
    return word if len(word) <= limit else word[: max(1, limit - 1)] + "…"

def _fill_main_entry_from_ocr(self, deps: MainEntryActionsDeps, entry: WordEntry, editor: tk.Entry | VerticalWordText, candidate: dict,
    engine: str, word: str, menu_button: tk.Menubutton | None = None,
) -> None:
    """Fill one main-page editor from a compact OCR choice and persist it."""
    if not self._claim_page_for_manual_edit():
        return
    word = str(word).strip()
    if not word:
        return
    side = candidate.get(engine, {}) if engine in {"paddle", "tesseract", "lens"} else {}
    confidence = side.get("confidence") if isinstance(side, dict) else None
    try:
        entry.confidence = float(confidence) if confidence is not None else entry.confidence
    except (TypeError, ValueError):
        pass
    entry.word = word
    entry.ocr_source = engine
    entry.final_engine = engine
    entry.manually_selected = True
    cid = str(candidate.get("candidate_id", ""))
    if cid:
        entry.candidate_id = cid
    candidate["word"] = word
    candidate["final_engine"] = engine
    candidate["selected"] = True
    candidate["decision_reason"] = "main_view_ocr_choice"
    issues = list(candidate.get("issue_types", []) or [])
    if "MANUAL_OVERRIDE" not in issues:
        issues.append("MANUAL_OVERRIDE")
    candidate["issue_types"] = issues
    entry.issue_type = ",".join(str(item) for item in issues)
    editor.delete(0, "end")
    editor.insert(0, word)
    editor.icursor("end")
    self._style_entry_editor(editor, entry, word)
    # Keep every main-page OCR selector the same compact width.
    # The selected OCR word belongs in the editor, not on the selector button.
    self._write_manual_override(candidate, selected=True, word=word, engine=engine)
    self.save_pdic(silent=True)
    editor.focus_set()
    self.status_var.set(f"已填入 OCR 结果：{word}")

def _create_main_ocr_menu(self, deps: MainEntryActionsDeps, entry: WordEntry, editor: tk.Entry | VerticalWordText, candidate: dict | None,
) -> tk.Menubutton | None:
    """Create a compact OCR-result selector displayed beside a main editor."""
    tk = deps.tk
    _candidate_choice_rows = deps._candidate_choice_rows
    _has_distinct_ocr_alternatives = deps._has_distinct_ocr_alternatives
    rows = _candidate_choice_rows(candidate)
    if not _has_distinct_ocr_alternatives(candidate) or not rows:
        return None
    button = tk.Menubutton(
        self.canvas, text="OCR ▾",
        relief="groove", bd=1, padx=2, pady=0,
        bg="#f5f5f5", activebackground="#e8e8e8",
        font=("TkDefaultFont", 8), cursor="hand2",
    )
    menu = tk.Menu(button, tearoff=False)
    self._apply_current_appearance(menu)
    final_separator_added = False
    for engine, label, word, confidence, is_final in rows:
        if is_final and not final_separator_added:
            menu.add_separator()
            final_separator_added = True
        suffix = f"  ({confidence:.2f})" if confidence is not None else ""
        menu.add_command(
            label=f"{label}: {word}{suffix}",
            command=lambda e=engine, w=word, b=button, c=candidate: self._fill_main_entry_from_ocr(
                entry, editor, c, e, w, b
            ),
        )
    button.configure(menu=menu)
    return button

def update_entry(self, deps: MainEntryActionsDeps, entry: WordEntry, widget: tk.Entry | VerticalWordText) -> None:
    tk = deps.tk
    new_word = widget.get().strip()
    if new_word != entry.word:
        if not self._claim_page_for_manual_edit():
            try:
                widget.configure(state="normal")
                widget.delete(0, "end"); widget.insert(0, entry.word)
                if self._foreground_batch_state(self.current_index) == "processing":
                    widget.configure(state="disabled")
            except tk.TclError:
                pass
            return
        entry.word = new_word
        # Manual text edits invalidate the OCR confidence for the word itself.
        entry.confidence = None
        entry.ocr_source = "manual"
        entry.final_engine = "manual"
        entry.manually_selected = True
        entry.alphabetical_warning = ""
        if entry.candidate_id:
            cand = self.get_review_candidate(entry.candidate_id)
            if cand is not None:
                cand["word"] = new_word; cand["selected"] = True; cand["final_engine"] = "manual"
                self._write_manual_override(cand, selected=True, word=new_word, engine="manual")
    self._style_entry_editor(widget, entry)

def focus_next(self, deps: MainEntryActionsDeps, widget: tk.Widget) -> str:
    widget.tk_focusNext().focus_set(); return "break"

def focus_previous(self, deps: MainEntryActionsDeps, widget: tk.Widget) -> str:
    widget.tk_focusPrev().focus_set(); return "break"

def _delete_aligned_simplified_entry(self, deps: MainEntryActionsDeps, entry: WordEntry) -> None:
    """Delete the simplified companion belonging to one main-page row.

    Original and simplified headwords are a one-to-one aligned pair keyed
    by the marker coordinates.  Deleting a row from the main window must
    therefore remove its simplified sidecar record too, including any
    unsaved copy currently held by an open proofreading window.
    """
    simplified_entry_key = deps.simplified_entry_key
    simplified_review_path_for_image = deps.simplified_review_path_for_image
    read_simplified_records = deps.read_simplified_records
    write_simplified_records = deps.write_simplified_records
    if not self.current_page:
        return
    stem = self.current_page.stem
    key = simplified_entry_key(entry.x, entry.y)
    review = getattr(self, "review_window", None)
    if review is not None and getattr(review, "_rendered_page_stem", "") == stem:
        records = review._simplified_page_records(stem)
        if key in records:
            original = records.pop(key)
            was_dirty = stem in review._simplified_dirty_pages
            review._simplified_dirty_pages.add(stem)
            try:
                review._persist_simplified_page(stem)
            except Exception:
                # Never downgrade a refused protected save into a raw rewrite.
                # Restore unsaved human editor cache if the disk was untouched.
                records[key] = original
                if not was_dirty:
                    review._simplified_dirty_pages.discard(stem)
                raise
            return
    from ..proofreading.transactions import _bytes_or_absent
    from ..proofreading.simplified_review import guarded_write_records
    path = simplified_review_path_for_image(self.current_page)
    expected = _bytes_or_absent(path)
    records = read_simplified_records(path)
    if _bytes_or_absent(path) != expected:
        raise RuntimeError("R3 主窗口删除时简体人工副本发生外部修改")
    if key in records:
        records.pop(key, None)
        guarded_write_records(
            self.current_page, path, stem, records, expected,
            writer=write_simplified_records,
        )

def delete_entry(self, deps: MainEntryActionsDeps, entry: WordEntry) -> str:
    tk = deps.tk
    if not self._claim_page_for_manual_edit():
        return "break"
    self._sync_entry_editor_texts()
    self._delete_aligned_simplified_entry(entry)
    if entry in self.entries:
        self.entries.remove(entry)
    self.redraw()
    review = getattr(self, "review_window", None)
    if review is not None and getattr(review, "_rendered_page_stem", "") == (self.current_page.stem if self.current_page else ""):
        try:
            review.render_rows()
        except tk.TclError:
            pass
    return "break"

