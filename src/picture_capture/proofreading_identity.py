"""Conservative replay of explicitly recorded proofreading Entry identities.

A proof is a contiguous journal chain of exact PDIC SHA-256 snapshots. This
module does not infer identity from row order, OCR guesses, word similarity or
coordinate proximity. Unknown/ambiguous provenance refuses identity reuse.
Existing PDIC, Profile and SECTION formats are never modified.
"""
from __future__ import annotations

from itertools import groupby
from typing import Any, Mapping


def _triple(value: object) -> tuple[str, int, int] | None:
    if not isinstance(value, dict):
        return None
    word, x, y = value.get("word"), value.get("x"), value.get("y")
    if not isinstance(word, str) or type(x) is not int or type(y) is not int:
        return None
    return (word, x, y)


def owned_entries_at_snapshot(
    events: list[dict[str, Any]], *, page_id: str, pdic_sha256: str,
    image_sha256: str | None = None,
    required_before: tuple[tuple[str, int, int], ...] = (),
) -> tuple[bool, dict[tuple[str, int, int], str]]:
    """Return proven identities at the current *pre-edit* PDIC snapshot.

    The newest committed event must match the caller's actual saved PDIC.
    Earlier ownership survives unrelated edits only across adjacent journal
    commits explicitly carrying the prior PDIC digest. Older journals without
    this link still support the immediately matching snapshot, not guesses.
    """
    edits = [row for row in events if row.get("action") != "verify"]
    if not edits:
        return True, {}
    if edits[-1].get("page_id") != page_id or edits[-1].get("pdic_sha256") != pdic_sha256:
        return False, {}

    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for _, segment in groupby(
        edits, key=lambda row: (row.get("page_id"), row.get("pdic_sha256")),
    ):
        block = list(segment)
        groups.append((str(block[0].get("pdic_sha256")), block))
    # Walk the exact ancestor chain, refusing any gap or unproven predecessor.
    start = len(groups) - 1
    while start:
        _, block = groups[start]
        priors = {row.get("prior_pdic_sha256") for row in block}
        if len(priors) != 1:
            break
        predecessor = next(iter(priors))
        if (not isinstance(predecessor, str) or len(predecessor) != 64
                or any(c not in "0123456789abcdef" for c in predecessor)):
            break
        if groups[start - 1][0] != predecessor:
            break
        start -= 1

    # An older owned row on the same physical coordinate is a collision risk
    # if an unrecorded edit breaks the snapshot chain. Never silently mint a
    # new XY-derived identity for that requested row: report unknown instead.
    if start and required_before:
        changed_xy = {(x, y) for _, x, y in required_before}
        for _, older in groups[:start]:
            for row in older:
                if row.get("page_id") != page_id:
                    continue
                after = _triple(row.get("after"))
                if after is not None and after[1:] in changed_xy:
                    return False, {}

    owners: dict[tuple[str, int, int], str] = {}
    for _, block in groups[start:]:
        changes: list[tuple[tuple[str, int, int] | None,
                            tuple[str, int, int] | None, str | None]] = []
        before_seen: set[tuple[str, int, int]] = set()
        after_seen: set[tuple[str, int, int]] = set()
        for row in block:
            if row.get("page_id") != page_id:
                return False, {}
            historical_image = row.get("image_sha256")
            if (image_sha256 is not None and historical_image is not None
                    and historical_image != image_sha256):
                return False, {}
            action = row.get("action")
            if action not in {"add", "delete", "rename", "move", "select", "deselect"}:
                return False, {}
            old, new = _triple(row.get("before")), _triple(row.get("after"))
            if (old is None and new is None) or (
                action in {"move", "rename"} and (old is None or new is None)
            ):
                return False, {}
            if old is not None:
                if old in before_seen:
                    return False, {}
                before_seen.add(old)
            if new is not None:
                if new in after_seen:
                    return False, {}
                after_seen.add(new)
            owner = row.get("entry_id")
            if new is not None and (not isinstance(owner, str) or not owner):
                return False, {}
            if old in owners and (not isinstance(owner, str) or owners[old] != owner):
                return False, {}
            changes.append((old, new, owner))
        for _, new, owner in changes:
            if new in owners and new not in before_seen and owners[new] != owner:
                return False, {}
        # Update simultaneously, so disjoint multi-rename events share a single
        # journal snapshot without introducing an order-dependent assignment.
        for old, _, _ in changes:
            if old is not None:
                owners.pop(old, None)
        for _, new, owner in changes:
            if new is not None and owner is not None:
                owners[new] = owner
    return True, owners
