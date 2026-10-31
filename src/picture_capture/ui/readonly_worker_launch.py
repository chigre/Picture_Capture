"""Launch acknowledgement barrier for read-only Tk background crop workers.

The scheduler can synchronously call a compatibility callback and still
decline the handoff (-1) or raise. Never publish such early results.
The real UI runtime normally enqueues completion for later Tk polling.
"""
from __future__ import annotations

from typing import Any, Callable


def dispatch_readonly_ui_worker(
    start_worker: Callable[..., Any],
    key: str,
    worker: Callable[..., Any],
    on_done: Callable[[Any], None],
    on_failed: Callable[[Any, Any], None],
) -> bool:
    """Deliver at most one terminal callback only after launch acknowledgement.

    A rejected launch uses the caller's generic failure path. Do not expose
    raw scheduler exceptions (possibly containing private source paths).
    None is accepted for existing synchronous in-process compatibility shims;
    only the actual shutdown sentinel -1 signals a normal-call rejection.
    """
    launch_state = ["pending"]
    buffered = [None]
    claimed = [False]

    def terminal(kind: str, payload: Any) -> None:
        if claimed[0] or launch_state[0] == "rejected":
            return
        if launch_state[0] == "pending":
            if buffered[0] is None:
                buffered[0] = (kind, payload)
            return
        claimed[0] = True
        if kind == "done":
            on_done(payload)
        else:
            on_failed(*payload)

    def done(payload: Any) -> None:
        terminal("done", payload)

    def failed(exc: Any, detail: Any) -> None:
        terminal("failed", (exc, detail))

    try:
        generation = start_worker(key, worker, done, failed)
    except Exception:
        launch_state[0] = "rejected"
        buffered[0] = None
        on_failed(None, None)
        return False

    if generation == -1:
        launch_state[0] = "rejected"
        buffered[0] = None
        on_failed(None, None)
        return False

    launch_state[0] = "accepted"
    if buffered[0] is not None:
        kind, payload = buffered[0]
        buffered[0] = None
        terminal(kind, payload)
    return True
