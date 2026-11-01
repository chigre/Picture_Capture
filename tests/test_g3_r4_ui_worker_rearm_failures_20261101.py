"""G3 R4.2: recurring Tk poll and deferred-close scheduling failure recovery.

Synthetic deterministic Tk scheduler only. No real project files, scans or OCR.
"""
from __future__ import annotations

import queue
import traceback
from types import SimpleNamespace

import pytest

from picture_capture.ui import background_job_runtime as runtime
from picture_capture.ui import main_app_lifecycle as lifecycle


class _Tk:
    class TclError(Exception):
        pass


class _Status:
    def __init__(self):
        self.messages = []

    def set(self, value):
        self.messages.append(value)


def _poll_app(*, after, after_idle, close_requested=False, idle_fallback_used=False):
    token = ("durable-save", 4)
    return SimpleNamespace(
        _ui_worker_shutdown=False,
        _ui_close_requested=close_requested,
        _ui_worker_poll_job="current-poll",
        _ui_worker_poll_idle_fallback_used=idle_fallback_used,
        _ui_worker_generations={"durable-save": 4},
        _ui_worker_handlers={token: (lambda _value: None, None)},
        _ui_worker_active={token},
        _ui_worker_close_wait={token},
        _ui_worker_queue=queue.Queue(),
        after=after,
        after_idle=after_idle,
        _poll_ui_worker_queue=lambda: None,
        on_close=lambda: None,
        status_var=_Status(),
        deiconify=lambda: None,
    )


def _deps():
    return {"tk": _Tk, "queue": queue, "traceback": traceback}


def test_recurring_after_failure_uses_one_idle_fallback_then_recovers():
    calls = {"after": 0, "idle": 0}

    def after(_ms, _callback):
        calls["after"] += 1
        if calls["after"] == 1:
            raise RuntimeError("PRIVATE_TK_AFTER:/synthetic/page001.pdic")
        return "recovered-after-job"

    def after_idle(_callback):
        calls["idle"] += 1
        return "one-shot-idle-fallback"

    app = _poll_app(after=after, after_idle=after_idle)
    runtime.poll_ui_worker_queue(app, deps=_deps())

    assert app._ui_worker_poll_job == "one-shot-idle-fallback"
    assert app._ui_worker_poll_idle_fallback_used is True
    assert app._ui_worker_active == {("durable-save", 4)}
    assert app._ui_worker_close_wait == {("durable-save", 4)}

    # Simulate the one-shot idle callback. A recovered normal after() resets
    # the fallback latch and restores the regular poll cadence.
    runtime.poll_ui_worker_queue(app, deps=_deps())
    assert app._ui_worker_poll_job == "recovered-after-job"
    assert app._ui_worker_poll_idle_fallback_used is False
    assert calls == {"after": 2, "idle": 1}


def test_second_recurring_schedule_failure_stops_idle_spin_and_preserves_worker():
    sentinel = "PRIVATE_TK_AFTER:/synthetic/private-word.pdic"

    def after(_ms, _callback):
        raise RuntimeError(sentinel)

    def after_idle(_callback):
        pytest.fail("one-shot idle fallback must not become an infinite retry loop")

    app = _poll_app(
        after=after, after_idle=after_idle, idle_fallback_used=True,
    )
    runtime.poll_ui_worker_queue(app, deps=_deps())

    assert app._ui_worker_poll_job is None
    assert app._ui_worker_active == {("durable-save", 4)}
    assert app._ui_worker_close_wait == {("durable-save", 4)}
    assert sentinel not in repr(app.status_var.messages)
    assert app.status_var.messages


def test_recurring_schedule_failure_during_close_restores_visible_retryable_state():
    sentinel = "PRIVATE_TK_AFTER:/synthetic/private-word.pdic"
    visibility = []

    def after(_ms, _callback):
        raise RuntimeError(sentinel)

    def after_idle(_callback):
        raise RuntimeError(sentinel)

    app = _poll_app(
        after=after, after_idle=after_idle, close_requested=True,
    )
    app.deiconify = lambda: visibility.append("visible")
    runtime.poll_ui_worker_queue(app, deps=_deps())

    assert app._ui_close_requested is True
    assert visibility == ["visible"]
    assert app._ui_worker_close_wait == {("durable-save", 4)}
    assert app._ui_worker_active == {("durable-save", 4)}
    assert app._ui_worker_poll_job is None
    assert sentinel not in repr(app.status_var.messages)


def test_after_idle_close_failure_falls_back_to_direct_tk_thread_close():
    calls = []

    def fail_idle(_callback):
        raise RuntimeError("PRIVATE_AFTER_IDLE:/synthetic/project.pdic")

    app = SimpleNamespace(
        _ui_worker_shutdown=False,
        _ui_close_requested=True,
        _ui_worker_poll_job="current-poll",
        _ui_worker_poll_idle_fallback_used=False,
        _ui_worker_generations={},
        _ui_worker_handlers={},
        _ui_worker_active=set(),
        _ui_worker_close_wait=set(),
        _ui_worker_queue=queue.Queue(),
        after=lambda *_args: "unused",
        after_idle=fail_idle,
        _poll_ui_worker_queue=lambda: None,
        on_close=lambda: calls.append("closed-on-tk-thread"),
        status_var=_Status(),
    )
    runtime.poll_ui_worker_queue(app, deps=_deps())
    assert calls == ["closed-on-tk-thread"]


def _close_app(*, after, after_idle, close_requested=False):
    token = ("durable-save", 4)
    invalidated = []
    withdrawn = []
    status = _Status()
    app = SimpleNamespace(
        _batch_active=False,
        _ui_worker_shutdown=False,
        _ui_close_requested=close_requested,
        _ui_worker_poll_job=None,
        _ui_worker_poll_idle_fallback_used=False,
        _ui_worker_generations={"durable-save": 4},
        _ui_worker_handlers={token: (lambda _value: None, None)},
        _ui_worker_active={token},
        _ui_worker_close_wait={token},
        status_var=status,
        after=after,
        after_idle=after_idle,
        _poll_ui_worker_queue=lambda: None,
        _invalidate_ui_worker=lambda key: invalidated.append(key),
        withdraw=lambda: withdrawn.append(True),
        _flush_deferred_page_save=lambda: None,
    )
    return app, invalidated, withdrawn, status


def _close_deps():
    return {
        "messagebox": SimpleNamespace(askyesno=lambda *a, **k: False),
        "tk": _Tk,
        "settings_path": lambda _root: "synthetic-settings",
        "schedule_ui_worker_poll": runtime.schedule_ui_worker_poll,
    }


def test_close_with_active_durable_worker_does_not_hide_if_poll_cannot_be_scheduled():
    sentinel = "PRIVATE_CLOSE_SCHEDULE:/synthetic/page001.pdic"

    def after(_ms, _callback):
        raise RuntimeError(sentinel)

    def after_idle(_callback):
        raise RuntimeError(sentinel)

    app, invalidated, withdrawn, status = _close_app(
        after=after, after_idle=after_idle,
    )
    lifecycle.on_close(app, deps=_close_deps())

    assert app._ui_close_requested is False
    assert invalidated == []
    assert withdrawn == []
    assert app._ui_worker_close_wait == {("durable-save", 4)}
    assert app._ui_worker_poll_job is None
    assert sentinel not in repr(status.messages)
    assert status.messages


def test_close_schedules_fallback_before_committing_close_intent_and_hiding():
    def after(_ms, _callback):
        raise RuntimeError("synthetic transient after failure")

    def after_idle(_callback):
        return "accepted-idle-poll"

    app, invalidated, withdrawn, _status = _close_app(
        after=after, after_idle=after_idle,
    )
    lifecycle.on_close(app, deps=_close_deps())

    assert app._ui_worker_poll_job == "accepted-idle-poll"
    assert app._ui_close_requested is True
    assert invalidated == ["durable-save"]
    assert withdrawn == [True]


def test_repeated_close_retries_missing_poll_without_reinvalidating_generation():
    scheduled = []

    def after(_ms, _callback):
        return "retry-after-poll"

    app, invalidated, withdrawn, _status = _close_app(
        after=after, after_idle=lambda *_args: pytest.fail("not needed"),
        close_requested=True,
    )
    lifecycle.on_close(app, deps=_close_deps())

    assert app._ui_worker_poll_job == "retry-after-poll"
    assert app._ui_close_requested is True
    assert invalidated == []
    assert withdrawn == [True]


def test_failed_rearm_during_close_keeps_close_intent_and_reopens_for_retry():
    visibility = []

    def fail(_ms, _callback):
        raise RuntimeError("PRIVATE_REARM:/synthetic/durable.pdic")

    app = _poll_app(after=fail, after_idle=fail, close_requested=True)
    app.deiconify = lambda: visibility.append("visible")
    runtime.poll_ui_worker_queue(app, deps=_deps())

    # The close request remains authoritative and callbacks stay suppressed;
    # the visible window exists only so the operator can retry scheduling.
    assert app._ui_close_requested is True
    assert visibility == ["visible"]
    assert app._ui_worker_close_wait == {("durable-save", 4)}
    assert app._ui_worker_active == {("durable-save", 4)}
    assert app._ui_worker_poll_job is None


def test_explicit_close_retry_resets_idle_fallback_latch_before_rescheduling():
    def after(_ms, _callback):
        raise RuntimeError("PRIVATE_RETRY_AFTER:/synthetic/durable.pdic")

    def after_idle(_callback):
        return "retry-idle-poll"

    app, invalidated, withdrawn, _status = _close_app(
        after=after, after_idle=after_idle, close_requested=True,
    )
    app._ui_worker_poll_idle_fallback_used = True
    lifecycle.on_close(app, deps=_close_deps())

    assert app._ui_worker_poll_job == "retry-idle-poll"
    assert app._ui_worker_poll_idle_fallback_used is True
    assert app._ui_close_requested is True
    assert invalidated == []
    assert withdrawn == [True]


def test_failed_explicit_close_retry_keeps_window_visible_and_close_intent():
    sentinel = "PRIVATE_RETRY_CLOSE:/synthetic/durable.pdic"

    def fail(_ms, _callback):
        raise RuntimeError(sentinel)

    app, invalidated, withdrawn, status = _close_app(
        after=fail, after_idle=fail, close_requested=True,
    )
    visible = []
    app.deiconify = lambda: visible.append(True)
    lifecycle.on_close(app, deps=_close_deps())

    assert app._ui_close_requested is True
    assert visible == [True]
    assert invalidated == []
    assert withdrawn == []
    assert sentinel not in repr(status.messages)
