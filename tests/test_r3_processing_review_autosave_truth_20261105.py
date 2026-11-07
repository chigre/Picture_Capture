"""Synthetic R3: partial simplified-row ownership cannot acknowledge text save.

Ordinary ReviewWindow can be between row rebind and simplified-widget rebind.
No real user records, scans, or persisted schema.
"""
from pathlib import Path
from types import SimpleNamespace

from picture_capture.proofreading import main_editor_sync
from picture_capture.ui import main_pdic_persistence, review_page_lifecycle


class Value:
    def __init__(self, text):
        self.text = text

    def get(self):
        return self.text


def _ordinary_review(*, partial: bool):
    row = SimpleNamespace(word="saved", x=12, y=24)
    status, calls = [], []
    app = SimpleNamespace(
        project=object(), current_page=Path("synthetic.png"),
        current_index=0, entries=[row],
        _foreground_batch_state=lambda _index: "",
        status_var=SimpleNamespace(set=status.append),
        autosave_job="scheduled",
        autosave_var=SimpleNamespace(get=lambda: True),
        _batch_active=False, _last_pdic_write_changed=False,
        _save_normalized_ppp=lambda: calls.append("PPP") or True,
        save_pdic=lambda **_kw: calls.append("UNSAFE-PDIC"),
        toggle_autosave=lambda: calls.append("rearm"),
    )
    review = SimpleNamespace(
        parent=app, row_entries=[row], vars=[Value("saved")],
        _bound_row_entries=lambda: [row],
        _rendered_page_stem="synthetic",
        _filter_rows_active=False, _r3_autosave_unconfirmed=True,
        simplified_vars=[Value("human text not yet captured" if partial else "auto")],
        # A partial redraw has recreated the visible simplified textbox
        # before its actual/manual provenance arrays are fully re-bound.
        simplified_actual_values=[] if partial else ["auto"],
        simplified_manual_flags=[] if partial else [False],
        _simplified_dirty_pages=set(),
        _simplified_display_from_value=lambda _word, actual, _manual: actual,
        winfo_exists=lambda: True,
    )
    review.autosave_commit = lambda: review_page_lifecycle.autosave_commit(
        review, None,
    )
    app.review_window = review
    return review, app, status, calls


def test_partial_simplified_widget_binding_remains_unconfirmed_even_if_ppp_saves(
    monkeypatch,
):
    monkeypatch.setattr(
        main_editor_sync, "bridge_main_canvas_text_into_review", lambda _review: None,
    )
    review, app, status, calls = _ordinary_review(partial=True)
    assert review.autosave_commit() is True
    # No matching simplified owner means neither human text nor a clean no-op
    # is proven. Do not acknowledge success or fall back to stale main PDIC.
    assert review._r3_autosave_unconfirmed is True
    assert status and ("未确认" in status[-1] or "未保存" in status[-1])

    main_pdic_persistence.autosave_tick(
        app, deps={"tk": SimpleNamespace(TclError=RuntimeError)},
    )
    assert calls == ["PPP", "rearm"]
    assert status[-1] != "已自动保存"
    assert "未确认" in status[-1] or "未保存" in status[-1]


def test_fully_bound_clean_review_still_acknowledges_no_op(monkeypatch):
    monkeypatch.setattr(
        main_editor_sync, "bridge_main_canvas_text_into_review", lambda _review: None,
    )
    review, _app, _status, _calls = _ordinary_review(partial=False)
    assert review.autosave_commit() is True
    assert review._r3_autosave_unconfirmed is False
