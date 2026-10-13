"""Issue #419: bounded in-flight process jobs, cancellation and result parity."""
from __future__ import annotations

from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
import threading

import pytest
import picture_capture.single_line_parallel as parallel


class _ThreadPoolLikeProcessPool(ThreadPoolExecutor):
    last = None

    def __init__(self, max_workers, mp_context=None):
        del mp_context
        super().__init__(max_workers=max_workers)
        self.submitted = []
        self.initial_window_submitted = threading.Event()
        type(self).last = self

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args))
        if len(self.submitted) == 4:
            self.initial_window_submitted.set()
        return super().submit(fn, *args, **kwargs)


def _stub_runtime(monkeypatch):
    _ThreadPoolLikeProcessPool.last = None
    monkeypatch.setattr(parallel, "configured_single_line_workers", lambda *_: 2)
    monkeypatch.setattr(parallel, "load_merge_by_page", lambda *_: False)
    monkeypatch.setattr(parallel, "ProcessPoolExecutor", _ThreadPoolLikeProcessPool)
    monkeypatch.setattr(parallel, "get_context", lambda *_: None)
    monkeypatch.setattr(parallel, "append_crop_log", lambda *_: None)


def test_two_worker_pool_submits_at_most_four_before_completion(tmp_path, monkeypatch):
    _stub_runtime(monkeypatch)
    release = threading.Event()
    completed = []
    images = tuple(tmp_path / f"p{index}.png" for index in range(30))

    def job(_root, _path, index, *_args):
        assert release.wait(timeout=10)
        return index, f"p{index}.png", [index], False

    monkeypatch.setattr(parallel, "single_line_page_job", job)
    with ThreadPoolExecutor(max_workers=1) as coordinator:
        outcome = coordinator.submit(
            parallel.run_single_line_pages, tmp_path, images, tuple(range(30)),
            object(), lambda *args: completed.append(args),
        )
        pool = None
        try:
            # Ensure the coordinator has queued its first window.
            for _ in range(300):
                pool = _ThreadPoolLikeProcessPool.last
                if pool is None:
                    threading.Event().wait(0.01)
                elif pool.initial_window_submitted.wait(0.01):
                    break
            assert pool is not None and pool.initial_window_submitted.is_set()
            assert len(pool.submitted) == 4
        finally:
            release.set()
        result = outcome.result(timeout=15)
    assert len(pool.submitted) == 30
    assert result[0:2] == (30, 30)
    assert len(completed) == 30


def test_cancel_stops_new_dispatch_and_retains_completed_result(tmp_path, monkeypatch):
    _stub_runtime(monkeypatch)
    canceled = threading.Event()
    completed = []
    images = tuple(tmp_path / f"p{index}.png" for index in range(80))
    monkeypatch.setattr(
        parallel, "single_line_page_job",
        lambda _root, _path, index, *_args: (index, f"p{index}.png", [index], False),
    )

    def progress(*args):
        completed.append(args)
        canceled.set()

    with pytest.raises(CancelledError):
        parallel.run_single_line_pages(
            tmp_path, images, tuple(range(80)), object(), progress,
            cancel_requested=canceled.is_set,
        )
    assert completed
    assert len(_ThreadPoolLikeProcessPool.last.submitted) <= 4


def test_serial_cancel_checks_before_next_page(tmp_path, monkeypatch):
    monkeypatch.setattr(parallel, "configured_single_line_workers", lambda *_: 1)
    monkeypatch.setattr(parallel, "load_merge_by_page", lambda *_: False)
    monkeypatch.setattr(parallel, "append_crop_log", lambda *_: None)
    canceled = threading.Event()
    called = []
    def job(_root, _path, index, *_args):
        called.append(index)
        return index, f"p{index}.png", [index], False
    monkeypatch.setattr(parallel, "single_line_page_job", job)
    images = tuple(tmp_path / f"p{index}.png" for index in range(3))
    with pytest.raises(CancelledError):
        parallel.run_single_line_pages(
            tmp_path, images, (0, 1, 2), object(),
            lambda *_: canceled.set(), cancel_requested=canceled.is_set,
        )
    assert called == [0]
