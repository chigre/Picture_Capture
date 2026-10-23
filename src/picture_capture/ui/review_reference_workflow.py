"""ReviewWindow reference-list lookup and virtualized browsing.

ReviewWindow delegates without importing the heavyweight GUI shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from pathlib import Path


@dataclass(frozen=True)
class ReviewReferenceDeps:
    """Live legacy collaborators captured separately for each callback."""
    tk: object
    filedialog: object
    messagebox: object
    Path: object
    unicodedata: object
    bisect: object
    resolve_wordslist_path: object
    read_pdic: object
    pdic_path: object
    reference_sort_key: object
    _is_cjk_review_index: object


def _effective_wordslist_locator_mode(self, deps: ReviewReferenceDeps) -> str:
    _is_cjk_review_index = deps._is_cjk_review_index
    """Resolve the auxiliary-list locator without assuming page alignment.

    Chinese projects default to a sorted external-index workflow because a
    one-word-per-line index copied from another dictionary can contain many
    missing/extra entries. Latin projects keep the historical sequential
    behaviour unless the user explicitly selects the external-index mode.
    """
    settings = getattr(self.parent, "settings", None)
    mode = str(getattr(settings, "wordslist_locator_mode", "auto") or "auto").lower()
    if mode in {"sorted", "sequential"}:
        return mode
    if settings is not None and _is_cjk_review_index(settings):
        return "sorted"
    return "sequential"


def _change_wordslist_locator_mode(self, deps: ReviewReferenceDeps, _event: tk.Event | None = None) -> None:
    key = self.WORDSLIST_LOCATOR_LABEL_TO_KEY.get(self.wordslist_locator_var.get(), "auto")
    self.parent.settings.wordslist_locator_mode = key
    self.parent.save_settings()
    self._previous_reference_base_cache = None
    self.refresh_wordslist_display()


def _wordslist_lookup_key(deps: ReviewReferenceDeps, word: str) -> str:
    unicodedata = deps.unicodedata
    """Cheap lookup key for the auxiliary list, not for dictionary order validation.

    Full collation_key() intentionally supports custom alphabets and multi-letter
    collation units, but compiling that machinery 190k times is unnecessary for
    merely positioning the review helper near an OCR word. Exact spelling lookup
    is attempted first; this folded key is only the fallback.
    """
    text = unicodedata.normalize("NFKD", (word or "").casefold().strip())
    return "".join(ch for ch in text if not unicodedata.combining(ch) and ch.isalnum())


def refresh_wordslist_display(self, deps: ReviewReferenceDeps) -> None:
    resolve_wordslist_path = deps.resolve_wordslist_path
    reference_words = self.parent.project.words if self.parent.project else []
    self._clear_word_list_rows()
    self.word_highlight_index = None
    self.word_window_start = 0
    self.word_window_indices = []

    # Build the lookup structures once when the file changes.  This is O(n)
    # plus one sort, but unlike the old implementation it never creates
    # 190k Tk list items.  Exact lookup is the common path during review.
    self.word_keys = [self._wordslist_lookup_key(word) for word in reference_words]
    self.word_exact_index = {}
    self.word_exact_indices = {}
    for i, word in enumerate(reference_words):
        key = word.strip().casefold()
        self.word_exact_index.setdefault(key, i)
        self.word_exact_indices.setdefault(key, []).append(i)
    # Keep the historical lightweight folded index for Latin/sequential
    # fallback.  Do NOT precompute pinyin for a 100k–200k Chinese index:
    # sorted external-index lookup below performs a lazy O(log n) binary
    # search and caches only the handful of probed pinyin keys.
    if self.word_keys and all(self.word_keys[i - 1] <= self.word_keys[i] for i in range(1, len(self.word_keys))):
        self.sorted_word_keys = self.word_keys
        self.sorted_word_indices = list(range(len(self.word_keys)))
    else:
        lightweight_pairs = sorted((key, i) for i, key in enumerate(self.word_keys))
        self.sorted_word_keys = [key for key, _i in lightweight_pairs]
        self.sorted_word_indices = [i for _key, i in lightweight_pairs]
    self.word_sort_key_cache = {}

    if self.parent.project:
        path = resolve_wordslist_path(self.parent.project.root, self.parent.settings.wordslist_path)
        self.word_window_var.set(f"{path.name} | 0-0 / {len(reference_words)}")
    else:
        self.word_window_var.set("未选择 | 0-0 / 0")
    if reference_words:
        if self.vars and 0 <= self.active_index < len(self.vars):
            self.locate_reference_word(self.vars[self.active_index].get())
        else:
            self._show_wordslist_window(0)


def _show_wordslist_window(self, deps: ReviewReferenceDeps, target: int) -> None:
    resolve_wordslist_path = deps.resolve_wordslist_path
    """Render only a small window around one global wordslist index."""
    words = self.parent.project.words if self.parent.project else []
    if not words:
        self._clear_word_list_rows()
        self.word_window_indices = []
        self.word_window_start = 0
        self.word_highlight_index = None
        if hasattr(self, "word_window_var"):
            if self.parent.project:
                path = resolve_wordslist_path(
                    self.parent.project.root, self.parent.settings.wordslist_path
                )
                self.word_window_var.set(f"{path.name} | 0-0 / 0")
            else:
                self.word_window_var.set("未选择 | 0-0 / 0")
        return
    target = max(0, min(int(target), len(words) - 1))
    span = self.word_window_radius * 2 + 1
    start = max(0, target - self.word_window_radius)
    start = min(start, max(0, len(words) - span))
    end = min(len(words), start + span)
    self.word_window_start = start
    self.word_window_indices = list(range(start, end))
    if hasattr(self, "word_window_var"):
        path = resolve_wordslist_path(
            self.parent.project.root, self.parent.settings.wordslist_path
        )
        self.word_window_var.set(
            f"{path.name} | {start + 1}-{end} / {len(words)}"
        )
    self._render_word_list_rows(words)
    local = target - start
    self.word_highlight_index = local
    self._set_word_list_highlight(local)


def shift_wordslist_window(self, deps: ReviewReferenceDeps, direction: int) -> None:
    """Browse the large reference list by 100 rows without bulk rendering."""
    words = self.parent.project.words if self.parent.project else []
    if not words:
        return
    span = self.word_window_radius * 2 + 1
    step = 100
    start = max(
        0,
        min(
            self.word_window_start + int(direction) * step,
            max(0, len(words) - span),
        ),
    )
    target = min(
        len(words) - 1,
        start + min(self.word_window_radius, max(0, len(words) - 1 - start)),
    )
    self._show_wordslist_window(target)


def choose_wordslist_file(self, deps: ReviewReferenceDeps) -> None:
    tk = deps.tk
    filedialog = deps.filedialog
    messagebox = deps.messagebox
    Path = deps.Path
    resolve_wordslist_path = deps.resolve_wordslist_path
    if not self.parent.project:
        return
    current = resolve_wordslist_path(self.parent.project.root, self.parent.settings.wordslist_path)
    chosen = filedialog.askopenfilename(
        parent=self, title="选择 wordslist 参考词表",
        initialdir=str(current.parent if current.parent.exists() else self.parent.project.root),
        initialfile=current.name if current.name else "wordslist.txt",
        filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
    )
    if not chosen:
        return
    self.word_window_var.set(f"{Path(chosen).name} | 正在读取…")

    def loaded(path: Path, count: int) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self.refresh_wordslist_display()
        words = self.parent._project_words
        for i, _editor in enumerate(self.editors):
            self._set_editor_membership_color(i, self.vars[i].get().strip() in words)
        self.parent.status_var.set(
            f"已选择 wordslist：{path}｜{count} 条；校对右侧参考词表已更新。"
        )

    def failed(exc: Exception) -> None:
        try:
            if self.winfo_exists():
                self.refresh_wordslist_display()
                messagebox.showerror("wordslist 读取失败", str(exc), parent=self)
        except tk.TclError:
            pass

    self.parent._request_wordslist_reload(
        Path(chosen), persist=True, redraw=True,
        on_done=loaded, on_error=failed,
    )


def _exact_reference_position(self, deps: ReviewReferenceDeps, word: str, near: int | None = None) -> int | None:
    key = (word or "").strip().casefold()
    if not key:
        return None
    positions = self.word_exact_indices.get(key, [])
    if not positions:
        return None
    if near is None:
        return positions[0]
    return min(positions, key=lambda value: abs(value - near))


def _previous_page_reference_target(self, deps: ReviewReferenceDeps, active_index: int) -> int | None:
    read_pdic = deps.read_pdic
    pdic_path = deps.pdic_path
    """Infer a current-page reference position from preceding PDIC tail anchors."""
    project = self.parent.project
    current_page_index = int(self.parent.current_index)
    if not project or current_page_index <= 0:
        return None
    cached = self._previous_reference_base_cache
    if cached is not None and cached[0] == current_page_index:
        return None if cached[1] is None else cached[1] + max(0, active_index)

    # Compute the expected reference index of the first entry on this page
    # once, then reuse it for consecutive empty/error entries.
    skipped_entries = 0
    base: int | None = None
    for page_index in range(current_page_index - 1, max(-1, current_page_index - 6), -1):
        try:
            entries = read_pdic(pdic_path(project.images[page_index]))
        except Exception:
            entries = []
        for local_index in range(len(entries) - 1, -1, -1):
            pos = self._exact_reference_position(entries[local_index].word)
            if pos is None:
                continue
            distance_to_first = (len(entries) - local_index) + skipped_entries
            base = pos + distance_to_first
            break
        if base is not None:
            break
        skipped_entries += len(entries)
    self._previous_reference_base_cache = (current_page_index, base)
    return None if base is None else base + max(0, active_index)


def _current_wordslist_global_target(self, deps: ReviewReferenceDeps) -> int | None:
    if self.word_window_indices and self.word_highlight_index is not None:
        local = min(max(0, int(self.word_highlight_index)), len(self.word_window_indices) - 1)
        return self.word_window_indices[local]
    return None


def _sorted_reference_position(self, deps: ReviewReferenceDeps, word: str) -> int | None:
    reference_sort_key = deps.reference_sort_key
    """Binary-search the native page-less list by pinyin/alphabet key lazily."""
    stripped = (word or "").strip()
    words = self.parent.project.words if self.parent.project else []
    if not stripped or not words:
        return None
    # Use the primary pinyin/alphabet key only. Chinese dictionaries often
    # use their own secondary rule (tone, stroke count, radical, etc.) for
    # homophones, so imposing Unicode as a secondary comparison could make
    # an otherwise pinyin-sorted external list appear non-monotonic. Exact
    # spelling lookup above still places a known word precisely.
    key = reference_sort_key(stripped)[0]
    lo, hi = 0, len(words)
    cache = self.word_sort_key_cache
    while lo < hi:
        mid = (lo + hi) // 2
        mid_key = cache.get(mid)
        if mid_key is None:
            mid_key = reference_sort_key(words[mid])
            cache[mid] = mid_key
        if mid_key[0] < key:
            lo = mid + 1
        else:
            hi = mid
    return min(max(0, lo), len(words) - 1)


def _infer_sorted_reference_target(self, deps: ReviewReferenceDeps, active_index: int, current_word: str) -> int:
    """Locate an external page-less index by exact word / collation, not row offset."""
    words = self.parent.project.words if self.parent.project else []
    if not words:
        return 0

    near = self._current_wordslist_global_target()
    current_exact = self._exact_reference_position(current_word, near=near)
    if current_exact is not None:
        return current_exact

    previous_anchor: tuple[int, int] | None = None
    next_anchor: tuple[int, int] | None = None
    for index in range(active_index - 1, -1, -1):
        if index >= len(self.vars):
            continue
        pos = self._exact_reference_position(self.vars[index].get(), near=near)
        if pos is not None:
            previous_anchor = (index, pos)
            break
    for index in range(active_index + 1, len(self.vars)):
        pos = self._exact_reference_position(self.vars[index].get(), near=near)
        if pos is not None:
            next_anchor = (index, pos)
            break

    stripped = (current_word or "").strip()
    if stripped:
        target = self._sorted_reference_position(stripped)
        if target is not None:
            # Exact neighbouring terms are useful bounds, but never assume
            # one row in this dictionary equals one row in the external one.
            if previous_anchor and next_anchor and previous_anchor[1] <= next_anchor[1]:
                return max(previous_anchor[1], min(next_anchor[1], target))
            if previous_anchor and target < previous_anchor[1]:
                return previous_anchor[1]
            if next_anchor and target > next_anchor[1]:
                return next_anchor[1]
            return target

    if previous_anchor and next_anchor and previous_anchor[1] <= next_anchor[1]:
        return round((previous_anchor[1] + next_anchor[1]) / 2)
    if previous_anchor:
        return previous_anchor[1]
    if next_anchor:
        return next_anchor[1]
    if near is not None:
        return near
    return 0


def _infer_reference_target(self, deps: ReviewReferenceDeps, active_index: int, current_word: str) -> int:
    bisect = deps.bisect
    words = self.parent.project.words if self.parent.project else []
    if not words:
        return 0
    if self._effective_wordslist_locator_mode() == "sorted":
        return self._infer_sorted_reference_target(active_index, current_word)

    # Do not trust the current OCR/edit field first: it may be empty or a
    # valid-looking but wrong word. Neighbouring already-verified words are
    # stronger anchors for locating the auxiliary dictionary list.
    previous_anchor: tuple[int, int] | None = None
    next_anchor: tuple[int, int] | None = None
    for index in range(active_index - 1, -1, -1):
        if index >= len(self.vars):
            continue
        pos = self._exact_reference_position(self.vars[index].get())
        if pos is not None:
            previous_anchor = (index, pos)
            break
    for index in range(active_index + 1, len(self.vars)):
        pos = self._exact_reference_position(self.vars[index].get())
        if pos is not None:
            next_anchor = (index, pos)
            break

    if previous_anchor and next_anchor:
        prev_i, prev_pos = previous_anchor
        next_i, next_pos = next_anchor
        prev_estimate = prev_pos + (active_index - prev_i)
        next_estimate = next_pos - (next_i - active_index)
        if prev_pos < next_pos:
            target = round((prev_estimate + next_estimate) / 2)
            return max(prev_pos, min(next_pos, target))
        # If the two anchors conflict, the preceding verified entry is the
        # more natural typing direction and therefore wins.
        return prev_estimate
    if previous_anchor:
        prev_i, prev_pos = previous_anchor
        return prev_pos + (active_index - prev_i)
    if next_anchor:
        next_i, next_pos = next_anchor
        return next_pos - (next_i - active_index)

    # No usable surrounding word on this page. Use current content only now.
    current_exact = self._exact_reference_position(current_word)
    if current_exact is not None:
        return current_exact

    previous_page = self._previous_page_reference_target(active_index)
    if previous_page is not None:
        return previous_page

    # Last-resort fuzzy/collation position for a non-empty OCR result. Keep
    # the current virtual-list position for a blank field rather than jumping
    # back to the beginning of a 190k-word list.
    stripped = (current_word or "").strip()
    if stripped and self.sorted_word_keys:
        key = self._wordslist_lookup_key(stripped)
        pos = bisect.bisect_left(self.sorted_word_keys, key)
        pos = min(max(0, pos), len(self.sorted_word_indices) - 1)
        return self.sorted_word_indices[pos]
    if self.word_window_indices and self.word_highlight_index is not None:
        local = min(max(0, self.word_highlight_index), len(self.word_window_indices) - 1)
        return self.word_window_indices[local]
    return 0


def locate_reference_word(self, deps: ReviewReferenceDeps, word: str, active_index: int | None = None) -> None:
    if not self.parent.project or not self.parent.project.words:
        return
    words = self.parent.project.words
    index = self.active_index if active_index is None else int(active_index)
    target = self._infer_reference_target(index, word)
    target = max(0, min(int(target), len(words) - 1))

    if target not in self.word_window_indices:
        self._show_wordslist_window(target)
        return
    local = target - self.word_window_start
    self.word_highlight_index = local
    self._set_word_list_highlight(local)

