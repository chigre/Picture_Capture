"""G1 red-first: no unhandled disk read errors during R3 Undo/Redo diagnostic.

When snapshot_review() cannot make a live snapshot, the history owner
performs a second source check to distinguish a transient Tk rebind
from genuinely stale file ownership. An inaccessible PDIC/Simplified
sidecar must invalidate stale history and return False, never escape
with a PermissionError from a human Undo/Redo command.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.proofreading import transactions


def _history(tmp_path, monkeypatch):
    page = tmp_path / "001.png"
    page.write_bytes(b"synthetic scan, not private")
    pdic = tmp_path / "001.pdic"
    pdic.write_bytes(b"authoritative bytes")
    simplified = tmp_path / "simplified.json"
    simplified.write_bytes(b'{"row":"text"}')
    snap = transactions.SavedSnapshot(
        page=page, image_sha="frozen-image-hash",
        entries=(), pdic_bytes=pdic.read_bytes(),
        manual_bytes=None, simplified_bytes=simplified.read_bytes(),
        ocr_bytes=None, candidates=(), owner_ids=(),
    )
    history = transactions.ReviewSessionHistory()
    history.undo_stack.append(transactions.SavedEdit(snap, snap))
    review = SimpleNamespace(parent=SimpleNamespace(current_page=page))
    monkeypatch.setattr(transactions, "snapshot_review", lambda *_a, **_k: None)
    monkeypatch.setattr(transactions, "sha256_file", lambda _page: snap.image_sha)
    monkeypatch.setattr(transactions, "pdic_path", lambda _page: pdic)
    monkeypatch.setattr(
        transactions, "simplified_review_path_for_image", lambda _page: simplified,
    )
    return page, pdic, simplified, snap, history, review


def test_undo_unreadable_pdic_diagnostic_is_fail_closed(tmp_path, monkeypatch):
    _, pdic, simplified, snap, history, review = _history(tmp_path, monkeypatch)
    original_read = transactions._bytes_or_absent
    def inaccessible(path):
        if path == pdic:
            raise PermissionError("injected unreadable PDIC")
        return original_read(path)
    monkeypatch.setattr(transactions, "_bytes_or_absent", inaccessible)
    assert history.undo(review) is False
    assert history.undo_stack == []
    assert history.redo_stack == []
    assert pdic.read_bytes() == snap.pdic_bytes
    assert simplified.read_bytes() == snap.simplified_bytes


def test_redo_unreadable_simplified_diagnostic_is_fail_closed(tmp_path, monkeypatch):
    _, pdic, simplified, snap, history, review = _history(tmp_path, monkeypatch)
    history.redo_stack[:] = history.undo_stack
    history.undo_stack.clear()
    original_read = transactions._bytes_or_absent
    def inaccessible(path):
        if path == simplified:
            raise PermissionError("injected inaccessible simplified sidecar")
        return original_read(path)
    monkeypatch.setattr(transactions, "_bytes_or_absent", inaccessible)
    assert history.redo(review) is False
    assert history.undo_stack == []
    assert history.redo_stack == []
    assert pdic.read_bytes() == snap.pdic_bytes
    assert simplified.read_bytes() == snap.simplified_bytes


def test_snapshot_none_with_unchanged_disk_retains_history_for_tk_retry(tmp_path, monkeypatch):
    _, pdic, simplified, snap, history, review = _history(tmp_path, monkeypatch)
    assert history.undo(review) is False
    assert len(history.undo_stack) == 1
    assert history.redo_stack == []
    assert pdic.read_bytes() == snap.pdic_bytes
    assert simplified.read_bytes() == snap.simplified_bytes


def test_snapshot_none_with_stale_pdic_invalidates_history(tmp_path, monkeypatch):
    _, pdic, simplified, snap, history, review = _history(tmp_path, monkeypatch)
    pdic.write_bytes(b"foreign changed human PDIC")
    assert history.undo(review) is False
    assert history.undo_stack == []
    assert history.redo_stack == []
    assert pdic.read_bytes() == b"foreign changed human PDIC"


def test_snapshot_none_with_stale_simplified_invalidates_history(tmp_path, monkeypatch):
    _, pdic, simplified, snap, history, review = _history(tmp_path, monkeypatch)
    simplified.write_bytes(b"new foreign simplified edit")
    assert history.undo(review) is False
    assert history.undo_stack == []
    assert history.redo_stack == []
    assert simplified.read_bytes() == b"new foreign simplified edit"
