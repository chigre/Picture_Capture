"""Pure, provenance-gated R4.1 *review triage*, not an OCR error classifier.

This module has no I/O, Tk, settings or persistence side effects. It is not
wired into the focused filter; R4.2 must separately verify real current cache
and PDIC bytes, exact project/page/SECTION ownership and unique Entry XY
identity before opting into any reordering. Synthetic results are not labels.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping


@dataclass(frozen=True)
class ReviewRiskProvenance:
    """Caller-supplied, independently observed byte/source ownership evidence.

    Evidence keys identify the *origin* of the candidate; the other keys
    identify the active review target. SHA-256 values must be obtained from
    actual current files, never copied from a cache claim or an old checkpoint.
    A sectionless page must use an explicit stable sentinel, e.g. whole-page.
    unique_matches counts exact same-page, same-SECTION source XY owners.
    """

    project_key: str
    page_key: str
    section_key: str
    candidate_id: str
    evidence_project_key: str
    evidence_page_key: str
    evidence_section_key: str
    evidence_cache_sha256: str
    current_cache_sha256: str
    evidence_pdic_sha256: str
    current_pdic_sha256: str
    unique_matches: int
    pdic_source_x: int
    pdic_source_y: int


@dataclass(frozen=True)
class ReviewRisk:
    tier: str  # priority | normal | unknown
    reasons: tuple[str, ...]


# All codes here are review signals, never verified false positives/negatives.
# Ordering is fixed to make diagnostics deterministic across cache row order.
_PRIORITY_CODES = (
    "NEEDS_REVIEW",
    "OCR_CONFLICT",
    "ACCEPTANCE_CONFLICT",
    "OCR_VARIANT",
    "LENS_DISAGREEMENT",
    "LOW_CONFIDENCE",
    "OCR_REPAIR",
    "MULTILINE_POS",
    "SPLIT_OCR_BOX",
    "LOW_PARSER_SCORE",
    "MISSING_STRUCTURE",
    "CONTINUATION_FRAGMENT",
    "ALPHABETICAL_WARNING",
    "PADDLE_ONLY",
    "TESSERACT_ONLY",
    "LENS_ONLY",
    "LEMMA_PARSE_FAILED",
    "MARKER_GLYPH_NOISE",
    "NOT_AT_LEFT",
    "INTERNAL_ARTICLE_STRUCTURE",
    "INTERNAL_LOCUTION",
    "DUAL_CONSENSUS_RESCUE",
    "DUAL_BOUNDARY_RESCUE",
    "MULTI_EVIDENCE_RESCUE",
)
_KNOWN_DECISIONS = frozenset((
    "dual_agree_higher_quality", "dual_similar_higher_quality",
    "acceptance_wins_conflict", "conflict_higher_quality",
    "paddle_only", "tesseract_only", "lens_only",
    "three_engine_agree_higher_quality", "lens_breaks_local_conflict",
    "local_consensus_over_lens", "dual_consensus_visual_rescue",
    "dual_consensus_boundary_rescue", "multi_evidence_visual_boundary_rescue",
))
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _valid_source(p: ReviewRiskProvenance) -> bool:
    if not isinstance(p, ReviewRiskProvenance):
        return False
    identity = (p.project_key, p.page_key, p.section_key, p.candidate_id)
    origin = (p.evidence_project_key, p.evidence_page_key, p.evidence_section_key)
    if not all(isinstance(x, str) and bool(x) for x in identity + origin):
        return False
    if identity[:3] != origin:
        return False
    if type(p.unique_matches) is not int or p.unique_matches != 1:
        return False
    if type(p.pdic_source_x) is not int or type(p.pdic_source_y) is not int:
        return False
    hashes = (p.evidence_cache_sha256, p.current_cache_sha256,
              p.evidence_pdic_sha256, p.current_pdic_sha256)
    if not all(isinstance(x, str) and _SHA256.fullmatch(x) for x in hashes):
        return False
    return hashes[0] == hashes[1] and hashes[2] == hashes[3]


def _valid_confidence(value: Any) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and 0.0 <= value <= 1.0)


def classify_review_risk(
    candidate: Mapping[str, Any] | None, *, provenance: ReviewRiskProvenance
) -> ReviewRisk:
    """Fail closed on stale, ambiguous or incomplete evidence.

    A current, unique selected candidate with recognized review diagnostics is
    priority. Only complete dual-engine agreement can be normal. Unknown is
    neither a known error nor a safe normal result. No candidate is mutated.
    """
    if not _valid_source(provenance):
        return ReviewRisk("unknown", ("STALE_OR_UNVERIFIED_SOURCE",))
    if not isinstance(candidate, dict):
        return ReviewRisk("unknown", ("MISSING_OR_MALFORMED_DIAGNOSTICS",))
    if (
        candidate.get("candidate_id") != provenance.candidate_id
        or candidate.get("coordinate_space") != "source_image_pixels"
        or candidate.get("position_variant") != "refined"
        or type(candidate.get("source_x")) is not int
        or type(candidate.get("source_y")) is not int
        or candidate["source_x"] != provenance.pdic_source_x
        or candidate["source_y"] != provenance.pdic_source_y
    ):
        return ReviewRisk("unknown", ("IDENTITY_NOT_PROVEN",))
    if candidate.get("selected") is not True:
        return ReviewRisk("unknown", ("NOT_A_SELECTED_PDic_OWNER",))
    chosen = candidate.get("final_engine")
    reason = candidate.get("decision_reason")
    if (
        chosen not in ("paddle", "tesseract", "lens")
        or reason not in _KNOWN_DECISIONS
        or reason == "lens_diagnostic_only"
    ):
        return ReviewRisk("unknown", ("UNVERIFIED_ARBITRATION",))
    needs_review = candidate.get("needs_review")
    issues = candidate.get("issue_types")
    if type(needs_review) is not bool or not isinstance(issues, (tuple, list)):
        return ReviewRisk("unknown", ("MISSING_OR_MALFORMED_DIAGNOSTICS",))
    if not all(isinstance(issue, str) for issue in issues):
        return ReviewRisk("unknown", ("MISSING_OR_MALFORMED_DIAGNOSTICS",))
    if any(issue not in _PRIORITY_CODES for issue in issues):
        return ReviewRisk("unknown", ("UNRECOGNIZED_DIAGNOSTIC",))
    flags = set(issues)
    if needs_review:
        flags.add("NEEDS_REVIEW")
    if flags:
        return ReviewRisk("priority", tuple(code for code in _PRIORITY_CODES if code in flags))

    # Absence of an issue is not evidence of a safe candidate. Do not infer
    # normal from a single OCR engine, Lens diagnostic-only, missing confidence,
    # different lemmas, or a repaired/forced/rescued arbitration branch.
    if reason != "dual_agree_higher_quality" or chosen not in ("paddle", "tesseract"):
        return ReviewRisk("unknown", ("NO_CONFIRMED_DUAL_CONSENSUS",))
    p = candidate.get("paddle")
    t = candidate.get("tesseract")
    if not isinstance(p, dict) or not isinstance(t, dict):
        return ReviewRisk("unknown", ("INCOMPLETE_DUAL_EVIDENCE",))
    left, right = p.get("lemma"), t.get("lemma")
    if (
        p.get("accepted") is not True or t.get("accepted") is not True
        or not isinstance(left, str) or not left.strip()
        or not isinstance(right, str) or left.casefold() != right.casefold()
        or not _valid_confidence(p.get("confidence"))
        or not _valid_confidence(t.get("confidence"))
    ):
        return ReviewRisk("unknown", ("INCOMPLETE_DUAL_EVIDENCE",))
    return ReviewRisk("normal", ("CURRENT_DUAL_AGREEMENT",))
