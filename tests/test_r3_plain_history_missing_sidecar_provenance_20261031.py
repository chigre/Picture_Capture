"""Red-first R3: plain saved-text Undo/Redo must pin every file owner.

The test uses disposable synthetic source bytes only. A temporarily unavailable
Tk row snapshot is *not* evidence that manual/OCR/SECTION/Profile provenance
remains unchanged. Preserve retry only if every original owner is readable
and byte-identical. No real scans, PDIC writer or user history format change.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.proofreading import transactions as tx


def _frozen_session(tmp_path: Path, monkeypatch):
    page = tmp_path / "001.png"
    page.write_bytes(b"synthetic-image")
    pdic = tmp_path / "001.pdic"
    pdic.write_bytes(b"alpha#10#20#1#2#test#@#@\n")
    simplified = tmp_path / "simplified.json"
    simplified.write_bytes(b'{"review":"untouched"}')
    paths = {
        "manual": tmp_path / "001_manual_selection.json",
        "ocr": tmp_path / "001_ocr.json",
        "section": tmp_path / "001.sections.json",
        "profile": tmp_path / "dictionary_profile.json",
    }
    originals = {
        "manual": b'{"overrides":{"abc":{"selected":true}}}',
        "ocr": b'{"candidate_id":"abc","source_y":20}',
        "section": b'{"sections":[{"page":1}]}',
        "profile": b'{"profile_version":3}',
    }
    for key, path in paths.items():
        path.write_bytes(originals[key])

    snap = tx.SavedSnapshot(
        page=page, image_sha="synthetic-fixed-image-digest",
        entries=(), pdic_bytes=pdic.read_bytes(),
        manual_bytes=originals["manual"],
        simplified_bytes=simplified.read_bytes(),
        ocr_bytes=originals["ocr"], candidates=(), owner_ids=(),
        manual_path=paths["manual"], ocr_path=paths["ocr"],
        section_path=paths["section"], section_bytes=originals["section"],
        profile_path=paths["profile"], profile_bytes=originals["profile"],
    )
    history = tx.ReviewSessionHistory()
    history.undo_stack.append(tx.SavedEdit(snap, snap))
    review = SimpleNamespace(
        parent=SimpleNamespace(current_page=page),
    )
    # A synthetic delayed native Tk rebind: no live snapshot can be taken.
    monkeypatch.setattr(tx, "snapshot_review", lambda *_args, **_kw: None)
    monkeypatch.setattr(tx, "sha256_file", lambda _path: snap.image_sha)
    monkeypatch.setattr(tx, "pdic_path", lambda _path: pdic)
    monkeypatch.setattr(
        tx, "simplified_review_path_for_image", lambda _path: simplified,
    )
    return pdic, simplified, paths, originals, history, review


@pytest.mark.parametrize("direction", ("undo", "redo"))
@pytest.mark.parametrize("source", ("manual", "ocr", "section", "profile"))
@pytest.mark.parametrize("failure", ("foreign_write", "deleted", "unreadable"))
def test_plain_history_source_drift_or_denied_read_invalidates(
    tmp_path, monkeypatch, capsys, direction, source, failure,
):
    pdic, simplified, paths, originals, history, review = _frozen_session(
        tmp_path, monkeypatch,
    )
    if direction == "redo":
        history.redo_stack[:] = history.undo_stack
        history.undo_stack.clear()
    preserved_pdic = pdic.read_bytes()
    preserved_simplified = simplified.read_bytes()
    target = paths[source]
    private_sentinel = "PRIVATE_UNDO_SIDE_EFFECT_C:/patient-docs/word"
    if failure == "foreign_write":
        target.write_bytes(b"foreign-human-source-change")
        altered = target.read_bytes()
    elif failure == "deleted":
        target.unlink()
        altered = None
    else:
        original_reader = tx._bytes_or_absent

        def denied_read(path):
            if path == target:
                raise PermissionError(private_sentinel)
            return original_reader(path)

        monkeypatch.setattr(tx, "_bytes_or_absent", denied_read)
        altered = originals[source]

    # A missing real UI snapshot cannot prove that a changed source is safe
    # for replay. Regardless of which history direction, quarantine it.
    assert (history.undo(review) if direction == "undo"
            else history.redo(review)) is False
    assert history.undo_stack == []
    assert history.redo_stack == []
    assert pdic.read_bytes() == preserved_pdic
    assert simplified.read_bytes() == preserved_simplified
    assert (target.read_bytes() if target.exists() else None) == altered
    assert private_sentinel not in repr(capsys.readouterr())


@pytest.mark.parametrize("direction", ("undo", "redo"))
def test_plain_history_unchanged_sources_retains_only_explicit_tk_retry(
    tmp_path, monkeypatch, direction,
):
    pdic, simplified, paths, originals, history, review = _frozen_session(
        tmp_path, monkeypatch,
    )
    if direction == "redo":
        history.redo_stack[:] = history.undo_stack
        history.undo_stack.clear()
    assert (history.undo(review) if direction == "undo"
            else history.redo(review)) is False
    assert len(history.redo_stack if direction == "redo"
               else history.undo_stack) == 1
    assert len(history.undo_stack if direction == "redo"
               else history.redo_stack) == 0
    assert pdic.read_bytes()
    assert simplified.read_bytes()
    assert all(paths[s].read_bytes() == originals[s] for s in paths)
