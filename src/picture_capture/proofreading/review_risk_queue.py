"""R4.2 read-only, exact-byte-attested review triage and opt-in stable queue.

Nothing here is connected to the production Tk focused filter by default.
A ReviewRiskWitness is an *independently recorded origin* supplied by a trusted
post-save source, never synthesized by copying hashes from the current cache.
Existing OCR caches have no sufficient witness and must remain 'unknown'.
Only exact source X/Y and candidate ID own a PDIC row; no nearest-Y matching.
No PDIC/PPP/SECTION/OCR/sidecar write, GUI import, or automatic ranking.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..io.formats import read_pdic
from .review_risk import ReviewRisk, ReviewRiskProvenance, classify_review_risk


@dataclass(frozen=True)
class ReviewRiskWitness:
    """Source-time proof from an *independently attested* provenance record.

    A caller MUST NOT construct this witness by hashing the same files at
    review time: doing so conceals stale, replaced or edited OCR/PDIC evidence.
    The section hash is required when a SECTION sidecar exists.
    """

    project_key: str
    page_key: str
    section_key: str
    candidate_id: str
    source_x: int
    source_y: int
    cache_sha256: str
    pdic_sha256: str
    section_sha256: str | None = None


_UNKNOWN_SOURCE = ReviewRisk("unknown", ("STALE_OR_UNVERIFIED_SOURCE",))
_UNKNOWN_IDENTITY = ReviewRisk("unknown", ("IDENTITY_NOT_PROVEN",))
_UNKNOWN_SECTION = ReviewRisk("unknown", ("SECTION_NOT_PROVEN",))


def _digest(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def review_risk_from_files(
    *,
    pdic_path: Path,
    cache_path: Path,
    section_path: Path,
    witness: ReviewRiskWitness | None,
    project_key: str,
    page_key: str,
    section_key: str,
    section_at_source_xy: Callable[[int, int], str] | None = None,
) -> ReviewRisk:
    """Verify immutable source hashes against actual on-disk bytes, then triage.

    No witness => no proof. SECTION identity must either be explicitly
    whole-page with a missing sidecar, or verified against the current sidecar
    bytes AND a geometry-backed section-at-source-XY resolver. Re-read the
    source PDIC to avoid applying a stale parser snapshot to changed bytes.
    """
    if not isinstance(witness, ReviewRiskWitness):
        return _UNKNOWN_SOURCE
    if (
        not isinstance(project_key, str) or not project_key
        or not isinstance(page_key, str) or not page_key
        or not isinstance(section_key, str) or not section_key
        or (witness.project_key, witness.page_key, witness.section_key)
        != (project_key, page_key, section_key)
    ):
        return _UNKNOWN_SOURCE
    try:
        cache = Path(cache_path)
        pdic = Path(pdic_path)
        section = Path(section_path)
        ocr_bytes = cache.read_bytes()
        pdic_bytes = pdic.read_bytes()
        if (
            _digest(ocr_bytes) != witness.cache_sha256
            or _digest(pdic_bytes) != witness.pdic_sha256
        ):
            return _UNKNOWN_SOURCE
        if section.exists():
            if (
                not witness.section_sha256
                or _digest(section.read_bytes()) != witness.section_sha256
                or section_at_source_xy is None
                or section_at_source_xy(witness.source_x, witness.source_y)
                != section_key
            ):
                return _UNKNOWN_SECTION
        elif (
            section_key != "whole-page"
            or witness.section_sha256 is not None
        ):
            return _UNKNOWN_SECTION

        payload = json.loads(ocr_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            return _UNKNOWN_SOURCE
        rows = payload.get("review_candidates")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            return _UNKNOWN_SOURCE
        if not isinstance(witness.candidate_id, str) or not witness.candidate_id:
            return _UNKNOWN_IDENTITY
        matched = [row for row in rows if row.get("candidate_id") == witness.candidate_id]
        if len(matched) != 1:
            return _UNKNOWN_IDENTITY
        candidate = matched[0]
        # Other candidate IDs sharing one physical source coordinate are also
        # ambiguous: never certify one from an arbitrary row-order selection.
        xy_rows = [
            row for row in rows
            if type(row.get("source_x")) is int
            and type(row.get("source_y")) is int
            and (row["source_x"], row["source_y"])
            == (witness.source_x, witness.source_y)
        ]
        if len(xy_rows) != 1 or xy_rows[0] is not candidate:
            return _UNKNOWN_IDENTITY
        if type(witness.source_x) is not int or type(witness.source_y) is not int:
            return _UNKNOWN_IDENTITY
        saved = read_pdic(pdic)
        # Do not silently accept changed PDIC bytes while the parser was
        # reading; this is a read-only observation, not a filesystem lock.
        if _digest(pdic.read_bytes()) != witness.pdic_sha256:
            return _UNKNOWN_SOURCE
        matching_entries = [
            row for row in saved
            if type(row.x) is int and type(row.y) is int
            and row.x == witness.source_x and row.y == witness.source_y
        ]
        if len(matching_entries) != 1:
            return _UNKNOWN_IDENTITY
        # Similarly detect late OCR/SECTION replacements during readback.
        if _digest(cache.read_bytes()) != witness.cache_sha256:
            return _UNKNOWN_SOURCE
        if section.exists():
            if _digest(section.read_bytes()) != witness.section_sha256:
                return _UNKNOWN_SECTION
        elif section_key != "whole-page":
            return _UNKNOWN_SECTION
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError):
        return _UNKNOWN_SOURCE

    source = ReviewRiskProvenance(
        project_key=project_key,
        page_key=page_key,
        section_key=section_key,
        candidate_id=witness.candidate_id,
        evidence_project_key=witness.project_key,
        evidence_page_key=witness.page_key,
        evidence_section_key=witness.section_key,
        evidence_cache_sha256=witness.cache_sha256,
        current_cache_sha256=_digest(ocr_bytes),
        evidence_pdic_sha256=witness.pdic_sha256,
        current_pdic_sha256=_digest(pdic_bytes),
        unique_matches=len(matching_entries),
        pdic_source_x=witness.source_x,
        pdic_source_y=witness.source_y,
    )
    return classify_review_risk(candidate, provenance=source)


def order_review_targets(
    targets: Sequence[Mapping[str, Any]],
    *,
    risks: Sequence[ReviewRisk] | None,
    enabled: bool = False,
) -> list[Mapping[str, Any]]:
    """Stable priority-first order only within contiguous page/SECTION spans.

    Default OFF returns the original references in their original order.
    Never derive a priority from a row's untrusted text, mutable flags or
    human selection. Only pass externally validated ReviewRisk results.
    Missing grouping or risk evidence => no changes even when enabled.
    """
    original = list(targets)
    if not enabled or risks is None or len(original) != len(risks):
        return original
    if any(not isinstance(risk, ReviewRisk) or risk.tier not in
           {"priority", "normal", "unknown"} for risk in risks):
        return original
    groups: list[tuple[int, str]] = []
    for row in original:
        if not isinstance(row, Mapping):
            return original
        page = row.get("page_index")
        section = row.get("section_key")
        if type(page) is not int or not isinstance(section, str) or not section:
            return original
        groups.append((page, section))

    ordered: list[Mapping[str, Any]] = []
    start = 0
    while start < len(original):
        stop = start + 1
        while stop < len(original) and groups[stop] == groups[start]:
            stop += 1
        # Python's stable sort preserves relative order of all items in
        # the same tier, including unknowns and multiple priority rows.
        indices = sorted(
            range(start, stop),
            key=lambda i: 0 if risks[i].tier == "priority" else 1,
        )
        ordered.extend(original[i] for i in indices)
        start = stop
    return ordered
