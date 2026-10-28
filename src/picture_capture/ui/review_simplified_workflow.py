"""Physical owner of simplified review callbacks.

ReviewWindow owns original public Tk signatures and passes current collaborators.
This module never imports app.py or changes the stored project formats.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..proofreading.simplified_review import source_word_conflicts

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
        if page is None:
            return {}
        from ..proofreading.transactions import _bytes_or_absent
        path = simplified_review_path_for_image(page)
        old_bytes = _bytes_or_absent(path)
        records = read_simplified_records(path)
        if _bytes_or_absent(path) != old_bytes:
            raise RuntimeError("R3 简体副本读取期间发生外部修改")
        self._simplified_page_cache[stem] = records
        self.__dict__.setdefault("_r3_simplified_source_bytes", {})[stem] = (
            path.resolve(), old_bytes,
        )
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
    stem = str(page_stem or "")
    if (not stem or not getattr(self, "simplified_vars", [])
            or self.__dict__.get("_r3_simplified_capture_blocked", False)):
        return
    # Old FocusOut / asynchronous Tk rows may not mutate another page cache.
    rendered_entries = _owned_rendered_simplified_rows(self)
    if rendered_entries is None or self.parent.current_page.stem != stem:
        return
    simplified_entry_key = deps.simplified_entry_key
    records = self._simplified_page_records(stem)
    for i, entry in enumerate(rendered_entries):
        key = simplified_entry_key(entry.x, entry.y)
        if source_word_conflicts(records.get(key), entry.word):
            continue
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
    stem = str(page_stem or (self.parent.current_page.stem if self.parent.current_page else ""))
    if not stem or not self.parent.project:
        return
    page = next((item for item in self.parent.project.images if item.stem == stem), None)
    if (page is None or self.parent.current_page != page
            or getattr(self, "_rendered_page_stem", "") != stem):
        raise RuntimeError("R3 不是当前校对页面，拒绝简体副本写入")
    records = self._simplified_page_records(stem)
    path = simplified_review_path_for_image(page)
    pinned = self.__dict__.get("_r3_simplified_source_bytes", {}).get(stem)
    if pinned is None or pinned[0] != path.resolve():
        raise RuntimeError("R3 无可信简体人工副本来源，拒绝覆盖")
    from ..proofreading.simplified_review import guarded_write_records
    committed = guarded_write_records(
        page, path, stem, records, pinned[1],
        writer=deps.write_simplified_records,
    )
    self.__dict__["_r3_simplified_source_bytes"][stem] = (
        path.resolve(), committed,
    )
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


def _owned_rendered_simplified_rows(self):
    """Prove every Tk row still belongs to the live page and original pixels.

    The current reading/SECTION order is not an owner of old Tk row indices.
    Refuse partial redraws, cross-page callbacks and duplicated XY keys rather
    than attaching a human edit to another Entry's sidecar record.
    """
    page = getattr(self.parent, "current_page", None)
    bound = getattr(self, "row_entries", None)
    if (page is None or bound is None
            or getattr(self, "_rendered_page_stem", "") != page.stem
            or getattr(self, "_filter_rows_active", False)):
        return None
    rows = tuple(bound)
    live = tuple(getattr(self.parent, "entries", ()))
    if (not rows or len(rows) != len(live)
            or len(rows) != len(getattr(self, "vars", ()))
            or len(rows) != len(getattr(self, "simplified_vars", ()))
            or len(rows) != len(getattr(self, "simplified_manual_flags", ()))
            or len(rows) != len(getattr(self, "simplified_actual_values", ()))):
        return None
    if ({id(row) for row in rows} != {id(row) for row in live}
            or len({id(row) for row in rows}) != len(rows)):
        return None
    try:
        coordinates = [(int(row.x), int(row.y)) for row in rows]
    except (TypeError, ValueError, AttributeError):
        return None
    if len(set(coordinates)) != len(rows):
        return None
    return rows


def _claim_simplified_clipboard_edit(self, deps: ReviewSimplifiedDeps, index: int) -> str | None:
    rows = _owned_rendered_simplified_rows(self)
    if rows is None or not 0 <= index < len(rows):
        return "break"
    owned = rows[index]
    page_stem = self.parent.current_page.stem
    if not self.parent._claim_page_for_manual_edit():
        return "break"

    def apply_if_still_owned():
        fresh = _owned_rendered_simplified_rows(self)
        if (fresh is not None and 0 <= index < len(fresh)
                and fresh[index] is owned and self.parent.current_page.stem == page_stem):
            self.on_simplified_key(type("_Event", (), {})(), index)

    self.after_idle(apply_if_still_owned)
    return None


def on_simplified_key(self, deps: ReviewSimplifiedDeps, _event: tk.Event, index: int) -> None:
    simplified_entry_key = deps.simplified_entry_key
    rows = _owned_rendered_simplified_rows(self)
    if rows is None or not 0 <= index < len(rows):
        return
    # A queued KeyRelease from a destroyed widget must never edit a newly
    # rendered row that happens to reuse the same numeric index.
    widget = getattr(_event, "widget", None)
    editors = getattr(self, "simplified_editors", ())
    if widget is not None and (index >= len(editors) or editors[index] is not widget):
        return
    entry = rows[index]
    value = self.simplified_vars[index].get().strip()
    original_word = self.vars[index].get().strip()
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
    if source_word_conflicts(
        self._simplified_page_records(self._rendered_page_stem).get(
            simplified_entry_key(entry.x, entry.y),
        ), entry.word,
    ):
        return
    if not self.parent._claim_page_for_manual_edit():
        return
    fresh = _owned_rendered_simplified_rows(self)
    if (fresh is None or fresh[index] is not entry
            or self.vars[index].get().strip() != original_word
            or self.simplified_vars[index].get().strip() != value
            or source_word_conflicts(
                self._simplified_page_records(self._rendered_page_stem).get(
                    simplified_entry_key(entry.x, entry.y),
                ), entry.word,
            )):
        return
    actual = original_word if value == "√" else value
    stem = self._rendered_page_stem
    records = self._simplified_page_records(stem)
    records[simplified_entry_key(entry.x, entry.y)] = {
        "x": int(entry.x), "y": int(entry.y),
        "source_word": original_word,
        "text": actual, "manual": True,
    }
    self.simplified_actual_values[index] = actual
    self.simplified_manual_flags[index] = True
    self._simplified_dirty_pages.add(stem)
    if index == self.active_index:
        self._refresh_cc_simplified_comparison(index)


def _refresh_simplified_for_index(self, deps: ReviewSimplifiedDeps, index: int) -> None:
    simplified_entry_key = deps.simplified_entry_key
    rows = _owned_rendered_simplified_rows(self)
    if rows is None or not 0 <= index < len(rows):
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
    entry = rows[index]
    if source_word_conflicts(
        self._simplified_page_records(stem).get(
            simplified_entry_key(entry.x, entry.y),
        ), entry.word,
    ):
        return
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
    row_entries = _owned_rendered_simplified_rows(self)
    if row_entries is None:
        return
    count = len(row_entries)
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
    fresh = _owned_rendered_simplified_rows(self)
    if (fresh is None or any(a is not b for a, b in zip(row_entries, fresh))
            or len(fresh) != count
            or [var.get().strip() for var in self.vars] != originals):
        return

    stem = self._rendered_page_stem
    records = self._simplified_page_records(stem)
    if any(source_word_conflicts(
        records.get(simplified_entry_key(entry.x, entry.y)), entry.word,
    ) for entry in row_entries):
        messagebox.showerror(
            "重新简体化",
            "本页原词与简体来源不一致，已拒绝覆盖，请核对旧人工数据。",
            parent=self,
        )
        return
    # A source-pinned persist may refuse a third-party human edit. Freeze the
    # entire visible/manual/cache state BEFORE changing anything, so a failed
    # whole-page regeneration cannot leave OpenCC results masquerading as saved
    # manual corrections. Keep unrelated cached rows and existing dirty state.
    previous_display = [var.get() for var in self.simplified_vars]
    previous_actual = list(self.simplified_actual_values)
    previous_manual = list(self.simplified_manual_flags)
    previous_auto = list(getattr(self, "simplified_auto_refresh_flags", ()))
    was_dirty = stem in self._simplified_dirty_pages
    proposals = [
        (simplified_entry_key(entry.x, entry.y), {
            "x": int(entry.x), "y": int(entry.y),
            "source_word": original, "text": str(actual), "manual": False,
        }, self._simplified_display_from_value(original, actual, False))
        for entry, original, actual in zip(row_entries, originals, regenerated)
    ]
    previous_records = {
        key: (key in records, records.get(key)) for key, _, _ in proposals
    }
    # Edits to unrelated source-coordinate rows may arrive synchronously
    # through a Tk callback while a protected persistence attempt runs.
    untouched_rows = {
        key: value for key, value in records.items()
        if key not in previous_records
    }
    try:
        for index, (key, proposed_record, display) in enumerate(proposals):
            self.simplified_actual_values[index] = regenerated[index]
            self.simplified_manual_flags[index] = False
            if index < len(previous_auto):
                self.simplified_auto_refresh_flags[index] = False
            self.simplified_vars[index].set(display)
            records[key] = proposed_record
        self._simplified_dirty_pages.add(stem)
        self._persist_simplified_page(stem)
    except Exception:
        # Do not erase a newer local edit if a synchronous Tk callback changed
        # it while persistence ran. Restore only values still owned by this
        # regeneration, and retain dirty state if any rollback is uncertain.
        restored = True
        for index, (key, proposed_record, display) in enumerate(proposals):
            current_actual = self.simplified_actual_values[index]
            if current_actual == regenerated[index]:
                self.simplified_actual_values[index] = previous_actual[index]
            elif current_actual != previous_actual[index]:
                restored = False
            current_manual = self.simplified_manual_flags[index]
            if current_manual is False:
                self.simplified_manual_flags[index] = previous_manual[index]
            elif current_manual != previous_manual[index]:
                restored = False
            if index < len(previous_auto):
                current_auto = self.simplified_auto_refresh_flags[index]
                if current_auto is False:
                    self.simplified_auto_refresh_flags[index] = previous_auto[index]
                elif current_auto != previous_auto[index]:
                    restored = False
            current_display = self.simplified_vars[index].get()
            if current_display == display:
                try:
                    self.simplified_vars[index].set(previous_display[index])
                except Exception:
                    restored = False
            elif current_display != previous_display[index]:
                restored = False
            existed, original_record = previous_records[key]
            if records.get(key) == proposed_record:
                if existed:
                    records[key] = original_record
                else:
                    records.pop(key, None)
            elif (key in records) != existed or (
                existed and records[key] != original_record
            ):
                # A different/newer cache entry must not be overwritten.
                restored = False
        if {
            key: value for key, value in records.items()
            if key not in previous_records
        } != untouched_rows:
            restored = False
        if not was_dirty and restored:
            self._simplified_dirty_pages.discard(stem)
        else:
            self._simplified_dirty_pages.add(stem)
        raise
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

