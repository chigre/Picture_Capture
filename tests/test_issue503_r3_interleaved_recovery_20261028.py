"""#503 R3: do not overwrite intervening human edits during crash recovery.

A journal is an optimistic exact-byte recovery plan, not a transaction lock.
Check each file just before compensating it, even if an earlier global read
showed a valid before/after state.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.io.formats import pdic_path
from picture_capture.persistence.project_storage import simplified_review_path_for_image
from picture_capture.proofreading import transactions as tx


OLD_PDIC = b"previous PDIC proofreading"
NEW_PDIC = b"pending PDIC revision"
OLD_SIMPLIFIED = b"previous simplified proofread"
NEW_SIMPLIFIED = b"pending simplified revision"
FOREIGN = b"human edit made during recovery"


def _setup(tmp_path, *, manual=False, rollback_required=True):
    page = tmp_path / "001.png"
    page.write_bytes(b"synthetic image")
    pdic = pdic_path(page)
    simplified = simplified_review_path_for_image(page)
    pdic.write_bytes(OLD_PDIC)
    simplified.parent.mkdir(parents=True, exist_ok=True)
    simplified.write_bytes(OLD_SIMPLIFIED)
    stages = [
        ("pdic", OLD_PDIC, NEW_PDIC),
        ("simplified", OLD_SIMPLIFIED, NEW_SIMPLIFIED),
    ]
    override = None
    if manual:
        override = tmp_path / "PaddleOCR" / "001_manual_selection.json"
        override.parent.mkdir(parents=True, exist_ok=True)
        stages.insert(1, ("manual", None, b'{"selected":false}'))
    marker = tx._stage_recovery(
        page, stages, manual_path=override,
        rollback_required=rollback_required,
    )
    paths = {"pdic": pdic, "simplified": simplified, "manual": override}
    for role, _, after in stages:
        tx._publish(paths[role], after)
    return page, pdic, simplified, override, marker


@pytest.mark.parametrize("manual", [False, True])
def test_edit_between_compensation_steps_is_not_overwritten(
    tmp_path, monkeypatch, manual,
):
    page, pdic, simplified, override, marker = _setup(tmp_path, manual=manual)
    original_publish = tx._publish
    interfered = []

    def human_edits_second_file(path, data):
        result = original_publish(path, data)
        if path == pdic and data == OLD_PDIC:
            second_file = override if manual else simplified
            second_file.write_bytes(FOREIGN)
            interfered.append(second_file)
        return result

    monkeypatch.setattr(tx, "_publish", human_edits_second_file)

    assert tx.recover_pending_for_page(page, manual_path=override) is False
    assert interfered == [override if manual else simplified]
    assert pdic.read_bytes() == OLD_PDIC
    assert interfered[0].read_bytes() == FOREIGN
    assert marker.is_file()  # No false "recovered" report.
    if manual:
        assert simplified.read_bytes() == NEW_SIMPLIFIED

    # The page can be recovered only after deliberate manual reconciliation
    # puts the foreign sidecar back in one of the journal-owned states.
    monkeypatch.setattr(tx, "_publish", original_publish)
    interfered[0].write_bytes(
        b'{"selected":false}' if manual else NEW_SIMPLIFIED
    )
    assert tx.recover_pending_for_page(page, manual_path=override)
    assert pdic.read_bytes() == OLD_PDIC
    assert simplified.read_bytes() == OLD_SIMPLIFIED
    if manual:
        assert not override.exists()
    assert not marker.exists()


def test_all_after_state_is_rechecked_before_discarding_journal(
    tmp_path, monkeypatch,
):
    page, pdic, simplified, _override, marker = _setup(
        tmp_path, rollback_required=False,
    )
    original_read = tx._bytes_or_absent
    reads = []
    edited = []

    def concurrent_edit(path):
        data = original_read(path)
        if path == simplified:
            reads.append(True)
            if len(reads) == 2:
                simplified.write_bytes(FOREIGN)
                edited.append(True)
                return FOREIGN
        return data

    monkeypatch.setattr(tx, "_bytes_or_absent", concurrent_edit)
    assert tx.recover_pending_for_page(page) is False
    assert reads == [True, True]
    assert edited == [True]
    assert pdic.read_bytes() == NEW_PDIC
    assert simplified.read_bytes() == FOREIGN
    assert marker.is_file()

    monkeypatch.setattr(tx, "_bytes_or_absent", original_read)
    simplified.write_bytes(NEW_SIMPLIFIED)
    assert tx.recover_pending_for_page(page)
    assert pdic.read_bytes() == NEW_PDIC
    assert simplified.read_bytes() == NEW_SIMPLIFIED
    assert not marker.exists()


def test_already_restored_files_are_not_rewritten(tmp_path, monkeypatch):
    page, pdic, simplified, _override, marker = _setup(tmp_path)
    # Mixed state forces before-state compensation, but the companion
    # was already restored by another recoverer.
    simplified.write_bytes(OLD_SIMPLIFIED)
    writes = []
    original_publish = tx._publish

    def count_compensation(path, data):
        writes.append((path, data))
        return original_publish(path, data)

    monkeypatch.setattr(tx, "_publish", count_compensation)
    assert tx.recover_pending_for_page(page)
    assert writes == [(pdic, OLD_PDIC)]
    assert pdic.read_bytes() == OLD_PDIC
    assert simplified.read_bytes() == OLD_SIMPLIFIED
    assert not marker.exists()


def test_silent_compensation_noop_keeps_recovery_marker(tmp_path, monkeypatch):
    page, pdic, simplified, _override, marker = _setup(tmp_path)
    original_publish = tx._publish

    def skip_pdic_restore(path, data):
        if path == pdic and data == OLD_PDIC:
            return None
        return original_publish(path, data)

    monkeypatch.setattr(tx, "_publish", skip_pdic_restore)
    assert tx.recover_pending_for_page(page) is False
    assert pdic.read_bytes() == NEW_PDIC
    assert simplified.read_bytes() == NEW_SIMPLIFIED
    assert marker.is_file()
