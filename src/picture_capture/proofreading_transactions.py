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
from .project_storage import (
    note_page_artifact_edit,
    page_sections_read_path_for_image,
    profile_path,
    simplified_review_path_for_image,
)
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
    # A frozen ownership fingerprint, not a late read from mutable Entry refs.
    # Without this a user/OCR rerun could attach a candidate_id after record()
    # and an old Undo would treat that candidate-owned row as plain text.
    owner_ids: tuple[tuple[int, str], ...] = ()
    manual_path: Path | None = None
    ocr_path: Path | None = None
    section_path: Path | None = None
    section_bytes: bytes | None = None
    profile_path: Path | None = None
    profile_bytes: bytes | None = None

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


def snapshot_review(review: Any, *, allow_unbound: bool = False, allow_evidence: bool = False) -> SavedSnapshot | None:
    """Require exact saved PDIC and object identities, no pending OCR owners."""
    app = review.parent
    page = getattr(app, "current_page", None)
    if (page is None or getattr(app, "project", None) is None
            or getattr(review, "_filter_rows_active", False)
            or getattr(review, "_rendered_page_stem", "") != page.stem
            or getattr(app, "_batch_active", False)
            or getattr(app, "_pending_manual_override_payload", None) is not None
            or (getattr(app.settings, "proofreading_event_capture", False) and not allow_evidence)):
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
        if (len({(x, y) for _, _, x, y in ordered}) != len(ordered)
                or from_disk != from_live):
            return None
        if not allow_unbound:
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
        manual_path = manual_fn() if callable(manual_fn) else None
        ocr_path = ocr_fn() if callable(ocr_fn) else None
        section_path = page_sections_read_path_for_image(page)
        profile_file = profile_path(app.project.root)
        return SavedSnapshot(
            page=page, image_sha=sha256_file(page) or "",
            entries=ordered, pdic_bytes=raw,
            manual_bytes=_bytes_or_absent(manual_path),
            simplified_bytes=_bytes_or_absent(simplified_review_path_for_image(page)),
            ocr_bytes=_bytes_or_absent(ocr_path),
            candidates=candidates,
            owner_ids=tuple(sorted(
                (id(entry), str(getattr(entry, "candidate_id", "") or ""))
                for entry in app.entries
            )),
            manual_path=manual_path, ocr_path=ocr_path,
            section_path=section_path, section_bytes=_bytes_or_absent(section_path),
            profile_path=profile_file, profile_bytes=_bytes_or_absent(profile_file),
        )
    except (OSError, ValueError, TypeError):
        return None


def _undoable_committed_change(
    before: SavedSnapshot, after: SavedSnapshot, *, allow_reversal: bool = False,
) -> bool:
    if (before.page != after.page or not before.image_sha
            or before.image_sha != after.image_sha
            or before.candidates != after.candidates
            or before.manual_bytes != after.manual_bytes
            or before.ocr_bytes != after.ocr_bytes
            or before.manual_path != after.manual_path
            or before.ocr_path != after.ocr_path
            or before.section_path != after.section_path
            or before.section_bytes != after.section_bytes
            or before.profile_path != after.profile_path
            or before.profile_bytes != after.profile_bytes):
        return False
    left, right = before.rows(), after.rows()
    left_owners, right_owners = dict(before.owner_ids), dict(after.owner_ids)
    if (set(left_owners) != set(left) or set(right_owners) != set(right)
            or any(left_owners[key] != right_owners[key]
                   for key in left.keys() & right.keys())):
        return False
    removed = left.keys() - right.keys()
    added = right.keys() - left.keys()
    # A single direct UI-owned deletion (or its redo reversal) can be restored
    # by the same file transaction. Compound insertions/multiple deletions
    # remain unknown until they have separately-owned operations.
    if len(removed) + len(added) > 1:
        return False
    # Only an explicit ReviewWindow DELETE can own disappearance of one row.
    # A newly appearing row during a save has no R3 UI add-operation owner.
    # The reverse direction is used exclusively to replay a stored delete.
    if added and not allow_reversal:
        return False
    lost_or_added = next(iter(removed or added), None)
    if lost_or_added is not None:
        orphan = (left if removed else right)[lost_or_added][0]
        if (left_owners if removed else right_owners).get(lost_or_added):
            return False
    word_changed = False
    for identifier in left.keys() & right.keys():
        old, new = left[identifier], right[identifier]
        if old[0] is not new[0] or old[2:] != new[2:]:
            return False
        if old[1] != new[1]:
            if left_owners.get(identifier):
                return False
            word_changed = True
    if before.pdic_bytes != after.pdic_bytes and not (word_changed or lost_or_added is not None):
        return False
    return word_changed or lost_or_added is not None or before.simplified_bytes != after.simplified_bytes


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
        # The file is already committed: cache bookkeeping must never turn a
        # successful replace into a reported write failure with stale UI.
        try:
            note_page_artifact_edit(path)
        except OSError:
            pass
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _publish(path: Path, data: bytes | None) -> None:
    if data is None:
        path.unlink(missing_ok=True)
        # Deletion already committed; nonessential cache bookkeeping must
        # never turn it into a false transaction failure.
        try:
            note_page_artifact_edit(path)
        except OSError:
            pass
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


def _valid_manual_path(page: Path, path: Path | None) -> bool:
    return bool(
        path is not None
        and Path(path).name == f"{page.stem}_manual_selection.json"
        and Path(path).parent.name.lower() == "paddleocr"
    )


def _stage_recovery(
    page: Path, changes: list[tuple[str, bytes | None, bytes | None]],
    *, manual_path: Path | None = None, rollback_required: bool = False,
) -> Path:
    marker = _recovery_path(page)
    if marker.exists():
        raise RuntimeError("Unresolved R3 recovery marker; refusing new undo")
    roles = [role for role, _, _ in changes]
    if len(roles) != len(set(roles)) or not roles or not set(roles) <= {"pdic", "simplified", "manual"}:
        raise ValueError("Invalid R3 recovery roles")
    owns_manual = "manual" in roles
    if owns_manual and not _valid_manual_path(page, manual_path):
        raise ValueError("Candidate manual-selection recovery path is not owned by this page")
    doc = {
        "format": "picture_capture_r3_transient_recovery",
        "version": 2 if owns_manual else 1,
        "page": str(page.resolve()),
        "rollback_required": rollback_required,
        "files": [
            {"role": role, "before": _encode(old), "after": _encode(new)}
            for role, old, new in changes
        ],
    }
    if owns_manual:
        # Version 2 is explicitly bound to the page's expected OCR override
        # location, never an arbitrary path from an untrusted recovery marker.
        doc["manual_path"] = str(Path(manual_path).resolve())
    # The marker exists only during a multi-file commit and is deleted
    # immediately. It is NOT a persistent Undo/Redo journal.
    marker_bytes = json.dumps(doc, ensure_ascii=False).encode("utf-8")
    _atomic_bytes(marker, marker_bytes)
    # Never write owned page files unless the rollback intent is durable.
    if _bytes_or_absent(marker) != marker_bytes:
        raise RuntimeError("R3 recovery marker readback mismatch")
    return marker


def _verified_recovery(
    page: Path, *, manual_path: Path | None = None,
) -> tuple[Path, list[tuple[Path, bytes | None, bytes | None]]] | None:
    marker = _recovery_path(page)
    if not marker.is_file():
        return None
    doc = json.loads(marker.read_text(encoding="utf-8"))
    if (not isinstance(doc, dict)
            or doc.get("format") != "picture_capture_r3_transient_recovery"
            or doc.get("version") not in {1, 2}
            or doc.get("page") != str(page.resolve())):
        raise ValueError("R3 recovery marker does not match current page")
    values = doc.get("files")
    if not isinstance(values, list) or not values:
        raise ValueError("R3 recovery marker has no files")
    known = {"pdic": pdic_path(page), "simplified": simplified_review_path_for_image(page)}
    if doc["version"] == 2:
        if (not _valid_manual_path(page, manual_path)
                or doc.get("manual_path") != str(Path(manual_path).resolve())):
            raise ValueError("R3 manual-selection recovery requires trusted project path")
        known["manual"] = Path(manual_path)
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
    if ("manual" in found) != (doc["version"] == 2):
        raise ValueError("R3 recovery marker/manual path schema mismatch")
    if not isinstance(doc.get("rollback_required", False), bool):
        raise ValueError("Invalid R3 recovery rollback policy")
    return marker, result


def recover_pending_for_page(page: Path, *, manual_path: Path | None = None) -> bool:
    """Reconcile an interrupted multi-file operation before loading any PDIC.

    All old/new bytes are explicitly embedded in a *temporary* local marker.
    A complete after-state wins; a mixed old/new state is rolled back to the
    before-state. Unexpected third-party modification requires manual action.
    """
    pending = _verified_recovery(page, manual_path=manual_path)
    if pending is None:
        return True
    marker, items = pending
    observed = [_bytes_or_absent(path) for path, _, _ in items]
    for current, (_, before, after) in zip(observed, items):
        if current not in (before, after):
            return False
    # If a live GUI action reported failure, even a complete after-state
    # must be restored before the page can be reopened.
    rollback_required = json.loads(marker.read_text(encoding="utf-8")).get(
        "rollback_required", False)
    if rollback_required or observed != [new for _, _, new in items]:
        for path, before, _ in items:
            _publish(path, before)
        # A silently skipped rollback must retain the marker and quarantine
        # page reloads rather than exposing a mixed persisted state.
        if any(_bytes_or_absent(path) != before for path, before, _ in items):
            return False
    marker.unlink()
    # A silent no-op unlink leaves the page quarantined.
    return not marker.exists()


def _rollback_failed_publish(
    page: Path, *, manual_path: Path | None = None,
) -> bool:
    """Restore exact before-state on a reported live action failure.

    The marker is left in place if rollback is not provably complete.
    This recovery contract is not cross-file OS-level atomicity.
    """
    pending = _verified_recovery(page, manual_path=manual_path)
    if pending is None:
        return False
    marker, items = pending
    raw = marker.read_bytes()
    doc = json.loads(raw)
    if marker.read_bytes() != raw:
        return False
    if doc.get("rollback_required") is not True:
        doc["rollback_required"] = True
        policy = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        _atomic_bytes(marker, policy)
        if _bytes_or_absent(marker) != policy:
            return False
    if any(_bytes_or_absent(path) not in (before, after)
           for path, before, after in items):
        return False
    for path, before, after in items:
        current = _bytes_or_absent(path)
        if current == before:
            continue
        if current != after:
            return False
        try:
            _publish(path, before)
        except (OSError, RuntimeError, ValueError):
            # The write may have succeeded immediately before raising.
            pass
    if any(_bytes_or_absent(path) != before for path, before, _ in items):
        return False
    try:
        marker.unlink()
    except OSError:
        return False
    return not marker.exists()


def publish_owned_review_bundle(
    expected: SavedSnapshot,
    *, pdic_bytes: bytes,
    manual_bytes: bytes,
    simplified_bytes: bytes | None,
) -> bool:
    """Publish a future operation-owned candidate edit as one recoverable unit.

    Pure persistence boundary: does not modify Entry, candidate checkbox or
    ReviewWindow. Callers must own a unique candidate and validate its intended
    content before supplying the exact target bytes. This function alone does
    not enable candidate Undo/Redo.
    """
    page = expected.page
    manual_path = expected.manual_path
    if not _valid_manual_path(page, manual_path):
        return False
    changes = []
    for role, old, new in (
        ("pdic", expected.pdic_bytes, pdic_bytes),
        ("manual", expected.manual_bytes, manual_bytes),
        ("simplified", expected.simplified_bytes, simplified_bytes),
    ):
        if old != new:
            changes.append((role, old, new))
    if not (len(changes) >= 2 and any(role == "manual" for role, _, _ in changes)
            and any(role == "pdic" for role, _, _ in changes)
            and not _recovery_path(page).exists()):
        return False

    def source_unchanged() -> bool:
        return bool(
            sha256_file(page) == expected.image_sha
            and _bytes_or_absent(pdic_path(page)) == expected.pdic_bytes
            and _bytes_or_absent(manual_path) == expected.manual_bytes
            and _bytes_or_absent(simplified_review_path_for_image(page))
                == expected.simplified_bytes
            and _bytes_or_absent(expected.ocr_path) == expected.ocr_bytes
            and page_sections_read_path_for_image(page) == expected.section_path
            and _bytes_or_absent(expected.section_path) == expected.section_bytes
            and _bytes_or_absent(expected.profile_path) == expected.profile_bytes
        )
    if not source_unchanged():
        return False
    paths = {
        "pdic": pdic_path(page),
        "manual": manual_path,
        "simplified": simplified_review_path_for_image(page),
    }
    marker = _stage_recovery(page, changes, manual_path=manual_path, rollback_required=True)
    if not source_unchanged():
        marker.unlink()
        return False
    try:
        for role, _, data in changes:
            _publish(paths[role], data)
        # Do not advance Entry/candidate/Tk state on a silent storage no-op.
        if any(_bytes_or_absent(paths[role]) != data
               for role, _, data in changes):
            raise RuntimeError("R3 bundle post-publication bytes mismatch")
        try:
            marker.unlink()
        except OSError:
            if marker.exists():
                raise
        if marker.exists():
            raise RuntimeError("R3 bundle recovery marker cleanup did not persist")
    except (OSError, RuntimeError, ValueError):
        # Report failure only after attempting exact before-state rollback.
        # Retain the marker whenever the disk state cannot be proven safe.
        try:
            _rollback_failed_publish(page, manual_path=manual_path)
        except (OSError, RuntimeError, ValueError):
            pass
        raise
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
    if (not _undoable_committed_change(expected, target, allow_reversal=True)
            or _recovery_path(page).exists()):
        return False
    # Revalidate exact bytes immediately before staging. An intervening writer
    # cannot be silently overwritten by a stale Undo snapshot.
    if (sha256_file(page) != expected.image_sha
            or _bytes_or_absent(pdic_path(page)) != expected.pdic_bytes
            or _bytes_or_absent(simplified_review_path_for_image(page))
               != expected.simplified_bytes
            # OCR and manual-selection are read-only dependencies for the
            # original R3 safe scope. Recheck immediately before publication;
            # snapshot-time checks alone leave a TOCTOU window.
            or _bytes_or_absent(expected.manual_path) != expected.manual_bytes
            or _bytes_or_absent(expected.ocr_path) != expected.ocr_bytes
            or page_sections_read_path_for_image(page) != expected.section_path
            or _bytes_or_absent(expected.section_path) != expected.section_bytes
            or _bytes_or_absent(expected.profile_path) != expected.profile_bytes):
        return False
    # Even single-file replacement can land and then raise; the GUI cannot
    # advance until success is proven, so stage both single and multi-file edits.
    marker = _stage_recovery(page, changes, rollback_required=True)
    try:
        for role, _, data in changes:
            path = (pdic_path(page) if role == "pdic"
                    else simplified_review_path_for_image(page))
            _publish(path, data)
        if any(
            _bytes_or_absent(pdic_path(page) if role == "pdic"
                             else simplified_review_path_for_image(page)) != data
            for role, _, data in changes
        ):
            raise RuntimeError("R3 restore bytes mismatch")
        try:
            marker.unlink()
        except OSError:
            if marker.exists():
                raise
        if marker.exists():
            raise RuntimeError("R3 restore recovery marker cleanup did not persist")
    except (OSError, RuntimeError, ValueError):
        try:
            _rollback_failed_publish(page)
        except (OSError, RuntimeError, ValueError):
            pass
        raise
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
        and current.owner_ids == expected.owner_ids
        and current.manual_path == expected.manual_path
        and current.ocr_path == expected.ocr_path
        and current.section_path == expected.section_path
        and current.section_bytes == expected.section_bytes
        and current.profile_path == expected.profile_path
        and current.profile_bytes == expected.profile_bytes
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
            or self.undo_stack[-1].after.manual_bytes != before.manual_bytes
            or self.undo_stack[-1].after.ocr_bytes != before.ocr_bytes
            or self.undo_stack[-1].after.candidates != before.candidates
            or self.undo_stack[-1].after.owner_ids != before.owner_ids
            or self.undo_stack[-1].after.image_sha != before.image_sha
            or self.undo_stack[-1].after.section_bytes != before.section_bytes
            or self.undo_stack[-1].after.profile_bytes != before.profile_bytes
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
        if current is None:
            # A genuine changed source is stale forever and must invalidate
            # history; only unchanged saved bytes with temporarily stale Tk
            # bindings are allowed to retry after async repaint.
            page = getattr(review.parent, "current_page", None)
            if (
                page != expected.page
                or sha256_file(expected.page) != expected.image_sha
                or _bytes_or_absent(pdic_path(expected.page)) != expected.pdic_bytes
                or _bytes_or_absent(simplified_review_path_for_image(expected.page))
                   != expected.simplified_bytes
            ):
                self.invalidate()
            return False
        if not _same_live_state(current, expected):
            self.invalidate()
            return False
        if expected.page.stem in getattr(review, "_simplified_dirty_pages", set()):
            return False
        bound = review._bound_row_entries()
        if len(bound) != len(review.vars):
            return False
        for entry, var in zip(bound, review.vars):
            if var.get().strip() != entry.word:
                return False
        try:
            if not _publish_restored_snapshot(expected, target):
                return False
        except (OSError, RuntimeError, ValueError):
            return False
        # Block obsolete simplified Tk bindings until render_rows rebinds them.
        review.__dict__["_r3_simplified_capture_blocked"] = True
        # Disk commit succeeded; only now restore model membership AND words
        # to the original Entry instances, never by current row index.
        review.parent.entries[:] = [entry for entry, _, _, _ in target.entries]
        for entry, word, _, _ in target.entries:
            entry.word = word
        current_words = {id(entry): word for entry, word, _, _ in target.entries}
        for entry, var in zip(review._bound_row_entries(), review.vars):
            if id(entry) in current_words:
                var.set(current_words[id(entry)])
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
