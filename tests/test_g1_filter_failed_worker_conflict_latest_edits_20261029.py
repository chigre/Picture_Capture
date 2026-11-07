"""G1 fail-first: asynchronous filtered PDIC failure/conflict preserves latest edits.

These tests invoke real save callbacks, including the in-flight new-edit race,
rather than asserting text patterns. The worker may be delayed or return an
exact-source XY conflict; neither result authorizes losing human Tk edits.
"""
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import focused_filter_workflow as focused


def _setup(*, original="甲", wanted="乙", current=None, close=False):
    callbacks, closed, statuses, warnings, errors, scheduled = [], [], [], [], [], []
    change = {"page_index": 0, "x": 10, "y": 20,
              "original_word": original, "new_word": wanted}
    target = {"page_index": 0, "x": 10, "y": 20,
              "original_word": original}
    if current is not None:
        target["current_word"] = current
    parent = SimpleNamespace(
        project=SimpleNamespace(images=[Path("001.png")]),
        current_index=0, entries=[],
        status_var=SimpleNamespace(set=statuses.append),
        _start_ui_worker=lambda *args, **kwargs: callbacks.append((args, kwargs)),
    )
    review = SimpleNamespace(
        parent=parent, _filter_save_job=None, _filter_save_running=False,
        _filter_pending_changes={0: {(10, 20): change}},
        filtered_targets=[target], _filter_close_after_save=close,
        after=lambda delay, callback: scheduled.append((delay, callback)) or "next",
        _finish_close_review=lambda: closed.append("closed"),
    )
    deps = SimpleNamespace(
        _apply_focused_review_page_updates=lambda *args: (_ for _ in ()).throw(
            AssertionError("worker should not be invoked in callback tests")
        ),
        messagebox=SimpleNamespace(
            showwarning=lambda *args, **kwargs: warnings.append((args, kwargs)),
            showerror=lambda *args, **kwargs: errors.append((args, kwargs)),
        ),
    )
    focused._flush_focused_changes(review, deps)
    (name, worker, done, failed), kwargs = callbacks[0]
    assert name.startswith("focused-filter-save-")
    assert kwargs["wait_on_close"] is True
    assert review._filter_save_running is True
    assert review._filter_pending_changes == {}
    return SimpleNamespace(
        review=review, change=change, target=target, done=done, failed=failed,
        closed=closed, statuses=statuses, warnings=warnings, errors=errors,
        scheduled=scheduled,
    )


def test_failed_worker_must_not_overwrite_newer_same_xy_edit():
    f = _setup(current="乙")
    newer = dict(f.change, new_word="丙")
    f.target["current_word"] = "丙"
    f.review._filter_pending_changes[0] = {(10, 20): newer}
    f.failed(OSError("disk full"), "")
    assert f.review._filter_pending_changes[0][(10, 20)]["new_word"] == "丙"
    assert not f.review._filter_save_running
    assert len(f.errors) == 1


def test_failed_worker_cancels_deferred_close_and_preserves_pending():
    f = _setup(close=True, current="乙")
    f.failed(OSError("disk full"), "")
    assert f.review._filter_close_after_save is False
    assert not f.closed
    assert f.review._filter_pending_changes[0][(10, 20)]["new_word"] == "乙"
    assert len(f.errors) == 1


def test_conflict_cannot_silently_drop_snapshot_or_auto_close():
    f = _setup(close=True, current="乙")
    f.done(([], ["001.png: (10,20) 甲"]))
    assert f.review._filter_close_after_save is False
    assert not f.closed
    assert f.review._filter_pending_changes[0][(10, 20)]["new_word"] == "乙"
    assert len(f.warnings) == 1
    assert not f.scheduled  # no infinite immediate retry on unresolved XY


def test_clean_success_still_closes_after_explicit_close_request():
    f = _setup(close=True, current="乙")
    f.done(([(0, 10, 20, "乙")], []))
    assert f.closed == ["closed"]
    assert not f.review._filter_pending_changes
    assert not f.warnings


def test_failed_worker_respects_latest_reversion_to_original():
    f = _setup(current="乙")
    # A user has reverted to the original word while an old save was running.
    # No new queued change is necessary; restoring the old snapshot would
    # silently resurrect an edit that the user just undid.
    f.target["current_word"] = "甲"
    f.failed(OSError("disk full"), "")
    assert f.review._filter_pending_changes == {}
    assert not f.closed
