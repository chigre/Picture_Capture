"""G3 R4.2: Tk poll scheduling must be acknowledged before a worker starts.

Synthetic deterministic scheduler; no real PDIC/PPP/SECTION/OCR data or Tk window.
"""
from __future__ import annotations

import queue
import traceback
from types import SimpleNamespace

import pytest

from picture_capture.ui import background_job_runtime as runtime


@pytest.mark.parametrize("previous", (False, True))
@pytest.mark.parametrize("wait_on_close", (False, True))
def test_initial_tk_poll_failure_prevents_thread_start_and_restores_ownership(
    previous, wait_on_close,
):
    key = "focused-filter-save"
    old_token = (key, 7)
    old_done = lambda payload: None
    old_failed = lambda *args: None
    old_handlers = {old_token: (old_done, old_failed)} if previous else {}
    old_generations = {key: 7} if previous else {}
    old_active = {old_token} if previous else set()
    old_close_wait = {old_token} if previous else set()
    started = []
    constructed = []

    def fail_after(_ms, _callback):
        raise RuntimeError("PRIVATE_TK_AFTER_FAILURE:/synthetic/source.pdic")

    def make_thread(*, target, name, daemon):
        constructed.append((target, name, daemon))
        return SimpleNamespace(start=lambda: started.append(name))

    app = SimpleNamespace(
        _ui_worker_shutdown=False,
        _ui_close_requested=False,
        _ui_worker_handlers=dict(old_handlers),
        _ui_worker_generations=dict(old_generations),
        _ui_worker_active=set(old_active),
        _ui_worker_close_wait=set(old_close_wait),
        _ui_worker_queue=queue.Queue(),
        _ui_worker_poll_job=None,
        after=fail_after,
        _poll_ui_worker_queue=lambda: None,
    )

    with pytest.raises(RuntimeError, match="PRIVATE_TK_AFTER_FAILURE"):
        runtime.start_ui_worker(
            app, key, lambda: "synthetic-result", lambda result: None,
            wait_on_close=wait_on_close,
            deps={"threading": SimpleNamespace(Thread=make_thread),
                  "traceback": traceback},
        )

    # A poll that cannot be registered must be detected before starting a
    # worker that would otherwise have no UI completion/close-wait observer.
    assert constructed == []
    assert started == []
    assert app._ui_worker_handlers == old_handlers
    assert app._ui_worker_generations == old_generations
    assert app._ui_worker_active == old_active
    assert app._ui_worker_close_wait == old_close_wait
    assert app._ui_worker_poll_job is None
    assert app._ui_worker_queue.empty()


def test_existing_poll_registration_is_reused_without_an_extra_tk_after_call():
    key = "readonly-prefetch"
    started = []
    app = SimpleNamespace(
        _ui_worker_shutdown=False,
        _ui_close_requested=False,
        _ui_worker_handlers={},
        _ui_worker_generations={},
        _ui_worker_active=set(),
        _ui_worker_close_wait=set(),
        _ui_worker_queue=queue.Queue(),
        _ui_worker_poll_job="already-scheduled",
        after=lambda *_args: pytest.fail("must reuse existing Tk poll"),
        _poll_ui_worker_queue=lambda: None,
    )

    def make_thread(*, target, name, daemon):
        return SimpleNamespace(start=lambda: started.append((target, name, daemon)))

    generation = runtime.start_ui_worker(
        app, key, lambda: "synthetic-result", lambda result: None,
        deps={"threading": SimpleNamespace(Thread=make_thread),
              "traceback": traceback},
    )

    assert generation == 1
    assert len(started) == 1
    assert app._ui_worker_poll_job == "already-scheduled"
