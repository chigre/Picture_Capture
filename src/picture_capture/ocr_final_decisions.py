"""Trace the actual persisted PDIC decisions back to OCR candidates.

The existing OCR cache is a *pre-Page-Understanding* observation cache, not a
record of final markers. This small sidecar is generated ONLY after PDIC is
successfully written. It never changes the PDIC format or user overrides.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .formats import read_pdic, write_text_atomic


def final_decisions_path(cache_path: Path) -> Path:
    return cache_path.with_name(f"{cache_path.stem}_final_decisions.json")


def pdic_snapshot(entries: Iterable[Any]) -> list[list[Any]]:
    """Ordered, literal PDIC fields; absence of OCR metadata is intentional."""
    return [[str(e.word).replace("#", "＃").replace("\r", " ").replace("\n", " ").strip(),
             int(e.x), int(e.y)] for e in entries]


def _snapshot_digest(rows: list[list[Any]]) -> str:
    raw = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_int(value: Any, fallback: int = -1000000) -> int:
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        return fallback


def build_final_decisions(
    detected: list[Any],
    saved: list[Any],
    ocr_candidates: list[dict[str, Any]],
    *,
    cache_signature: str = "",
    tolerance: int = 12,
) -> dict[str, Any]:
    """One-to-one candidate-to-PDIC provenance, never fuzzy many-to-one links.

    Match unique detector candidate IDs first, but ONLY if geometrically near.
    If an ID is absent/duplicated (e.g. rounded-Y collisions), match by actual
    position and word. Ambiguous matches are left unmatched, never guessed.
    The persisted PDIC coordinates are always authoritative.
    """
    saved_rows = pdic_snapshot(saved)
    ids = Counter(str(getattr(e, "candidate_id", "") or "") for e in detected)
    used: set[int] = set()
    source_by_saved: dict[int, Any] = {}
    for index, stored in enumerate(saved):
        options = [
            (j, e) for j, e in enumerate(detected) if j not in used
            and int(e.x) == int(stored.x) and int(e.y) == int(stored.y)
            and str(e.word).replace("#", "＃").strip() == str(stored.word).strip()
        ]
        if len(options) == 1:
            j, e = options[0]
            source_by_saved[index] = e
            used.add(j)

    tolerance = max(3, int(tolerance))
    links: dict[int, int] = {}
    used_final: set[int] = set()
    id_to_indices: dict[str, list[int]] = {}
    for i, e in source_by_saved.items():
        cid = str(getattr(e, "candidate_id", "") or "")
        if cid and ids[cid] == 1:
            id_to_indices.setdefault(cid, []).append(i)

    # Final review candidates include alternate (original/anchor) Y variants.
    # Never link two variants to the same saved final marker.
    candidate_id_counts = Counter(
        str(c.get("candidate_id", "") or "") for c in ocr_candidates
    )
    for index, cand in enumerate(ocr_candidates):
        cid = str(cand.get("candidate_id", "") or "")
        rows = id_to_indices.get(cid, [])
        if not cid or candidate_id_counts[cid] != 1 or len(rows) != 1:
            continue
        j = rows[0]
        stored = saved[j]
        if j in used_final:
            continue
        if (
            abs(int(stored.y) - _safe_int(cand.get("source_y"))) <= tolerance * 4
            and abs(int(stored.x) - _safe_int(cand.get("source_x"))) <= max(24, tolerance * 4)
        ):
            links[index] = j
            used_final.add(j)

    for i, cand in enumerate(ocr_candidates):
        if i in links:
            continue
        # Quantized IDs may collide on dense pages or between refined/anchor
        # variants. Never guess which of those checkboxes inherited a PDIC row.
        cid = str(cand.get("candidate_id", "") or "")
        if cid and candidate_id_counts[cid] > 1:
            continue
        x, y = _safe_int(cand.get("source_x")), _safe_int(cand.get("source_y"))
        word = str(cand.get("word", "") or "").strip()
        matches: list[tuple[int, int]] = []
        for j, stored in enumerate(saved):
            if j in used_final:
                continue
            dx, dy = abs(int(stored.x) - x), abs(int(stored.y) - y)
            if dx > max(24, tolerance * 3) or dy > tolerance:
                continue
            distance = dx + 2 * dy
            if word and str(stored.word).strip() == word:
                distance = max(0, distance - 5)
            matches.append((distance, j))
        matches.sort()
        # A close runner-up is ambiguous: do NOT steal another word's line.
        if matches and (len(matches) == 1 or matches[1][0] - matches[0][0] > 4):
            j = matches[0][1]
            links[i] = j
            used_final.add(j)

    candidates: list[dict[str, Any]] = []
    for i, cand in enumerate(ocr_candidates):
        j = links.get(i)
        original = bool(cand.get("selected", False))
        final = saved[j] if j is not None else None
        final_origin = source_by_saved.get(j) if j is not None else None
        moved = bool(
            final is not None
            and (int(final.x) != _safe_int(cand.get("source_x"))
                 or int(final.y) != _safe_int(cand.get("source_y")))
        )
        candidates.append({
            "candidate_id": str(cand.get("candidate_id", "") or ""),
            "ocr_selected": original,
            "final_selected": j is not None,
            "final_pdic_index": j,
            "final_source_x": int(final.x) if final is not None else None,
            "final_source_y": int(final.y) if final is not None else None,
            "final_word": str(final.word) if final is not None else None,
            "final_entry_source": str(getattr(final_origin, "ocr_source", "") or "") if final is not None else None,
            "final_issue_type": str(getattr(final_origin, "issue_type", "") or "") if final is not None else None,
            "final_manually_selected": bool(getattr(final_origin, "manually_selected", False)) if final is not None else None,
            "ocr_manual_override": bool(cand.get("manual_override", False)),
            "final_status": (
                "moved_by_post_ocr" if moved else "retained"
            ) if j is not None else ("removed_after_ocr" if original else "rejected"),
            "ocr_decision_reason": str(cand.get("decision_reason", "") or ""),
        })

    final_only = []
    for j, stored in enumerate(saved):
        if j in used_final:
            continue
        origin = source_by_saved.get(j)
        final_only.append({
            "pdic_index": j,
            "word": str(stored.word), "x": int(stored.x), "y": int(stored.y),
            "source": str(getattr(origin, "ocr_source", "") or "unmatched_final"),
            "issue_type": str(getattr(origin, "issue_type", "") or ""),
            "reason": "post_ocr_layout_or_symbol" if (
                origin is not None and str(getattr(origin, "ocr_source", "")).startswith("page_understanding:")
            ) else "final_without_unambiguous_ocr_match",
        })

    return {
        "format": "picture-capture-final-ocr-decisions-v1",
        "ocr_cache_signature": str(cache_signature),
        "pdic_snapshot_sha256": _snapshot_digest(saved_rows),
        "pdic_rows": saved_rows,
        "candidate_decisions": candidates,
        "final_only": final_only,
        "summary": {
            "ocr_candidates": len(ocr_candidates),
            "final_markers": len(saved),
            "linked": len(links),
            "post_ocr_removed": sum(
                1 for c in candidates if c["final_status"] == "removed_after_ocr"
            ),
            "post_ocr_moved": sum(
                1 for c in candidates if c["final_status"] == "moved_by_post_ocr"
            ),
            "unmatched_final": len(final_only),
        },
    }


def record_final_decisions(
    cache_path: Path, pdic_file: Path, detected: list[Any], *,
    tolerance: int = 12,
) -> dict[str, Any]:
    """Read back actual PDIC after successful write, then atomically audit."""
    saved = read_pdic(pdic_file)
    cache: dict[str, Any] = {}
    if cache_path.exists():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cache = raw
        except (OSError, ValueError, TypeError):
            pass
    candidates = [
        row for row in (cache.get("review_candidates") or [])
        if isinstance(row, dict)
    ]
    report = build_final_decisions(
        detected, saved, candidates,
        cache_signature=str(cache.get("signature", "")),
        tolerance=tolerance,
    )
    target = final_decisions_path(cache_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(target, json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return report["summary"]


def load_current_final_decisions(cache_path: Path, pdic_file: Path) -> dict[str, Any] | None:
    """Reject an audit from before a manual PDIC edit, not a cached guess."""
    path = final_decisions_path(cache_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != "picture-capture-final-ocr-decisions-v1":
            return None
        # A forced OCR refresh can regenerate proposals without changing the
        # PDIC. Do not attach old decisions to a different source OCR run.
        if not cache_path.exists():
            return None
        source_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(source_cache, dict) or str(source_cache.get("signature", "")) != str(data.get("ocr_cache_signature", "")):
            return None
        saved_rows = pdic_snapshot(read_pdic(pdic_file))
        if data.get("pdic_snapshot_sha256") != _snapshot_digest(saved_rows):
            return None
        if data.get("pdic_rows") != saved_rows:
            return None
        return data
    except (OSError, ValueError, TypeError, KeyError):
        return None


def apply_final_review_annotations(
    candidates: list[dict[str, Any]], audit: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Annotate OCR review rows; never replace editable OCR proposal fields."""
    if not audit or len(candidates) != len(audit.get("candidate_decisions", [])):
        return candidates
    result = []
    for item, decision in zip(candidates, audit["candidate_decisions"]):
        if str(item.get("candidate_id", "")) != str(decision.get("candidate_id", "")):
            return candidates  # Rebuilt OCR cache: sidecar cannot be trusted.
        row = dict(item)
        row["final_decision"] = dict(decision)
        result.append(row)
    return result
