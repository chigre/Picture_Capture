"""G3/R3 review-close privacy and async ownership boundary (synthetic E2).

A review window must not close on an unverified save, nor expose project
paths/headwords embedded in filesystem or transaction errors. No real scans.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.ui.review_close_actions import close_review
from picture_capture.ui import focused_filter_workflow as flow


class _Status:
    def __init__(self):
        self.text = ""
    def set(self, value):
        self.text = value
    def get(self):
        return self.text


def _normal_review(save):
    closed, dialogs = [], []
    review = SimpleNamespace(
        _filter_rows_active=False,
        save=save,
        parent=SimpleNamespace(status_var=_Status()),
        _finish_close_review=lambda: closed.append(True),
    )
    return review, closed, dialogs


@pytest.mark.parametrize("secret", [
    r"C:\PRIVATE_PATIENT_PROJECT\SCAN_0081.tif",
    "/PRIVATE_PATIENT_PROJECT/001.pdic",
    "PRIVATE_HEADWORD_敏感内容",
])
def test_normal_review_failed_close_redacts_private_error_and_keeps_window(
    secret, capsys,
):
    """A generic save exception must never put its message into Tk text."""
    def fail():
        raise OSError("synthetic IO failure " + secret)

    review, closed, dialogs = _normal_review(fail)
    close_review(
        review, showerror=lambda title, message, **kw: dialogs.append(
            (title, message)
        ),
    )
    assert not closed
    assert len(dialogs) == 1
    assert "保存失败" in review.parent.status_var.get()
    assert "校对未保存" in dialogs[0][0]
    assert "不会关闭" in dialogs[0][1]
    reported = review.parent.status_var.get() + repr(dialogs)
    output = capsys.readouterr()
    assert secret not in reported + output.out + output.err
    assert "PRIVATE_" not in reported


def test_normal_review_false_save_stays_open_without_success_or_error():
    review, closed, dialogs = _normal_review(lambda: False)
    close_review(review, showerror=lambda *a, **kw: dialogs.append((a, kw)))
    assert not closed and not dialogs


def test_normal_review_success_closes_once_without_dialogs():
    review, closed, dialogs = _normal_review(lambda: True)
    close_review(review, showerror=lambda *a, **kw: dialogs.append((a, kw)))
    assert closed == [True] and not dialogs


def test_focused_review_close_waits_for_running_worker_even_without_queue():
    closed = []
    review = SimpleNamespace(
        _filter_rows_active=True,
        _filter_save_running=True,
        _filter_pending_changes={},
        _filter_close_after_save=False,
        _flush_focused_changes_now=lambda: None,
        _finish_close_review=lambda: closed.append(True),
        parent=SimpleNamespace(status_var=_Status()),
    )
    close_review(review, showerror=lambda *a, **kw: pytest.fail("unexpected modal"))
    assert not closed and review._filter_close_after_save
    assert "正在保存" in review.parent.status_var.get()


def test_focused_review_close_flushes_new_queue_and_waits_for_worker():
    closed, flushed = [], []
    review = SimpleNamespace(
        _filter_rows_active=True,
        _filter_save_running=False,
        _filter_pending_changes={0: {(3, 4): "synthetic-unsaved"}},
        _filter_close_after_save=False,
        parent=SimpleNamespace(status_var=_Status()),
        _finish_close_review=lambda: closed.append(True),
    )
    def flush():
        flushed.append(True)
        review._filter_pending_changes.clear()
        review._filter_save_running = True
    review._flush_focused_changes_now = flush
    close_review(review, showerror=lambda *a, **kw: pytest.fail("unexpected modal"))
    assert flushed == [True] and not closed and review._filter_close_after_save


def test_focused_idle_review_closes_without_scheduling_work():
    closed = []
    review = SimpleNamespace(
        _filter_rows_active=True,
        _filter_save_running=False,
        _filter_pending_changes={},
        _filter_close_after_save=False,
        _flush_focused_changes_now=lambda: None,
        _finish_close_review=lambda: closed.append(True),
        parent=SimpleNamespace(status_var=_Status()),
    )
    close_review(review, showerror=lambda *a, **kw: pytest.fail("unexpected modal"))
    assert closed == [True]


def test_recovered_but_uncommitted_save_disarms_stale_close_intent():
    """A writer that reports no commit must not defer-close indefinitely.

    The restored correction is intentionally left for explicit inspection.
    A later unrelated autosave may not inherit this earlier close intent.
    """
    calls, scheduled, closed, dialogs = [], [], [], []
    point = (3, 4)
    change = {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "new_word": "human-edit",
    }
    target = {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "current_word": "human-edit",
    }
    parent = SimpleNamespace(
        project=SimpleNamespace(images=["synthetic.bmp"]),
        current_index=0,
        entries=[],
        status_var=_Status(),
        _start_ui_worker=lambda *a, **kw: calls.append((a, kw)),
    )
    review = SimpleNamespace(
        parent=parent,
        _filter_rows_active=False,  # legacy helper ABI; no physical write
        _filter_save_job=None,
        _filter_save_running=False,
        _filter_close_after_save=True,
        _filter_pending_changes={0: {point: change}},
        filtered_targets=[target],
        _focused_timing_session=None,
        after=lambda ms, fn: scheduled.append((ms, fn)) or "job",
        _finish_close_review=lambda: closed.append(True),
    )
    deps = SimpleNamespace(
        messagebox=SimpleNamespace(
            showwarning=lambda *a, **kw: dialogs.append((a, kw))
        ),
        _apply_focused_review_page_updates=lambda *a: ([], []),
    )
    flow._flush_focused_changes(review, deps)
    _args, _kw = calls[0]
    _name, worker, done, failed = _args
    done(worker())
    assert not closed and not dialogs
    assert review._filter_pending_changes[0][point]["new_word"] == "human-edit"
    assert not review._filter_close_after_save
    assert "尚有未确认修改" in review.parent.status_var.get()
    assert not scheduled
