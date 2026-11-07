"""G1 fail-first: serialized filtered writer must honor latest user intent.

An in-flight writer commits A -> B; meanwhile the user reverts text to A.
Before callback, _queue_focused_change cancels the old pending edit because
the original_word is A. Once B commits, the reversion MUST become B -> A,
not be silently dropped while Tk continues displaying A.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import focused_filter_workflow as focused


def _running_save(*, close=False):
    callbacks, scheduled, closed, statuses = [], [], [], []
    target = {
        "page_index": 0, "x": 10, "y": 20,
        "original_word": "甲", "current_word": "乙",
    }
    review = SimpleNamespace(
        parent=SimpleNamespace(
            project=SimpleNamespace(images=[Path("001.png")]),
            current_index=0, entries=[],
            status_var=SimpleNamespace(set=statuses.append),
            _start_ui_worker=lambda *a, **kw: callbacks.append((a, kw)),
        ),
        _filter_save_running=False, _filter_save_job=None,
        _filter_pending_changes={0: {(10, 20): {
            "page_index": 0, "x": 10, "y": 20,
            "original_word": "甲", "new_word": "乙",
        }}},
        filtered_targets=[target], _filter_close_after_save=close,
        after=lambda delay, callback: scheduled.append((delay, callback)) or "timer",
        after_cancel=lambda _: None,
        _flush_focused_changes=lambda: None,
        _finish_close_review=lambda: closed.append(True),
    )
    deps = SimpleNamespace(
        tk=SimpleNamespace(TclError=RuntimeError),
        messagebox=SimpleNamespace(showwarning=lambda *a, **k: None),
        _apply_focused_review_page_updates=lambda *a: ([(0, 10, 20, "乙")], []),
    )
    focused._flush_focused_changes(review, deps)
    name, worker, done, failed = callbacks[0][0]
    assert name.startswith("focused-filter-save-")
    assert review._filter_save_running and review._filter_pending_changes == {}
    return review, target, deps, done, scheduled, closed


def test_reversion_during_successful_write_becomes_new_pending_change():
    review, target, deps, done, scheduled, _ = _running_save()
    focused._queue_focused_change(review, deps, target, "甲")
    assert review._filter_pending_changes == {}  # prior to old B commit
    done(([(0, 10, 20, "乙")], []))
    assert target["original_word"] == "乙"
    assert target["current_word"] == "甲"
    assert review._filter_pending_changes[0][(10, 20)] == {
        "page_index": 0, "x": 10, "y": 20,
        "original_word": "乙", "new_word": "甲",
    }
    assert any(delay == 1 for delay, _ in scheduled)


def test_reversion_during_close_request_does_not_discard_last_edit():
    review, target, deps, done, scheduled, closed = _running_save(close=True)
    focused._queue_focused_change(review, deps, target, "甲")
    done(([(0, 10, 20, "乙")], []))
    assert not closed
    assert review._filter_pending_changes[0][(10, 20)]["new_word"] == "甲"
    assert scheduled[-1][0] == 1


def test_pending_same_as_successful_committed_word_is_not_rewritten():
    review, target, deps, done, scheduled, closed = _running_save()
    focused._queue_focused_change(review, deps, target, "丙")
    focused._queue_focused_change(review, deps, target, "乙")
    assert review._filter_pending_changes[0][(10, 20)]["new_word"] == "乙"
    done(([(0, 10, 20, "乙")], []))
    assert target["original_word"] == "乙"
    assert target["current_word"] == "乙"
    assert review._filter_pending_changes == {}
    assert not any(delay == 1 for delay, _ in scheduled)


def test_newer_distinct_edit_keeps_new_disk_word_as_expected_original():
    review, target, deps, done, scheduled, _ = _running_save()
    focused._queue_focused_change(review, deps, target, "丙")
    done(([(0, 10, 20, "乙")], []))
    assert review._filter_pending_changes[0][(10, 20)]["original_word"] == "乙"
    assert review._filter_pending_changes[0][(10, 20)]["new_word"] == "丙"
    assert target["current_word"] == "丙"
    assert any(delay == 1 for delay, _ in scheduled)


def test_legacy_target_without_current_word_keeps_existing_pending_owner():
    review, target, deps, done, scheduled, _ = _running_save()
    target.pop("current_word")
    review._filter_pending_changes[0] = {(10, 20): {
        "page_index": 0, "x": 10, "y": 20,
        "original_word": "甲", "new_word": "丙",
    }}
    done(([(0, 10, 20, "乙")], []))
    assert review._filter_pending_changes[0][(10, 20)]["new_word"] == "丙"
    assert review._filter_pending_changes[0][(10, 20)]["original_word"] == "乙"
