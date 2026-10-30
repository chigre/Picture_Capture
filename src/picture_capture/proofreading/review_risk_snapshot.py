"""One-page, opt-in, provenance-validated R4.2 focused review risk queue.

The historical focused filter remains untouched when disabled: no extra I/O,
no mutation of target rows and identical source ordering. When enabled the
input is an independently post-PDIC-published software-owned origin witness,
*never* a hash newly invented during review. Every page is verified once,
then stable priority-first sorting is limited to contiguous page/SECTION spans.
Risks are diagnostic triage suggestions, not error ground truth.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from ..io.formats import read_pdic
from ..persistence.project_storage import (
    ocr_cache_root, page_sections_read_path_for_image, pdic_path_for_image,
)
from .review_risk import ReviewRisk, ReviewRiskProvenance, classify_review_risk
from .review_risk_queue import order_review_targets
from .review_risk_witness_storage import review_risk_witness_path
from .review_section_provenance import section_keys_for_source_points

_FORMAT = "picture-capture-review-risk-origin-v1"
_UNKNOWN = ReviewRisk("unknown", ("STALE_OR_UNVERIFIED_SOURCE",))


def _sha(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _snapshot(
    project_root: Path, page: Path, cache_path: Path, pdic_path: Path,
) -> dict[tuple[int, int, str], tuple[str, ReviewRisk]]:
    """Read/cache/verify each page as one unit; fail closed on any source drift."""
    project = Path(project_root).resolve()
    image = Path(page).resolve()
    cache = Path(cache_path)
    pdic = Path(pdic_path)
    if (
        image.parent != project
        or cache.resolve() != (ocr_cache_root(project) / f"{image.stem}.json").resolve()
        or pdic.resolve() != pdic_path_for_image(image).resolve()
    ):
        return {}
    section = page_sections_read_path_for_image(image)
    origin = review_risk_witness_path(cache)
    try:
        if not origin.is_file():
            return {}
        origin_bytes = origin.read_bytes()
        record = json.loads(origin_bytes.decode("utf-8"))
        if (
            not isinstance(record, dict)
            or record.get("format") != _FORMAT
            or record.get("project_key") != str(project)
            or record.get("page_key") != image.name
            or not isinstance(record.get("witnesses"), list)
        ):
            return {}
        cache_bytes, pdic_bytes, image_bytes = (
            cache.read_bytes(), pdic.read_bytes(), image.read_bytes()
        )
        section_bytes = section.read_bytes() if section.exists() else None
        if (
            _sha(cache_bytes) != record.get("cache_sha256")
            or _sha(pdic_bytes) != record.get("pdic_sha256")
            or _sha(image_bytes) != record.get("image_sha256")
            or (
                _sha(section_bytes) if section_bytes is not None else None
            ) != record.get("section_sha256")
        ):
            return {}
        payload = json.loads(cache_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            return {}
        proposals = payload.get("review_candidates")
        if not isinstance(proposals, list) or any(
            not isinstance(row, dict) for row in proposals
        ):
            return {}
        saved = read_pdic(pdic)
        ids = Counter(row.get("candidate_id") for row in proposals
                      if isinstance(row.get("candidate_id"), str))
        xy_counts = Counter(
            (row.get("source_x"), row.get("source_y"))
            for row in proposals
            if type(row.get("source_x")) is int
            and type(row.get("source_y")) is int
        )
        pdic_counts = Counter((int(row.x), int(row.y)) for row in saved)
        pdic_by_xy = {(int(row.x), int(row.y)): row for row in saved}
        by_id = {row.get("candidate_id"): row for row in proposals
                 if isinstance(row.get("candidate_id"), str)}
        witnessed = record["witnesses"]
        witness_ids = Counter(
            row.get("candidate_id") for row in witnessed if isinstance(row, dict)
        )
        xy_points = [
            (row.get("source_x"), row.get("source_y"))
            for row in witnessed if isinstance(row, dict)
        ]
        section_keys = (
            section_keys_for_source_points(image, section, xy_points)
            if section_bytes is not None else {}
        )
        result: dict[tuple[int, int, str], tuple[str, ReviewRisk]] = {}
        for row in witnessed:
            if not isinstance(row, dict):
                return {}
            cid, x, y, sec = (
                row.get("candidate_id"), row.get("source_x"),
                row.get("source_y"), row.get("section_key"),
            )
            if (
                not isinstance(cid, str) or not cid or ids[cid] != 1
                or witness_ids[cid] != 1
                or type(x) is not int or type(y) is not int
                or xy_counts[x, y] != 1 or pdic_counts[x, y] != 1
                or not isinstance(sec, str)
                or (section_keys.get((x, y)) if section_bytes is not None
                    else "whole-page") != sec
            ):
                continue
            candidate = by_id.get(cid)
            saved_row = pdic_by_xy.get((x, y))
            if (
                not isinstance(candidate, dict)
                or candidate.get("source_x") != x
                or candidate.get("source_y") != y
                or candidate.get("selected") is not True
                or candidate.get("position_variant") != "refined"
                or candidate.get("coordinate_space") != "source_image_pixels"
                or saved_row is None
                or not isinstance(candidate.get("word"), str)
                or candidate["word"].strip() != str(saved_row.word).strip()
            ):
                continue
            provenance = ReviewRiskProvenance(
                project_key=str(project), page_key=image.name,
                section_key=sec, candidate_id=cid,
                evidence_project_key=str(project), evidence_page_key=image.name,
                evidence_section_key=sec,
                evidence_cache_sha256=_sha(cache_bytes),
                current_cache_sha256=_sha(cache_bytes),
                evidence_pdic_sha256=_sha(pdic_bytes),
                current_pdic_sha256=_sha(pdic_bytes),
                unique_matches=1, pdic_source_x=x, pdic_source_y=y,
            )
            result[(x, y, str(saved_row.word).strip())] = (
                sec, classify_review_risk(candidate, provenance=provenance),
            )
        # Invalidate the entire page if any file changed during decoding.
        if (
            origin.read_bytes() != origin_bytes
            or cache.read_bytes() != cache_bytes
            or pdic.read_bytes() != pdic_bytes
            or image.read_bytes() != image_bytes
            or (section.read_bytes() if section.exists() else None) != section_bytes
            or page_sections_read_path_for_image(image).resolve() != section.resolve()
        ):
            return {}
        return result
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        return {}


def prioritized_focused_page_targets(
    targets: list[dict[str, Any]],
    *, project_root: Path, page: Path, cache_path: Path,
    pdic_path: Path, enabled: bool = False,
) -> list[dict[str, Any]]:
    """Return original rows untouched unless opted in with valid provenance."""
    original = list(targets)
    if not enabled or not original:
        return original
    risk_by_owner = _snapshot(project_root, page, cache_path, pdic_path)
    if not risk_by_owner:
        return original
    sectioned = page_sections_read_path_for_image(Path(page)).exists()
    augmented: list[dict[str, Any]] = []
    risks: list[ReviewRisk] = []
    for row in original:
        try:
            key = (int(row["x"]), int(row["y"]), str(row["original_word"]).strip())
            sec, risk = risk_by_owner.get(key, ("", _UNKNOWN))
        except (KeyError, ValueError, TypeError):
            return original
        if not sec:
            if sectioned:
                # Cannot sort an unproven target across SECTION boundaries.
                return original
            sec = "whole-page"
        copy = dict(row)
        copy["section_key"] = sec
        copy["review_risk_tier"] = risk.tier
        copy["review_risk_reasons"] = risk.reasons
        if risk.tier == "priority":
            marker = "风险优先（已校验诊断：" + "、".join(risk.reasons) + "）"
        elif risk.tier == "normal":
            marker = "诊断一致（非人工正确性验证）"
        else:
            marker = "风险未知（来源未核验）"
        copy["reasons"] = tuple(row.get("reasons", ())) + (marker,)
        augmented.append(copy)
        risks.append(risk)
    return list(order_review_targets(augmented, risks=risks, enabled=True))
