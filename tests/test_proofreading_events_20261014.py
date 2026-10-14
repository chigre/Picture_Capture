"""B2: proofreading events must never be confused with verified gold labels."""
from __future__ import annotations

import json

import pytest

from picture_capture.proofreading_events import (
    EVENT_FORMAT, append_event, audit_events, load_events, make_event,
    sha256_file,
)


def _case(tmp_path):
    pdic = tmp_path / "page.PDIC"
    pdic.write_bytes(b"original manual PDIC")
    journal = tmp_path / "proofreading_events.json"
    return pdic, journal


def _event(pdic, **overrides):
    kwargs = {
        "page_id": "page-00001", "action": "rename",
        "before": {"word": "lemna", "x": 10, "y": 30},
        "after": {"word": "lemma", "x": 10, "y": 30},
        "entry_id": "entry-abc",
        "pdic_sha256": sha256_file(pdic),
    }
    kwargs.update(overrides)
    return make_event(**kwargs)


def test_edit_is_not_automatically_promoted_to_verified_label(tmp_path):
    pdic, journal = _case(tmp_path)
    entry = _event(pdic)
    assert entry["verification_status"] == "explicit_action_unverified_page"
    with pytest.raises(ValueError, match="not automatically a verified label"):
        _event(pdic, verification_status="verified")
    assert not journal.exists()


def test_event_journal_is_local_atomic_and_does_not_change_pdic(tmp_path):
    pdic, journal = _case(tmp_path)
    before = pdic.read_bytes()
    event = _event(pdic)
    append_event(journal, event, pdic_file=pdic)
    assert pdic.read_bytes() == before
    assert load_events(journal) == [event]
    raw = json.loads(journal.read_text(encoding="utf-8"))
    assert raw["format"] == EVENT_FORMAT
    with pytest.raises(ValueError, match="Duplicate"):
        append_event(journal, event, pdic_file=pdic)
    assert load_events(journal) == [event]


def test_mutated_pdic_rejects_outdated_event_without_writing(tmp_path):
    pdic, journal = _case(tmp_path)
    event = _event(pdic)
    pdic.write_bytes(b"re-edited PDIC")
    with pytest.raises(ValueError, match="Current PDIC"):
        append_event(journal, event, pdic_file=pdic)
    assert not journal.exists()


def test_corrupt_event_journal_never_silently_erased(tmp_path):
    pdic, journal = _case(tmp_path)
    journal.write_text("invalid-json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        append_event(journal, _event(pdic), pdic_file=pdic)
    assert journal.read_text(encoding="utf-8") == "invalid-json"


def test_event_audit_explicit_verified_and_stale_are_separate(tmp_path):
    pdic, journal = _case(tmp_path)
    source = _event(pdic, candidate_id="c-1")
    verified = _event(
        pdic, action="verify",
        before={"reviewed_operation_id": source["operation_id"]},
        after={"judgment": "correct_headword"},
        verification_status="verified",
        explicitly_verified=True, candidate_id="c-1",
    )
    inferred = _event(
        pdic, action="add", verification_status="inferred",
        entry_id="entry-b", candidate_id=None,
    )
    append_event(journal, source, pdic_file=pdic)
    append_event(journal, verified, pdic_file=pdic)
    append_event(journal, inferred, pdic_file=pdic)
    result = audit_events(
        load_events(journal), current_pdic_sha256=sha256_file(pdic),
        current_ocr_signature=None,
    )
    assert result["current_verified_records_requiring_link_audit"] == 1
    assert result["training_labels_exported"] == 0
    assert result["not_training_ready"] == 2
    pdic.write_bytes(b"edited again")
    stale = audit_events(
        load_events(journal), current_pdic_sha256=sha256_file(pdic),
        current_ocr_signature=None,
    )
    assert stale["stale_events"] == 3
    assert stale["current_verified_records_requiring_link_audit"] == 0


def test_event_audit_fails_open_to_unknown_not_gold_when_ocr_changes(tmp_path):
    pdic, journal = _case(tmp_path)
    source = _event(pdic, candidate_id="c-1", ocr_signature="ocr-v1")
    event = _event(
        pdic, action="verify",
        before={"reviewed_operation_id": source["operation_id"]},
        after={"judgment": "correct_headword"},
        verification_status="verified",
        explicitly_verified=True, candidate_id="c-1", ocr_signature="ocr-v1",
    )
    append_event(journal, source, pdic_file=pdic)
    append_event(journal, event, pdic_file=pdic)
    result = audit_events(
        load_events(journal), current_pdic_sha256=sha256_file(pdic),
        current_ocr_signature="ocr-v2",
    )
    assert result["stale_events"] == 2
    assert result["training_labels_exported"] == 0


def test_journal_rejects_false_predecessor_even_when_postsave_pdic_matches(tmp_path):
    pdic, journal = _case(tmp_path)
    first = _event(pdic)
    append_event(journal, first, pdic_file=pdic)
    before = journal.read_bytes()
    second = _event(pdic, before={"word": "lemma", "x": 10, "y": 30},
                    after={"word": "lemma2", "x": 10, "y": 30})
    second["prior_pdic_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="predecessor"):
        append_event(journal, second, pdic_file=pdic)
    assert journal.read_bytes() == before


def test_atomic_multi_rename_rejects_mixed_or_stale_predecessors(tmp_path):
    from picture_capture.proofreading_events import append_rename_batch
    pdic, journal = _case(tmp_path)
    first = _event(pdic)
    append_event(journal, first, pdic_file=pdic)
    saved = journal.read_bytes()
    one = _event(pdic, before={"word": "one", "x": 10, "y": 20},
                 after={"word": "ONE", "x": 10, "y": 20},
                 entry_id="first-owner")
    two = _event(pdic, before={"word": "two", "x": 20, "y": 30},
                 after={"word": "TWO", "x": 20, "y": 30},
                 entry_id="second-owner")
    one["prior_pdic_sha256"] = "f" * 64
    two["prior_pdic_sha256"] = "e" * 64
    with pytest.raises(ValueError, match="Mixed"):
        append_rename_batch(journal, [one, two], pdic_file=pdic)
    assert journal.read_bytes() == saved
    two["prior_pdic_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="predecessor"):
        append_rename_batch(journal, [one, two], pdic_file=pdic)
    assert journal.read_bytes() == saved
