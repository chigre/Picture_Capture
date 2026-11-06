"""R3 synthetic ReviewWindow repaint: never discard unowned simplified Tk text.

An async same-page crop refresh may arrive during a partially bound simplified
editor repaint. An unproven simplified row cannot be silently skipped before
all Tk editors are destroyed. No filesystem writes, real Tk or private pages.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import review_workspace_workflow as workflow
from picture_capture.ui import review_simplified_workflow as simplified


class ReachedPostClear(Exception):
    """Fixture stops after hazardous clear, before real Tk construction."""


class Value:
    def __init__(self, value):
        self.text = value

    def get(self):
        return self.text


def _case(*, bound):
    page = Path("/synthetic/r3-review-redraw/page-01.png")
    entry = SimpleNamespace(word="原词", x=12, y=33)
    status = []
    parent = SimpleNamespace(
        project=SimpleNamespace(root=page.parent, images=[page]),
        current_page=page, image=object(), entries=[entry],
        _ordered_entries_reading_order=lambda: [entry],
        status_var=SimpleNamespace(set=status.append),
    )
    review = SimpleNamespace(
        parent=parent, _filter_rows_active=False,
        _rendered_page_stem=page.stem if bound else "",
        row_entries=[entry] if bound else [],
        vars=[Value("原词")] if bound else [],
        simplified_vars=[Value("未确认人工简体")] if bound else [],
        simplified_actual_values=[], simplified_manual_flags=[],
        simplified_auto_refresh_flags=[], simplified_editors=[],
        simplified_search_buttons=[],
        _review_render_original_words={id(entry): entry.word},
        _review_crop_height_jobs={}, _review_crop_single_flags=[],
        _review_crop_render_generation=0,
        editor_crop_widths=[], thumbnails=[], editors=[], editor_frames=[],
        _review_row_pictures=[],
        rows=SimpleNamespace(winfo_children=lambda: []),
        _simplified_page_records=lambda stem: (_ for _ in ()).throw(
            ReachedPostClear()
        ),
    )
    review._capture_simplified_edits = lambda stem: simplified._capture_simplified_edits(
        review, SimpleNamespace(), stem
    )
    deps = SimpleNamespace(
        tk=SimpleNamespace(TclError=RuntimeError), Image=SimpleNamespace(),
        font=SimpleNamespace(), _entry_font_spec=lambda *_args: None,
        _review_editor_font_size=lambda *_args: 1,
        resolve_content_font_family=lambda *_args: "",
        _focused_review_is_single_character=lambda *_args: False,
        simplified_entry_key=lambda *_args: "12,33",
    )
    return review, deps, status


def test_partial_simplified_human_editor_blocks_destructive_repaint():
    view, deps, status = _case(bound=True)
    workflow.render_rows(view, deps, preloaded_crops=[object()])
    assert [value.get() for value in view.simplified_vars] == ["未确认人工简体"]
    assert [value.get() for value in view.vars] == ["原词"]
    assert view.row_entries == view.parent.entries
    assert any("简体" in message and ("未确认" in message or "绑定" in message) for message in status)


def test_initial_empty_review_render_still_advances_to_materialization():
    view, deps, status = _case(bound=False)
    with pytest.raises(ReachedPostClear):
        workflow.render_rows(view, deps, preloaded_crops=[object()])
    assert view.vars == []
