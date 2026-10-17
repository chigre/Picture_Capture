"""Failure injection for R3 ReviewWindow and deferred PDIC commit safety."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.app import PictureCaptureApp, ReviewWindow
from picture_capture.formats import pdic_path, write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading_save_safety import (
    protect_app_pdic_commit, protect_review_pdic_commit,
)


class Var:
    def __init__(self, text):
        self.text = text

    def get(self):
        return self.text

    def set(self, text):
        self.text = text


def _app(tmp_path):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-not-private")
    entry = Entry("before", 10, 20)
    write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
    app = SimpleNamespace(
        current_page=page, entries=[entry], entry_editor_bindings=[],
        _deferred_save_snapshot=("queued",), _deferred_save_page=page,
    )
    return app, entry, page


def test_review_pdic_failure_restores_entry_but_preserves_user_input(tmp_path):
    app, entry, page = _app(tmp_path)
    review = SimpleNamespace(
        parent=app, _rendered_page_stem=page.stem,
        vars=[Var("unsaved user text")],
        _simplified_page_cache={page.stem: {"key": {"text": "before"}}},
        _simplified_dirty_pages={page.stem},
        simplified_manual_flags=[False],
        simplified_actual_values=["before"],
    )
    original = pdic_path(page).read_bytes()
    with pytest.raises(OSError, match="disk full"):
        with protect_review_pdic_commit(review):
            entry.word = "unsaved user text"
            review._simplified_page_cache[page.stem]["key"]["text"] = "changed"
            review.simplified_manual_flags[0] = True
            raise OSError("disk full")
    assert entry.word == "before"
    assert review.vars[0].get() == "unsaved user text"
    assert review.simplified_manual_flags == [False]
    assert review._simplified_page_cache[page.stem]["key"]["text"] == "before"
    assert pdic_path(page).read_bytes() == original


def test_app_failed_pdic_write_restores_order_and_entry_words(tmp_path):
    app, entry, page = _app(tmp_path)
    second = Entry("second", 30, 40)
    app.entries.append(second)
    before = pdic_path(page).read_bytes()
    with pytest.raises(OSError):
        with protect_app_pdic_commit(app):
            app.entries.reverse()
            entry.word = "changed"
            raise OSError("write refused")
    assert app.entries == [entry, second]
    assert entry.word == "before"
    assert pdic_path(page).read_bytes() == before
    assert app._deferred_save_snapshot == ("queued",)


def test_app_ambiguous_write_does_not_restore_stale_words(tmp_path):
    app, entry, page = _app(tmp_path)
    with pytest.raises(OSError):
        with protect_app_pdic_commit(app):
            entry.word = "committed"
            write_pdic(pdic_path(page), app.entries, 100, ("synthetic", "@", "@"))
            raise OSError("error after replace")
    assert entry.word == "committed"
    assert app._deferred_save_uncertain is True


def test_close_refuses_destroy_when_save_fails(monkeypatch):
    fake = SimpleNamespace(
        _filter_rows_active=False,
        parent=SimpleNamespace(status_var=SimpleNamespace(set=lambda _x: None)),
        save=lambda: (_ for _ in ()).throw(OSError("synthetic full disk")),
        _finish_close_review=lambda: pytest.fail("window must remain open"),
    )
    monkeypatch.setattr("picture_capture.app.messagebox.showerror", lambda *a, **k: None)
    ReviewWindow._close_review(fake)


def test_close_refuses_destroy_when_pending_page_cannot_save(monkeypatch):
    fake = SimpleNamespace(
        _filter_rows_active=False,
        save=lambda: False,
        _finish_close_review=lambda: pytest.fail("window must remain open"),
    )
    ReviewWindow._close_review(fake)


def test_app_save_pdic_does_not_drop_deferred_snapshot_on_failure(tmp_path, monkeypatch):
    app, entry, page = _app(tmp_path)
    app.project = SimpleNamespace(root=tmp_path)
    app.image = SimpleNamespace(width=100)
    app.__dict__["_batch_active"] = False
    app._deferred_save_job = None
    app._sync_entry_editor_texts = lambda: setattr(entry, "word", "changed")
    app._sort_entries_reading_order = lambda: None
    app.pages_tuple = lambda: ("synthetic", "@", "@")
    monkeypatch.setattr("picture_capture.app.write_pdic",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        PictureCaptureApp.save_pdic(app)
    assert app._deferred_save_snapshot == ("queued",)
    assert app._deferred_save_page == page
    assert entry.word == "before"


def test_uncertain_deferred_snapshot_cannot_overwrite_committed_pdic(tmp_path):
    from picture_capture.proofreading_deferred_save import flush_deferred_page_save

    app, entry, page = _app(tmp_path)
    app._deferred_save_job = None
    app._deferred_save_uncertain = True
    app._deferred_save_snapshot = (page, [Entry("stale", 10, 20)], 100,
                                   ("synthetic", "@", "@"), 0)
    original = pdic_path(page).read_bytes()
    with pytest.raises(RuntimeError, match="uncertain"):
        flush_deferred_page_save(app, write_pdic=write_pdic, pdic_path=pdic_path)
    assert pdic_path(page).read_bytes() == original
    assert app._deferred_save_snapshot[0] == page


def test_autosave_review_failure_keeps_review_owner_and_rearms():
    status = []
    calls = []
    review = SimpleNamespace(
        winfo_exists=lambda: True,
        autosave_commit=lambda: (_ for _ in ()).throw(OSError("synthetic full disk")),
    )
    fake = SimpleNamespace(
        autosave_job="previous",
        autosave_var=SimpleNamespace(get=lambda: True),
        _batch_active=False, project=object(), current_page="synthetic.png",
        review_window=review, status_var=SimpleNamespace(set=status.append),
        toggle_autosave=lambda: calls.append("rearmed"),
        save_pdic=lambda **_kw: pytest.fail("no stale main-canvas fallback"),
    )
    PictureCaptureApp.autosave_tick(fake)
    assert calls == ["rearmed"]
    assert fake.review_window is review
    assert any("自动保存失败" in value for value in status)
