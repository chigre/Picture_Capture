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

from .transactions import SavedSnapshot, publish_owned_review_bundle


@dataclass(frozen=True)
class CandidateDeletePlan:
    candidate_id: str
    pdic_bytes: bytes
    manual_bytes: bytes
    simplified_bytes: bytes | None


def _unique_json_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous manual fields instead of dropping a human JSON value."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object member in proofreading sidecar")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> Any:
    raise ValueError(f"Non-finite JSON constant in proofreading sidecar: {value}")


def _load_unambiguous_json(raw: bytes) -> Any:
    """Never reserialize a sidecar that would lose duplicate human fields."""
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_json_members,
        parse_constant=_reject_nonfinite_json,
    )


def prepare_candidate_delete(
    snapshot: SavedSnapshot, entry: Any, candidate: dict[str, Any],
) -> CandidateDeletePlan | None:
    """Prepare exact file bytes for *one uniquely owned* selected OCR entry."""
    cid = str(candidate.get("candidate_id") or "")
    if not cid or str(getattr(entry, "candidate_id", "") or "") != cid:
        return None
    # The on-disk manual override belongs to one candidate, never to a
    # shared candidate_id attached to two live Entry objects. A plain dict
    # lookup would silently accept the second owner and deselect both.
    owners = dict(snapshot.owner_ids)
    if (len(owners) != len(snapshot.owner_ids)
            or owners.get(id(entry)) != cid
            or sum(owner == cid for owner in owners.values()) != 1):
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
            manual = _load_unambiguous_json(snapshot.manual_bytes)
        if not isinstance(manual, dict) or not isinstance(manual.get("overrides"), dict):
            return None
        if str(manual.get("page") or snapshot.page.stem) != snapshot.page.stem:
            return None
        prior = manual["overrides"].get(cid)
        if prior is not None:
            # A preexisting explicit override must still describe this
            # exact selected word. Do not silently turn a stale/foreign
            # override for the same candidate_id into a deletion.
            if (not isinstance(prior, dict)
                    or prior.get("selected") is not True
                    or ("word" in prior
                        and prior["word"] != str(entry.word))
                    or set(prior) - {"selected", "word", "engine"}):
                # This candidate owns the selection state, NOT arbitrary
                # extra human annotations in the existing override. A
                # replacement would silently discard those extra bytes.
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
            simplified = _load_unambiguous_json(target_simplified)
            if (not isinstance(simplified, dict)
                    or simplified.get("format") != "picture_capture_simplified_review"
                    or simplified.get("format_version") != 1
                    or simplified.get("page") != snapshot.page.stem
                    or not isinstance(simplified.get("entries"), list)):
                return None
            matches = []
            for i, record in enumerate(simplified["entries"]):
                if not isinstance(record, dict):
                    return None
                x, y = int(record["x"]), int(record["y"])
                if x == int(entry.x) and y == int(entry.y):
                    # Coordinates alone do not prove that the simplified
                    # record belongs to the selected headword; a later
                    # manual edit or stale sidecar can reuse the same key.
                    if record.get("source_word") != str(entry.word):
                        return None
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
