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


def test_review_window_passes_real_precommit_snapshot_to_owned_id_replay(tmp_path):
    from types import SimpleNamespace
    from picture_capture.app import ReviewWindow
    from picture_capture.models import AppSettings

    page, pdic, journal = _owned_move(tmp_path)
    parent = SimpleNamespace(
        current_page=page, project=SimpleNamespace(root=tmp_path),
        settings=AppSettings(proofreading_event_capture=True),
        _paddle_cache_path=lambda: None,
        status_var=SimpleNamespace(set=lambda _: None),
    )
    review = SimpleNamespace(parent=parent)
    previous = ReviewWindow._review_evidence_before_save(review)
    assert review.__dict__["_review_evidence_prior_pdic_sha256"] == sha256_file(pdic)
    write_pdic(pdic, [Entry("alpha-edited", 11, 27), Entry("beta", 50, 80)],
               100, ("page", "@", "@"))
    ReviewWindow._review_evidence_after_save(review, previous)
    assert load_events(journal)[-1]["entry_id"] == "owned-alpha-event"


def test_review_window_never_attaches_pre_edit_snapshot_to_other_page(tmp_path):
    from types import SimpleNamespace
    from picture_capture.app import ReviewWindow
    from picture_capture.models import AppSettings

    page, pdic, journal = _owned_move(tmp_path)
    parent = SimpleNamespace(
        current_page=page, project=SimpleNamespace(root=tmp_path),
        settings=AppSettings(proofreading_event_capture=True),
        _paddle_cache_path=lambda: None,
        status_var=SimpleNamespace(set=lambda _: None),
    )
    review = SimpleNamespace(parent=parent)
    previous = ReviewWindow._review_evidence_before_save(review)
    source_journal = journal.read_bytes()
    other = tmp_path / "second.png"
    other.write_bytes(b"different page")
    write_pdic(pdic_path(other), [Entry("alpha-edited", 11, 27),
                                 Entry("beta", 50, 80)], 100,
               ("second", "page", "@"))
    parent.current_page = other
    ReviewWindow._review_evidence_after_save(review, previous)
    assert journal.read_bytes() == source_journal
    other_journal = data_root(tmp_path) / "ProofreadingEvidence" / (
        uuid5(NAMESPACE_URL, "second.png").hex + ".json"
    )
    assert not other_journal.exists()


def test_owned_identity_survives_unrelated_committed_rename_and_reopen(tmp_path):
    page, pdic, journal = _owned_move(tmp_path)

    def change(words):
        previous, digest = read_pdic(pdic), sha256_file(pdic)
        write_pdic(pdic, [Entry(words[0], 11, 27), Entry(words[1], 50, 80)],
                   100, ("page", "@", "@"))
        assert capture_saved_review_rename(
            project_root=tmp_path, page=page,
            prior_pdic_entries=previous, prior_pdic_sha256=digest,
        )

    change(("alpha", "beta-fixed"))  # The tracked alpha is untouched.
    change(("alpha-fixed", "beta-fixed"))
    change(("alpha-final", "beta-final"))  # Multi-rename, shared atomic commit.
    events = load_events(journal)
    alpha_events = [e for e in events if e["after"] and e["after"]["x"] == 11]
    assert len(alpha_events) == 3
    assert all(e["entry_id"] == "owned-alpha-event" for e in alpha_events)
    assert all(e["verification_status"] == "explicit_action_unverified_page"
               for e in events)
    assert all(e.get("prior_pdic_sha256") for e in events[1:])


def test_unobserved_pdic_edit_breaks_proven_snapshot_chain(tmp_path):
    page, pdic, journal = _owned_move(tmp_path)
    # No evidence event records this independent on-disk mutation.
    write_pdic(pdic, [Entry("alpha", 11, 27), Entry("outside", 50, 80)],
               100, ("page", "@", "@"))
    previous, digest = read_pdic(pdic), sha256_file(pdic)
    old_journal = journal.read_bytes()
    write_pdic(pdic, [Entry("alpha-fixed", 11, 27),
                      Entry("outside", 50, 80)], 100, ("page", "@", "@"))
    assert not capture_saved_review_rename(
        project_root=tmp_path, page=page,
        prior_pdic_entries=previous, prior_pdic_sha256=digest,
    )
    assert journal.read_bytes() == old_journal


def test_source_image_drift_blocks_identity_reuse(tmp_path):
    page, pdic, journal = _owned_move(tmp_path)
    previous, digest = read_pdic(pdic), sha256_file(pdic)
    before = journal.read_bytes()
    page.write_bytes(b"source-image-replaced")
    write_pdic(pdic, [Entry("alpha-fixed", 11, 27),
                      Entry("beta", 50, 80)], 100, ("page", "@", "@"))
    assert not capture_saved_review_rename(
        project_root=tmp_path, page=page,
        prior_pdic_entries=previous, prior_pdic_sha256=digest,
    )
    assert journal.read_bytes() == before


def test_broken_ancestry_does_not_mint_new_xy_id_over_prior_moved_owner(tmp_path):
    page, pdic, journal = _owned_move(tmp_path)
    existing = read_pdic(pdic)
    # Simulate another older capture path that produced a valid event but did
    # not yet store the additive predecessor field.
    write_pdic(
        pdic, [Entry("alpha", 11, 27), Entry("beta-legacy", 50, 80)],
        100, ("page", "@", "@"),
    )
    previous_commit = make_event(
        page_id=load_events(journal)[0]["page_id"], action="rename",
        before={"word": "beta", "x": 50, "y": 80},
        after={"word": "beta-legacy", "x": 50, "y": 80},
        entry_id="beta-owned", pdic_sha256=sha256_file(pdic),
        image_sha256=sha256_file(page),
    )
    append_event(journal, previous_commit, pdic_file=pdic)
    prior_rows, prior_sha = read_pdic(pdic), sha256_file(pdic)
    before_journal = journal.read_bytes()
    write_pdic(
        pdic, [Entry("alpha-renamed", 11, 27),
               Entry("beta-legacy", 50, 80)],
        100, ("page", "@", "@"),
    )
    assert not capture_saved_review_rename(
        project_root=tmp_path, page=page,
        prior_pdic_entries=prior_rows, prior_pdic_sha256=prior_sha,
    )
    assert journal.read_bytes() == before_journal
