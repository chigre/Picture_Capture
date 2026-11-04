"""Regression for reported ReviewWindow save/re-simplify failures (synthetic only).

A new original headword must reach the paired PDIC save before a separate
simplified-sidecar regeneration writes its new source_word. The pending autosave
refusal must remain visible even if a later PPP save succeeds.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import review_simplified_workflow as simplified
from picture_capture.ui import review_page_lifecycle as lifecycle


class Text:
    def __init__(self, value=""):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


def setup_regeneration():
    page = Path("synthetic.png")
    row = SimpleNamespace(word="old", x=10, y=20)
    app = SimpleNamespace(
        current_page=page, project=SimpleNamespace(images=[page]),
        entries=[row], status_var=Text(""),
        _claim_page_for_manual_edit=lambda: True,
    )
    record = {"x": 10, "y": 20, "source_word": "old",
              "text": "old simplified", "manual": False}
    cache = {"10,20": record}
    events = []
    review = SimpleNamespace(
        parent=app, row_entries=[row], _rendered_page_stem="synthetic",
        _filter_rows_active=False, vars=[Text("new")],
        simplified_vars=[Text("old simplified")],
        simplified_actual_values=["old simplified"],
        simplified_manual_flags=[False],
        simplified_auto_refresh_flags=[False],
        _simplified_dirty_pages=set(),
        active_index=-1,
        _simplified_page_records=lambda stem: cache,
        _simplified_display_from_value=lambda original, actual, manual: actual,
        _refresh_cc_simplified_comparison=lambda index: None,
    )
    def commit_original(*, redraw_main=True):
        assert redraw_main is False
        events.append("save_original")
        row.word = review.vars[0].get()
        cache["10,20"]["source_word"] = row.word
        return True
    def persist_sidecar(stem):
        events.append("persist_simplified")
        # A standalone simplified writer's actual PDIC binding is equivalent
        # to this source/word assertion; never write the new sidecar first.
        assert row.word == review.vars[0].get()
        assert cache["10,20"]["source_word"] == row.word
    review.save = commit_original
    review._persist_simplified_page = persist_sidecar
    deps = SimpleNamespace(
        simplified_entry_key=lambda x, y: f"{x},{y}",
        simplify_text=lambda word: "simplified:" + word,
        messagebox=SimpleNamespace(showerror=lambda *a, **kw: None),
    )
    return review, row, cache, events, deps


def test_regenerate_saves_pending_original_before_simplified_sidecar():
    review, row, cache, events, deps = setup_regeneration()
    simplified.regenerate_simplified_current_page(review, deps)
    assert events == ["save_original", "persist_simplified"]
    assert row.word == "new"
    assert cache["10,20"]["source_word"] == "new"
    assert cache["10,20"]["manual"] is False
    assert review.simplified_vars[0].get() == "simplified:new"


def test_regenerate_refuses_to_publish_if_original_save_failed():
    review, row, cache, events, deps = setup_regeneration()
    def refused(*, redraw_main=True):
        events.append("save_refused")
        return False
    review.save = refused
    simplified.regenerate_simplified_current_page(review, deps)
    assert events == ["save_refused"]
    assert row.word == "old"
    assert cache["10,20"]["source_word"] == "old"
    assert review.simplified_vars[0].get() == "old simplified"
    assert "已重新简体化" not in review.parent.status_var.get()


def test_pending_edit_permission_refusal_keeps_review_unconfirmed(monkeypatch):
    from picture_capture.proofreading import main_editor_sync
    monkeypatch.setattr(main_editor_sync, "bridge_main_canvas_text_into_review", lambda _: 0)
    monkeypatch.setattr(lifecycle, "_has_unreported_simplified_input", lambda _: False)
    page = Path("synthetic.png")
    row = SimpleNamespace(word="old")
    status = Text("")
    app = SimpleNamespace(
        project=object(), current_page=page, current_index=0,
        entries=[row], _foreground_batch_state=lambda index: "pending",
        _claim_page_for_manual_edit=lambda: False, status_var=status,
    )
    review = SimpleNamespace(
        parent=app, vars=[Text("new")], row_entries=[row],
        _bound_row_entries=lambda: [row], _rendered_page_stem=page.stem,
        _filter_rows_active=False, _simplified_dirty_pages=set(),
        _r3_autosave_unconfirmed=False,
    )
    assert lifecycle.autosave_commit(review, None) is True
    assert review._r3_autosave_unconfirmed is True
    assert "未保存" in status.get()
    assert review.vars[0].get() == "new"
