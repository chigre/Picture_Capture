"""Keep pause/stop responsive during heavy batch progress updates."""
from pathlib import Path

from picture_capture.batch_progress_budget import (
    MAX_BATCH_EVENTS_PER_POLL,
    MAX_BATCH_POLL_SECONDS,
    SATURATED_BATCH_POLL_DELAY_MS,
    batch_poll_should_yield,
)


def test_poll_budget_caps_large_backlog_even_when_each_event_is_fast():
    assert not batch_poll_should_yield(1, 100.0, now=100.001)
    assert batch_poll_should_yield(MAX_BATCH_EVENTS_PER_POLL, 100.0, now=100.001)


def test_poll_budget_yields_on_expensive_gui_events_before_count_limit():
    assert batch_poll_should_yield(1, 100.0, now=100.0 + MAX_BATCH_POLL_SECONDS)
    assert not batch_poll_should_yield(0, 100.0, now=100.0 + 10.0)
    assert SATURATED_BATCH_POLL_DELAY_MS >= 1


def test_batch_poll_wires_budget_without_blocking_pause_stop():
    src = (Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py").read_text("utf-8")
    poll = src[src.index("    def _poll_batch_queue("):src.index("    def _finish_batch_task(", src.index("    def _poll_batch_queue("))]
    assert "batch_poll_should_yield(processed_events, poll_started)" in poll
    assert "SATURATED_BATCH_POLL_DELAY_MS if yielded else 80" in poll
    assert "thread.join(" not in poll
    assert "time.sleep(" not in poll
