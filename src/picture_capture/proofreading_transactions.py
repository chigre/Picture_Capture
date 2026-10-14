"""Conservative same-session undo/redo of committed ReviewWindow edits.

No persisted user Undo history.  A short-lived, local write-ahead *recovery*
marker protects multi-file PDIC+simplified updates from crash or disk failure.
A pending recovery marker must be reconciled before reloading the page.
Candidate decisions, manual OCR overrides, image/geometry changes and unrelated
page changes are never inferred as undoable operations.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import base64
import json
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
    entries: tuple[tuple[Any, str, int, int], ...]
    pdic_bytes: bytes
    manual_bytes: bytes | None
    simplified_bytes: bytes | None
    ocr_bytes: bytes | None
    candidates: tuple[tuple[str, str], ...]

    def rows(self) -> dict[int, tuple[Any, str, int, int]]:
        return {id(item[0]): item for item in self.entries}


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
    """Require exact saved PDIC and object identities, no pending OCR owners."""
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
        if digest is None or _recovery_path(page).exists():
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
        manual_fn = getattr(app, "_manual_selection_path", None)
        ocr_fn = getattr(app, "_paddle_cache_path", None)
        candidates = tuple(sorted(
            (str(c.get("candidate_id", "")), repr(c))
            for c in getattr(app, "ocr_review_candidates", ())
            if isinstance(c, dict)
        ))
        return SavedSnapshot(
            page=page, image_sha=sha256_file(page) or "",
            entries=ordered, pdic_bytes=raw,
            manual_bytes=_bytes_or_absent(manual_fn() if callable(manual_fn) else None),
            simplified_bytes=_bytes_or_absent(simplified_review_path_for_image(page)),
            ocr_bytes=_bytes_or_absent(ocr_fn() if callable(ocr_fn) else None),
            candidates=candidates,
        )
    except (OSError, ValueError, TypeError):
        return None


def _undoable_committed_change(before: SavedSnapshot, after: SavedSnapshot) -> bool:
    if (before.page != after.page or not before.image_sha
            or before.image_sha != after.image_sha
            or before.candidates != after.candidates
            or before.manual_bytes != after.manual_bytes
            or before.ocr_bytes != after.ocr_bytes):
        return False
    left, right = before.rows(), after.rows()
    if left.keys() != right.keys():
        return False
    for identifier, old in left.items():
        new = right[identifier]
        if old[0] is not new[0] or old[2:] != new[2:]:
            return False
    # Both pure text and simplified text changes are user-owned in this open
    # review session; manual OCR override decisions are deliberately excluded.
    return (
        before.pdic_bytes != after.pdic_bytes
        or before.simplified_bytes != after.simplified_bytes
    )


def _atomic_bytes(path: Path, data: bytes) -> None:
    temp: Path | None = None
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            "wb", delete=False, dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp",
        ) as handle:
            temp = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        note_page_artifact_edit(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _publish(path: Path, data: bytes | None) -> None:
    if data is None:
        path.unlink(missing_ok=True)
        note_page_artifact_edit(path)
    else:
        _atomic_bytes(path, data)


def _recovery_path(page: Path) -> Path:
    return pdic_path(page).with_name(f".{pdic_path(page).name}.r3-inflight.json")


def _encode(data: bytes | None) -> str | None:
    return None if data is None else base64.b64encode(data).decode("ascii")


def _decode(value: Any) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid R3 recovery bytes")
    return base64.b64decode(value, validate=True)


def _stage_recovery(
    page: Path, changes: list[tuple[str, bytes | None, bytes | None]],
) -> Path:
    marker = _recovery_path(page)
    if marker.exists():
        raise RuntimeError("Unresolved R3 recovery marker; refusing new undo")
    doc = {
        "format": "picture_capture_r3_transient_recovery", "version": 1,
        "page": str(page.resolve()),
        "files": [
            {"role": role, "before": _encode(old), "after": _encode(new)}
            for role, old, new in changes
        ],
    }
    # The marker exists only during a multi-file commit and is deleted
    # immediately. It is NOT a persistent Undo/Redo journal.
    _atomic_bytes(marker, json.dumps(doc, ensure_ascii=False).encode("utf-8"))
    return marker


def _verified_recovery(
    page: Path,
) -> tuple[Path, list[tuple[Path, bytes | None, bytes | None]]] | None:
    marker = _recovery_path(page)
    if not marker.is_file():
        return None
    doc = json.loads(marker.read_text(encoding="utf-8"))
    if (not isinstance(doc, dict)
            or doc.get("format") != "picture_capture_r3_transient_recovery"
            or doc.get("version") != 1 or doc.get("page") != str(page.resolve())):
        raise ValueError("R3 recovery marker does not match current page")
    values = doc.get("files")
    if not isinstance(values, list) or not values:
        raise ValueError("R3 recovery marker has no files")
    known = {"pdic": pdic_path(page), "simplified": simplified_review_path_for_image(page)}
    found = set()
    result = []
    for row in values:
        if not isinstance(row, dict) or row.get("role") not in known:
            raise ValueError("R3 recovery contains unknown file")
        role = row["role"]
        if role in found:
            raise ValueError("R3 recovery contains duplicate file")
        found.add(role)
        result.append((known[role], _decode(row.get("before")), _decode(row.get("after"))))
    return marker, result


def recover_pending_for_page(page: Path) -> bool:
    """Reconcile an interrupted multi-file operation before loading any PDIC.

    All old/new bytes are explicitly embedded in a *temporary* local marker.
    A complete after-state wins; a mixed old/new state is rolled back to the
    before-state. Unexpected third-party modification requires manual action.
    """
    pending = _verified_recovery(page)
    if pending is None:
        return True
    marker, items = pending
    observed = [_bytes_or_absent(path) for path, _, _ in items]
    for current, (_, before, after) in zip(observed, items):
        if current not in (before, after):
            return False
    if observed != [new for _, _, new in items]:
        for path, before, _ in items:
            _publish(path, before)
    marker.unlink()
    return True


def _publish_restored_snapshot(
    expected: SavedSnapshot, target: SavedSnapshot,
) -> bool:
    page = expected.page
    changes = []
    if expected.pdic_bytes != target.pdic_bytes:
        changes.append(("pdic", expected.pdic_bytes, target.pdic_bytes))
    if expected.simplified_bytes != target.simplified_bytes:
        changes.append(("simplified", expected.simplified_bytes, target.simplified_bytes))
    if not changes:
        return False
    if (not _undoable_committed_change(expected, target)
            or _recovery_path(page).exists()):
        return False
    # One-file restore is already atomic. Two files require short-lived
    # write-ahead recovery so crash/restart cannot silently mis-pair them.
    if len(changes) == 1:
        role, _, data = changes[0]
        _publish(pdic_path(page) if role == "pdic" else simplified_review_path_for_image(page), data)
        return True
    marker = _stage_recovery(page, changes)
    try:
        for role, _, data in changes:
            _publish(pdic_path(page) if role == "pdic" else simplified_review_path_for_image(page), data)
    except OSError:
        # If any write failed, revert all under the same recovery marker.
        # An interrupted rollback keeps marker so next page load can recover.
        recover_pending_for_page(page)
        raise
    marker.unlink()
    return True


def _same_live_state(current: SavedSnapshot, expected: SavedSnapshot) -> bool:
    return (
        current.page == expected.page
        and current.pdic_bytes == expected.pdic_bytes
        and current.image_sha == expected.image_sha
        and current.manual_bytes == expected.manual_bytes
        and current.simplified_bytes == expected.simplified_bytes
        and current.ocr_bytes == expected.ocr_bytes
        and current.candidates == expected.candidates
        and current.rows() == expected.rows()
    )


@dataclass
class ReviewSessionHistory:
    undo_stack: list[SavedEdit] = field(default_factory=list)
    redo_stack: list[SavedEdit] = field(default_factory=list)
    max_steps: int = 20

    def invalidate(self) -> None:
        self.undo_stack.clear()
        self.redo_stack.clear()

    def record(self, before: SavedSnapshot | None, after: SavedSnapshot | None) -> bool:
        if before is None or after is None or not _undoable_committed_change(before, after):
            self.invalidate()
            return False
        if self.undo_stack and (
            self.undo_stack[-1].after.pdic_bytes != before.pdic_bytes
            or self.undo_stack[-1].after.simplified_bytes != before.simplified_bytes
        ):
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
        if expected.page.stem in getattr(review, "_simplified_dirty_pages", set()):
            return False
        for entry, var in zip(review._bound_row_entries(), review.vars):
            if var.get().strip() != entry.word:
                return False
        try:
            if not _publish_restored_snapshot(expected, target):
                return False
        except (OSError, RuntimeError, ValueError):
            return False
        # Disk commit succeeded; only now restore shared Entry and widgets.
        for entry, word, _, _ in target.entries:
            entry.word = word
        for entry, var in zip(review._bound_row_entries(), review.vars):
            var.set(entry.word)
        cache = getattr(review, "_simplified_page_cache", None)
        if isinstance(cache, dict):
            cache.pop(expected.page.stem, None)
        getattr(review, "_simplified_dirty_pages", set()).discard(expected.page.stem)
        stack.pop()
        (self.undo_stack if redo else self.redo_stack).append(frame)
        return True

    def undo(self, review: Any) -> bool:
        return self._apply(review, redo=False)

    def redo(self, review: Any) -> bool:
        return self._apply(review, redo=True)
