"""Explicit, local-only verification of a saved human proofreading action.

Only user-invoked confirmation (never ordinary editing or automatic OCR) may
create a verified outcome. Nothing is uploaded or exported as training labels.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .proofreading_events import (
    append_event, load_events, make_event, sha256_file,
)

JUDGMENTS = frozenset({"correct_headword", "not_headword"})


def verify_saved_action(
    *, journal: Path, pdic_file: Path, image_file: Path,
    operation_id: str, judgment: str,
    explicitly_confirmed: bool,
    ocr_cache: Path | None = None,
) -> dict[str, Any]:
    """Require exact current source snapshots and explicit human confirmation.

    Reject a duplicate verification, missing identity, stale PDIC/image,
    missing OCR-cache signature for OCR-linked events, or malformed sources.
    Recording a verified *judgment* is not authorization to train a model.
    """
    if not explicitly_confirmed:
        raise ValueError("Explicit user visual confirmation is required")
    if judgment not in JUDGMENTS:
        raise ValueError("Judgment must be correct_headword or not_headword")
    if not operation_id:
        raise ValueError("An existing operation id is required")
    events = load_events(journal)
    matches = [e for e in events if e.get("operation_id") == operation_id]
    if len(matches) != 1:
        raise ValueError("Target proofreading event was not found uniquely")
    target = matches[0]
    if target.get("action") == "verify":
        raise ValueError("Cannot verify an existing verification")
    if target.get("verification_status") != "explicit_action_unverified_page":
        raise ValueError("Only recorded unverified human actions can be confirmed")
    if not target.get("entry_id"):
        raise ValueError("Target has no reliable entry identity; do not guess")
    current_pdic = sha256_file(pdic_file)
    current_image = sha256_file(image_file)
    if not current_pdic or current_pdic != target.get("pdic_sha256"):
        raise ValueError("Stale saved PDIC: recheck the latest page and action")
    if not current_image or current_image != target.get("image_sha256"):
        raise ValueError("Missing or changed source image")
    # Bind both the scanned pixels and any linked OCR cache to the
    # journal's exclusive-write section. Checking once before the lock
    # would allow the scan to change after the visual decision.
    source_checks: dict[Path, str] = {Path(image_file): current_image}
    signature = target.get("ocr_signature")
    if signature is not None:
        if ocr_cache is None or not Path(ocr_cache).is_file():
            raise ValueError("The matching original OCR cache is required")
        try:
            payload = json.loads(Path(ocr_cache).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Invalid OCR cache") from exc
        if not isinstance(payload, dict) or payload.get("signature") != signature:
            raise ValueError("OCR source changed; cannot verify stale ancestry")
        cache_digest = sha256_file(ocr_cache)
        if cache_digest is None:
            raise ValueError("OCR cache disappeared before verification")
        source_checks[Path(ocr_cache)] = cache_digest
    if any(
        e.get("action") == "verify"
        and isinstance(e.get("before"), dict)
        and e["before"].get("reviewed_operation_id") == operation_id
        for e in events
    ):
        raise ValueError("This operation already has an explicit verification")
    review = make_event(
        page_id=target["page_id"],
        action="verify",
        before={"reviewed_operation_id": operation_id},
        after={"judgment": judgment},
        pdic_sha256=current_pdic,
        image_sha256=current_image,
        entry_id=target["entry_id"],
        candidate_id=target.get("candidate_id"),
        section_id=target.get("section_id"),
        section_snapshot_sha256=target.get("section_snapshot_sha256"),
        ocr_signature=target.get("ocr_signature"),
        final_snapshot_sha256=target.get("final_snapshot_sha256"),
        verification_status="verified",
        explicitly_verified=True,
    )
    append_event(
        journal, review, pdic_file=pdic_file, source_checks=source_checks
    )
    return review


def explicit_verification_counts(
    events: list[dict[str, Any]], *,
    pdic_sha256: str | None, image_sha256: str | None,
) -> dict[str, int]:
    """Count fresh, referentially valid user judgments (NOT training labels)."""
    targets = {
        e.get("operation_id"): e for e in events
        if e.get("action") != "verify"
    }
    judgments = {"correct_headword": 0, "not_headword": 0}
    seen: set[str] = set()
    for event in events:
        if event.get("action") != "verify" or event.get("verification_status") != "verified":
            continue
        before = event.get("before")
        after = event.get("after")
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        original = str(before.get("reviewed_operation_id") or "")
        judgment = after.get("judgment")
        source = targets.get(original)
        if not original or original in seen or judgment not in judgments or not source:
            continue
        if not pdic_sha256 or not image_sha256:
            continue
        if any(
            item.get("pdic_sha256") != pdic_sha256
            or item.get("image_sha256") != image_sha256
            for item in (event, source)
        ):
            continue
        if not source.get("entry_id") or event.get("entry_id") != source["entry_id"]:
            continue
        seen.add(original)
        judgments[judgment] += 1
    return judgments
