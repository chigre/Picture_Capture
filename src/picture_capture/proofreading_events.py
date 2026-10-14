"""Local-only, provenance-preserving proofreading event journal.

This module is deliberately not wired to UI writes until the caller can prove
that its PDIC commit succeeded. An edit is NOT an independently verified label.
Existing PDIC, OCR cache and manual-selection formats remain untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .formats import write_text_atomic

EVENT_FORMAT = "picture-capture-proofreading-events-v1"
ACTIONS = frozenset({
    "add", "delete", "rename", "move", "select", "deselect",
    "verify", "undo", "redo",
})
LABEL_STATUSES = frozenset({
    "verified", "explicit_action_unverified_page", "inferred", "unknown",
})
STAGES = frozenset({
    "ocr_proposal", "saved_final_pdic", "human_edited_pdic", "unknown",
})


def sha256_file(path: Path) -> str | None:
    """Return actual file digest, never a guess based on file modification time."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def make_event(
    *, page_id: str, action: str,
    before: dict[str, Any] | None, after: dict[str, Any] | None,
    pdic_sha256: str, source_stage: str = "human_edited_pdic",
    verification_status: str = "explicit_action_unverified_page",
    explicitly_verified: bool = False,
    candidate_id: str | None = None,
    ocr_signature: str | None = None,
    final_snapshot_sha256: str | None = None,
    entry_id: str | None = None,
    operation_id: str | None = None,
    image_sha256: str | None = None,
    section_id: str | None = None,
    section_snapshot_sha256: str | None = None,
) -> dict[str, Any]:
    """Create an event AFTER saving PDIC, with explicit (not inferred) provenance.

    `verified` is forbidden unless the user explicitly verified the label.
    Entry ID is supplied by its owner, never guessed from a sorted row index.
    """
    if not page_id or action not in ACTIONS:
        raise ValueError("Invalid page identity or proofreading action")
    if source_stage not in STAGES or verification_status not in LABEL_STATUSES:
        raise ValueError("Invalid event provenance")
    if verification_status == "verified" and not explicitly_verified:
        raise ValueError("A manual action is not automatically a verified label")
    if not isinstance(pdic_sha256, str) or len(pdic_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in pdic_sha256
    ):
        raise ValueError("A saved PDIC SHA-256 is required")
    if entry_id is not None and (not isinstance(entry_id, str) or not entry_id):
        raise ValueError("Entry identity must not be a row index or empty reference")
    return {
        "schema_version": 1,
        "coordinate_space": "original_image_xy",
        "operation_id": operation_id or uuid4().hex,
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "page_id": str(page_id),
        "action": action,
        "entry_id": entry_id,
        "candidate_id": candidate_id,
        "before": before,
        "after": after,
        "source_stage": source_stage,
        "verification_status": verification_status,
        "pdic_sha256": pdic_sha256,
        "ocr_signature": ocr_signature,
        "final_snapshot_sha256": final_snapshot_sha256,
        "image_sha256": image_sha256,
        "section_id": section_id,
        "section_snapshot_sha256": section_snapshot_sha256,
    }


def load_events(path: Path) -> list[dict[str, Any]]:
    """Fail closed on invalid journal, never silently erase damaged user evidence."""
    source = Path(path)
    if not source.is_file():
        return []
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("format") != EVENT_FORMAT:
        raise ValueError("Unknown proofreading journal format")
    events = raw.get("events")
    if not isinstance(events, list) or any(
        not isinstance(event, dict)
        or not isinstance(event.get("operation_id"), str)
        or not isinstance(event.get("pdic_sha256"), str)
        or event.get("verification_status") not in LABEL_STATUSES
        for event in events
    ):
        raise ValueError("Malformed proofreading event journal")
    ids = [event["operation_id"] for event in events]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate proofreading operation id")
    return events


def append_event(
    path: Path, event: dict[str, Any], *, pdic_file: Path,
    source_checks: Mapping[Path, str] | None = None,
) -> None:
    """Atomically persist evidence only if it represents CURRENT saved PDIC.

    No writes to PDIC, OCR caches or human overrides. A cross-process local
    exclusive directory lock serializes journal updates without waiting.
    """
    if not isinstance(event, dict) or event.get("verification_status") not in LABEL_STATUSES:
        raise ValueError("Invalid proofreading event")
    if event.get("action") not in ACTIONS or not event.get("operation_id"):
        raise ValueError("Invalid proofreading action")
    path = Path(path)
    # Source checks are supplied only by an explicit verification caller.
    # Ordinary proofreading events retain their historical write contract.
    checks = {Path(p): digest for p, digest in (source_checks or {}).items()}
    if any(not isinstance(digest, str) or len(digest) != 64 for digest in checks.values()):
        raise ValueError("Verification source digest is invalid")
    # mkdir is an atomic exclusive operation on Windows, macOS and Linux.
    # Refuse overlapping writers instead of racing on read-modify-replace;
    # never automatically delete a stale lock belonging to another process.
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_dir = path.with_name(f"{path.name}.lock")
    try:
        lock_dir.mkdir()
    except FileExistsError as error:
        raise OSError(
            f"Proofreading journal is locked by another writer: {lock_dir}"
        ) from error
    try:
        actual = sha256_file(pdic_file)
        if checks and any(sha256_file(p) != digest for p, digest in checks.items()):
            raise ValueError("Verification source changed before journal publication")
        if actual is None or event.get("pdic_sha256") != actual:
            raise ValueError("Current PDIC does not match the recorded post-save snapshot")
        events = load_events(path)
        # Predecessor links are additive provenance. Enforce the same direct
        # predecessor used for identity replay while the journal lock is held.
        predecessor = event.get("prior_pdic_sha256")
        if predecessor is not None:
            if (not isinstance(predecessor, str)
                    or len(predecessor) != 64
                    or any(ch not in "0123456789abcdef" for ch in predecessor)):
                raise ValueError("Invalid prior proofreading PDIC digest")
            last_edit = next(
                (row for row in reversed(events) if row.get("action") != "verify"),
                None,
            )
            if last_edit is not None and last_edit.get("pdic_sha256") != predecessor:
                raise ValueError("Proofreading predecessor no longer matches journal")
        if any(existing["operation_id"] == event["operation_id"] for existing in events):
            raise ValueError("Duplicate proofreading operation id")
        if event.get("action") == "verify":
            # The UI preflight runs BEFORE acquiring the journal lock. Two
            # clients can both approve the same operation from stale reads.
            # Repeat all referential checks inside this exclusive write lock.
            before = event.get("before")
            reviewed_id = (
                before.get("reviewed_operation_id")
                if isinstance(before, dict) else None
            )
            if not isinstance(reviewed_id, str) or not reviewed_id:
                raise ValueError("Verification requires an existing source operation")
            matching = [
                row for row in events
                if row.get("operation_id") == reviewed_id and row.get("action") != "verify"
            ]
            if len(matching) != 1:
                raise ValueError("Verification source operation is missing or ambiguous")
            source = matching[0]
            if source.get("verification_status") != "explicit_action_unverified_page":
                raise ValueError("Verification source is not an unverified human action")
            if event.get("verification_status") != "verified":
                raise ValueError("Verification must be explicitly confirmed")
            if not source.get("entry_id") or event.get("entry_id") != source["entry_id"]:
                raise ValueError("Verification entry identity does not match source")
            for key in ("page_id", "pdic_sha256", "ocr_signature"):
                if event.get(key) != source.get(key):
                    raise ValueError(f"Verification {key} does not match source")
            # Legacy synthetic fixtures may omit image provenance; whenever
            # both records have it, forbid a mismatched source image.
            if source.get("image_sha256") is not None and (
                event.get("image_sha256") is not None
                and event.get("image_sha256") != source["image_sha256"]
            ):
                raise ValueError("Verification image does not match source")
            if any(
                row.get("action") == "verify"
                and isinstance(row.get("before"), dict)
                and row["before"].get("reviewed_operation_id") == reviewed_id
                for row in events
            ):
                raise ValueError("This proofreading operation was already verified")
        elif event.get("verification_status") == "verified":
            raise ValueError("Ordinary proofreading edits cannot become verified labels")
        events.append(dict(event))
        # Recheck source right before atomic publication, not just before load.
        if sha256_file(pdic_file) != actual:
            raise ValueError("PDIC changed while writing proofreading evidence")
        if checks and any(sha256_file(p) != digest for p, digest in checks.items()):
            raise ValueError("Verification source changed before journal publication")
        write_text_atomic(
            path,
            json.dumps({"format": EVENT_FORMAT, "events": events},
                       ensure_ascii=False, separators=(",", ":")),
        )
    finally:
        lock_dir.rmdir()


def append_rename_batch(
    path: Path, additions: list[dict[str, Any]], *, pdic_file: Path,
) -> None:
    """One atomic journal publication for a provable multi-row text-only save.

    The caller has independently validated unchanged, unique original XY for
    every row. Never batch verification actions, OCR votes or mixed operations.
    Unlike repeated append_event calls, failure cannot leave a partial group.
    """
    rows = list(additions)
    if len(rows) < 2:
        raise ValueError("Multi-rename batch requires two or more events")
    first = rows[0]
    operation_ids = []
    entry_ids = []
    for event in rows:
        if not isinstance(event, dict) or any((
            event.get("action") != "rename",
            event.get("source_stage") != "human_edited_pdic",
            event.get("verification_status") != "explicit_action_unverified_page",
            not isinstance(event.get("operation_id"), str),
            not isinstance(event.get("entry_id"), str) or not event.get("entry_id"),
            event.get("page_id") != first.get("page_id"),
            event.get("pdic_sha256") != first.get("pdic_sha256"),
            event.get("image_sha256") != first.get("image_sha256"),
            event.get("ocr_signature") != first.get("ocr_signature"),
            event.get("final_snapshot_sha256") != first.get("final_snapshot_sha256"),
            event.get("prior_pdic_sha256") != first.get("prior_pdic_sha256"),
        )):
            raise ValueError("Mixed or unproven proofreading rename batch")
        operation_ids.append(event["operation_id"])
        entry_ids.append(event["entry_id"])
    if len(set(operation_ids)) != len(rows) or len(set(entry_ids)) != len(rows):
        raise ValueError("Duplicate operation or entry identity in rename batch")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_name(f"{target.name}.lock")
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise OSError(f"Proofreading journal is locked by another writer: {lock}") from error
    try:
        saved_sha = sha256_file(pdic_file)
        if saved_sha is None or saved_sha != first.get("pdic_sha256"):
            raise ValueError("Current PDIC does not match the recorded post-save snapshot")
        previous = load_events(target)
        predecessor = first.get("prior_pdic_sha256")
        if predecessor is not None:
            if (not isinstance(predecessor, str)
                    or len(predecessor) != 64
                    or any(ch not in "0123456789abcdef" for ch in predecessor)):
                raise ValueError("Invalid prior proofreading PDIC digest")
            last_edit = next(
                (row for row in reversed(previous) if row.get("action") != "verify"),
                None,
            )
            if last_edit is not None and last_edit.get("pdic_sha256") != predecessor:
                raise ValueError("Proofreading predecessor no longer matches journal")
        existing_ids = {event["operation_id"] for event in previous}
        if any(operation_id in existing_ids for operation_id in operation_ids):
            raise ValueError("Duplicate proofreading operation id")
        previous.extend(dict(event) for event in rows)
        if sha256_file(pdic_file) != saved_sha:
            raise ValueError("PDIC changed while writing proofreading evidence")
        write_text_atomic(
            target,
            json.dumps({"format": EVENT_FORMAT, "events": previous},
                       ensure_ascii=False, separators=(",", ":")),
        )
    finally:
        lock.rmdir()


def audit_events(
    events: list[dict[str, Any]], *, current_pdic_sha256: str | None,
    current_ocr_signature: str | None,
    current_image_sha256: str | None = None,
) -> dict[str, Any]:
    """Read-only provenance counts; never promote inferred edits into gold labels."""
    counts = {status: 0 for status in sorted(LABEL_STATUSES)}
    eligible = 0
    stale = 0
    uncertain = 0
    for item in events:
        status = str(item.get("verification_status", "unknown"))
        counts[status if status in counts else "unknown"] += 1
        pdic_ok = bool(current_pdic_sha256) and item.get("pdic_sha256") == current_pdic_sha256
        ocr_ref = item.get("ocr_signature")
        ocr_ok = ocr_ref is None or (
            current_ocr_signature is not None and ocr_ref == current_ocr_signature
        )
        image_ref = item.get("image_sha256")
        image_ok = image_ref is None or (
            current_image_sha256 is not None and image_ref == current_image_sha256
        )
        if not pdic_ok or not ocr_ok or not image_ok:
            stale += 1
        elif status == "verified" and item.get("entry_id") and (
            item.get("candidate_id") or item.get("action") == "verify"
        ):
            # Unique candidate mapping must still be checked by the R2.2 owner
            # before exporting any record into a supervised training dataset.
            eligible += 1
        else:
            uncertain += 1
    return {
        "events": len(events),
        "label_status_counts": counts,
        "current_verified_records_requiring_link_audit": eligible,
        "stale_events": stale,
        "not_training_ready": uncertain,
        "training_labels_exported": 0,
    }
