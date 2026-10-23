"""Physical owner of ocr review callbacks.

ReviewWindow owns original public Tk signatures and passes current collaborators.
This module never imports app.py or changes the stored project formats.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk


@dataclass(frozen=True)
class ReviewOcrDeps:
    """Live collaborators resolved afresh by the GUI shell."""
    tk: object
    _candidate_word_for_ocr_source: object
    _review_similarity_key: object
    _candidate_choice_rows: object
    _review_similarity_color: object
    _review_text_similarity: object

def _change_review_ocr_compare_source(self, deps: ReviewOcrDeps, _event: tk.Event | None = None) -> None:
    key = self.OCR_COMPARE_LABEL_TO_KEY.get(self.review_ocr_compare_var.get(), "fusion")
    self.parent.settings.review_ocr_compare_source = key
    self.parent.save_settings()
    self._refresh_editor_ocr_compare()
    if getattr(self, "_filter_rows_active", False):
        self.parent.status_var.set(
            "已切换筛选 OCR 比较来源；点击【筛选】可按新来源重新筛选 OCR 不匹配。"
        )


def _ocr_compare_word(self, deps: ReviewOcrDeps, candidate: dict | None) -> str:
    _candidate_word_for_ocr_source = deps._candidate_word_for_ocr_source
    key = self.OCR_COMPARE_LABEL_TO_KEY.get(self.review_ocr_compare_var.get(), "fusion")
    return _candidate_word_for_ocr_source(candidate, key)


def _refresh_editor_ocr_compare(self, deps: ReviewOcrDeps, index: int | None = None) -> None:
    """Outline review editors in red when they differ from the selected OCR source.

    A missing result for the selected OCR engine is neutral: no mismatch
    outline is shown. Comparison uses the same normalized text key as the
    coloured OCR-result buttons, so spacing/full-width/punctuation noise
    does not create a false red border.
    """
    tk = deps.tk
    _review_similarity_key = deps._review_similarity_key
    if not self.editor_frames or not self.vars:
        return
    row_entries = self._bound_row_entries()
    indices = [index] if index is not None else list(range(min(len(self.vars), len(row_entries))))
    for i in indices:
        if i is None or not (0 <= i < len(self.editor_frames)) or i >= len(row_entries):
            continue
        candidate = self._candidate_for_entry(row_entries[i])
        ocr_word = self._ocr_compare_word(candidate)
        editor_word = self.vars[i].get()
        mismatch = bool(ocr_word) and _review_similarity_key(editor_word) != _review_similarity_key(ocr_word)
        frame = self.editor_frames[i]
        normal_bg = str(frame.cget("bg"))
        border = "#d32f2f" if mismatch else normal_bg
        try:
            frame.configure(
                highlightthickness=(2 if mismatch else 1),
                highlightbackground=border,
                highlightcolor=border,
            )
        except tk.TclError:
            pass


def _show_ocr_options(self, deps: ReviewOcrDeps, candidate: dict | None) -> None:
    """Render Paddle/Tesseract/Lens/fused OCR results on one compact line."""
    tk = deps.tk
    _candidate_choice_rows = deps._candidate_choice_rows
    _review_similarity_color = deps._review_similarity_color
    _review_text_similarity = deps._review_text_similarity
    for child in self.ocr_options.winfo_children():
        child.destroy()
    self.ocr_result_buttons = []
    self.active_candidate = candidate

    current_word = self.vars[self.active_index].get() if 0 <= self.active_index < len(self.vars) else ""
    values: dict[str, str] = {"paddle": "", "tesseract": "", "lens": "", "fusion": ""}
    if candidate:
        for engine, _label, word, _confidence, is_final in _candidate_choice_rows(candidate):
            if is_final:
                values["fusion"] = word
            elif engine in values:
                values[engine] = word

    slots = (("P", "paddle"), ("T", "tesseract"), ("L", "lens"), ("融", "fusion"))
    for slot_index, (short_label, key) in enumerate(slots):
        word = values.get(key, "")
        if word:
            bg = _review_similarity_color(_review_text_similarity(current_word, word))
            button = tk.Button(
                self.ocr_options, text=f"{short_label}: {word}",
                command=lambda value=word: self.use_ocr_word(value),
                anchor="w", justify="left", relief="flat", bd=0, padx=5, pady=2,
                bg=bg, activebackground=bg, foreground="#202020",
                highlightthickness=1, highlightbackground=bg,
            )
            button.grid(row=0, column=slot_index, sticky="ew", padx=((0 if slot_index == 0 else 3), 0))
            self.ocr_result_buttons.append((button, word))
        else:
            button = tk.Button(
                self.ocr_options, text=f"{short_label}: -", state="disabled",
                anchor="w", justify="left", relief="flat", bd=0, padx=5, pady=2,
                bg="#f1f2f4", activebackground="#f1f2f4",
                disabledforeground="#777777", highlightthickness=1,
                highlightbackground="#e1e4e8",
            )
            button.grid(row=0, column=slot_index, sticky="ew", padx=((0 if slot_index == 0 else 3), 0))
        self.ocr_options.columnconfigure(slot_index, weight=1)


def _refresh_ocr_similarity_colors(self, deps: ReviewOcrDeps) -> None:
    """Recolour OCR choices against the currently edited headword."""
    tk = deps.tk
    _review_similarity_color = deps._review_similarity_color
    _review_text_similarity = deps._review_text_similarity
    if not self.ocr_result_buttons:
        return
    current_word = self.vars[self.active_index].get() if 0 <= self.active_index < len(self.vars) else ""
    for button, candidate_word in self.ocr_result_buttons:
        color = _review_similarity_color(_review_text_similarity(current_word, candidate_word))
        try:
            button.configure(bg=color, activebackground=color)
        except tk.TclError:
            pass


def use_ocr_word(self, deps: ReviewOcrDeps, word: str) -> None:
    if not self.editors or not self.parent._claim_page_for_manual_edit():
        return
    self.vars[self.active_index].set(word)
    self.editors[self.active_index].icursor("end")
    self.on_key(type("_Event", (), {"char": ""})(), self.active_index)

