"""Read-only, privacy-minimal summaries of project-local proofreading evidence.

The source journal stays local and retains full user-owned correction data;
exports contain ONLY aggregate counts, source digest and a license statement.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from .proofreading_events import audit_events, load_events, sha256_file
from .proofreading_verification import explicit_verification_counts
from .project_storage import page_sections_read_path_for_image

EXPORT_FORMAT = "picture-capture-proofreading-quality-export-v1"


def _change_type(event: dict[str, Any]) -> str:
    action = event.get("action")
    if action in {"add", "delete", "select", "deselect", "verify", "undo", "redo"}:
        return str(action)
    before = event.get("before")
    after = event.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return "unknown"
    word_diff = before.get("word") != after.get("word")
    point_diff = (before.get("x"), before.get("y")) != (after.get("x"), after.get("y"))
    if word_diff and not point_diff:
        return "text_only"
    if point_diff and not word_diff:
        return "position_only"
    if word_diff and point_diff:
        return "text_and_position"
    return "no_change"


def summarize_local_events(
    journal_path: Path, pdic_path: Path, *,
    image_path: Path | None = None,
    project_id: str,
    license_statement: str,
    current_ocr_signature: str | None = None,
) -> dict[str, Any]:
    """Return a local report without words, candidate IDs or filesystem paths."""
    if not project_id or not license_statement:
        raise ValueError("Explicit project identity and dataset license statement required")
    journal_path = Path(journal_path)
    if not journal_path.is_file():
        raise FileNotFoundError("The requested proofreading journal does not exist")
    events = load_events(journal_path)
    image_digest = sha256_file(image_path) if image_path is not None else None
    provenance = audit_events(
        events,
        current_pdic_sha256=sha256_file(pdic_path),
        current_ocr_signature=current_ocr_signature,
        current_image_sha256=image_digest,
    )
    review_counts = explicit_verification_counts(
        events, pdic_sha256=sha256_file(pdic_path),
        image_sha256=image_digest,
    )
    types = Counter(_change_type(event) for event in events)
    # SECTION must be bound to the actual original-image coordinate and
    # sidecar digest captured at edit time. An unbound or changed sidecar is
    # unknown, never attributed to the nearest SECTION.
    section_sha = (
        sha256_file(page_sections_read_path_for_image(image_path))
        if image_path is not None else None
    )
    section_counts = Counter()
    stale_section = 0
    for event in events:
        saved_section = event.get("section_snapshot_sha256")
        saved_image = event.get("image_sha256")
        if (
            section_sha is not None
            and saved_section == section_sha
            and image_digest is not None
            and saved_image == image_digest
            and isinstance(event.get("section_id"), str)
            and event["section_id"].startswith("section:")
        ):
            section_counts[event["section_id"]] += 1
        else:
            section_counts["unknown"] += 1
            if saved_section is not None and saved_section != section_sha:
                stale_section += 1
    # Sections may have free text. Only emit salted, non-reversible identifiers,
    # scoped to this project (and not user-provided section titles).
    section_summaries = {
        hashlib.sha256(f"{project_id}|{section}".encode("utf-8")).hexdigest()[:16]: count
        for section, count in sorted(section_counts.items())
    }
    return {
        "format": EXPORT_FORMAT,
        "dataset_version": 1,
        "dataset_source_sha256": sha256_file(journal_path),
        "project_id": project_id,
        "license_statement": license_statement,
        "evidence_kind": "human_actions_not_verified_ground_truth",
        "source_pdic_integrity": "current_file_digest_checked",
        "provenance": provenance,
        "change_types": dict(sorted(types.items())),
        "section_counts_hashed": section_summaries,
        "section_unattributed_events": section_counts.get("unknown", 0),
        "section_snapshot_stale_events": stale_section,
        "verified_positive_labels": review_counts["correct_headword"],
        "verified_negative_labels": review_counts["not_headword"],
        "verification_basis": "explicit_current_saved_pdic_and_source_image_judgment_only",
        "training_labels_exported": 0,
        "warning": (
            "Historical events may be stale after edits. No candidate link is "
            "certified, explicit verified judgments are not training labels, "
            "no raw words/pages are exported, and nothing is uploaded."
        ),
    }
