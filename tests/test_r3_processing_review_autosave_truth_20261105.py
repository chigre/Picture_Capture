"""Synthetic R3 regression: a processing ReviewWindow is not a text save.

A separate PPP write must not display blanket autosave success while the
ordinary ReviewWindow text remains unconfirmed. No user images or records.
"""
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import main_pdic_persistence, review_page_lifecycle


def test_processing_page_review_text_remains_unconfirmed_after_ppp_autosave():
    row = SimpleNamespace(word="saved")
    status, calls = [], []
    app = SimpleNamespace(
        project=object(),
        current_page=Path("synthetic.png"),
        current_index=0,
        entries=[row],
        _foreground_batch_state=lambda _index: "processing",
        status_var=SimpleNamespace(set=status.append),
        autosave_job="scheduled",
        autosave_var=SimpleNamespace(get=lambda: True),
        _batch_active=False,
        _last_pdic_write_changed=False,
        _save_normalized_ppp=lambda: calls.append("PPP") or True,
        save_pdic=lambda **_kwargs: calls.append("UNSAFE-PDIC"),
        toggle_autosave=lambda: calls.append("rearm"),
    )
    review = SimpleNamespace(
        parent=app,
        _filter_rows_active=False,
        _r3_autosave_unconfirmed=False,
        vars=[SimpleNamespace(get=lambda: "uncommitted human edit")],
        _bound_row_entries=lambda: [row],
        _rendered_page_stem="synthetic",
        winfo_exists=lambda: True,
    )
    review.autosave_commit = lambda: review_page_lifecycle.autosave_commit(
        review, None,
    )
    app.review_window = review

    # The processing page is owned by its worker, so this must NOT write
    # the human editor's text or claim it has been saved.
    assert review.autosave_commit() is True
    assert review._r3_autosave_unconfirmed is True
    assert any("未确认" in message or "未保存" in message for message in status)

    # PPP is independent; even its successful write cannot validate PDIC.
    main_pdic_persistence.autosave_tick(
        app, deps={"tk": SimpleNamespace(TclError=RuntimeError)},
    )
    assert calls == ["PPP", "rearm"]
    assert status and ("未确认" in status[-1] or "未保存" in status[-1])
    assert status[-1] != "已自动保存"
