"""PR #547 multi-page Y refinement must advance after its first worker wave.

Runs the production dispatcher with a controlled thread-backed process-pool
double. This exercises scheduling, result consumption and page ownership
without loading Tk, PaddleOCR or changing any PDIC.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import queue
import threading
import time
from types import SimpleNamespace

import pytest

from picture_capture.app import PictureCaptureApp


class _Var:
    def __init__(self):
        self.values = []
    def set(self, value):
        self.values.append(value)


class _Widget:
    def configure(self, **_kwargs):
        pass
    def winfo_manager(self):
        return True
    def pack(self, **_kwargs):
        pass


def _fake_app():
    app = SimpleNamespace(
        _batch_active=False,
        _batch_state_lock=threading.Lock(),
        _batch_page_states={},
        _batch_queue=queue.Queue(),
        _batch_stop_event=threading.Event(),
        _batch_pause_event=threading.Event(),
        _ui_close_requested=False,
        _ui_worker_key_active=lambda _key: False,
        _flush_deferred_page_save=lambda: None,
        _update_page_row=lambda _index: None,
        _poll_batch_queue=lambda: None,
        _batch_text_var=None,
        batch_progress_var=_Var(),
        batch_text_var=_Var(),
        status_var=_Var(),
        batch_progress=_Widget(),
        batch_pause_button=_Widget(),
        batch_stop_button=_Widget(),
        batch_bar=_Widget(),
        after=lambda *_args: None,
    )
    return app


@pytest.mark.parametrize("workers", [2, 4])
def test_multiple_parallel_waves_complete_and_parent_commits_each_page(monkeypatch, workers):
    from picture_capture import app as app_module
    # macOS CI may expose fewer than four logical cores. The synthetic
    # dispatcher test intentionally models a machine with ample CPUs.
    monkeypatch.setattr(app_module.os, "cpu_count", lambda: 16)

    # Maintain the true executor scheduling API while avoiding external
    # process spawning in the unit test. The first worker wave must overlap.
    monkeypatch.setattr(
        app_module, "ProcessPoolExecutor",
        lambda *, max_workers, mp_context: ThreadPoolExecutor(max_workers=max_workers),
    )
    app = _fake_app()
    first_wave = threading.Barrier(workers)
    lock = threading.Lock()
    active = 0
    maximum = 0
    computed = []
    committed = []
    coordinator_thread_ids = []

    def compute(index):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            computed.append(index)
        if index < workers:
            first_wave.wait(timeout=5)
        time.sleep(.01)
        with lock:
            active -= 1
        return {"index": index}

    def publish(index, result):
        assert result["index"] == index
        with app._batch_state_lock:
            assert app._batch_page_states[index] == "processing"
        committed.append(index)
        coordinator_thread_ids.append(threading.get_ident())
        return result

    main_thread_id = threading.get_ident()
    total = workers * 3
    assert PictureCaptureApp._start_parallel_batch_task(
        app, "精修画线", list(range(total)), compute,
        lambda index, _position, _total: (index,),
        result_consumer=publish,
        item_label=lambda i: f"page{i:03}",
        max_workers=workers, respect_cpu_workers=True,
        foreground_page_edit=True,
        allow_pdic_edits=True,
    )
    app._batch_thread.join(timeout=10)
    assert not app._batch_thread.is_alive(), "First worker wave completed but next wave was not dispatched"

    events = []
    while not app._batch_queue.empty():
        events.append(app._batch_queue.get_nowait())
    assert [r[0] for r in events].count("parallel_progress") == total
    assert events[-1][0] == "done"
    assert events[-1][1:4] == (total, total, False)
    assert maximum == workers
    assert sorted(computed) == sorted(committed) == list(range(total))
    assert set(coordinator_thread_ids) != {main_thread_id}
    assert app._batch_page_states == {i: "done" for i in range(total)}


def test_manually_locked_pending_page_still_skips_without_publication(monkeypatch):
    from picture_capture import app as app_module
    monkeypatch.setattr(
        app_module, "ProcessPoolExecutor",
        lambda *, max_workers, mp_context: ThreadPoolExecutor(max_workers=max_workers),
    )
    app = _fake_app()
    started = threading.Barrier(3)
    release = threading.Event()
    committed = []

    def compute(index):
        if index in (0, 1):
            started.wait(timeout=5)
            assert release.wait(timeout=5)
        return {"index": index}

    def publish(index, result):
        committed.append(index)
        return result

    assert PictureCaptureApp._start_parallel_batch_task(
        app, "精修画线", [0, 1, 2, 3], compute,
        lambda index, _position, _total: (index,),
        result_consumer=publish, max_workers=2, respect_cpu_workers=True,
        foreground_page_edit=True, allow_pdic_edits=True,
    )
    started.wait(timeout=5)
    with app._batch_state_lock:
        assert app._batch_page_states[3] == "pending"
        app._batch_page_states[3] = "manual_locked"
    release.set()
    app._batch_thread.join(timeout=10)
    assert not app._batch_thread.is_alive()
    assert sorted(committed) == [0, 1, 2]
    assert app._batch_page_states[3] == "manual_locked"
    events = []
    while not app._batch_queue.empty():
        events.append(app._batch_queue.get_nowait())
    assert [e[0] for e in events].count("skipped") == 1
    assert events[-1][0] == "done"
    assert events[-1][1:4] == (4, 4, False)


def test_single_gpu_worker_remains_spawn_isolated_across_multiple_pages(monkeypatch):
    """The one-model safety cap must NOT run Paddle inside the GUI process."""
    from picture_capture import app as app_module
    created = []
    real_executor = ThreadPoolExecutor

    def executor_double(*, max_workers, mp_context):
        created.append((max_workers, mp_context.get_start_method()))
        return real_executor(max_workers=max_workers)

    monkeypatch.setattr(app_module, "ProcessPoolExecutor", executor_double)
    app = _fake_app()
    consumed = []

    def compute(index):
        return {"index": index}

    def publish(index, result):
        consumed.append(index)
        assert result["index"] == index
        return result

    assert PictureCaptureApp._start_parallel_batch_task(
        app, "精修画线", list(range(8)), compute,
        lambda index, _position, _total: (index,),
        result_consumer=publish,
        max_workers=1, respect_cpu_workers=True, isolate_worker=True,
        foreground_page_edit=True, allow_pdic_edits=True,
    )
    app._batch_thread.join(timeout=10)
    assert not app._batch_thread.is_alive()
    assert created == [(1, "spawn")]
    assert consumed == list(range(8))
    assert app._batch_page_states == {i: "done" for i in range(8)}
    events = []
    while not app._batch_queue.empty():
        events.append(app._batch_queue.get_nowait())
    assert [event[0] for event in events].count("parallel_progress") == 8
    assert events[-1][0] == "done"
    assert events[-1][1:4] == (8, 8, False)
