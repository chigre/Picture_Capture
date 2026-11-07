"""R3: polygon autosave cannot falsely confirm uncommitted ReviewWindow text.

Entirely fake Tk owners and disposable page identifiers; no project or data.
"""
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import main_pdic_persistence, review_page_lifecycle


def test_ppp_only_autosave_cannot_replace_unconfirmed_review_text_warning():
    notes, calls = [], []
    review = SimpleNamespace(
        winfo_exists=lambda: True,
        autosave_commit=lambda: calls.append("review-refused") or True,
        _filter_rows_active=False,
        _r3_autosave_unconfirmed=True,
    )
    app = SimpleNamespace(
        autosave_job="scheduled", autosave_var=SimpleNamespace(get=lambda: True),
        _batch_active=False, project=object(), current_page=Path("synthetic.bmp"),
        review_window=review, _last_pdic_write_changed=False,
        _save_normalized_ppp=lambda: calls.append("only-ppp") or True,
        save_pdic=lambda **kw: calls.append("unexpected-main-pdic"),
        toggle_autosave=lambda: calls.append("rearmed"),
        status_var=SimpleNamespace(set=notes.append),
    )
    main_pdic_persistence.autosave_tick(
        app, deps={"tk": SimpleNamespace(TclError=RuntimeError)},
    )
    assert calls == ["review-refused", "only-ppp", "rearmed"]
    assert notes and ("未保存" in notes[-1] or "未确认" in notes[-1]), (
        "a polygon-only save must never promise the human ReviewWindow text saved",
        notes,
    )


def test_clean_review_does_not_inherit_previous_unconfirmed_flag(monkeypatch):
    entry = SimpleNamespace(word="already-saved")
    review = SimpleNamespace(
        parent=SimpleNamespace(
            project=object(), current_page=Path("synthetic.bmp"),
            current_index=0, entries=[entry],
            _foreground_batch_state=lambda index: "idle",
            status_var=SimpleNamespace(set=lambda status: None),
        ),
        row_entries=[entry], vars=[SimpleNamespace(get=lambda: "already-saved")],
        _bound_row_entries=lambda: [entry], _rendered_page_stem="synthetic",
        _filter_rows_active=False, _simplified_dirty_pages=set(),
        _r3_autosave_unconfirmed=True,
    )
    from picture_capture.proofreading import main_editor_sync
    monkeypatch.setattr(main_editor_sync, "bridge_main_canvas_text_into_review", lambda _review: None)
    monkeypatch.setattr(review_page_lifecycle, "_has_unreported_simplified_input", lambda _review: False)
    assert review_page_lifecycle.autosave_commit(review, None) is True
    assert review._r3_autosave_unconfirmed is False


def test_clean_review_and_real_polygon_change_can_report_other_save():
    notes, calls = [], []
    review = SimpleNamespace(
        winfo_exists=lambda: True,
        autosave_commit=lambda: True,
        _filter_rows_active=False,
        _r3_autosave_unconfirmed=False,
    )
    app = SimpleNamespace(
        autosave_job="scheduled", autosave_var=SimpleNamespace(get=lambda: True),
        _batch_active=False, project=object(), current_page=Path("synthetic.bmp"),
        review_window=review, _last_pdic_write_changed=False,
        _save_normalized_ppp=lambda: True,
        save_pdic=lambda **kw: calls.append("unexpected-main-pdic"),
        toggle_autosave=lambda: calls.append("rearmed"),
        status_var=SimpleNamespace(set=notes.append),
    )
    main_pdic_persistence.autosave_tick(
        app, deps={"tk": SimpleNamespace(TclError=RuntimeError)},
    )
    assert calls == ["rearmed"]
    assert notes == ["已自动保存"]


def test_refused_stale_row_autosave_marks_text_as_unconfirmed(monkeypatch):
    source = SimpleNamespace(word="old")
    notes = []
    review = SimpleNamespace(
        parent=SimpleNamespace(
            project=object(), current_page=Path("synthetic.bmp"),
            current_index=0, entries=[source],
            _foreground_batch_state=lambda index: "idle",
            status_var=SimpleNamespace(set=notes.append),
        ),
        row_entries=[], vars=[SimpleNamespace(get=lambda: "unsaved-human-text")],
        _bound_row_entries=lambda: [], _rendered_page_stem="synthetic",
        _filter_rows_active=False, _simplified_dirty_pages=set(),
    )
    assert review_page_lifecycle.autosave_commit(review, None) is True
    assert getattr(review, "_r3_autosave_unconfirmed", False) is True
    assert notes and "未确认" in notes[-1]
