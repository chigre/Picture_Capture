"""Optional R4.2 source-time OCR/PDIC provenance witness publication.

This owner runs only AFTER an actual successful PDIC write, at an explicit
default-off call site. It never changes OCR, PDIC, PPP, SECTION or labels.
No legacy OCR cache can be retroactively given a genuine source-time witness.
SECTION v2 candidates are attested only after strict original-image geometry
attribution; missing, overlapping or malformed sections remain unprovable.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from ..io.formats import read_pdic, write_text_atomic
from ..persistence.project_storage import (
    ocr_cache_root, page_sections_read_path_for_image, pdic_path_for_image,
)
from .review_risk_queue import ReviewRiskWitness
from .review_section_provenance import section_key_for_source_point

_FORMAT = "picture-capture-review-risk-origin-v1"


def review_risk_witness_path(cache_path: Path) -> Path:
    """Software-owned sibling, not part of the editable OCR/PDIC file."""
    cache = Path(cache_path)
    return cache.with_name(f"{cache.stem}_risk_origin_v1.json")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _snapshot(cache_path: Path, pdic_file: Path) -> tuple[bytes, bytes] | None:
    try:
        return Path(cache_path).read_bytes(), Path(pdic_file).read_bytes()
    except OSError:
        return None




def _sources_current(
    *,
    project_page: Path,
    cache: Path,
    pdic: Path,
    section: Path,
    cache_pdic_snapshot: tuple[bytes, bytes],
    image_bytes: bytes,
    section_bytes: bytes | None,
) -> bool:
    """Verify the same source paths and byte snapshots across publication."""
    try:
        if page_sections_read_path_for_image(project_page).resolve() != section.resolve():
            return False
        current_section = section.read_bytes() if section.exists() else None
        return (
            _snapshot(cache, pdic) == cache_pdic_snapshot
            and current_section == section_bytes
            and project_page.read_bytes() == image_bytes
        )
    except OSError:
        return False

def publish_review_risk_witnesses(
    *,
    project_root: Path,
    page: Path,
    cache_path: Path,
    pdic_path: Path,
) -> int:
    """Attest post-save file bytes and uniquely linked original-image rows.

    Must be called from the trusted successful OCR+PDIC publication owner;
    never call from the review reader or synthesize an origin from old files.
    Returns count; zero means none provable, not an error or negative label.
    """
    project = Path(project_root).resolve()
    page = Path(page).resolve()
    cache = Path(cache_path)
    pdic = Path(pdic_path)
    # Reject callers trying to associate an arbitrary cache/PDIC with this
    # project's physical page. Migrated PDIC paths are determined by storage.
    if (
        page.parent != project
        or cache.resolve() != (ocr_cache_root(project) / f"{page.stem}.json").resolve()
        or pdic.resolve() != pdic_path_for_image(page).resolve()
    ):
        return 0
    section = page_sections_read_path_for_image(page)
    try:
        section_bytes = section.read_bytes() if section.exists() else None
        image_bytes = page.read_bytes()
    except OSError:
        return 0
    initial = _snapshot(cache, pdic)
    if initial is None:
        return 0
    raw_cache, raw_pdic = initial
    try:
        payload = json.loads(raw_cache.decode("utf-8"))
        if not isinstance(payload, dict):
            return 0
        candidates = payload.get("review_candidates")
        if not isinstance(candidates, list) or any(
            not isinstance(row, dict) for row in candidates
        ):
            return 0
        saved = read_pdic(pdic)
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError):
        return 0
    if not _sources_current(
        project_page=page, cache=cache, pdic=pdic, section=section,
        cache_pdic_snapshot=initial, image_bytes=image_bytes,
        section_bytes=section_bytes,
    ):
        return 0

    candidate_ids = Counter(
        row.get("candidate_id") for row in candidates
        if isinstance(row.get("candidate_id"), str)
        and row.get("candidate_id")
    )
    xy_counts = Counter(
        (row.get("source_x"), row.get("source_y"))
        for row in candidates
        if type(row.get("source_x")) is int
        and type(row.get("source_y")) is int
    )
    pdic_counts = Counter((int(row.x), int(row.y)) for row in saved)
    saved_by_xy = {(int(row.x), int(row.y)): row for row in saved}
    witnessed = []
    for row in candidates:
        cid = row.get("candidate_id")
        x, y = row.get("source_x"), row.get("source_y")
        if (
            not isinstance(cid, str) or not cid
            or type(x) is not int or type(y) is not int
            or candidate_ids[cid] != 1
            or xy_counts[x, y] != 1
            or pdic_counts[x, y] != 1
            or row.get("selected") is not True
            or row.get("coordinate_space") != "source_image_pixels"
            or row.get("position_variant") != "refined"
            or not isinstance(row.get("word"), str)
            or row["word"].strip() != str(saved_by_xy[x, y].word).strip()
        ):
            continue
        section_key = (
            section_key_for_source_point(page, section, x, y)
            if section_bytes is not None else "whole-page"
        )
        if section_key is None:
            continue
        witnessed.append({
            "candidate_id": cid, "source_x": x, "source_y": y,
            "section_key": section_key,
        })
    if not witnessed:
        return 0
    record = {
        "format": _FORMAT, "project_key": str(project),
        "page_key": page.name,
        "cache_sha256": _sha(raw_cache), "pdic_sha256": _sha(raw_pdic),
        "section_sha256": _sha(section_bytes) if section_bytes is not None else None,
        "image_sha256": _sha(image_bytes),
        "witnesses": witnessed,
    }
    # Re-check all observed files immediately before publishing, and after
    # atomic publication; later mutations invalidate readers via byte hashes.
    if not _sources_current(
        project_page=page, cache=cache, pdic=pdic, section=section,
        cache_pdic_snapshot=initial, image_bytes=image_bytes,
        section_bytes=section_bytes,
    ):
        raise RuntimeError("OCR/PDIC/SECTION source changed before provenance publication")
    target = review_risk_witness_path(cache)
    write_text_atomic(target, json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    if not _sources_current(
        project_page=page, cache=cache, pdic=pdic, section=section,
        cache_pdic_snapshot=initial, image_bytes=image_bytes,
        section_bytes=section_bytes,
    ):
        raise RuntimeError("OCR/PDIC/SECTION source changed during provenance publication")
    return len(witnessed)


def load_review_risk_witness(
    cache_path: Path, candidate_id: str,
) -> ReviewRiskWitness | None:
    """Read only an already-published, still-current source-time witness.

    This sidecar is not cryptographic authorization or a human label. It only
    binds a writer-observed source revision to the saved file bytes. Never
    create a witness during review or trust a stale cache-supplied digest.
    """
    if not isinstance(candidate_id, str) or not candidate_id:
        return None
    cache = Path(cache_path)
    try:
        record = json.loads(review_risk_witness_path(cache).read_text("utf-8"))
        if not isinstance(record, dict) or record.get("format") != _FORMAT:
            return None
        project_key = record.get("project_key")
        page_key = record.get("page_key")
        if (
            not isinstance(project_key, str) or not project_key
            or not isinstance(page_key, str) or not page_key
            or Path(page_key).name != page_key
        ):
            return None
        project = Path(project_key).resolve()
        page = project / page_key
        if cache.resolve() != (ocr_cache_root(project) / f"{page.stem}.json").resolve():
            return None
        section = page_sections_read_path_for_image(page)
        if section.exists():
            if _sha(section.read_bytes()) != record.get("section_sha256"):
                return None
        elif record.get("section_sha256") is not None:
            return None
        if _sha(page.read_bytes()) != record.get("image_sha256"):
            return None
        pdic = pdic_path_for_image(page)
        snapshot = _snapshot(cache, pdic)
        if snapshot is None or (
            _sha(snapshot[0]) != record.get("cache_sha256")
            or _sha(snapshot[1]) != record.get("pdic_sha256")
        ):
            return None
        witnesses = record.get("witnesses")
        if not isinstance(witnesses, list):
            return None
        found = [row for row in witnesses
                 if isinstance(row, dict) and row.get("candidate_id") == candidate_id]
        if len(found) != 1:
            return None
        row = found[0]
        if type(row.get("source_x")) is not int or type(row.get("source_y")) is not int:
            return None
        section_key = (
            section_key_for_source_point(
                page, section, row["source_x"], row["source_y"]
            ) if section.exists() else "whole-page"
        )
        if section_key is None or section_key != row.get("section_key"):
            return None
        if not _sources_current(
            project_page=page, cache=cache, pdic=pdic, section=section,
            cache_pdic_snapshot=snapshot,
            image_bytes=page.read_bytes(),
            section_bytes=section.read_bytes() if section.exists() else None,
        ):
            return None
        return ReviewRiskWitness(
            project_key=str(project), page_key=page_key,
            section_key=section_key, candidate_id=candidate_id,
            source_x=row["source_x"], source_y=row["source_y"],
            cache_sha256=record["cache_sha256"],
            pdic_sha256=record["pdic_sha256"],
            section_sha256=record.get("section_sha256"),
        )
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        return None
