"""R3 E2 synthetic: exception before verified ReviewWindow commit must retain warning.

No real dictionary, OCR, private data, or user source files.
"""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import (
    main_pdic_persistence,
    review_page_lifecycle as lifecycle,
    review_transaction_actions,
)
from picture_capture.proofreading import (
    main_editor_sync,
    review_bundle,
    save_safety,
)


def _review(*, dirty: bool):
    row = SimpleNamespace(word="frozen")
    statuses = []
    app = SimpleNamespace(
        project=object(),
        current_page=Path("synthetic.bmp"),
        current_index=0,
        entries=[row],
        _foreground_batch_state=lambda _index: "idle",
        status_var=SimpleNamespace(set=statuses.append),
        settings=SimpleNamespace(review_zoom_percent=100),
    )
    review = SimpleNamespace(
        parent=app,
        row_entries=[row],
        vars=[SimpleNamespace(get=lambda: "unsaved" if dirty else "frozen")],
        _bound_row_entries=lambda: [row],
        _rendered_page_stem="synthetic",
        _filter_rows_active=False,
        _simplified_dirty_pages=set(),
        _r3_autosave_unconfirmed=True,
        _review_evidence_before_save=lambda: None,
        _review_evidence_after_save=lambda _prior: None,
        _commit_edits=lambda: None,
        _stored_review_zoom_percent=lambda: 100,
    )
    return review, statuses


def _install(monkeypatch, failing_stage: str | None):
    monkeypatch.setattr(lifecycle, "_has_unreported_simplified_input", lambda _review: False)

    def bridge(_review):
        if failing_stage == "bridge":
            raise RuntimeError("synthetic bridge failure")

    def capture(_review):
        if failing_stage == "capture":
            raise RuntimeError("synthetic snapshot failure")
        return object()

    def bundle(_review, _source):
        if failing_stage == "bundle":
            raise RuntimeError("synthetic bundle failure")

    monkeypatch.setattr(main_editor_sync, "bridge_main_canvas_text_into_review", bridge)
    monkeypatch.setattr(review_transaction_actions, "capture_review_before", capture)
    monkeypatch.setattr(review_transaction_actions, "record_review_after", lambda *_args: None)
    monkeypatch.setattr(save_safety, "protect_review_pdic_commit", lambda _review: nullcontext())
    monkeypatch.setattr(review_bundle, "commit_review_bundle", bundle)


@pytest.mark.parametrize("failing_stage", ["bridge", "capture", "bundle"])
def test_failed_review_autosave_retains_unconfirmed_truth_through_ppp(
    monkeypatch, failing_stage,
):
    """A later independent PPP save must not turn a prior failed text write GREEN."""
    review, _statuses = _review(dirty=True)
    _install(monkeypatch, failing_stage)
    with pytest.raises(RuntimeError, match="synthetic"):
        lifecycle.autosave_commit(review, None)
    assert review._r3_autosave_unconfirmed is True

    notes, calls = [], []
    review.winfo_exists = lambda: True
    review.autosave_commit = lambda: True
    app = SimpleNamespace(
        autosave_job="scheduled", autosave_var=SimpleNamespace(get=lambda: True),
        _batch_active=False, project=object(), current_page=Path("synthetic.bmp"),
        review_window=review, _last_pdic_write_changed=False,
        _save_normalized_ppp=lambda: calls.append("ppp-only") or True,
        save_pdic=lambda **_kw: calls.append("UNSAFE-main-pdic"),
        toggle_autosave=lambda: calls.append("rearmed"),
        status_var=SimpleNamespace(set=notes.append),
    )
    main_pdic_persistence.autosave_tick(
        app, deps={"tk": SimpleNamespace(TclError=RuntimeError)},
    )
    assert calls == ["ppp-only", "rearmed"]
    assert notes and ("未保存" in notes[-1] or "未确认" in notes[-1])


def test_verified_clean_review_can_clear_previous_unconfirmed_flag(monkeypatch):
    review, _statuses = _review(dirty=False)
    _install(monkeypatch, None)
    assert lifecycle.autosave_commit(review, None) is True
    assert review._r3_autosave_unconfirmed is False
