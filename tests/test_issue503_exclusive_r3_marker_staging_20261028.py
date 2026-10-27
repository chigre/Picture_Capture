"""Issue #503: an R3 recovery journal has exactly one creating writer.

These tests exercise the filesystem O_CREAT|O_EXCL ownership boundary, not a
mocked Python thread lock. A crashed/partial journal must quarantine the page
and must never be overwritten by another Undo/candidate-owned transaction.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from picture_capture.io.formats import pdic_path
from picture_capture.proofreading import transactions as tx


OLD = b"proofread PDIC before R3"
NEW = b"proposed R3 PDIC"


def _page(tmp_path):
    page = tmp_path / "001.png"
    page.write_bytes(b"synthetic scan fixture")
    target = pdic_path(page)
    target.write_bytes(OLD)
    return page, target, tx._recovery_path(page)


def _stage(page):
    return tx._stage_recovery(page, [("pdic", OLD, NEW)])


def test_r3_journal_created_with_exclusive_flags_and_regular_compatible_schema(
    tmp_path, monkeypatch,
):
    page, pdic, marker = _page(tmp_path)
    real_open = os.open
    opens = []

    def capture_open(path, flags, mode=0o777, *args, **kwargs):
        if Path(path) == marker:
            opens.append((flags, mode))
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(tx.os, "open", capture_open)
    assert _stage(page) == marker
    assert len(opens) == 1
    flags, mode = opens[0]
    assert flags & os.O_EXCL
    assert flags & os.O_CREAT
    assert flags & os.O_WRONLY
    assert mode == 0o600
    assert tx._verified_recovery(page) is not None
    assert pdic.read_bytes() == OLD
    assert tx.recover_pending_for_page(page)
    assert not tx._marker_present(marker)


def test_competitor_creates_journal_after_preflight_cannot_be_replaced(
    tmp_path, monkeypatch,
):
    page, pdic, marker = _page(tmp_path)
    competitor = b'{"foreign":"another pending R3 transaction"}'
    real_open = os.open
    tries = []

    def competitor_wins(path, flags, mode=0o777, *args, **kwargs):
        if Path(path) == marker:
            tries.append(True)
            # Simulate another process winning exactly between the old
            # existence check and this process's exclusive creation syscall.
            marker.write_bytes(competitor)
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(tx.os, "open", competitor_wins)
    with pytest.raises(RuntimeError, match="Unresolved R3 recovery marker") as caught:
        _stage(page)
    assert isinstance(caught.value.__cause__, FileExistsError)
    assert tries == [True]
    assert marker.read_bytes() == competitor
    assert pdic.read_bytes() == OLD


def test_existing_valid_journal_is_unchanged_by_second_stage(tmp_path):
    page, pdic, marker = _page(tmp_path)
    _stage(page)
    previous = marker.read_bytes()
    with pytest.raises(RuntimeError, match="Unresolved R3 recovery marker"):
        tx._stage_recovery(page, [("pdic", OLD, b"second writer")])
    assert marker.read_bytes() == previous
    assert pdic.read_bytes() == OLD


def test_partial_marker_after_fsync_fault_remains_quarantined(
    tmp_path, monkeypatch,
):
    page, pdic, marker = _page(tmp_path)
    failure = OSError("journal fsync failed")
    real_fsync = tx.os.fsync
    attempts = []

    def fail_journal_fsync(fd):
        attempts.append(fd)
        raise failure

    monkeypatch.setattr(tx.os, "fsync", fail_journal_fsync)
    with pytest.raises(OSError) as caught:
        _stage(page)
    assert caught.value is failure
    assert len(attempts) == 1
    assert tx._marker_present(marker)
    assert pdic.read_bytes() == OLD
    with pytest.raises(RuntimeError, match="Unresolved R3 recovery marker"):
        _stage(page)
    # A failed fsync is not a successful durable commit: never silently
    # delete its marker or proceed with a different recovery plan.
    monkeypatch.setattr(tx.os, "fsync", real_fsync)


def test_exclusive_creation_permission_error_cannot_mutate_owned_files(
    tmp_path, monkeypatch,
):
    page, pdic, marker = _page(tmp_path)
    error = PermissionError("journal directory denied")
    real_open = os.open

    def deny_marker(path, flags, mode=0o777, *args, **kwargs):
        if Path(path) == marker:
            raise error
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(tx.os, "open", deny_marker)
    with pytest.raises(PermissionError) as caught:
        _stage(page)
    assert caught.value is error
    assert pdic.read_bytes() == OLD
    assert not tx._marker_present(marker)
