"""B2 visual verification source lookup and cross-process journal integrity."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from picture_capture.formats import pdic_path, write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading_capture import _project_identity
from picture_capture.proofreading_events import (
    append_event, load_events, make_event, sha256_file,
)
from picture_capture.proofreading_verification import verify_saved_action
from picture_capture.proofreading_verify_ui import (
    actionable_saved_events, journal_for_existing_page,
)


def _project(tmp_path):
    page = tmp_path / "page.png"
    page.write_bytes(b"original scanned page bytes")
    pdic = pdic_path(page)
    write_pdic(pdic, [Entry("new", 30, 55)], 90, ("page", "@", "@"))
    _project_identity(tmp_path)
    assert journal_for_existing_page(tmp_path, page) is None
    event = make_event(
        page_id="project/page.png", action="rename",
        before={"word": "old", "x": 30, "y": 55},
        after={"word": "new", "x": 30, "y": 55},
        entry_id="stable-1", pdic_sha256=sha256_file(pdic),
        image_sha256=sha256_file(page),
    )
    from picture_capture.project_storage import data_root
    from uuid import uuid5, NAMESPACE_URL
    journal = (
        data_root(tmp_path) / "ProofreadingEvidence"
        / f"{uuid5(NAMESPACE_URL, 'page.png').hex}.json"
    )
    append_event(journal, event, pdic_file=pdic)
    return page, pdic, journal, event


def test_verification_dialog_is_read_only_until_human_confirms(tmp_path):
    page, pdic, journal, event = _project(tmp_path)
    previous = (page.read_bytes(), pdic.read_bytes(), journal.read_bytes())
    assert journal_for_existing_page(tmp_path, page) == journal
    rows = actionable_saved_events(journal, pdic, page)
    assert [row["operation_id"] for row in rows] == [event["operation_id"]]
    assert (page.read_bytes(), pdic.read_bytes(), journal.read_bytes()) == previous
    verify_saved_action(
        journal=journal, pdic_file=pdic, image_file=page,
        operation_id=event["operation_id"], judgment="correct_headword",
        explicitly_confirmed=True,
    )
    assert actionable_saved_events(journal, pdic, page) == []


def test_stale_scans_and_pdic_are_not_offered_for_visual_confirmation(tmp_path):
    page, pdic, journal, event = _project(tmp_path)
    page.write_bytes(b"changed scanned page")
    assert actionable_saved_events(journal, pdic, page) == []
    page.write_bytes(b"original scanned page bytes")
    pdic.write_bytes(b"changed by another editing session")
    assert actionable_saved_events(journal, pdic, page) == []


def test_ocr_lineage_requires_current_matching_cache_for_user_review(tmp_path):
    page, pdic, journal, event = _project(tmp_path)
    entry = make_event(
        page_id="project/page.png", action="select",
        before=None, after={"word": "new", "x": 30, "y": 55},
        entry_id="entry-ocr", candidate_id="cid-1",
        pdic_sha256=sha256_file(pdic), image_sha256=sha256_file(page),
        ocr_signature="original-ocr-cache",
        final_snapshot_sha256="a" * 64,
    )
    append_event(journal, entry, pdic_file=pdic)
    assert len(actionable_saved_events(journal, pdic, page)) == 1
    cache = tmp_path / "ocr.json"
    cache.write_text(json.dumps({"signature": "different"}), encoding="utf-8")
    assert len(actionable_saved_events(journal, pdic, page, ocr_cache=cache)) == 1
    cache.write_text(json.dumps({"signature": "original-ocr-cache"}), encoding="utf-8")
    assert len(actionable_saved_events(journal, pdic, page, ocr_cache=cache)) == 2


def test_no_identity_or_corrupt_project_identity_never_creates_a_journal(tmp_path):
    page = tmp_path / "page.png"
    page.write_bytes(b"image")
    assert journal_for_existing_page(tmp_path, page) is None
    assert not (tmp_path / "ProofreadingEvidence").exists()
    from picture_capture.project_storage import data_root
    identity = data_root(tmp_path) / "ProofreadingEvidence" / "project_identity.json"
    identity.parent.mkdir(parents=True, exist_ok=True)
    identity.write_text('{"format":"untrusted","project_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')
    assert journal_for_existing_page(tmp_path, page) is None


def test_existing_interprocess_lock_refuses_any_writer_without_corruption(tmp_path):
    page, pdic, journal, before = _project(tmp_path)
    contents = journal.read_bytes()
    lock = journal.with_name(f"{journal.name}.lock")
    lock.mkdir()
    try:
        next_event = make_event(
            page_id="project/page.png", action="verify",
            before={"reviewed_operation_id": before["operation_id"]},
            after={"judgment": "correct_headword"},
            entry_id="stable-1", pdic_sha256=sha256_file(pdic),
            image_sha256=sha256_file(page),
            verification_status="verified", explicitly_verified=True,
        )
        with pytest.raises(OSError, match="locked"):
            append_event(journal, next_event, pdic_file=pdic)
        assert journal.read_bytes() == contents
    finally:
        lock.rmdir()
    append_event(journal, next_event, pdic_file=pdic)
    assert len(load_events(journal)) == 2


def test_journal_lock_is_released_after_failing_publication(tmp_path, monkeypatch):
    from picture_capture import proofreading_events as mod
    page, pdic, journal, prior = _project(tmp_path)
    original = journal.read_bytes()
    event = make_event(
        page_id="project/page.png", action="verify",
        before={"reviewed_operation_id": prior["operation_id"]},
        after={"judgment": "not_headword"},
        entry_id="stable-1", pdic_sha256=sha256_file(pdic),
        verification_status="verified", explicitly_verified=True,
    )
    original_writer = mod.write_text_atomic
    def failure(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(mod, "write_text_atomic", failure)
    with pytest.raises(OSError, match="disk full"):
        append_event(journal, event, pdic_file=pdic)
    assert journal.read_bytes() == original
    assert not journal.with_name(journal.name + ".lock").exists()
    monkeypatch.setattr(mod, "write_text_atomic", original_writer)
    append_event(journal, event, pdic_file=pdic)
    assert len(load_events(journal)) == 2


def test_explicit_confirmation_ui_controls_have_no_automatic_approval():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    source = (root / "proofreading_verify_ui.py").read_text(encoding="utf-8")
    app = (root / "app.py").read_text(encoding="utf-8")
    assert "self.confirmed = tk.BooleanVar(value=False)" in source
    assert "self._preview_valid = False" in source
    assert "self._preview_valid and self.confirmed.get()" in source
    assert "messagebox.askyesno(" in source
    assert "explicitly_confirmed=True" in source
    assert "review_window.save(redraw_main=False)" in source
    assert "proofreading_event_capture" in source
    assert 'text="核验记录"' in app
    assert "command=self._open_proofreading_visual_verification" in app


def test_visual_verification_does_not_open_after_noop_review_save(tmp_path, monkeypatch):
    """The user cannot confirm an old record over still-unsaved editor text."""
    from types import SimpleNamespace
    from picture_capture import proofreading_verify_ui as ui

    page, pdic, journal, event = _project(tmp_path)
    opened = []
    messages = []
    row = Entry("saved", 30, 55)
    parent = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path), current_page=page,
        settings=SimpleNamespace(proofreading_event_capture=True),
        current_index=0, _foreground_batch_state=lambda index: "idle",
        _paddle_cache_path=lambda: None,
    )
    review = SimpleNamespace(
        parent=parent, _filter_rows_active=False,
        vars=[SimpleNamespace(get=lambda: "not yet saved")],
        _bound_row_entries=lambda: [row],
        save=lambda **kwargs: None,  # simulated refusal to claim pending page
    )
    monkeypatch.setattr(ui.messagebox, "showinfo",
                        lambda title, message, **kwargs: messages.append(message))
    monkeypatch.setattr(ui, "ProofreadingVisualVerificationDialog",
                        lambda *args, **kwargs: opened.append(kwargs))
    ui.open_visual_verification(review)
    assert not opened
    assert messages
    assert len(load_events(journal)) == 1


def test_visual_verification_opens_after_provably_committed_review(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from picture_capture import proofreading_verify_ui as ui

    page, pdic, journal, event = _project(tmp_path)
    opened = []
    row = Entry("saved", 30, 55)
    parent = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path), current_page=page,
        settings=SimpleNamespace(proofreading_event_capture=True),
        current_index=0, _foreground_batch_state=lambda index: "idle",
        _paddle_cache_path=lambda: None,
    )
    def commit(**kwargs):
        row.word = "committed"
    review = SimpleNamespace(
        parent=parent, _filter_rows_active=False,
        vars=[SimpleNamespace(get=lambda: "committed")],
        _bound_row_entries=lambda: [row], save=commit,
    )
    monkeypatch.setattr(ui, "ProofreadingVisualVerificationDialog",
                        lambda *args, **kwargs: opened.append(kwargs))
    ui.open_visual_verification(review)
    assert len(opened) == 1
    assert opened[0]["page"] == page
    assert len(load_events(journal)) == 1


def test_visual_verification_fails_closed_on_unstable_row_bindings(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from picture_capture import proofreading_verify_ui as ui

    page, pdic, journal, event = _project(tmp_path)
    opened = []
    messages = []
    parent = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path), current_page=page,
        settings=SimpleNamespace(proofreading_event_capture=True),
        current_index=0, _foreground_batch_state=lambda index: "idle",
        _paddle_cache_path=lambda: None,
    )
    review = SimpleNamespace(
        parent=parent, _filter_rows_active=False, vars=[],
        _bound_row_entries=lambda: [Entry("saved", 30, 55)],
        save=lambda **kwargs: None,
    )
    monkeypatch.setattr(ui.messagebox, "showinfo",
                        lambda title, message, **kwargs: messages.append(message))
    monkeypatch.setattr(ui, "ProofreadingVisualVerificationDialog",
                        lambda *args, **kwargs: opened.append(kwargs))
    ui.open_visual_verification(review)
    assert not opened
    assert messages
