from __future__ import annotations

import tkinter as tk


class VerticalWordText(tk.Text):
    """Editable Tk widget presenting one headword as a narrow vertical column.

    It exposes the small subset of Entry-like methods used by the main overlay
    code, so OCR fill, autosave, wordslist styling and manual-edit persistence
    share the same code path as horizontal Entry widgets.
    """

    @staticmethod
    def _entry_index(index) -> str:
        if index in {"end", tk.END}:
            return "end-1c"
        if isinstance(index, int):
            return f"1.{max(0, index)}"
        if str(index) == "0":
            return "1.0"
        return str(index)

    def get(self, *args):
        if args:
            return super().get(*args)
        # Main-overlay words are single logical strings. A pasted newline must
        # not become part of the dictionary headword.
        return super().get("1.0", "end-1c").replace("\n", "")

    def delete(self, first=0, last=None):
        first_index = self._entry_index(first)
        if last is None:
            return super().delete(first_index)
        return super().delete(first_index, self._entry_index(last))

    def insert(self, index, chars, *args):
        return super().insert(self._entry_index(index), chars, *args)

    def icursor(self, index) -> None:
        target = self._entry_index(index)
        self.mark_set("insert", target)
        self.see(target)

    def selection_range(self, start, end) -> None:
        self.tag_remove("sel", "1.0", "end")
        self.tag_add("sel", self._entry_index(start), self._entry_index(end))


__all__ = ["VerticalWordText"]
