"""G3/R4.2: malformed focused-row identities must not be normalized into edits.

Pure synthetic targets; no real dictionary, PDIC, OCR or operator records.
This test-only change is intentional RED evidence for the queue boundary.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.ui import focused_filter_workflow as focused


def _review():
    scheduled = []
    review = SimpleNamespace(
        _filter_pending_changes={},
        _filter_save_job=None,
        after=lambda ms, callback: scheduled.append(ms) or "job",
        _flush_focused_changes=lambda: None,
    )
    deps = SimpleNamespace(tk=SimpleNamespace(TclError=Exception))
    return review, deps, scheduled


@pytest.mark.parametrize(("field", "invalid"), [
    ("page_index", 0.9),
    ("page_index", "0"),
    ("page_index", False),
    ("x", 3.9),
    ("x", "3"),
    ("x", True),
    ("y", 4.9),
    ("y", "4"),
    ("y", False),
])
def test_invalid_focused_target_identity_is_never_queued(field, invalid):
    review, deps, scheduled = _review()
    target = {"page_index": 0, "x": 3, "y": 4, "original_word": "old"}
    target[field] = invalid

    try:
        focused._queue_focused_change(review, deps, target, "edit")
    except (RuntimeError, ValueError, TypeError):
        # Either explicit rejection or an unchanged queue is fail-closed.
        pass

    assert review._filter_pending_changes == {}
    assert scheduled == []
    assert "current_word" not in target


def test_valid_integral_focused_target_still_queues_normal_edit():
    review, deps, scheduled = _review()
    target = {"page_index": 0, "x": 3, "y": 4, "original_word": "old"}

    focused._queue_focused_change(review, deps, target, "edit")

    assert review._filter_pending_changes[0][(3, 4)]["new_word"] == "edit"
    assert review._filter_pending_changes[0][(3, 4)]["x"] == 3
    assert scheduled == [160]


@pytest.mark.parametrize(("field", "invalid"), [
    ("page_index", 0.9), ("page_index", "0"), ("page_index", False),
    ("x", 3.9), ("x", "3"), ("x", True),
    ("y", 4.9), ("y", "4"), ("y", False),
])
def test_editor_trace_invalid_source_identity_does_not_change_target(field, invalid):
    """An invalid StringVar trace must not mutate target/current_word first.

    Calling the guarded queue directly is insufficient: native Tk invokes
    the editor commit adapter, which previously changed current_word before
    the exact-page/XY queue validator could refuse the malformed identity.
    """
    review, deps, scheduled = _review()
    target = {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "current_word": "old",
    }
    target[field] = invalid
    status = []
    review.parent = SimpleNamespace(
        _project_words=[], status_var=SimpleNamespace(set=status.append),
    )
    review.filter_vars = [SimpleNamespace(get=lambda: "edited")]
    review.filter_editors = [SimpleNamespace(configure=lambda **_kw: None)]
    review._filter_current_batch_targets = [target]
    review._queue_focused_change = lambda row, value: focused._queue_focused_change(
        review, deps, row, value,
    )

    focused._commit_filter_editor_value(review, deps, 0)

    assert target["current_word"] == "old"
    assert target["original_word"] == "old"
    assert review._filter_pending_changes == {}
    assert scheduled == []
    assert any("拒绝保存" in text for text in status)


def test_editor_trace_valid_source_identity_still_changes_and_queues():
    review, deps, scheduled = _review()
    target = {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "current_word": "old",
    }
    review.parent = SimpleNamespace(_project_words=[])
    review.filter_vars = [SimpleNamespace(get=lambda: "edited")]
    review.filter_editors = [SimpleNamespace(configure=lambda **_kw: None)]
    review._filter_current_batch_targets = [target]
    review._queue_focused_change = lambda row, value: focused._queue_focused_change(
        review, deps, row, value,
    )

    focused._commit_filter_editor_value(review, deps, 0)

    assert target["current_word"] == "edited"
    assert review._filter_pending_changes[0][(3, 4)]["new_word"] == "edited"
    assert scheduled == [160]
