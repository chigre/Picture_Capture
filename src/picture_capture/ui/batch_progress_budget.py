"""Time-bounded processing of high-volume batch progress events.

A bounded *count* alone is insufficient: each event can refresh a Tk page
row, redraw the canvas, or load a page. Always yield to Tk after a short
wall-clock budget so pause/stop clicks get serviced promptly.
"""
from __future__ import annotations

from time import perf_counter


MAX_BATCH_EVENTS_PER_POLL = 16
MAX_BATCH_POLL_SECONDS = 0.008
SATURATED_BATCH_POLL_DELAY_MS = 16


def start_batch_poll_budget() -> float:
    return perf_counter()


def batch_poll_should_yield(
    events_processed: int,
    started_at: float,
    *,
    now: float | None = None,
    max_events: int = MAX_BATCH_EVENTS_PER_POLL,
    max_seconds: float = MAX_BATCH_POLL_SECONDS,
) -> bool:
    """Prevent progress-event backlogs from monopolizing the GUI thread."""
    if events_processed >= max_events:
        return True
    if events_processed <= 0:
        return False
    return (perf_counter() if now is None else now) - started_at >= max_seconds
