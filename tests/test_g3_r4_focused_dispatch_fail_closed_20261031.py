"""G3/R3 focused-save synchronous dispatch & close refusal contract.

Synthetic E2 only. No project scan, OCR, or actual disk publication.  These
cases distinguish a failed worker launch from an acknowledged worker result.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import focused_filter_workflow as workflow
from picture_capture.ui.review_close_actions import close_review


class _Status:
    def __init__(self):
        self.messages = []

    def set(self, value):
        self.messages.append(value)

    def get(self):
        return self.messages[-1] if self.messages else ""


def _review(tmp_path, *, two_pages=False, close_intent=True):
    pages = [tmp_path / "001.bmp"]
    if two_pages:
        pages.append(tmp_path / "002.bmp")
    for p in pages:
        p.write_bytes(b"SYNTHETIC-BMP-PATH-WITNESS")
    changes = {}
    targets = []
    for index, _page in enumerate(pages):
        point = (10 + index, 20 + index)
        change = {
            "page_index": index, "x": point[0], "y": point[1],
            "original_word": f"old-{index}",
            "new_word": f"human-{index}",
            "_focused_save_source_witness": f"synthetic-source-{index}",
        }
        changes[index] = {point: change}
        targets.append({
            "page_index": index, "x": point[0], "y": point[1],
            "original_word": f"old-{index}",
            "current_word": f"human-{index}",
            "_focused_save_source_witness": f"synthetic-source-{index}",
        })
    dialogs = []
    closed = []
    status = _Status()
    review = SimpleNamespace(
        _filter_rows_active=True,
        _filter_save_job=None,
        _filter_save_running=False,
        _filter_close_after_save=close_intent,
        _filter_pending_changes=changes,
        _focused_timing_session=None,
        filtered_targets=targets,
        parent=SimpleNamespace(
            project=SimpleNamespace(images=pages),
            status_var=status,
        ),
        _finish_close_review=lambda: closed.append(True),
    )
    deps = SimpleNamespace(
        messagebox=SimpleNamespace(showerror=lambda *a, **kw: dialogs.append((a, kw))),
        _apply_focused_review_page_updates=lambda *args: pytest.fail(
            "no worker should run after launch refused"
        ),
    )
    return review, deps, dialogs, closed, status, pages


@pytest.mark.parametrize("old_close_intent", [False, True])
def test_failed_worker_launch_restores_single_human_correction(
    tmp_path, capsys, old_close_intent,
):
    review, deps, dialogs, closed, status, pages = _review(
        tmp_path, close_intent=old_close_intent
    )
    original_bytes = pages[0].read_bytes()
    before = review._filter_pending_changes[0][(10, 20)]
    sentinel = "PRIVATE_TEST_C:/patients/word-and-page001.pdic"

    def unavailable(*_a, **_kw):
        raise RuntimeError(sentinel)

    review.parent._start_ui_worker = unavailable
    workflow._flush_focused_changes(review, deps)

    assert not closed
    assert review._filter_save_running is False
    assert review._filter_close_after_save is False
    assert review._filter_pending_changes[0][(10, 20)] is before
    assert review._filter_save_launch_failed is True
    assert pages[0].read_bytes() == original_bytes
    assert len(dialogs) == 1
    presented = repr((dialogs, status.messages, capsys.readouterr()))
    assert sentinel not in presented
    assert "Traceback" not in presented


def test_failed_launch_keeps_newer_same_xy_edit_untouched(tmp_path):
    review, deps, dialogs, _closed, _status, _pages = _review(tmp_path)
    initial = review._filter_pending_changes[0][(10, 20)]

    def refuse_with_newer_edit(*_a, **_kw):
        review.filtered_targets[0]["current_word"] = "human-newer"
        review._filter_pending_changes[0] = {
            (10, 20): {**initial, "new_word": "human-newer"}
        }
        raise OSError("PRIVATE_TEST_SECOND_EDITOR")

    review.parent._start_ui_worker = refuse_with_newer_edit
    workflow._flush_focused_changes(review, deps)

    assert review._filter_save_launch_failed is True
    assert review._filter_pending_changes[0][(10, 20)]["new_word"] == "human-newer"
    assert review.filtered_targets[0]["original_word"] == "old-0"
    assert review._filter_close_after_save is False
    assert len(dialogs) == 1


def test_failed_launch_after_explicit_reversion_still_disarms_close(tmp_path):
    review, deps, dialogs, closed, _status, _pages = _review(tmp_path)

    def refuse_after_user_reversion(*_a, **_kw):
        review.filtered_targets[0]["current_word"] = "old-0"
        raise OSError("PRIVATE_TEST_REVERTED")

    review.parent._start_ui_worker = refuse_after_user_reversion
    workflow._flush_focused_changes(review, deps)
    assert review._filter_pending_changes == {}
    assert review._filter_close_after_save is False
    assert review._filter_save_launch_failed is True

    # An empty queue alone is not proof that an uncertain worker launch was safe.
    review._flush_focused_changes_now = lambda: workflow._flush_focused_changes(
        review, deps
    )
    close_review(review, showerror=lambda *a, **kw: dialogs.append((a, kw)))
    assert not closed
    assert review._filter_save_launch_failed is True


def test_failed_launch_restores_all_pages_without_claiming_atomic_write(tmp_path):
    review, deps, dialogs, closed, _status, pages = _review(
        tmp_path, two_pages=True
    )
    initial_bytes = [p.read_bytes() for p in pages]
    original_changes = {
        index: list(changes.values())[0]
        for index, changes in review._filter_pending_changes.items()
    }
    review.parent._start_ui_worker = lambda *a, **kw: (
        (_ for _ in ()).throw(OSError("PRIVATE_TEST_PAGE_002"))
    )
    workflow._flush_focused_changes(review, deps)

    assert not closed
    assert review._filter_save_launch_failed is True
    assert review._filter_close_after_save is False
    assert [p.read_bytes() for p in pages] == initial_bytes
    assert set(review._filter_pending_changes) == {0, 1}
    for i in (0, 1):
        p = (10 + i, 20 + i)
        assert review._filter_pending_changes[i][p] is original_changes[i]
    assert len(dialogs) == 1


def test_project_page_snapshot_failure_does_not_erase_queued_human_edits(
    tmp_path, capsys,
):
    review, deps, _dialogs, closed, status, _pages = _review(tmp_path)
    pending = review._filter_pending_changes[0][(10, 20)]
    sentinel = "PRIVATE_TEST_BAD_PAGE_SOURCE"

    class BrokenPages:
        def __iter__(self):
            raise OSError(sentinel)

    review.parent.project.images = BrokenPages()
    review._flush_focused_changes_now = lambda: workflow._flush_focused_changes(
        review, deps
    )
    review.parent._start_ui_worker = lambda *a, **kw: pytest.fail(
        "invalid source must not schedule a worker"
    )
    alerts = []
    close_review(review, showerror=lambda *a, **kw: alerts.append((a, kw)))

    assert not closed
    assert review._filter_pending_changes[0][(10, 20)] is pending
    assert review._filter_save_running is False
    assert review._filter_close_after_save is False
    assert len(alerts) == 1
    assert sentinel not in repr((alerts, status.messages, capsys.readouterr()))


@pytest.mark.parametrize("silent_return", ["missing_project", "empty_project"])
def test_focused_close_does_not_claim_saving_if_no_worker_was_launched(
    tmp_path, silent_return,
):
    review, deps, dialogs, closed, status, _pages = _review(tmp_path)
    if silent_return == "missing_project":
        review.parent.project = None
    else:
        review.parent.project.images = ()
    # A missing project currently stops before any _start_ui_worker call.
    # The empty-project case intentionally supplies no worker; a future
    # implementation must still never declare an unstarted save as in flight.
    review._flush_focused_changes_now = lambda: (
        workflow._flush_focused_changes(review, deps)
        if silent_return == "missing_project" else None
    )
    close_review(review, showerror=lambda *a, **kw: dialogs.append((a, kw)))

    assert not closed
    assert review._filter_close_after_save is False
    assert review._filter_pending_changes[0][(10, 20)]["new_word"] == "human-0"
    assert "正在保存" not in status.get()
    assert "未" in status.get() or "重试" in status.get()


def test_late_callback_from_rejected_launch_cannot_autoretry_or_certify_write(
    tmp_path,
):
    review, deps, dialogs, closed, status, _pages = _review(tmp_path)
    callbacks, delayed_autosaves = [], []
    review.parent.current_index = 0
    review.parent.entries = []
    review.after = lambda *args: delayed_autosaves.append(args) or "unexpected-job"

    def launch_then_raise(_key, worker, done, failed, **_options):
        callbacks.append((worker, done, failed))
        raise RuntimeError("PRIVATE_LATE_WORKER_START_FAILURE")

    review.parent._start_ui_worker = launch_then_raise
    workflow._flush_focused_changes(review, deps)
    assert review._filter_save_launch_failed is True
    assert len(callbacks) == 1
    assert not closed

    # Some worker implementations can report a late result after an
    # ambiguous start failure; neither that result nor a status label
    # gives the close coordinator an acknowledged dispatch contract.
    _worker, done, _failed = callbacks[0]
    done(([(0, 10, 20, "human-0")], []))

    assert review._filter_save_launch_failed is True
    assert not review._filter_save_running
    assert not review._filter_close_after_save
    assert review._filter_pending_changes[0][(10, 20)]["new_word"] == "human-0"
    assert review.filtered_targets[0]["original_word"] == "old-0"
    assert delayed_autosaves == []
    assert not closed
    assert len(dialogs) == 1
    assert "未确认" in status.get() or "重试" in status.get()


def test_explicit_retry_after_failed_dispatch_can_launch_verified_worker(tmp_path):
    review, deps, dialogs, closed, _status, _pages = _review(tmp_path)
    review.parent._start_ui_worker = lambda *_a, **_kw: (
        (_ for _ in ()).throw(RuntimeError("PRIVATE_TRANSIENT_START"))
    )
    workflow._flush_focused_changes(review, deps)
    assert review._filter_save_launch_failed is True
    assert review._filter_pending_changes[0][(10, 20)]["new_word"] == "human-0"

    accepted = []
    review.parent._start_ui_worker = lambda *a, **kw: accepted.append((a, kw))
    workflow._flush_focused_changes(review, deps)
    assert len(accepted) == 1
    assert review._filter_save_launch_failed is False
    assert review._filter_save_running is True
    assert review._filter_pending_changes == {}
    assert not closed
    assert len(dialogs) == 1
