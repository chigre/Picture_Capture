"""R3 real review repaint: protect unsaved original-word Tk input.

Only synthetic row objects; no real patient dictionary, OCR cache or files.
A short/out-of-date async crop cannot destroy the old editable Tk values.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import review_workspace_workflow as workspace


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Child:
    def __init__(self):
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


def _short_crop_review():
    entry = SimpleNamespace(word="saved-word", x=12, y=34)
    typed = _Var("我尚未保存的词条")
    child = _Child()
    notes = []
    parent = SimpleNamespace(
        current_page=Path("001.png"), current_index=0,
        entries=[entry], image=object(),
        _ordered_entries_reading_order=lambda: [entry],
        status_var=SimpleNamespace(set=notes.append),
    )
    review = SimpleNamespace(
        parent=parent, _filter_rows_active=False, active_index=0,
        _rendered_page_stem="001",
        _review_render_original_words={id(entry): "saved-word"},
        _capture_simplified_edits=lambda _stem: None,
        _review_crop_height_jobs={}, _review_crop_single_flags=[],
        _review_crop_render_generation=0,
        rows=SimpleNamespace(winfo_children=lambda: [child]),
        vars=[typed], row_entries=[entry],
        editors=[], editor_frames=[], simplified_vars=[],
        simplified_editors=[], simplified_search_buttons=[],
        simplified_actual_values=[], simplified_manual_flags=[],
        simplified_auto_refresh_flags=[], editor_crop_widths=[],
        thumbnails=[], _review_row_pictures=[],
        _active_crop_page_stem="001", _active_crop_fixed_size=None,
        _simplified_page_records=lambda _stem: {},
        _request_render_rows=lambda **_kw: notes.append("retry"),
    )
    return review, entry, typed, child, notes


def test_short_async_crop_never_destroys_unsaved_review_text():
    review, entry, var, child, notes = _short_crop_review()
    deps = SimpleNamespace(
        tk=SimpleNamespace(TclError=RuntimeError),
        Image=object(), font=object(),
        _entry_font_spec=None, _review_editor_font_size=None,
        resolve_content_font_family=None, _focused_review_is_single_character=None,
        simplified_entry_key=None,
    )
    workspace.render_rows(review, deps, [])
    assert not child.destroyed
    assert review.vars == [var]
    assert var.get() == "我尚未保存的词条"
    assert review.row_entries == [entry]
    assert "retry" in notes


@pytest.mark.parametrize("mode", [
    "legitimate", "changed_source", "replaced_entry", "duplicate_live",
])
def test_paint_snapshot_only_reuses_exact_original_entry_owner(mode):
    from picture_capture.proofreading.review_pending_text import capture_pending_review_words
    entry = SimpleNamespace(word="saved", x=12, y=34)
    typed = _Var("人工输入")
    live = [entry]
    baseline = {id(entry): "saved"}
    if mode == "changed_source":
        entry.word = "foreign-changed"
    elif mode == "replaced_entry":
        live = [SimpleNamespace(word="saved", x=12, y=34)]
    elif mode == "duplicate_live":
        live.append(entry)
    if mode == "legitimate":
        assert capture_pending_review_words(
            [entry], [typed], baseline, live,
        ) == {id(entry): "人工输入"}
    else:
        with pytest.raises(RuntimeError, match="(来源|归属|版本|重复|绑定)"):
            capture_pending_review_words([entry], [typed], baseline, live)


def test_unchanged_review_word_does_not_create_pending_edits():
    from picture_capture.proofreading.review_pending_text import capture_pending_review_words
    entry = SimpleNamespace(word="saved", x=12, y=34)
    assert capture_pending_review_words(
        [entry], [_Var("saved")], {id(entry): "saved"}, [entry],
    ) == {}


@pytest.mark.parametrize("drift", ["same_entry_reworded", "new_entry_same_xy"])
def test_source_drift_repaint_refuses_without_clearing_user_input(drift):
    review, entry, typed, child, notes = _short_crop_review()
    if drift == "same_entry_reworded":
        entry.word = "external-modified"
    else:
        replacement = SimpleNamespace(word="saved-word", x=12, y=34)
        review.parent.entries = [replacement]
        review.parent._ordered_entries_reading_order = lambda: [replacement]
    deps = SimpleNamespace(
        tk=SimpleNamespace(TclError=RuntimeError),
        Image=object(), font=object(),
        _entry_font_spec=None, _review_editor_font_size=None,
        resolve_content_font_family=None, _focused_review_is_single_character=None,
        simplified_entry_key=None,
    )
    workspace.render_rows(review, deps, [object()])
    assert not child.destroyed
    assert review.vars == [typed]
    assert typed.get() == "我尚未保存的词条"
    assert any("未保存" in str(x) or "保持" in str(x) for x in notes)
