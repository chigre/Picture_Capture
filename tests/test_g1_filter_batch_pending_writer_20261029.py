"""G1 fail-first: filtered batch navigation must wait for the same save gate.

Changing the filter batch after starting the asynchronous page/XY PDIC writer
must not destroy the original editing rows while a write is still running
or has failed with pending changes restored.
"""
from types import SimpleNamespace

from picture_capture.ui import focused_filter_workflow


def make_review(*, saving: bool, pending: bool):
    events = []
    review = SimpleNamespace(
        _filter_rows_active=True,
        filtered_targets=[{"page_index": 0, "x": i, "y": i + 1} for i in range(8)],
        filtered_batch_index=0,
        _filter_scan_complete=True,
        _filter_available_target_count=lambda: 8,
        _focused_batch_size=lambda: 4,
        _filter_save_running=False,
        _filter_pending_changes={0: {(1, 2): {"new_word": "校对"}}} if pending else {},
        _flush_focused_changes_now=lambda: (
            events.append("flush"),
            setattr(review, "_filter_save_running", saving),
        ),
        _request_filter_batch_render=lambda: events.append("render"),
        parent=SimpleNamespace(
            status_var=SimpleNamespace(set=lambda s: events.append(("status", s))),
        ),
    )
    return review, events


def test_filter_batch_refuses_navigation_during_running_write():
    review, events = make_review(saving=True, pending=False)
    focused_filter_workflow.change_filter_batch(review, None, 1)
    assert review.filtered_batch_index == 0
    assert events[0] == "flush"
    assert "render" not in events


def test_filter_batch_refuses_navigation_with_failed_pending_snapshot():
    review, events = make_review(saving=False, pending=True)
    focused_filter_workflow.change_filter_batch(review, None, 1)
    assert review.filtered_batch_index == 0
    assert "render" not in events


def test_filter_batch_clean_navigation_still_renders_next_batch():
    review, events = make_review(saving=False, pending=False)
    focused_filter_workflow.change_filter_batch(review, None, 1)
    assert review.filtered_batch_index == 1
    assert events == ["flush", "render"]
