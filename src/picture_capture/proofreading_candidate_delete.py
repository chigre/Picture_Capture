"""Strict plan for one ReviewWindow OCR-owned candidate deletion.

This is a *persisted* operation, not a claim that candidate Undo is safe.
Do not mutate Entry, candidate selection or the Tk checkbox before all files
have been committed by proofreading_transactions.publish_owned_review_bundle.
Malformed/ambiguous sidecars and unsaved editorial changes fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json

from .proofreading_transactions import SavedSnapshot, publish_owned_review_bundle


@dataclass(frozen=True)
class CandidateDeletePlan:
    candidate_id: str
    pdic_bytes: bytes
    manual_bytes: bytes
    simplified_bytes: bytes | None


def prepare_candidate_delete(
    snapshot: SavedSnapshot, entry: Any, candidate: dict[str, Any],
) -> CandidateDeletePlan | None:
    """Prepare exact file bytes for *one uniquely owned* selected OCR entry."""
    cid = str(candidate.get("candidate_id") or "")
    if not cid or str(getattr(entry, "candidate_id", "") or "") != cid:
        return None
    if dict(snapshot.owner_ids).get(id(entry)) != cid:
        return None
    # Legacy OCR caches need not store a "selected" flag. The owned live
    # Entry is stronger evidence of selection; an explicit false still vetoes.
    if candidate.get("selected", True) is not True:
        return None
    matched = [value for key, value in snapshot.candidates if key == cid]
    if len(matched) != 1 or matched[0] != repr(candidate):
        return None

    try:
        original = snapshot.pdic_bytes.decode("utf-8")
        records = original.splitlines(keepends=True)
        idxs = []
        for i, line in enumerate(records):
            parts = line.strip("\r\n").split("#")
            if len(parts) < 8:
                return None
            if (
                parts[0] == str(entry.word)
                and int(parts[1]) == int(entry.x)
                and int(parts[2]) == int(entry.y)
            ):
                idxs.append(i)
        if len(idxs) != 1:
            return None
        target_pdic = "".join(
            line for i, line in enumerate(records) if i != idxs[0]
        ).encode("utf-8")

        if snapshot.manual_bytes is None:
            manual = {"version": 1, "overrides": {}}
        else:
            manual = json.loads(snapshot.manual_bytes.decode("utf-8"))
        if not isinstance(manual, dict) or not isinstance(manual.get("overrides"), dict):
            return None
        if str(manual.get("page") or snapshot.page.stem) != snapshot.page.stem:
            return None
        prior = manual["overrides"].get(cid)
        if prior is not None and (
            not isinstance(prior, dict) or prior.get("selected") is False
        ):
            return None
        manual["page"] = snapshot.page.stem
        manual["overrides"][cid] = {
            "selected": False,
            "word": str(entry.word),
            "engine": "review_delete",
        }
        target_manual = json.dumps(manual, ensure_ascii=False, indent=2).encode("utf-8")

        target_simplified = snapshot.simplified_bytes
        if target_simplified is not None:
            simplified = json.loads(target_simplified.decode("utf-8"))
            if not isinstance(simplified, dict) or not isinstance(simplified.get("entries"), list):
                return None
            matches = []
            for i, record in enumerate(simplified["entries"]):
                if not isinstance(record, dict):
                    return None
                x, y = int(record["x"]), int(record["y"])
                if x == int(entry.x) and y == int(entry.y):
                    matches.append(i)
            if len(matches) > 1:
                return None
            if matches:
                simplified["entries"].pop(matches[0])
                target_simplified = json.dumps(
                    simplified, ensure_ascii=False, indent=2,
                ).encode("utf-8")
    except (UnicodeError, ValueError, TypeError, KeyError, AttributeError):
        return None
    return CandidateDeletePlan(
        candidate_id=cid, pdic_bytes=target_pdic,
        manual_bytes=target_manual, simplified_bytes=target_simplified,
    )


def commit_candidate_delete(
    snapshot: SavedSnapshot, entry: Any, candidate: dict[str, Any],
) -> CandidateDeletePlan | None:
    """Return a plan only after every file committed; never change GUI state."""
    plan = prepare_candidate_delete(snapshot, entry, candidate)
    if plan is None:
        return None
    if not publish_owned_review_bundle(
        snapshot,
        pdic_bytes=plan.pdic_bytes,
        manual_bytes=plan.manual_bytes,
        simplified_bytes=plan.simplified_bytes,
    ):
        return None
    return plan
