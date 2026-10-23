"""Physical owner of simplified review callbacks.

ReviewWindow owns original public Tk signatures and passes current collaborators.
This module never imports app.py or changes the stored project formats.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from ..models import Entry as WordEntry


@dataclass(frozen=True)
class ReviewSimplifiedDeps:
    """Live collaborators resolved afresh by the GUI shell."""
    tk: object
    messagebox: object
    read_simplified_records: object
    simplified_review_path_for_image: object
    write_simplified_records: object
    simplified_entry_key: object
    simplify_text: object

def _bound_row_entries(self, deps: ReviewSimplifiedDeps) -> list[WordEntry]:
    """Return stable rendered-row bindings, with compatibility fallback."""
    bound = getattr(self, "row_entries", None)
    return list(bound) if bound is not None else self.parent._ordered_entries_reading_order()


def _simplified_page_records(self, deps: ReviewSimplifiedDeps, page_stem: str | None = None) -> dict[str, dict]:
    read_simplified_records = deps.read_simplified_records
    simplified_review_path_for_image = deps.simplified_review_path_for_image
    stem = str(page_stem or (self.parent.current_page.stem if self.parent.current_page else ""))
    if not stem:
        return {}
    if stem not in self._simplified_page_cache:
        page = None
        if self.parent.project:
            for candidate in self.parent.project.images:
                if candidate.stem == stem:
                    page = candidate
                    break
        if page is None and self.parent.current_page and self.parent.current_page.stem == stem:
            page = self.parent.current_page
        records = read_simplified_records(simplified_review_path_for_image(page)) if page else {}
        self._simplified_page_cache[stem] = records
    return self._simplified_page_cache[stem]


def _simplified_display_from_value(deps: ReviewSimplifiedDeps, original: str, value: str | None, manual: bool) -> str:
    if value is None:
        return "OpenCC不可用"
    if not manual and value == original:
        return "√"
    return value


def _auto_simplified_value(self, deps: ReviewSimplifiedDeps, original: str, fallback: str | None = None) -> str | None:
    simplify_text = deps.simplify_text
    converted = simplify_text(original)
    if converted is None:
        return fallback
    return converted


def _capture_simplified_edits(self, deps: ReviewSimplifiedDeps, page_stem: str | None = None) -> None:
    simplified_entry_key = deps.simplified_entry_key
    stem = str(page_stem or "")
    if (not stem or not getattr(self, "simplified_vars", [])
            or self.__dict__.get("_r3_simplified_capture_blocked", False)):
        return
    records = self._simplified_page_records(stem)
    # Preserve rendered row identities across section-order changes.
    rendered_entries = self._bound_row_entries()
    # Only capture against the currently rendered page.  During navigation
    # parent.current_page may already refer to the next page while the old
    # widgets are still being destroyed.
    if self.parent.current_page and self.parent.current_page.stem != stem:
        return
    for i, entry in enumerate(rendered_entries[:len(self.simplified_vars)]):
        key = simplified_entry_key(entry.x, entry.y)
        manual = bool(self.simplified_manual_flags[i]) if i < len(self.simplified_manual_flags) else False
        actual = self.simplified_actual_values[i] if i < len(self.simplified_actual_values) else None
        display = self.simplified_vars[i].get().strip()
        expected = self._simplified_display_from_value(entry.word, actual, False)
        if not manual and display != expected:
            manual = True
            if i < len(self.simplified_manual_flags):
                self.simplified_manual_flags[i] = True
            self._simplified_dirty_pages.add(stem)
        if manual:
            actual = entry.word if display == "√" else display
            if i < len(self.simplified_actual_values):
                self.simplified_actual_values[i] = actual
        records[key] = {
            "x": int(entry.x), "y": int(entry.y),
            "source_word": entry.word, "text": "" if actual is None else str(actual),
            "manual": manual,
        }


def _persist_simplified_page(self, deps: ReviewSimplifiedDeps, page_stem: str | None = None) -> None:
    simplified_review_path_for_image = deps.simplified_review_path_for_image
    write_simplified_records = deps.write_simplified_records
    stem = str(page_stem or (self.parent.current_page.stem if self.parent.current_page else ""))
    if not stem or not self.parent.project:
        return
    page = next((item for item in self.parent.project.images if item.stem == stem), None)
    if page is None:
        return
    records = self._simplified_page_records(stem)
    write_simplified_records(simplified_review_path_for_image(page), stem, records)
    self._simplified_dirty_pages.discard(stem)


def _simplified_query_for_index(self, deps: ReviewSimplifiedDeps, index: int) -> str:
    if not (0 <= index < len(self.vars)):
        return ""
    if index < len(self.simplified_actual_values):
        value = self.simplified_actual_values[index]
        if value is not None and str(value).strip():
            return str(value).strip()
    shown = self.simplified_vars[index].get().strip() if index < len(self.simplified_vars) else ""
    if shown == "√":
        return self.vars[index].get().strip()
    if shown and shown != "OpenCC不可用":
        return shown
    return ""


def lookup_simplified_online(self, deps: ReviewSimplifiedDeps, index: int) -> None:
    if not (0 <= index < len(self.vars)):
        return
    self.set_active(index)
    word = self._simplified_query_for_index(index)
    if not word:
        self.network_lookup_status_var.set("网络词汇核验：简化词条为空")
        return
    self._schedule_network_lookup(word, force=True)


def _focus_simplified_editor(self, deps: ReviewSimplifiedDeps, index: int) -> None:
    tk = deps.tk
    self.set_active(index)
    if not (0 <= index < len(self.simplified_editors)):
        return
    # Auto placeholders are scan-friendly but awkward to type over. Select
    # them on focus so the first keystroke replaces √/OpenCC提示 directly.
    if self.simplified_vars[index].get() in {"√", "OpenCC不可用"}:
        try:
            self.simplified_editors[index].selection_range(0, "end")
        except tk.TclError:
            pass


def _claim_simplified_clipboard_edit(self, deps: ReviewSimplifiedDeps, index: int) -> str | None:
    if not self.parent._claim_page_for_manual_edit():
        return "break"
    self.after_idle(lambda i=index: self.on_simplified_key(type("_Event", (), {})(), i))
    return None


def on_simplified_key(self, deps: ReviewSimplifiedDeps, _event: tk.Event, index: int) -> None:
    simplified_entry_key = deps.simplified_entry_key
    if not (0 <= index < len(self.simplified_vars)):
        return
    value = self.simplified_vars[index].get().strip()
    already_manual = bool(self.simplified_manual_flags[index]) if index < len(self.simplified_manual_flags) else False
    if not already_manual:
        original = self.vars[index].get().strip() if index < len(self.vars) else ""
        auto_refresh = (
            bool(self.simplified_auto_refresh_flags[index])
            if index < len(self.simplified_auto_refresh_flags) else True
        )
        if auto_refresh:
            expected_actual = self._auto_simplified_value(
                original,
                fallback=(self.simplified_actual_values[index] if index < len(self.simplified_actual_values) else None),
            )
        else:
            expected_actual = (
                self.simplified_actual_values[index]
                if index < len(self.simplified_actual_values) else None
            )
        expected = self._simplified_display_from_value(original, expected_actual, False)
        # Arrow/Home/End/etc. do not turn an untouched saved/OpenCC value
        # into a manual override merely because a KeyRelease event occurred.
        if value == expected:
            return
    if not self.parent._claim_page_for_manual_edit():
        return
    actual = self.vars[index].get().strip() if value == "√" else value
    if index < len(self.simplified_actual_values):
        self.simplified_actual_values[index] = actual
    if index < len(self.simplified_manual_flags):
        self.simplified_manual_flags[index] = True
    stem = self._rendered_page_stem
    if stem:
        ordered = self.parent._ordered_entries_reading_order()
        if index < len(ordered):
            entry = ordered[index]
            records = self._simplified_page_records(stem)
            records[simplified_entry_key(entry.x, entry.y)] = {
                "x": int(entry.x), "y": int(entry.y),
                "source_word": self.vars[index].get().strip(),
                "text": actual, "manual": True,
            }
            self._simplified_dirty_pages.add(stem)
    if index == self.active_index:
        self._refresh_cc_simplified_comparison(index)


def _refresh_simplified_for_index(self, deps: ReviewSimplifiedDeps, index: int) -> None:
    simplified_entry_key = deps.simplified_entry_key
    if not (0 <= index < len(self.vars) and index < len(self.simplified_vars)):
        return
    # Any simplified value already persisted before this page was opened
    # is independent data, even when it was originally generated by OpenCC.
    # Only never-saved rows are allowed to follow original-headword edits
    # automatically during the current session.
    manual = bool(self.simplified_manual_flags[index]) if index < len(self.simplified_manual_flags) else False
    refresh_flags = getattr(self, "simplified_auto_refresh_flags", [])
    auto_refresh = bool(refresh_flags[index]) if index < len(refresh_flags) else True
    if manual or not auto_refresh:
        if index == getattr(self, "active_index", -1):
            self._refresh_cc_simplified_comparison(index)
        return
    original = self.vars[index].get().strip()
    fallback = self.simplified_actual_values[index] if index < len(self.simplified_actual_values) else None
    actual = self._auto_simplified_value(original, fallback=fallback)
    if index < len(self.simplified_actual_values):
        self.simplified_actual_values[index] = actual
    self.simplified_vars[index].set(self._simplified_display_from_value(original, actual, False))
    stem = self._rendered_page_stem
    row_entries = self._bound_row_entries()
    if stem and index < len(row_entries):
        entry = row_entries[index]
        self._simplified_page_records(stem)[simplified_entry_key(entry.x, entry.y)] = {
            "x": int(entry.x), "y": int(entry.y),
            "source_word": original, "text": "" if actual is None else str(actual),
            "manual": False,
        }
        self._simplified_dirty_pages.add(stem)
    if index == getattr(self, "active_index", -1):
        self._refresh_cc_simplified_comparison(index)


def _refresh_all_simplified(self, deps: ReviewSimplifiedDeps) -> None:
    for index in range(min(len(self.vars), len(self.simplified_vars))):
        self._refresh_simplified_for_index(index)


def regenerate_simplified_current_page(self, deps: ReviewSimplifiedDeps) -> None:
    """Force OpenCC regeneration for every simplified headword on the current page."""
    messagebox = deps.messagebox
    simplified_entry_key = deps.simplified_entry_key
    simplify_text = deps.simplify_text
    if not self.parent.current_page or not self.vars:
        return
    row_entries = self._bound_row_entries()
    count = min(len(self.vars), len(self.simplified_vars), len(row_entries))
    if count <= 0:
        return
    originals = [self.vars[index].get().strip() for index in range(count)]
    regenerated = [simplify_text(original) for original in originals]
    if any(value is None for value in regenerated):
        messagebox.showerror(
            "重新简体化",
            "OpenCC不可用，未覆盖本页已有的简体化结果。",
            parent=self,
        )
        return
    if not self.parent._claim_page_for_manual_edit():
        return

    stem = self._rendered_page_stem or self.parent.current_page.stem
    records = self._simplified_page_records(stem)
    for index, (entry, original, actual) in enumerate(
        zip(row_entries[:count], originals, regenerated)
    ):
        if index < len(self.simplified_actual_values):
            self.simplified_actual_values[index] = actual
        if index < len(self.simplified_manual_flags):
            self.simplified_manual_flags[index] = False
        if index < len(self.simplified_auto_refresh_flags):
            self.simplified_auto_refresh_flags[index] = False
        self.simplified_vars[index].set(
            self._simplified_display_from_value(original, actual, False)
        )
        records[simplified_entry_key(entry.x, entry.y)] = {
            "x": int(entry.x),
            "y": int(entry.y),
            "source_word": original,
            "text": str(actual),
            "manual": False,
        }

    self._simplified_dirty_pages.add(stem)
    self._persist_simplified_page(stem)
    self._refresh_cc_simplified_comparison(self.active_index)
    self.parent.status_var.set(
        f"已重新简体化当前页：{self.parent.current_page.name}｜覆盖 {count} 条简体结果"
    )


def _apply_simplified_visibility(self, deps: ReviewSimplifiedDeps) -> None:
    tk = deps.tk
    show = bool(self.review_show_simplified_var.get())
    for index, (frame, widget) in enumerate(zip(self.editor_frames, self.simplified_editors)):
        button = self.simplified_search_buttons[index] if index < len(self.simplified_search_buttons) else None
        try:
            if show:
                self._refresh_simplified_for_index(index)
                frame.columnconfigure(1, weight=1, uniform=f"review_pair_{index}")
                frame.columnconfigure(2, weight=1, uniform=f"review_pair_{index}")
                widget.grid()
                if button is not None:
                    button.grid()
            else:
                widget.grid_remove()
                if button is not None:
                    button.grid_remove()
                frame.columnconfigure(1, weight=1, uniform="")
                frame.columnconfigure(2, weight=0, uniform="")
        except tk.TclError:
            pass


def _toggle_review_simplified(self, deps: ReviewSimplifiedDeps) -> None:
    self.parent.settings.review_show_simplified = bool(self.review_show_simplified_var.get())
    self.parent.save_settings()
    self._apply_simplified_visibility()

