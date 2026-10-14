"""B2 UI boundary: no evidence until saving the intended page succeeds."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.app import PictureCaptureApp
from picture_capture.formats import pdic_path, write_pdic
from picture_capture.models import AppSettings, Entry


def _state(tmp_path, *, enabled=True):
    page = tmp_path / "first.png"
    page.write_bytes(b"image")
    previous = [Entry("previous", 5, 15)]
    write_pdic(pdic_path(page), previous, 100, ("first", "@", "@"))
    fake = SimpleNamespace(
        settings=AppSettings(proofreading_event_capture=enabled),
        project=SimpleNamespace(root=tmp_path),
        current_page=page,
    )
    return fake, page, previous


def _evidence_files(tmp_path):
    return [
        item
        for item in (tmp_path / "ProofreadingEvidence").glob("*.json")
        if item.name != "project_identity.json"
    ] if (tmp_path / "ProofreadingEvidence").is_dir() else []


def test_manual_add_stage_without_disk_commit_creates_no_event(tmp_path):
    app, page, entries = _state(tmp_path)
    PictureCaptureApp._queue_proofreading_add_evidence(app, 22, 33)
    PictureCaptureApp._flush_proofreading_add_evidence(app)
    assert _evidence_files(tmp_path) == []
    assert len(entries) == 1


def test_manual_add_stage_successful_pdic_save_creates_local_event(tmp_path):
    app, page, entries = _state(tmp_path)
    PictureCaptureApp._queue_proofreading_add_evidence(app, 22, 33)
    write_pdic(
        pdic_path(page), entries + [Entry("new word", 22, 33)],
        100, ("first", "@", "@"),
    )
    saved = pdic_path(page).read_bytes()
    PictureCaptureApp._flush_proofreading_add_evidence(app)
    assert pdic_path(page).read_bytes() == saved
    assert len(_evidence_files(tmp_path)) == 1


def test_manual_add_queue_is_invalidated_by_multiple_clicks(tmp_path):
    app, page, entries = _state(tmp_path)
    PictureCaptureApp._queue_proofreading_add_evidence(app, 22, 33)
    PictureCaptureApp._queue_proofreading_add_evidence(app, 40, 60)
    # Even if disk ends with one newly added row, two clicks make provenance ambiguous.
    write_pdic(
        pdic_path(page), entries + [Entry("only one", 22, 33)],
        100, ("first", "@", "@"),
    )
    PictureCaptureApp._flush_proofreading_add_evidence(app)
    assert _evidence_files(tmp_path) == []


def test_manual_add_queue_never_records_after_switching_pages(tmp_path):
    app, page, entries = _state(tmp_path)
    PictureCaptureApp._queue_proofreading_add_evidence(app, 22, 33)
    write_pdic(
        pdic_path(page), entries + [Entry("new word", 22, 33)],
        100, ("first", "@", "@"),
    )
    other_page = tmp_path / "next.png"
    other_page.write_bytes(b"second")
    app.current_page = other_page
    PictureCaptureApp._flush_proofreading_add_evidence(app)
    assert _evidence_files(tmp_path) == []


def test_manual_add_opt_out_and_legacy_settings_do_not_journal(tmp_path):
    app, page, entries = _state(tmp_path, enabled=False)
    PictureCaptureApp._queue_proofreading_add_evidence(app, 22, 33)
    assert "_pending_evidence_add" not in app.__dict__
    write_pdic(
        pdic_path(page), entries + [Entry("user", 22, 33)],
        100, ("first", "@", "@"),
    )
    PictureCaptureApp._flush_proofreading_add_evidence(app)
    assert _evidence_files(tmp_path) == []
    del app.settings
    PictureCaptureApp._queue_proofreading_add_evidence(app, 22, 33)
    assert "_pending_evidence_add" not in app.__dict__


def test_saved_manual_add_then_reopen_does_not_repeat_an_event(tmp_path):
    app, page, entries = _state(tmp_path)
    PictureCaptureApp._queue_proofreading_add_evidence(app, 22, 33)
    write_pdic(
        pdic_path(page), entries + [Entry("added", 22, 33)],
        100, ("first", "@", "@"),
    )
    PictureCaptureApp._flush_proofreading_add_evidence(app)
    before = _evidence_files(tmp_path)[0].read_bytes()
    app2 = SimpleNamespace(settings=app.settings, project=app.project, current_page=page)
    PictureCaptureApp._flush_proofreading_add_evidence(app2)
    assert _evidence_files(tmp_path)[0].read_bytes() == before
