"""R3 plain saved-edit chain: identical bytes do not prove same page/source.

All snapshots are synthetic. A new ordinary committed edit can be undoable on
its own, while the prior edit belongs to another page or different origin path.
Only byte- and identity-exact chained snapshots may share Undo history.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from picture_capture.models import Entry
from picture_capture.proofreading.transactions import (
    ReviewSessionHistory, SavedSnapshot,
)


def _snapshot(tmp_path: Path, *, word: str, page: Path | None = None):
    row = Entry(word, 10, 20)
    page = page or tmp_path / "001.png"
    return SavedSnapshot(
        page=page, image_sha="synthetic-image-digest",
        entries=((row, word, 10, 20),),
        pdic_bytes=(word + "#10#20#1#2#test#@#@\n").encode("utf-8"),
        manual_bytes=b'{"manual":1}',
        simplified_bytes=b'{"simplified":1}',
        ocr_bytes=b'{"ocr":1}',
        candidates=(),
        owner_ids=((id(row), ""),),
        manual_path=tmp_path / "paddle" / "001_manual_selection.json",
        ocr_path=tmp_path / "paddle" / "001_ocr.json",
        section_path=tmp_path / "001.sections.json",
        section_bytes=b'{"section":1}',
        profile_path=tmp_path / "dictionary_profile.json",
        profile_bytes=b'{"profile":1}',
    )


def _with_word(snapshot: SavedSnapshot, word: str):
    row = snapshot.entries[0][0]
    return replace(
        snapshot, entries=((row, word, 10, 20),),
        pdic_bytes=(word + "#10#20#1#2#test#@#@\n").encode("utf-8"),
    )


@pytest.mark.parametrize("binding", (
    "page", "manual_path", "ocr_path", "section_path", "profile_path",
))
def test_new_saved_commit_cannot_keep_undo_frame_from_different_source_binding(
    tmp_path, binding,
):
    original = _snapshot(tmp_path, word="alpha")
    first = _with_word(original, "beta")
    history = ReviewSessionHistory()
    assert history.record(original, first)

    # Files may have byte-identical contents even after a project path
    # resolution change. A second save is legitimate on its OWN new source,
    # but the first frame cannot be chained into that new ownership scope.
    old_path = getattr(first, binding)
    second_before = replace(
        first, **{binding: old_path.with_name("foreign-" + old_path.name)},
    )
    second_after = _with_word(second_before, "gamma")
    assert history.record(second_before, second_after)
    assert len(history.undo_stack) == 1
    assert history.undo_stack[0].before is second_before
    assert history.undo_stack[0].after is second_after
    assert history.redo_stack == []


@pytest.mark.parametrize("word2", ("gamma", "delta"))
def test_exact_same_page_and_source_identity_retains_multi_step_undo_chain(
    tmp_path, word2,
):
    first_before = _snapshot(tmp_path, word="alpha")
    first_after = _with_word(first_before, "beta")
    second_after = _with_word(first_after, word2)
    history = ReviewSessionHistory()
    assert history.record(first_before, first_after)
    assert history.record(first_after, second_after)
    assert len(history.undo_stack) == 2
    assert history.undo_stack[0].after is first_after
    assert history.undo_stack[1].before is first_after


def test_identity_equivalent_snapshot_objects_can_continue_same_chain(tmp_path):
    first_before = _snapshot(tmp_path, word="alpha")
    first_after = _with_word(first_before, "beta")
    chain_before = replace(first_after)
    chain_after = _with_word(chain_before, "gamma")
    history = ReviewSessionHistory()
    assert history.record(first_before, first_after)
    assert history.record(chain_before, chain_after)
    assert len(history.undo_stack) == 2
