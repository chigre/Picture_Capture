"""PC-CQ/B2 #483: replay only operation-owned entry identities from matching snapshots."""
from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from picture_capture.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading_capture import (
    _project_identity, capture_saved_review_rename,
)
from picture_capture.proofreading_events import (
    append_event, load_events, make_event, sha256_file,
)
from picture_capture.project_storage import data_root


def _owned_move(tmp_path):
    page = tmp_path / "page.png"
    page.write_bytes(b"synthetic-image-identity")
    original = pdic_path(page)
    before = [Entry("alpha", 10, 20), Entry("beta", 50, 80)]
    write_pdic(original, before, 100, ("page", "@", "@"))
    moved = [Entry("alpha", 11, 27), Entry("beta", 50, 80)]
    write_pdic(original, moved, 100, ("page", "@", "@"))
    page_id = f"{_project_identity(tmp_path)}/page.png"
    journal = data_root(tmp_path) / "ProofreadingEvidence" / (
        uuid5(NAMESPACE_URL, "page.png").hex + ".json"
    )
    event = make_event(
        page_id=page_id, action="move",
        before={"word": "alpha", "x": 10, "y": 20},
        after={"word": "alpha", "x": 11, "y": 27},
        entry_id="owned-alpha-event", pdic_sha256=sha256_file(original),
        image_sha256=sha256_file(page),
    )
    append_event(journal, event, pdic_file=original)
    return page, original, journal


def test_rename_after_explicit_move_keeps_operation_owned_identity_across_reopen(tmp_path):
    page, pdic, journal = _owned_move(tmp_path)
    previous = read_pdic(pdic)
    digest = sha256_file(pdic)
    write_pdic(
        pdic, [Entry("alpha-fixed", 11, 27), Entry("beta", 50, 80)],
        100, ("page", "@", "@"),
    )
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page,
        prior_pdic_entries=previous, prior_pdic_sha256=digest,
    )
    events = load_events(journal)
    assert len(events) == 2
    assert events[-1]["entry_id"] == events[0]["entry_id"] == "owned-alpha-event"
    assert events[-1]["verification_status"] == "explicit_action_unverified_page"

    # Simulate reopening the project: no runtime Entry reference survives.
    previous = read_pdic(pdic)
    digest = sha256_file(pdic)
    write_pdic(
        pdic, [Entry("alpha-final", 11, 27), Entry("beta", 50, 80)],
        100, ("page", "@", "@"),
    )
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page,
        prior_pdic_entries=previous, prior_pdic_sha256=digest,
    )
    assert [e["entry_id"] for e in load_events(journal)] == [
        "owned-alpha-event", "owned-alpha-event", "owned-alpha-event",
    ]


def test_unmatched_prior_digest_refuses_guess_and_preserves_journal(tmp_path):
    page, pdic, journal = _owned_move(tmp_path)
    before = read_pdic(pdic)
    journal_before = journal.read_bytes()
    write_pdic(
        pdic, [Entry("alpha-fixed", 11, 27), Entry("beta", 50, 80)],
        100, ("page", "@", "@"),
    )
    assert not capture_saved_review_rename(
        project_root=tmp_path, page=page,
        prior_pdic_entries=before, prior_pdic_sha256="0" * 64,
    )
    assert journal.read_bytes() == journal_before


def test_ambiguous_owned_identity_is_not_replaced_by_xy_guess(tmp_path):
    page, pdic, journal = _owned_move(tmp_path)
    first = load_events(journal)[0]
    duplicate_owner = make_event(
        page_id=first["page_id"], action="move",
        before={"word": "alpha", "x": 10, "y": 20},
        after={"word": "alpha", "x": 11, "y": 27},
        entry_id="different-owner", pdic_sha256=sha256_file(pdic),
    )
    append_event(journal, duplicate_owner, pdic_file=pdic)
    previous = read_pdic(pdic)
    digest = sha256_file(pdic)
    snapshot = journal.read_bytes()
    write_pdic(
        pdic, [Entry("alpha-fixed", 11, 27), Entry("beta", 50, 80)],
        100, ("page", "@", "@"),
    )
    assert not capture_saved_review_rename(
        project_root=tmp_path, page=page,
        prior_pdic_entries=previous, prior_pdic_sha256=digest,
    )
    assert journal.read_bytes() == snapshot
