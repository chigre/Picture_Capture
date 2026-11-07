"""G1 fail-first: unreadable postfailure PDIC must quarantine, never mask I/O.

The original writer failure owns the traceback. A second exception
from the diagnostic PDIC readback must not replace it, and must
never authorize restoring an Entry/ReviewWindow snapshot as if the
old disk bytes were verified.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path, write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading import save_safety
from picture_capture.proofreading.save_safety import (
    protect_app_pdic_commit, protect_review_pdic_commit,
)


def _page(tmp_path):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-not-private-image")
    entry = Entry("甲", 10, 20)
    write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
    app = SimpleNamespace(current_page=page, entries=[entry], entry_editor_bindings=[])
    review = SimpleNamespace(
        parent=app,
        _rendered_page_stem="synthetic",
        _simplified_page_cache={"synthetic": {"row": {"text": "before"}}},
        _simplified_dirty_pages={"synthetic"},
        simplified_manual_flags=[False],
        simplified_actual_values=["before"],
        vars=[SimpleNamespace(get=lambda: "unsaved visible user input")],
    )
    return page, entry, app, review


def _make_postfailure_readback_unreadable(monkeypatch):
    real = save_safety._bytes_or_absent
    reads = []
    def flaky(path):
        reads.append(path)
        if len(reads) == 2:
            raise PermissionError("injected PDIC readback access denied")
        return real(path)
    monkeypatch.setattr(save_safety, "_bytes_or_absent", flaky)
    return reads


def test_app_original_write_error_survives_unreadable_readback(tmp_path, monkeypatch):
    page, entry, app, _ = _page(tmp_path)
    original = pdic_path(page).read_bytes()
    reads = _make_postfailure_readback_unreadable(monkeypatch)
    with pytest.raises(OSError, match="original disk full during save"):
        with protect_app_pdic_commit(app):
            entry.word = "new unsaved word"
            raise OSError("original disk full during save")
    assert len(reads) == 2
    assert app._deferred_save_uncertain is True
    # Cannot prove no publication: do not roll back user-visible edits.
    assert entry.word == "new unsaved word"
    assert pdic_path(page).read_bytes() == original


def test_review_original_write_error_survives_unreadable_readback(tmp_path, monkeypatch):
    page, entry, app, review = _page(tmp_path)
    original = pdic_path(page).read_bytes()
    reads = _make_postfailure_readback_unreadable(monkeypatch)
    with pytest.raises(OSError, match="original disk full during review save"):
        with protect_review_pdic_commit(review):
            entry.word = "new unsaved review word"
            review._simplified_page_cache["synthetic"]["row"]["text"] = "new manual input"
            review.simplified_manual_flags[0] = True
            raise OSError("original disk full during review save")
    assert len(reads) == 2
    assert app._deferred_save_uncertain is True
    assert entry.word == "new unsaved review word"
    assert review._simplified_page_cache["synthetic"]["row"]["text"] == "new manual input"
    assert review.simplified_manual_flags == [True]
    assert review.vars[0].get() == "unsaved visible user input"
    assert pdic_path(page).read_bytes() == original


def test_app_verified_unchanged_disk_still_restores_snapshot(tmp_path):
    page, entry, app, _ = _page(tmp_path)
    with pytest.raises(OSError, match="original disk full"):
        with protect_app_pdic_commit(app):
            entry.word = "failed speculative update"
            raise OSError("original disk full")
    assert entry.word == "甲"
    assert not app.__dict__.get("_deferred_save_uncertain", False)


def test_review_verified_unchanged_disk_still_restores_snapshot(tmp_path):
    page, entry, app, review = _page(tmp_path)
    with pytest.raises(OSError, match="original disk full"):
        with protect_review_pdic_commit(review):
            entry.word = "failed speculative update"
            review.simplified_manual_flags[0] = True
            raise OSError("original disk full")
    assert entry.word == "甲"
    assert review.simplified_manual_flags == [False]
    assert review.vars[0].get() == "unsaved visible user input"
    assert not app.__dict__.get("_deferred_save_uncertain", False)
