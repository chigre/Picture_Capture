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
import stat
import tempfile
from typing import Any

from ..io.formats import pdic_path, read_pdic
from ..persistence.project_storage import (
    note_page_artifact_edit,
    page_sections_read_path_for_image,
    profile_path,
    simplified_review_path_for_image,
)
from .events import sha256_file


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
        if digest is None or _marker_present(_recovery_path(page)):
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


def _marker_present(marker: Path) -> bool:
    """Treat even dangling symlinks as pending R3 ownership.

    Path.exists()/is_file() follow links, so both can return False for a
    broken symlink. Only a genuinely absent directory entry means no journal.
    Unreadable status must propagate and stop an unsafe page operation.
    """
    try:
        marker.lstat()
    except FileNotFoundError:
        return False
    return True


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


def _create_exclusive_recovery_marker(marker: Path, data: bytes) -> None:
    """Claim the recovery journal pathname once, without replacing a peer.

    O_EXCL|O_CREAT makes marker ownership exclusive on cooperating local
    filesystems, including Windows. A crash during writing can leave a
    partial/empty marker: retain it to quarantine the page, never infer that
    it is safe to start another transaction. The reader will reject invalid
    JSON instead of deleting the marker or guessing rollback bytes.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(marker, flags, 0o600)
    except FileExistsError as conflict:
        raise RuntimeError("Unresolved R3 recovery marker; refusing new undo") from conflict
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _stage_recovery(
    page: Path, changes: list[tuple[str, bytes | None, bytes | None]],
    *, manual_path: Path | None = None, rollback_required: bool = False,
) -> Path:
    marker = _recovery_path(page)
    if _marker_present(marker):
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
    # Do not os.replace() a journal after a non-atomic existence check:
    # two R3 writers could otherwise each replace the other's recovery plan.
    _create_exclusive_recovery_marker(marker, marker_bytes)
    # Never write owned page files unless the rollback intent is durable.
    if _bytes_or_absent(marker) != marker_bytes:
        raise RuntimeError("R3 recovery marker readback mismatch")
    return marker


def _verified_recovery(
    page: Path, *, manual_path: Path | None = None,
) -> tuple[Path, list[tuple[Path, bytes | None, bytes | None]], bool, bytes] | None:
    marker = _recovery_path(page)
    try:
        marker_mode = marker.lstat().st_mode
    except FileNotFoundError:
        return None
    # A directory or symbolic link is an unresolved/invalid transaction
    # marker, *not* proof that there is no transaction. Never follow a
    # link outside the project to obtain recovery bytes.
    if not stat.S_ISREG(marker_mode):
        raise ValueError("R3 recovery marker is not a regular file; manual recovery required")
    raw = marker.read_bytes()
    doc = json.loads(raw)
    if (not isinstance(doc, dict)
            or doc.get("format") != "picture_capture_r3_transient_recovery"
            or type(doc.get("version")) is not int
            or doc["version"] not in {1, 2}
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
        # A torn/hand-edited journal must not reinterpret a missing before
        # or after field as an intentional deletion (JSON null).
        if not {"role", "before", "after"} <= row.keys():
            raise ValueError("R3 recovery contains incomplete file record")
        role = row["role"]
        if role in found:
            raise ValueError("R3 recovery contains duplicate file")
        found.add(role)
        result.append((known[role], _decode(row.get("before")), _decode(row.get("after"))))
    if ("manual" in found) != (doc["version"] == 2):
        raise ValueError("R3 recovery marker/manual path schema mismatch")
    if not isinstance(doc.get("rollback_required", False), bool):
        raise ValueError("Invalid R3 recovery rollback policy")
    return marker, result, doc.get("rollback_required", False), raw


def _recovery_marker_unchanged(marker: Path, raw: bytes) -> bool:
    """Optimistic journal identity gate, including an unsafe symlink swap.

    We must never use a new journal's rollback policy with the old journal's
    file rows. This cannot replace a cross-process lock or atomic file CAS.
    """
    try:
        if not stat.S_ISREG(marker.lstat().st_mode):
            return False
        return marker.read_bytes() == raw
    except FileNotFoundError:
        return False


def recover_pending_for_page(page: Path, *, manual_path: Path | None = None) -> bool:
    """Reconcile an interrupted multi-file operation before loading any PDIC.

    All old/new bytes are explicitly embedded in a *temporary* local marker.
    A complete after-state wins; a mixed old/new state is rolled back to the
    before-state. Unexpected third-party modification requires manual action.
    """
    pending = _verified_recovery(page, manual_path=manual_path)
    if pending is None:
        return True
    marker, items, rollback_required, raw = pending
    if not _recovery_marker_unchanged(marker, raw):
        return False
    observed = [_bytes_or_absent(path) for path, _, _ in items]
    for current, (_, before, after) in zip(observed, items):
        if current not in (before, after):
            return False
    # The rollback policy and owned paths come from the SAME parsed bytes.
    # A replacement journal detected after parsing quarantines the page.
    if not _recovery_marker_unchanged(marker, raw):
        return False
    if rollback_required or observed != [new for _, _, new in items]:
        for path, before, after in items:
            if not _recovery_marker_unchanged(marker, raw):
                return False
            # Recovery is not exclusive: a proofreader may update an owned
            # file after the initial snapshot, including between two rollbacks.
            # Never overwrite a byte version that is neither the staged old
            # nor the staged new state. Avoid rewriting already-restored files.
            current = _bytes_or_absent(path)
            if current == before:
                continue
            if current != after:
                return False
            _publish(path, before)
            if not _recovery_marker_unchanged(marker, raw):
                return False
            if _bytes_or_absent(path) != before:
                return False
        # A silently skipped rollback or a late external edit must retain the
        # recovery marker and quarantine page reloads.
        if any(_bytes_or_absent(path) != before for path, before, _ in items):
            return False
    else:
        # Even a complete after-state can be externally edited after the
        # initial observation. Do not discard the recovery journal without
        # confirming every exact target byte value immediately beforehand.
        if any(_bytes_or_absent(path) != after for path, _, after in items):
            return False
    if not _recovery_marker_unchanged(marker, raw):
        return False
    marker.unlink()
    # A silent no-op unlink leaves the page quarantined.
    return not _marker_present(marker)


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
    marker, items, rollback_required, raw = pending
    if not _recovery_marker_unchanged(marker, raw):
        return False
    if not rollback_required:
        # Keep legacy false-policy recovery markers compatible, but do not
        # re-publish their intent when a peer changed the journal after parse.
        doc = json.loads(raw)
        doc["rollback_required"] = True
        policy = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        if not _recovery_marker_unchanged(marker, raw):
            return False
        _atomic_bytes(marker, policy)
        raw = policy
        if not _recovery_marker_unchanged(marker, raw):
            return False
    if any(_bytes_or_absent(path) not in (before, after)
           for path, before, after in items):
        return False
    for path, before, after in items:
        if not _recovery_marker_unchanged(marker, raw):
            return False
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
        if not _recovery_marker_unchanged(marker, raw):
            return False
    if any(_bytes_or_absent(path) != before for path, before, _ in items):
        return False
    if not _recovery_marker_unchanged(marker, raw):
        return False
    try:
        marker.unlink()
    except OSError:
        return False
    return not _marker_present(marker)


def _snapshot_sources_match(
    expected: SavedSnapshot, *, published: dict[str, bytes | None] | None = None,
) -> bool:
    """Recheck every owned file and read-only source at a publication boundary.

    Published roles are the *only* permitted changes from the frozen snapshot.
    This is optimistic protection, not an OS-level cross-file atomic CAS.
    """
    published = published or {}
    page = expected.page
    return bool(
        sha256_file(page) == expected.image_sha
        and _bytes_or_absent(pdic_path(page))
            == published.get("pdic", expected.pdic_bytes)
        and _bytes_or_absent(simplified_review_path_for_image(page))
            == published.get("simplified", expected.simplified_bytes)
        and _bytes_or_absent(expected.manual_path)
            == published.get("manual", expected.manual_bytes)
        and _bytes_or_absent(expected.ocr_path) == expected.ocr_bytes
        and page_sections_read_path_for_image(page) == expected.section_path
        and _bytes_or_absent(expected.section_path) == expected.section_bytes
        and _bytes_or_absent(expected.profile_path) == expected.profile_bytes
    )


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
            and not _marker_present(_recovery_path(page))):
        return False

    def source_unchanged(published: dict[str, bytes | None] | None = None) -> bool:
        return _snapshot_sources_match(expected, published=published)

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
        published: dict[str, bytes | None] = {}
        for role, _, data in changes:
            # A human may edit PDIC/manual/simplified or a read-only OCR
            # dependency after the journal was staged or a prior role landed.
            if not source_unchanged(published):
                raise RuntimeError("R3 bundle source drift before next file publication")
            _publish(paths[role], data)
            published[role] = data
        # Also verify untouched dependencies after the final replacement.
        if not source_unchanged(published):
            raise RuntimeError("R3 bundle post-publication source drift")
        try:
            marker.unlink()
        except OSError:
            if _marker_present(marker):
                raise
        if _marker_present(marker):
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
            or _marker_present(_recovery_path(page))):
        return False
    # Revalidate exact bytes immediately before staging. An intervening writer
    # cannot be silently overwritten by a stale Undo snapshot.
    if not _snapshot_sources_match(expected):
        return False
    # Even single-file replacement can land and then raise; the GUI cannot
    # advance until success is proven, so stage both single and multi-file edits.
    marker = _stage_recovery(page, changes, rollback_required=True)
    try:
        published: dict[str, bytes | None] = {}
        # The earlier preflight is not enough: staging the recovery marker
        # performs I/O, during which another proofreader can change sources.
        for role, _, data in changes:
            if not _snapshot_sources_match(expected, published=published):
                raise RuntimeError("R3 restore source drift after journal staging")
            path = (pdic_path(page) if role == "pdic"
                    else simplified_review_path_for_image(page))
            _publish(path, data)
            published[role] = data
        if not _snapshot_sources_match(expected, published=published):
            raise RuntimeError("R3 restore post-publication source drift")
        try:
            marker.unlink()
        except OSError:
            if _marker_present(marker):
                raise
        if _marker_present(marker):
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
        # Chaining committed saves requires the complete frozen ownership
        # of the previous post-state, not just equal PDIC/sidecar contents.
        # A page or manual/OCR/SECTION/Profile *path* may change while bytes
        # happen to match. A separately valid new save must drop the old
        # cross-source Undo frame rather than inherit its unrelated history.
        if self.undo_stack and not _same_live_state(
            self.undo_stack[-1].after, before,
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
            try:
                stale_source = (
                    page != expected.page
                    or sha256_file(expected.page) != expected.image_sha
                    or _bytes_or_absent(pdic_path(expected.page)) != expected.pdic_bytes
                    or _bytes_or_absent(simplified_review_path_for_image(expected.page))
                       != expected.simplified_bytes
                    or _bytes_or_absent(expected.manual_path) != expected.manual_bytes
                    or _bytes_or_absent(expected.ocr_path) != expected.ocr_bytes
                    or _bytes_or_absent(expected.section_path) != expected.section_bytes
                    or _bytes_or_absent(expected.profile_path) != expected.profile_bytes
                )
            except (OSError, ValueError, TypeError):
                # A transient Tk rebind is retryable only if *all* source
                # owners remain byte-identical. A denied or invalid read is
                # not proof of unchanged human/OCR/SECTION/Profile evidence.
                # Refuse and quarantine the old history without leaking the
                # private exception path through a Tk Undo/Redo callback.
                stale_source = True
            if stale_source:
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
        pins = review.__dict__.get("_r3_simplified_source_bytes")
        if isinstance(pins, dict):
            pins.pop(expected.page.stem, None)
        getattr(review, "_simplified_dirty_pages", set()).discard(expected.page.stem)
        stack.pop()
        (self.undo_stack if redo else self.redo_stack).append(frame)
        return True

    def undo(self, review: Any) -> bool:
        return self._apply(review, redo=False)

    def redo(self, review: Any) -> bool:
        return self._apply(review, redo=True)
