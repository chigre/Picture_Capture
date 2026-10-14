"""Proofreading delete capture: opt-in, post-save, never alter user PDIC.

Only records a *provable* one-row deletion. Renames performed in the same save
are not assigned false provenance; future typed transactions will handle them.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from uuid import uuid4, uuid5, NAMESPACE_URL

from .formats import pdic_path, read_pdic, write_text_atomic
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
    )
    # Namespace journal by full relative page name, not just its stem.
    page_key = uuid5(NAMESPACE_URL, relative_page).hex
    journal = data_root(project_root) / "ProofreadingEvidence" / f"{page_key}.json"
    append_event(journal, event, pdic_file=new_file)
    return True
