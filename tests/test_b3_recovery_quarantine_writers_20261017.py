"""R3 unresolved transactions block direct PDIC writes and pre-save editor writes."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.app import PictureCaptureApp
from picture_capture.formats import pdic_path, write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading_transactions import _recovery_path
from picture_capture.review_main_editor_sync import commit_proofread_entries


@pytest.mark.parametrize("marker_payload", [b"partial", b'{"rollback_required":true}'])
def test_shared_pdic_writer_refuses_pending_r3_marker(tmp_path, marker_payload):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-not-real-scan")
    path = pdic_path(page)
    write_pdic(path, [Entry("before", 10, 20)], 100, ("synthetic", "@", "@"))
    old = path.read_bytes()
    marker = _recovery_path(page)
    marker.write_bytes(marker_payload)
    with pytest.raises(RuntimeError, match="Unresolved R3 transaction"):
        write_pdic(path, [Entry("after", 10, 20)], 100, ("synthetic", "@", "@"))
    assert path.read_bytes() == old
    assert marker.read_bytes() == marker_payload


def test_review_commit_refuses_marker_before_mutating_entry_or_canvas(tmp_path):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-not-real-scan")
    entry = Entry("before", 10, 20)
    parent = SimpleNamespace(current_page=page, entries=[entry])
    review = SimpleNamespace(
        parent=parent,
        vars=[SimpleNamespace(get=lambda: "after")],
        _bound_row_entries=lambda: [entry],
    )
    marker = _recovery_path(page)
    marker.write_bytes(b"unresolved")
    with pytest.raises(RuntimeError, match="Unresolved R3 transaction"):
        commit_proofread_entries(review)
    assert entry.word == "before"
    assert marker.exists()


def test_shared_pdic_writer_unchanged_without_marker(tmp_path):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-not-real-scan")
    path = pdic_path(page)
    assert write_pdic(path, [Entry("original", 10, 20)], 100, ("synthetic", "@", "@"))
    assert not write_pdic(path, [Entry("original", 10, 20)], 100, ("synthetic", "@", "@"))


def test_deferred_checkbox_save_retains_snapshot_while_quarantined(tmp_path):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-not-real-scan")
    snapshot = (page, [], 100, ("synthetic", "@", "@"), 0)
    fake = SimpleNamespace(
        _deferred_save_job=None,
        _deferred_save_snapshot=snapshot,
        _deferred_save_page=page,
    )
    marker = _recovery_path(page)
    marker.write_bytes(b"unresolved")
    with pytest.raises(RuntimeError, match="Unresolved R3 transaction"):
        PictureCaptureApp._flush_deferred_page_save(fake)
    assert fake._deferred_save_snapshot is snapshot
    assert fake._deferred_save_page == page
    assert marker.exists()


def test_deferred_io_failure_keeps_exact_snapshot_for_retry(tmp_path, monkeypatch):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-not-real-scan")
    snapshot = (page, [Entry("before", 10, 20)], 100, ("synthetic", "@", "@"), 0)
    fake = SimpleNamespace(
        _deferred_save_job=None,
        _deferred_save_snapshot=snapshot,
        _deferred_save_page=page,
        project=None,
        _flush_pending_manual_override=lambda: None,
        _flush_proofreading_candidate_evidence=lambda: None,
        _flush_proofreading_add_evidence=lambda: None,
    )
    import picture_capture.app as app_module

    def fail_write(*_args, **_kwargs):
        raise OSError("synthetic storage failure")

    real_write = app_module.write_pdic
    monkeypatch.setattr(app_module, "write_pdic", fail_write)
    with pytest.raises(OSError, match="synthetic storage failure"):
        PictureCaptureApp._flush_deferred_page_save(fake)
    assert fake._deferred_save_snapshot is snapshot
    assert fake._deferred_save_page == page
    assert not pdic_path(page).exists()
    monkeypatch.setattr(app_module, "write_pdic", real_write)
    PictureCaptureApp._flush_deferred_page_save(fake)
    assert fake._deferred_save_snapshot is None
    assert fake._deferred_save_page is None
    assert pdic_path(page).exists()
