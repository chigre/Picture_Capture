"""G1 fail-first: an R3 marker must quarantine *before* mutating UI state.

Path.exists() follows symlinks. With a dangling R3 marker link, the
shared PDIC writer now refuses publication, but the main save, deferred
save and ReviewWindow editor commit still use exists() *before* invoking
non-idempotent editors, manual-source checks and human sidecar capture.
The preflight must be fail closed, not merely the eventual disk write.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.app import PictureCaptureApp
from picture_capture.models import Entry
from picture_capture.proofreading import deferred_save, main_editor_sync
from picture_capture.proofreading.transactions import _recovery_path


def _dangling_marker(tmp_path):
    page = tmp_path / "001.png"
    page.write_bytes(b"synthetic-no-private-page")
    marker = _recovery_path(page)
    try:
        marker.symlink_to("nonexistent-recovery.json")
    except (OSError, NotImplementedError):
        pytest.skip("OS cannot construct symlinks")
    assert marker.is_symlink() and not marker.exists()
    return page, marker


def test_app_save_rejects_dangling_marker_before_manual_preflight(tmp_path, monkeypatch):
    page, marker = _dangling_marker(tmp_path)
    calls = []
    def manual_check(*args):
        calls.append("manual")
        raise AssertionError("must not consult or mutate manual state while R3 is held")
    monkeypatch.setattr(
        "picture_capture.ui.review_selection_workflow.verify_pending_manual_source",
        manual_check,
    )
    fake = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, images=[page]),
        current_page=page, image=SimpleNamespace(width=100),
    )
    with pytest.raises(RuntimeError, match="(R3|marker|事务|恢复)"):
        PictureCaptureApp.save_pdic(fake)
    assert calls == []
    assert marker.is_symlink()


def test_deferred_save_rejects_dangling_marker_before_manual_preflight(tmp_path, monkeypatch):
    page, marker = _dangling_marker(tmp_path)
    calls = []
    def manual_check(*args):
        calls.append("manual")
        raise AssertionError("deferred save preflight must quarantine first")
    monkeypatch.setattr(deferred_save, "verify_pending_manual_source", manual_check)
    entries = [Entry("甲", 10, 20)]
    snapshot = (page, entries, 100, (page.stem, "@", "@"), 0)
    fake = SimpleNamespace(
        _deferred_save_job=None,
        _deferred_save_snapshot=snapshot,
        _deferred_save_page=page,
    )
    def forbidden_write(*_a):
        raise AssertionError("must never write under R3 marker")
    with pytest.raises(RuntimeError, match="(R3|marker|事务|恢复)"):
        deferred_save.flush_deferred_page_save(
            fake, write_pdic=forbidden_write, pdic_path=lambda _: tmp_path / "001.pdic",
        )
    assert calls == []
    assert fake._deferred_save_snapshot is snapshot
    assert fake._deferred_save_page == page
    assert marker.is_symlink()


def test_review_editor_commit_rejects_dangling_marker_before_entry_change(tmp_path):
    page, marker = _dangling_marker(tmp_path)
    entry = Entry("甲", 10, 20)
    sidecar_calls = []
    review = SimpleNamespace(
        parent=SimpleNamespace(current_page=page, entries=[entry]),
        vars=[SimpleNamespace(get=lambda: "乙")],
        _bound_row_entries=lambda: [entry],
        _rendered_page_stem="001",
        _capture_simplified_edits=lambda _stem: sidecar_calls.append("called"),
    )
    with pytest.raises(RuntimeError, match="(R3|marker|事务|恢复)"):
        main_editor_sync.commit_proofread_entries(review)
    assert entry.word == "甲"
    assert sidecar_calls == []
    assert marker.is_symlink()


def test_normal_marker_still_rejects_before_review_entry_change(tmp_path):
    page = tmp_path / "001.png"
    page.write_bytes(b"synthetic-no-private-page")
    marker = _recovery_path(page)
    marker.write_bytes(b"unresolved")
    entry = Entry("甲", 10, 20)
    review = SimpleNamespace(
        parent=SimpleNamespace(current_page=page, entries=[entry]),
        vars=[SimpleNamespace(get=lambda: "乙")],
        _bound_row_entries=lambda: [entry],
    )
    with pytest.raises(RuntimeError, match="R3"):
        main_editor_sync.commit_proofread_entries(review)
    assert entry.word == "甲"


def test_unmarked_review_editor_commit_keeps_existing_behavior(tmp_path, monkeypatch):
    page = tmp_path / "001.png"
    page.write_bytes(b"synthetic-no-private-page")
    entry = Entry("甲", 10, 20)
    calls = []
    review = SimpleNamespace(
        parent=SimpleNamespace(
            current_page=page, entries=[entry], entry_editor_bindings=[],
        ),
        vars=[SimpleNamespace(get=lambda: "乙")],
        _bound_row_entries=lambda: [entry],
        _rendered_page_stem="001",
        _capture_simplified_edits=lambda stem: calls.append(stem),
    )
    main_editor_sync.commit_proofread_entries(review)
    assert entry.word == "乙"
    assert calls == ["001"]
