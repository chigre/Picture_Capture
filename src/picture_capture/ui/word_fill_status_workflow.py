"""PictureCaptureApp word_fill actions and state: physical owner.

Original user-visible callbacks remain on the Tk shell with identical signatures.
Dependencies bind at each call, without importing heavyweight app.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from pathlib import Path

@dataclass(frozen=True)
class WordFillStatusDeps:
    """Live collaborators from the compatibility shell."""
    Path: object
    json: object
    os: object
    word_fill_status_path: object


def _word_fill_status_path(self, deps: WordFillStatusDeps) -> Path | None:
    word_fill_status_path = deps.word_fill_status_path
    if not self.project:
        return None
    return word_fill_status_path(self.project.root)


def _load_word_fill_status(self, deps: WordFillStatusDeps) -> None:
    """Restore persisted TXT-vs-line count checks for the current project."""
    json = deps.json
    self._word_fill_check_status = {}
    self._word_fill_mismatch_pages.clear()
    path = self._word_fill_status_path()
    if path is None or not path.exists() or not self.project:
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_pages = payload.get("pages", {}) if isinstance(payload, dict) else {}
        if not isinstance(raw_pages, dict):
            return
        known = {page.stem: i for i, page in enumerate(self.project.images)}
        for stem, raw in raw_pages.items():
            if stem not in known or not isinstance(raw, dict):
                continue
            try:
                line_count = max(0, int(raw.get("line_count", 0)))
                word_count = max(0, int(raw.get("word_count", 0)))
            except (TypeError, ValueError):
                continue
            # v1 sidecars had only mismatch. Infer their state so old projects
            # open cleanly, while v2 sidecars retain stale/no-data states.
            state = str(raw.get("state", "")).strip().lower()
            if state not in {"match", "mismatch", "stale", "no_data"}:
                state = "mismatch" if bool(raw.get("mismatch", line_count != word_count)) else "match"
            mismatch = state == "mismatch"
            item = {
                "line_count": line_count,
                "word_count": word_count,
                "mismatch": mismatch,
                "state": state,
                "source": str(raw.get("source", "")),
            }
            self._word_fill_check_status[stem] = item
            if mismatch:
                self._word_fill_mismatch_pages.add(known[stem])
    except Exception:
        # A damaged optional UI-status sidecar must never block opening the
        # dictionary itself. The next successful fill rewrites it.
        self._word_fill_check_status = {}
        self._word_fill_mismatch_pages.clear()


def _persist_word_fill_status(self, deps: WordFillStatusDeps) -> None:
    """Atomically save persistent line-count comparison results."""
    json = deps.json
    os = deps.os
    path = self._word_fill_status_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 2, "pages": self._word_fill_check_status}
    temp = path.with_name(f".{path.name}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def _word_fill_status_text(self, deps: WordFillStatusDeps, index: int) -> str:
    """Return the compact per-page text shown in the new fill-status column."""
    if not self.project or not (0 <= index < len(self.project.images)):
        return "未核对"
    stem = self.project.images[index].stem
    item = self.__dict__.get("_word_fill_check_status", {}).get(stem)
    if not item:
        return "未核对"
    state = str(item.get("state", "")).lower()
    if state == "no_data":
        return "无资料"
    if state == "stale":
        return "待重新核对"
    line_count = max(0, int(item.get("line_count", 0) or 0))
    word_count = max(0, int(item.get("word_count", 0) or 0))
    diff = line_count - word_count
    if diff == 0 and state != "mismatch":
        return "一致"
    if diff < 0:
        return f"少 {abs(diff)}"
    if diff > 0:
        return f"多 {diff}"
    return "一致"


def _record_word_fill_check(self, deps: WordFillStatusDeps, index: int, line_count: int, word_count: int, *, source: str = "",
    has_data: bool = True, persist: bool = False, refresh_overlay: bool = True,
    refresh_row: bool = True,
) -> None:
    if not self.project or not (0 <= index < len(self.project.images)):
        return
    stem = self.project.images[index].stem
    line_count = max(0, int(line_count))
    word_count = max(0, int(word_count))
    state = "no_data" if not has_data else ("match" if line_count == word_count else "mismatch")
    mismatch = state == "mismatch"
    if "_word_fill_check_status" not in self.__dict__:
        self._word_fill_check_status = {}
    if "_word_fill_mismatch_pages" not in self.__dict__:
        self._word_fill_mismatch_pages = set()
    previous = self._word_fill_check_status.get(stem, {})
    self._word_fill_check_status[stem] = {
        "line_count": line_count,
        "word_count": word_count,
        "mismatch": mismatch,
        "state": state,
        "source": str(source or previous.get("source", "")),
    }
    if mismatch:
        self._word_fill_mismatch_pages.add(index)
    else:
        self._word_fill_mismatch_pages.discard(index)
    if persist:
        self._persist_word_fill_status()
    if refresh_row and "page_list" in self.__dict__:
        self._update_page_row(index)
    if refresh_overlay and "page_list" in self.__dict__:
        self._schedule_page_cell_overlay_refresh()


def _refresh_word_fill_check_from_line_count(self, deps: WordFillStatusDeps, index: int, line_count: int, *, persist: bool = False,
) -> None:
    """Mark a prior fill check stale only when the number of lines changed.

    Editing OCR/headword text does not invalidate a count check. Adding or
    deleting a line does: the page then shows ``待重新核对`` until the user
    runs “填充词条” again.
    """
    if not self.project or not (0 <= index < len(self.project.images)):
        return
    stem = self.project.images[index].stem
    previous = self.__dict__.get("_word_fill_check_status", {}).get(stem)
    if not previous:
        return
    line_count = max(0, int(line_count))
    old_line_count = max(0, int(previous.get("line_count", 0) or 0))
    state = str(previous.get("state", "")).lower()
    # No source data remains no source data; changing PDIC lines cannot make
    # a page suddenly appear in the selected TXT.
    if state == "no_data":
        if line_count != old_line_count:
            previous["line_count"] = line_count
            if persist:
                self._persist_word_fill_status()
            if "page_list" in self.__dict__:
                self._update_page_row(index)
        return
    if line_count == old_line_count:
        return
    previous = dict(previous)
    previous["line_count"] = line_count
    previous["state"] = "stale"
    previous["mismatch"] = False
    self._word_fill_check_status[stem] = previous
    self._word_fill_mismatch_pages.discard(index)
    if persist:
        self._persist_word_fill_status()
    if "page_list" in self.__dict__:
        self._update_page_row(index)
    if "page_list" in self.__dict__:
        self._schedule_page_cell_overlay_refresh()


def _clear_word_fill_checks_for_indices(self, deps: WordFillStatusDeps, indices, *, persist: bool = False) -> None:
    if not self.project:
        return
    if "_word_fill_check_status" not in self.__dict__:
        self._word_fill_check_status = {}
    if "_word_fill_mismatch_pages" not in self.__dict__:
        self._word_fill_mismatch_pages = set()
    changed = False
    changed_indices: list[int] = []
    for index in indices:
        if not (0 <= int(index) < len(self.project.images)):
            continue
        i = int(index)
        stem = self.project.images[i].stem
        if stem in self._word_fill_check_status:
            self._word_fill_check_status.pop(stem, None)
            changed = True
            changed_indices.append(i)
        if i in self._word_fill_mismatch_pages:
            self._word_fill_mismatch_pages.discard(i)
            changed = True
            if i not in changed_indices:
                changed_indices.append(i)
    if changed and persist:
        self._persist_word_fill_status()
    if changed and "page_list" in self.__dict__:
        for i in changed_indices:
            self._update_page_row(i)
        self._schedule_page_cell_overlay_refresh()

