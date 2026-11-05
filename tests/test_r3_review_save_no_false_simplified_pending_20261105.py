"""Regression: normal original-word Save must not invent simplified input.

Tests use synthetic rows/Tk-like values only. No real dictionary data.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import review_simplified_workflow as workflow
from picture_capture.proofreading import main_editor_sync


class Value:
    def __init__(self, value: str):
        self.value = value

    def get(self) -> str:
        return self.value


def _case(*, old: str, new: str, actual: str, displayed: str):
    page = Path("synthetic.png")
    row = SimpleNamespace(word=old, x=10, y=20)
    saved = {
        "x": 10, "y": 20, "source_word": old,
        "text": actual, "manual": False,
    }
    records = {"10,20": saved.copy()}
    deps = SimpleNamespace(simplified_entry_key=lambda x, y: f"{x},{y}")
    app = SimpleNamespace(
        current_page=page, entries=[row], entry_editor_bindings=[],
    )
    view = SimpleNamespace(
        parent=app, _rendered_page_stem=page.stem, _filter_rows_active=False,
        row_entries=[row], vars=[Value(new)],
        simplified_vars=[Value(displayed)],
        simplified_actual_values=[actual], simplified_manual_flags=[False],
        _simplified_dirty_pages=set(),
        _simplified_page_records=lambda _stem: records,
        _simplified_display_from_value=lambda word, text, manual:
            workflow._simplified_display_from_value(deps, word, text, manual),
    )
    view._bound_row_entries = lambda: list(view.row_entries)
    view._capture_simplified_edits = lambda stem: workflow._capture_simplified_edits(
        view, deps, stem,
    )
    return page, row, records, view, deps


@pytest.mark.parametrize("old,new,actual,displayed", [
    ("原詞", "修訂詞", "原詞", "√"),
    ("繁體字", "另一個詞", "简体字", "简体字"),
    ("旧词", "新词", "新词", "新词"),
])
def test_unchanged_simplified_preview_is_not_a_human_override(
    old, new, actual, displayed,
):
    page, row, records, view, deps = _case(
        old=old, new=new, actual=actual, displayed=displayed,
    )
    workflow._capture_simplified_edits(view, deps, page.stem)
    assert view.simplified_manual_flags == [False]
    assert view._simplified_dirty_pages == set()
    assert row.word == old  # model still source-pinned before commit
    assert records["10,20"] == {
        "x": 10, "y": 20, "source_word": old,
        "text": actual, "manual": False,
    }
    main_editor_sync.commit_proofread_entries(view)
    assert row.word == new
    assert records["10,20"]["source_word"] == new
    assert records["10,20"]["manual"] is False


def test_real_simplified_edit_remains_manual_and_dirty():
    page, row, records, view, deps = _case(
        old="原詞", new="改詞", actual="原詞", displayed="人工简体",
    )
    workflow._capture_simplified_edits(view, deps, page.stem)
    assert view.simplified_manual_flags == [True]
    assert page.stem in view._simplified_dirty_pages
    assert records["10,20"] == {
        "x": 10, "y": 20, "source_word": "原詞",
        "text": "人工简体", "manual": True,
    }
    assert row.word == "原詞"
