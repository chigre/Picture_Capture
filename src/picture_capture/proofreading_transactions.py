"""Conservative same-session, committed-PDIC undo/redo for review text edits.

Only a pure saved text-only transaction with exact Entry-object continuity and
unchanged sidecars can be reversed.  Candidate decisions, OCR cache, simplified
headwords, row additions/deletions and cross-page changes are NEVER inferred or
silently reverted.  Disk state is validated before writing; UI state changes
only after atomic PDIC publication.  No on-disk history, training or schema.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import os
import tempfile
from typing import Any

from .formats import pdic_path, read_pdic
from .project_storage import note_page_artifact_edit, simplified_review_path_for_image
from .proofreading_events import sha256_file


@dataclass(frozen=True)
class SavedSnapshot:
    page: Path
    image_sha: str
    # Entry object references ensure identity survives sorting. No row indexes.
    entries: tuple[tuple[Any, str, int, int], ...]
    pdic_bytes: bytes
    manual_bytes: bytes | None
    simplified_bytes: bytes | None
    ocr_bytes: bytes | None
    candidates: tuple[tuple[str, str], ...]

    def rows(self) -> dict[int, tuple[Any, str, int, int]]:
        return {id(record[0]): record for record in self.entries}


@dataclass(frozen=True)
class SavedEdit:
    before: SavedSnapshot
    after: SavedSnapshot


def _bytes_or_absent(path: Path | None) -> bytes | None:
    if path is None:
        return None
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        return None


def snapshot_review(review: Any) -> SavedSnapshot | None:
    """Capture an exact committed page; refuse dirty shared model and OCR owners."""
    app = review.parent
    page = getattr(app, "current_page", None)
    if (page is None or getattr(app, "project", None) is None
            or getattr(review, "_filter_rows_active", False)
            or getattr(review, "_rendered_page_stem", "") != page.stem
            or getattr(app, "_batch_active", False)
            or getattr(app, "_pending_manual_override_payload", None) is not None
            or getattr(app.settings, "proofreading_event_capture", False)):
        return None
    try:
        pdic = pdic_path(page)
        digest = sha256_file(pdic)
        if digest is None:
            return None
        raw = pdic.read_bytes()
        if sha256_file(pdic) != digest:
            return None
        ordered = tuple(
            (entry, str(entry.word), int(entry.x), int(entry.y))
            for entry in app.entries
        )
        from_disk = Counter(
            (str(e.word), int(e.x), int(e.y)) for e in read_pdic(pdic)
        )
        from_live = Counter((word, x, y) for _, word, x, y in ordered)
        if (not ordered or len({(x, y) for _, _, x, y in ordered}) != len(ordered)
                or from_disk != from_live):
            return None
        bound = review._bound_row_entries()
        if {id(e) for e in bound} != {id(e) for e in app.entries}:
            return None
        manual_path = app._manual_selection_path() if callable(
            getattr(app, "_manual_selection_path", None)
        ) else None
        ocr_path = app._paddle_cache_path() if callable(
            getattr(app, "_paddle_cache_path", None)
        ) else None
        candidates = tuple(sorted(
            (str(c.get("candidate_id", "")), repr(c))
            for c in getattr(app, "ocr_review_candidates", ())
            if isinstance(c, dict)
        ))
        return SavedSnapshot(
            page=page, image_sha=sha256_file(page) or "",
            entries=ordered, pdic_bytes=raw,
            manual_bytes=_bytes_or_absent(manual_path),
            simplified_bytes=_bytes_or_absent(simplified_review_path_for_image(page)),
            ocr_bytes=_bytes_or_absent(ocr_path), candidates=candidates,
        )
    except (OSError, ValueError, TypeError):
        return None


def _pure_saved_words(before: SavedSnapshot, after: SavedSnapshot) -> bool:
    if (before.page != after.page or before.image_sha != after.image_sha
            or not before.image_sha or before.candidates != after.candidates
            or before.manual_bytes != after.manual_bytes
            or before.simplified_bytes != after.simplified_bytes
            or before.ocr_bytes != after.ocr_bytes
            or before.pdic_bytes == after.pdic_bytes):
        return False
    left, right = before.rows(), after.rows()
    if left.keys() != right.keys():
        return False
    changed = False
    for identifier, old in left.items():
        new = right[identifier]
        if old[0] is not new[0] or old[2:] != new[2:]:
            return False
        changed |= old[1] != new[1]
    return changed


def _atomic_bytes(path: Path, data: bytes) -> None:
    """Write one PDIC atomically. In-memory state is updated only after replace."""
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", delete=False, dir=path.parent, prefix=f".{path.name}.",
            suffix=".tmp",
        ) as stream:
            temp = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        note_page_artifact_edit(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


@dataclass
class ReviewSessionHistory:
    undo_stack: list[SavedEdit] = field(default_factory=list)
    redo_stack: list[SavedEdit] = field(default_factory=list)
    max_steps: int = 20

    def invalidate(self) -> None:
        self.undo_stack.clear()
        self.redo_stack.clear()

    def record(self, before: SavedSnapshot | None, after: SavedSnapshot | None) -> bool:
        if before is None or after is None or not _pure_saved_words(before, after):
            self.invalidate()
            return False
        # An unexpected intermediate edit breaks the contiguous session chain.
        if self.undo_stack and self.undo_stack[-1].after.pdic_bytes != before.pdic_bytes:
            self.invalidate()
        self.undo_stack.append(SavedEdit(before, after))
        del self.undo_stack[:-self.max_steps]
        self.redo_stack.clear()
        return True

    def _apply(self, review: Any, *, redo: bool) -> bool:
        stack = self.redo_stack if redo else self.undo_stack
        if not stack:
            return False
        frame = stack[-1]
        expected, target = (frame.before, frame.after) if redo else (frame.after, frame.before)
        current = snapshot_review(review)
        if current is None or not _same_live_state(current, expected):
            self.invalidate()
            return False
        # A pending widget edit must not be discarded by undo.
        for entry, var in zip(review._bound_row_entries(), review.vars):
            if var.get().strip() != entry.word:
                return False
        pdic = pdic_path(expected.page)
        try:
            _atomic_bytes(pdic, target.pdic_bytes)
        except OSError:
            # Atomic replacement failed: leave both memory and history intact.
            return False
        # No other persistence operation follows the atomic write. Shared
        # Entry identities remain valid; only their saved words are restored.
        for entry, word, _, _ in target.entries:
            entry.word = word
        for entry, var in zip(review._bound_row_entries(), review.vars):
            var.set(entry.word)
        stack.pop()
        (self.undo_stack if redo else self.redo_stack).append(frame)
        return True

    def undo(self, review: Any) -> bool:
        return self._apply(review, redo=False)

    def redo(self, review: Any) -> bool:
        return self._apply(review, redo=True)


def _same_live_state(current: SavedSnapshot, target: SavedSnapshot) -> bool:
    return (
        current.page == target.page
        and current.pdic_bytes == target.pdic_bytes
        and current.image_sha == target.image_sha
        and current.manual_bytes == target.manual_bytes
        and current.simplified_bytes == target.simplified_bytes
        and current.ocr_bytes == target.ocr_bytes
        and current.candidates == target.candidates
        and current.rows() == target.rows()
    )
