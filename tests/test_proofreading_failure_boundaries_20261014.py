"""B2 fail-closed UI save and local journal recovery boundaries (headless)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.app import PictureCaptureApp
from picture_capture.formats import pdic_path, write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.proofreading_events import (
    append_event, load_events, make_event, sha256_file,
)


def _page(tmp_path):
    page = tmp_path / "one.png"
    page.write_bytes(b"test source image")
    pdic = pdic_path(page)
    write_pdic(pdic, [Entry("old", 10, 20)], 100, ("one", "@", "@"))
    return page, pdic


def test_main_save_disk_failure_cannot_flush_manual_override_or_evidence(tmp_path, monkeypatch):
    page, pdic = _page(tmp_path)
    from picture_capture import app as app_module

    calls: list[str] = []
    instance = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path),
        current_page=page, image=SimpleNamespace(width=100),
        _deferred_save_job=None,
        entries=[Entry("edited", 10, 20)],
        pages_tuple=lambda: ("one", "@", "@"),
        _sort_entries_reading_order=lambda: None,
        _flush_pending_manual_override=lambda: calls.append("override"),
        _flush_proofreading_candidate_evidence=lambda: calls.append("candidate"),
        _flush_proofreading_add_evidence=lambda: calls.append("add"),
    )
    before = pdic.read_bytes()

    def fail_write(*args, **kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(app_module, "write_pdic", fail_write)
    with pytest.raises(OSError, match="disk full"):
        PictureCaptureApp.save_pdic(instance, silent=True, sync_editors=False)
    assert calls == []
    assert pdic.read_bytes() == before


def test_deferred_ocr_save_disk_failure_never_flushes_evidence_or_sidecar(tmp_path, monkeypatch):
    page, pdic = _page(tmp_path)
    from picture_capture import app as app_module

    calls: list[str] = []
    obj = SimpleNamespace(
        _deferred_save_job=None,
        _deferred_save_snapshot=(
            page, [Entry("edited", 10, 20)], 100,
            ("one", "@", "@"), 0,
        ),
        _deferred_save_page=page,
        project=SimpleNamespace(root=tmp_path, images=[page]),
        _flush_pending_manual_override=lambda: calls.append("override"),
        _flush_proofreading_candidate_evidence=lambda: calls.append("candidate"),
        _flush_proofreading_add_evidence=lambda: calls.append("add"),
    )
    snapshot = pdic.read_bytes()

    def fail_write(*args, **kwargs):
        raise OSError("simulated interrupted PDIC save")

    monkeypatch.setattr(app_module, "write_pdic", fail_write)
    with pytest.raises(OSError, match="interrupted"):
        PictureCaptureApp._flush_deferred_page_save(obj)
    assert calls == []
    assert pdic.read_bytes() == snapshot



def test_manual_override_save_failure_blocks_all_evidence_after_pdic_commit(tmp_path):
    """The PDIC may be durable, but an uncommitted override is not evidence."""
    page, pdic = _page(tmp_path)
    from picture_capture.formats import read_pdic
    calls: list[str] = []

    def failed_override():
        calls.append("override")
        raise OSError("manual override disk full")

    instance = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path),
        current_page=page, image=SimpleNamespace(width=100),
        _deferred_save_job=None,
        entries=[Entry("edited", 10, 20)],
        pages_tuple=lambda: ("one", "@", "@"),
        _sort_entries_reading_order=lambda: None,
        _flush_pending_manual_override=failed_override,
        _flush_proofreading_candidate_evidence=lambda: calls.append("candidate"),
        _flush_proofreading_add_evidence=lambda: calls.append("add"),
    )
    with pytest.raises(OSError, match="manual override disk full"):
        PictureCaptureApp.save_pdic(instance, silent=True, sync_editors=False)
    assert [entry.word for entry in read_pdic(pdic)] == ["edited"]
    assert calls == ["override"]
    assert not (tmp_path / "ProofreadingEvidence").exists()


def test_deferred_override_failure_never_attributes_saved_pdic_as_verified_action(tmp_path):
    page, pdic = _page(tmp_path)
    calls: list[str] = []

    def failed_override():
        calls.append("override")
        raise OSError("sidecar permission denied")

    obj = SimpleNamespace(
        _deferred_save_job=None,
        _deferred_save_snapshot=(
            page, [Entry("edited", 10, 20)], 100,
            ("one", "@", "@"), 0,
        ),
        _deferred_save_page=page,
        project=SimpleNamespace(root=tmp_path, images=[page]),
        _refresh_word_fill_check_from_line_count=lambda *args, **kwargs: None,
        _update_page_row=lambda *args, **kwargs: None,
        _flush_pending_manual_override=failed_override,
        _flush_proofreading_candidate_evidence=lambda: calls.append("candidate"),
        _flush_proofreading_add_evidence=lambda: calls.append("add"),
    )
    with pytest.raises(OSError, match="sidecar permission denied"):
        PictureCaptureApp._flush_deferred_page_save(obj)
    assert calls == ["override"]
    assert not (tmp_path / "ProofreadingEvidence").exists()

def test_page_navigation_discards_queued_candidate_audit_without_writing(tmp_path):
    page, pdic = _page(tmp_path)
    next_page = tmp_path / "two.png"
    next_page.write_bytes(b"other page")
    obj = SimpleNamespace(
        current_page=next_page,
        project=SimpleNamespace(root=tmp_path),
        settings=AppSettings(proofreading_event_capture=True),
        _pending_evidence_toggle=(
            page, [Entry("old", 10, 20)],
            ("new", 10, 50), "cid-1", True,
            tmp_path / "one_manual_selection.json", None, None,
        ),
    )
    PictureCaptureApp._flush_proofreading_candidate_evidence(obj)
    assert "_pending_evidence_toggle" not in obj.__dict__
    assert not (tmp_path / "ProofreadingEvidence").exists()


def test_atomic_journal_failure_does_not_corrupt_previous_evidence(tmp_path, monkeypatch):
    from picture_capture import proofreading_events as journal_module

    page, pdic = _page(tmp_path)
    journal = tmp_path / "events.json"
    first = make_event(
        page_id="project/one", action="rename",
        before={"word": "old"}, after={"word": "new"},
        entry_id="row1", pdic_sha256=sha256_file(pdic),
    )
    append_event(journal, first, pdic_file=pdic)
    previous = journal.read_bytes()
    second = make_event(
        page_id="project/one", action="verify",
        before={"reviewed_operation_id": first["operation_id"]},
        after={"judgment": "correct_headword"},
        entry_id="row1", pdic_sha256=sha256_file(pdic),
        verification_status="verified", explicitly_verified=True,
    )

    def fail_atomic(*args, **kwargs):
        raise OSError("simulated interruption writing evidence journal")

    monkeypatch.setattr(journal_module, "write_text_atomic", fail_atomic)
    with pytest.raises(OSError, match="interruption"):
        append_event(journal, second, pdic_file=pdic)
    assert journal.read_bytes() == previous
    assert load_events(journal) == [first]
