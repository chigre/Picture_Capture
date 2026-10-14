"""Proofreading delete capture: opt-in, post-save, never alter user PDIC.

Only records a *provable* one-row deletion. Renames performed in the same save
are not assigned false provenance; future typed transactions will handle them.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from uuid import uuid4, uuid5, NAMESPACE_URL

from .formats import pdic_path, read_pdic
from .project_storage import data_root
from .proofreading_events import append_event, make_event, sha256_file

IDENTITY_FORMAT = "picture-capture-proofreading-project-identity-v1"


def _project_identity(project_root: Path) -> str:
    """Persist project identity across project moves, only after explicit opt-in."""
    identity = data_root(project_root) / "ProofreadingEvidence" / "project_identity.json"
    if identity.is_file():
        raw = json.loads(identity.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("format") != IDENTITY_FORMAT:
            raise ValueError("Unknown proofreading project identity format")
        value = str(raw.get("project_id") or "")
        if len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("Invalid proofreading project identity")
        return value
    uid = uuid4().hex
    # One UI process per project is expected. If an identity is damaged,
    # never overwrite it, and report the failure rather than resetting IDs.
    identity.parent.mkdir(parents=True, exist_ok=True)
    try:
        with identity.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps({"format": IDENTITY_FORMAT, "project_id": uid}))
    except FileExistsError:
        return _project_identity(project_root)
    return uid


def _triples(entries: list[object]) -> list[tuple[str, int, int]]:
    return [(str(entry.word), int(entry.x), int(entry.y)) for entry in entries]


def capture_saved_review_deletion(
    *, project_root: Path, page: Path, prior_pdic_entries: list[object],
    expected_deleted: tuple[str, int, int],
    deleted_candidate_id: str | None, candidate_id_unique: bool,
) -> bool:
    """Capture a just-saved deletion only if disk proves exactly one row removed.

    Caller invokes this only after a successful PDIC save and manual-selection
    flush. Returns False if the snapshot also contains renames/moves or an
    ambiguous duplicate. A warning about dropped evidence is the caller's job;
    the PDIC is authoritative regardless of logging success.
    """
    project_root, page = Path(project_root), Path(page)
    existing = Counter(_triples(prior_pdic_entries))
    new_file = pdic_path(page)
    current = Counter(_triples(read_pdic(new_file)))
    removed, added = existing - current, current - existing
    if added or sum(removed.values()) != 1 or sum(existing.values()) - sum(current.values()) != 1:
        return False
    (word, x, y), = removed.keys()
    if (word, x, y) != expected_deleted:
        return False
    if existing[(word, x, y)] != 1:
        # Could be either of two indistinguishable rows; don't claim identity.
        return False

    project_id = _project_identity(project_root)
    relative_page = page.resolve().relative_to(project_root.resolve()).as_posix()
    page_id = f"{project_id}/{relative_page}"
    # Candidate identity is stable only if the candidate ID was unique on this
    # page. An OCR-unlinked manual row gets no fabricated stable entry identity.
    candidate = str(deleted_candidate_id or "") if candidate_id_unique else ""
    entry_id = uuid5(NAMESPACE_URL, f"{page_id}|{candidate}").hex if candidate else None
    sha = sha256_file(new_file)
    if sha is None:
        raise OSError("Saved PDIC disappeared before evidence capture")
    event = make_event(
        page_id=page_id, action="delete",
        before={"word": word, "x": x, "y": y}, after=None,
        pdic_sha256=sha, candidate_id=candidate or None, entry_id=entry_id,
        image_sha256=sha256_file(page),
    )
    # Namespace journal by full relative page name, not just its stem.
    page_key = uuid5(NAMESPACE_URL, relative_page).hex
    journal = data_root(project_root) / "ProofreadingEvidence" / f"{page_key}.json"
    append_event(journal, event, pdic_file=new_file)
    return True


def capture_saved_review_rename(
    *, project_root: Path, page: Path, prior_pdic_entries: list[object],
) -> bool:
    """Log exactly one committed text-only edit, never inferred edits in bulk.

    Both prior and after snapshots come from the on-disk PDIC. Unique original
    XY positions are the stable identity across word changes and SECTION
    reorder; ambiguous duplicate coordinates or changed coordinates are
    rejected. OCR ancestry is deliberately unknown until independently linked.
    """
    project_root, page = Path(project_root), Path(page)
    old = _triples(prior_pdic_entries)
    saved_file = pdic_path(page)
    current = _triples(read_pdic(saved_file))
    if len(old) != len(current) or not old:
        return False
    if len({(x, y) for _, x, y in old}) != len(old):
        return False
    if len({(x, y) for _, x, y in current}) != len(current):
        return False
    old_map = {(x, y): word for word, x, y in old}
    new_map = {(x, y): word for word, x, y in current}
    if old_map.keys() != new_map.keys():
        return False
    changed = [
        ((x, y), old_word, new_map[(x, y)])
        for (x, y), old_word in old_map.items()
        if old_word != new_map[(x, y)]
    ]
    if len(changed) != 1:
        return False
    ((x, y), before_word, after_word), = changed
    project_id = _project_identity(project_root)
    relative_page = page.resolve().relative_to(project_root.resolve()).as_posix()
    page_id = f"{project_id}/{relative_page}"
    # Stable through renames and list reordering, but never claim an OCR ID.
    entry_id = uuid5(NAMESPACE_URL, f"{page_id}|xy|{x}|{y}").hex
    saved_hash = sha256_file(saved_file)
    if saved_hash is None:
        raise OSError("PDIC disappeared after saved review rename")
    event = make_event(
        page_id=page_id, action="rename",
        before={"word": before_word, "x": x, "y": y},
        after={"word": after_word, "x": x, "y": y},
        pdic_sha256=saved_hash, entry_id=entry_id,
        image_sha256=sha256_file(page),
    )
    page_key = uuid5(NAMESPACE_URL, relative_page).hex
    journal = data_root(project_root) / "ProofreadingEvidence" / f"{page_key}.json"
    append_event(journal, event, pdic_file=saved_file)
    return True


def capture_saved_candidate_selection(
    *, project_root: Path, page: Path, prior_pdic_entries: list[object],
    expected_entry: tuple[str, int, int], candidate_id: str,
    selected: bool, candidate_id_unique: bool, manual_selection_path: Path,
) -> bool:
    """Persist a unique explicit checkbox action after BOTH source files commit.

    All other edits, replaced OCR alternatives, missing/stale manual overrides,
    duplicate candidate identities, or multi-click coalescing are not evidence
    of an individually attributable toggle.
    """
    if not candidate_id or not candidate_id_unique:
        return False
    old = Counter(_triples(prior_pdic_entries))
    pdic = pdic_path(page)
    current = Counter(_triples(read_pdic(pdic)))
    if selected:
        expected_before, expected_after = old, old + Counter([expected_entry])
        if old[expected_entry]:
            return False
    else:
        if old[expected_entry] != 1:
            return False
        expected_before, expected_after = old, old - Counter([expected_entry])
    if old != expected_before or current != expected_after:
        return False
    try:
        override = json.loads(Path(manual_selection_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(override, dict) or not isinstance(override.get("overrides"), dict):
        return False
    row = override["overrides"].get(candidate_id)
    if not isinstance(row, dict) or row.get("selected") is not selected:
        return False
    if row.get("engine") != "manual_checkbox":
        return False
    if str(row.get("word", "")) != expected_entry[0]:
        return False
    if str(override.get("page", "")) != page.stem:
        return False

    project_root = Path(project_root)
    project_id = _project_identity(project_root)
    relative_page = Path(page).resolve().relative_to(project_root.resolve()).as_posix()
    page_id = f"{project_id}/{relative_page}"
    entry_id = uuid5(NAMESPACE_URL, f"{page_id}|{candidate_id}").hex
    word, x, y = expected_entry
    row_data = {"word": word, "x": x, "y": y}
    sha = sha256_file(pdic)
    if sha is None:
        raise OSError("Saved PDIC disappeared before candidate evidence capture")
    event = make_event(
        page_id=page_id, action="select" if selected else "deselect",
        before=None if selected else row_data,
        after=row_data if selected else None,
        pdic_sha256=sha, entry_id=entry_id, candidate_id=candidate_id,
        image_sha256=sha256_file(page),
    )
    key = uuid5(NAMESPACE_URL, relative_page).hex
    append_event(
        data_root(project_root) / "ProofreadingEvidence" / f"{key}.json",
        event, pdic_file=pdic,
    )
    return True
