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
from typing import Any
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


def append_event(path: Path, event: dict[str, Any], *, pdic_file: Path) -> None:
    """Atomically persist evidence only if it represents CURRENT saved PDIC.

    No writes to PDIC, OCR caches or human overrides. Caller must serialize
    concurrent writes for this page; the journal is not a multi-process lock.
    """
    if not isinstance(event, dict) or event.get("verification_status") not in LABEL_STATUSES:
        raise ValueError("Invalid proofreading event")
    if event.get("action") not in ACTIONS or not event.get("operation_id"):
        raise ValueError("Invalid proofreading action")
    actual = sha256_file(pdic_file)
    if actual is None or event.get("pdic_sha256") != actual:
        raise ValueError("Current PDIC does not match the recorded post-save snapshot")
    events = load_events(path)
    if any(existing["operation_id"] == event["operation_id"] for existing in events):
        raise ValueError("Duplicate proofreading operation id")
    events.append(dict(event))
    write_text_atomic(
        path,
        json.dumps({"format": EVENT_FORMAT, "events": events},
                   ensure_ascii=False, separators=(",", ":")),
    )


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
