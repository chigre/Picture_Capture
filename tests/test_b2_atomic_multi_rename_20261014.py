"""PC-CQ/B2: same-save multiple text edits are atomic and not gold labels.

This deliberately uses only synthetic PDICs. Arbitrary marker moves and
renames mixed with coordinate changes must still fail closed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading_capture import capture_saved_review_rename
from picture_capture.proofreading_events import (
    append_rename_batch, load_events, make_event, sha256_file,
)


def _case(root: Path):
    page = root / "page.png"
    page.write_bytes(b"synthetic scan payload")
    old = [
        Entry("old-a", 16, 24),
        Entry("old-b", 16, 68),
        Entry("same", 16, 110),
    ]
    write_pdic(pdic_path(page), old, 56, ("page", "@", "@"))
    return page, old


def _journal(root: Path):
    return next(
        f for f in (root / "ProofreadingEvidence").glob("*.json")
        if f.name != "project_identity.json"
    )


def test_multiple_verified_geometry_text_changes_are_one_atomic_journal(tmp_path):
    page, original = _case(tmp_path)
    # Order in saved PDIC is intentionally unrelated to before/after pairing.
    edited = [
        original[2], Entry("new-b", 16, 68), Entry("new-a", 16, 24),
    ]
    write_pdic(pdic_path(page), edited, 56, ("page", "@", "@"))
    saved_pdic = pdic_path(page).read_bytes()
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page, prior_pdic_entries=original,
    )
    assert pdic_path(page).read_bytes() == saved_pdic
    journal = _journal(tmp_path)
    events = load_events(journal)
    assert len(events) == 2
    assert [e["before"]["word"] for e in events] == ["old-a", "old-b"]
    assert [e["after"]["word"] for e in events] == ["new-a", "new-b"]
    assert len({e["entry_id"] for e in events}) == 2
    assert all(e["verification_status"] == "explicit_action_unverified_page" for e in events)
    assert all(e["candidate_id"] is None for e in events)
    assert all(e["pdic_sha256"] == sha256_file(pdic_path(page)) for e in events)
    assert not journal.with_name(journal.name + ".lock").exists()

    # A later same-position rename after reopening reuses that entity ID.
    before_next = read_pdic(pdic_path(page))
    write_pdic(
        pdic_path(page), [
            Entry("newer-a", 16, 24), Entry("same", 16, 110), Entry("newer-b", 16, 68)
        ], 56, ("page", "@", "@"),
    )
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page, prior_pdic_entries=before_next,
    )
    after = load_events(journal)
    assert len(after) == 4
    pairs = {}
    for e in after:
        pairs.setdefault((e["before"]["x"], e["before"]["y"]), set()).add(e["entry_id"])
    assert all(len(v) == 1 for v in pairs.values())


def test_batch_failure_never_publishes_half_of_the_same_save(tmp_path, monkeypatch):
    from picture_capture import proofreading_events

    page, original = _case(tmp_path)
    write_pdic(
        pdic_path(page),
        [Entry("new-a", 16, 24), Entry("new-b", 16, 68), original[2]],
        56, ("page", "@", "@"),
    )
    saved_bytes = pdic_path(page).read_bytes()

    def disk_failure(*args, **kwargs):
        raise OSError("simulated journal disk failure")

    with monkeypatch.context() as patcher:
        patcher.setattr(proofreading_events, "write_text_atomic", disk_failure)
        with pytest.raises(OSError, match="journal disk failure"):
            capture_saved_review_rename(
                project_root=tmp_path, page=page,
                prior_pdic_entries=original,
            )

    assert pdic_path(page).read_bytes() == saved_bytes
    journal = _journal(tmp_path) if any(
        p.name != "project_identity.json"
        for p in (tmp_path / "ProofreadingEvidence").glob("*.json")
    ) else None
    assert journal is None
    assert not list((tmp_path / "ProofreadingEvidence").glob("*.lock"))

    # Retry of the same saved diff must publish BOTH once or neither.
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page,
        prior_pdic_entries=original,
    )
    assert len(load_events(_journal(tmp_path))) == 2


def test_failed_batch_preserves_existing_journal_bytes(tmp_path, monkeypatch):
    from picture_capture import proofreading_events

    page, original = _case(tmp_path)
    # First save and journal record remain readable after a later failed batch.
    write_pdic(
        pdic_path(page),
        [Entry("edited-a", 16, 24), original[1], original[2]],
        56, ("page", "@", "@"),
    )
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page, prior_pdic_entries=original,
    )
    journal = _journal(tmp_path)
    journal_before = journal.read_bytes()
    prior = read_pdic(pdic_path(page))
    write_pdic(
        pdic_path(page),
        [Entry("edited-again", 16, 24), Entry("edited-b", 16, 68), original[2]],
        56, ("page", "@", "@"),
    )
    saved_pdic = pdic_path(page).read_bytes()
    with monkeypatch.context() as m:
        m.setattr(
            proofreading_events, "write_text_atomic",
            lambda *_a, **_kw: (_ for _ in ()).throw(OSError("disk full")),
        )
        with pytest.raises(OSError, match="disk full"):
            capture_saved_review_rename(
                project_root=tmp_path, page=page, prior_pdic_entries=prior,
            )
    assert journal.read_bytes() == journal_before
    assert pdic_path(page).read_bytes() == saved_pdic
    assert not journal.with_name(journal.name + ".lock").exists()
    assert len(load_events(journal)) == 1


def test_changed_coordinates_duplicates_and_co_saved_other_actions_are_unknown(tmp_path):
    page, original = _case(tmp_path)
    combos = [
        [Entry("new-a", 17, 24), Entry("new-b", 16, 68), original[2]],
        [Entry("new-a", 16, 24), Entry("new-b", 16, 68)],
        [Entry("new-a", 16, 24), Entry("new-b", 16, 68),
         original[2], Entry("added", 20, 144)],
        [Entry("new-a", 16, 24), Entry("new-b", 16, 24), original[2]],
    ]
    for rows in combos:
        write_pdic(pdic_path(page), rows, 56, ("page", "@", "@"))
        assert not capture_saved_review_rename(
            project_root=tmp_path, page=page,
            prior_pdic_entries=original,
        )
    assert not (tmp_path / "ProofreadingEvidence").exists()


def test_duplicate_or_stale_atomic_batch_rejected_without_any_write(tmp_path):
    page, old = _case(tmp_path)
    target = pdic_path(page)
    journal = tmp_path / "ProofreadingEvidence" / "test.json"
    digest = sha256_file(target)
    base = {
        "page_id": "project/page.png", "action": "rename",
        "pdic_sha256": digest, "entry_id": "stable-entry",
        "before": {"word": "old-a", "x": 16, "y": 24},
        "after": {"word": "new-a", "x": 16, "y": 24},
    }
    first = make_event(**base)
    duplicate = make_event(**base)
    with pytest.raises(ValueError, match="Duplicate operation or entry"):
        append_rename_batch(journal, [first, duplicate], pdic_file=target)
    assert not journal.exists()
    second = make_event(**{**base, "entry_id": "other"})
    target.write_bytes(target.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Current PDIC"):
        append_rename_batch(journal, [first, second], pdic_file=target)
    assert not journal.exists()
    assert not journal.with_name(journal.name + ".lock").exists()


def test_atomic_batch_never_accepts_verification_or_mixed_sources(tmp_path):
    page, _ = _case(tmp_path)
    pdic = pdic_path(page)
    journal = tmp_path / "ProofreadingEvidence" / "test.json"
    sha = sha256_file(pdic)
    a = make_event(
        page_id="same", action="rename", entry_id="a",
        before={"word": "a", "x": 12, "y": 22},
        after={"word": "A", "x": 12, "y": 22}, pdic_sha256=sha,
    )
    b = make_event(
        page_id="other-page", action="rename", entry_id="b",
        before={"word": "b", "x": 12, "y": 62},
        after={"word": "B", "x": 12, "y": 62}, pdic_sha256=sha,
    )
    with pytest.raises(ValueError, match="Mixed or unproven"):
        append_rename_batch(journal, [a, b], pdic_file=pdic)
    b["page_id"] = "same"
    b["action"] = "verify"
    with pytest.raises(ValueError, match="Mixed or unproven"):
        append_rename_batch(journal, [a, b], pdic_file=pdic)
    assert not journal.exists()
