"""G3 R4.2 Tk worker startup rejection must not leak close-wait reservations.

Synthetic deterministic scheduler; no Tk screen or real PDIC/PPP pages.
"""
from __future__ import annotations

import queue
import traceback
from types import SimpleNamespace

import pytest

from picture_capture.ui import background_job_runtime as runtime


def _app(previous: bool):
    previous_key = ("focused-filter-save", 7)
    old_done = lambda payload: None
    old_failed = lambda *args: None
    previous_handlers = {previous_key: (old_done, old_failed)} if previous else {}
    previous_generations = {"focused-filter-save": 7} if previous else {}
    previous_active = {previous_key} if previous else set()
    # Old durable worker is still active; its close-wait token must be kept.
    previous_close_wait = {previous_key} if previous else set()
    app = SimpleNamespace(
        _ui_worker_shutdown=False,
        _ui_close_requested=False,
        _ui_worker_handlers=dict(previous_handlers),
        _ui_worker_generations=dict(previous_generations),
        _ui_worker_active=set(previous_active),
        _ui_worker_close_wait=set(previous_close_wait),
        _ui_worker_queue=queue.Queue(),
        _ui_worker_poll_job=None,
        after=lambda _ms, _func: "scheduled-poll",
        _poll_ui_worker_queue=lambda: None,
    )
    return app, (
        previous_handlers, previous_generations,
        previous_active, previous_close_wait,
    )


@pytest.mark.parametrize("stage", ("constructor", "start"))
@pytest.mark.parametrize("previous", (False, True))
@pytest.mark.parametrize("wait_on_close", (False, True))
def test_worker_start_failure_rolls_back_only_new_reservation(
    stage, previous, wait_on_close,
):
    app, expected = _app(previous)
    secret = "PRIVATE_TK_THREAD_FAILURE_C:/patient/001.pdic"

    def thread_constructor(*, target, name, daemon):
        if stage == "constructor":
            raise OSError(secret)
        assert callable(target) and name.startswith("PictureCapture-")
        assert daemon is True
        def refuse_start():
            raise RuntimeError(secret)
        return SimpleNamespace(start=refuse_start)

    deps = {
        "threading": SimpleNamespace(Thread=thread_constructor),
        "traceback": traceback,
    }
    with pytest.raises((OSError, RuntimeError)):
        runtime.start_ui_worker(
            app, "focused-filter-save",
            lambda: "new-result", lambda result: None,
            wait_on_close=wait_on_close, deps=deps,
        )
    handlers, generations, active, close_wait = expected
    assert app._ui_worker_handlers == handlers
    assert app._ui_worker_generations == generations
    assert app._ui_worker_active == active
    assert app._ui_worker_close_wait == close_wait
    assert app._ui_worker_poll_job is None
    assert app._ui_worker_queue.empty()


@pytest.mark.parametrize("previous", (False, True))
def test_successful_worker_start_retains_existing_generation_contract(previous):
    app, expected = _app(previous)
    started = []

    def thread_constructor(*, target, name, daemon):
        def start():
            started.append((target, name, daemon))
        return SimpleNamespace(start=start)

    result = runtime.start_ui_worker(
        app, "focused-filter-save",
        lambda: "done", lambda payload: None,
        wait_on_close=True,
        deps={"threading": SimpleNamespace(Thread=thread_constructor),
              "traceback": traceback},
    )
    assert result == (8 if previous else 1)
    assert len(started) == 1
    assert app._ui_worker_generations["focused-filter-save"] == result
    assert ("focused-filter-save", result) in app._ui_worker_active
    assert ("focused-filter-save", result) in app._ui_worker_close_wait
    assert ("focused-filter-save", result) in app._ui_worker_handlers
    assert not any(
        key[0] == "focused-filter-save" and key[1] != result
        for key in app._ui_worker_handlers
    )
    assert app._ui_worker_poll_job == "scheduled-poll"


@pytest.mark.parametrize("closed_flag", ("_ui_worker_shutdown", "_ui_close_requested"))
def test_closed_runtime_returns_minus_one_without_touching_existing_worker(closed_flag):
    app, expected = _app(previous=True)
    setattr(app, closed_flag, True)
    generation = runtime.start_ui_worker(
        app, "focused-filter-save",
        lambda: "never", lambda result: None, wait_on_close=True,
        deps={"threading": SimpleNamespace(
            Thread=lambda **_kw: pytest.fail("must not construct worker")),
            "traceback": traceback},
    )
    assert generation == -1
    handlers, generations, active, close_wait = expected
    assert app._ui_worker_handlers == handlers
    assert app._ui_worker_generations == generations
    assert app._ui_worker_active == active
    assert app._ui_worker_close_wait == close_wait
