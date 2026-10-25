"""Nonblocking Tk worker generations, callbacks and close-safe queue polling.

Historical app class names and signatures stay stable; current Tk modules,
thread/queue callbacks, and OCR runtime helpers are injected per invocation.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    import tkinter as tk
    from ..models import AppSettings


def start_ui_worker(
    self, key: str, worker, on_done, on_error=None, *, wait_on_close: bool = False,
    deps: dict[str, Any],
) -> int:
    threading = deps["threading"]
    traceback = deps["traceback"]
    """Run one replaceable blocking operation without letting its worker touch Tk.

    wait_on_close is reserved for workers that may mutate durable files.
    A close request suppresses their UI callback but defers destroy() until
    the worker has reached its own success/error cleanup boundary.
    """
    if self._ui_worker_shutdown or self._ui_close_requested:
        return -1
    stale = [token for token in self._ui_worker_handlers if token[0] == key]
    for token in stale:
        self._ui_worker_handlers.pop(token, None)
    generation = int(self._ui_worker_generations.get(key, 0)) + 1
    self._ui_worker_generations[key] = generation
    token = (key, generation)
    self._ui_worker_handlers[token] = (on_done, on_error)
    self._ui_worker_active.add(token)
    if wait_on_close:
        self._ui_worker_close_wait.add(token)

    def runner() -> None:
        try:
            result = worker()
            event = ("done", key, generation, result, None, None)
        except Exception as exc:
            event = ("error", key, generation, None, exc, traceback.format_exc())
        self._ui_worker_queue.put(event)

    threading.Thread(
        target=runner, name=f"PictureCapture-{key}-{generation}", daemon=True,
    ).start()
    if self._ui_worker_poll_job is None:
        self._ui_worker_poll_job = self.after(40, self._poll_ui_worker_queue)
    return generation


def poll_ui_worker_queue(self, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    queue = deps["queue"]
    traceback = deps["traceback"]
    self._ui_worker_poll_job = None
    if self._ui_worker_shutdown:
        return
    processed = 0
    while processed < 48:
        try:
            kind, key, generation, result, exc, detail = self._ui_worker_queue.get_nowait()
        except queue.Empty:
            break
        processed += 1
        token = (key, generation)
        self._ui_worker_active.discard(token)
        self._ui_worker_close_wait.discard(token)
        handler = self._ui_worker_handlers.pop(token, None)
        if (
            not self._ui_close_requested
            and generation == self._ui_worker_generations.get(key)
            and handler is not None
        ):
            on_done, on_error = handler
            try:
                if kind == "done":
                    on_done(result)
                elif on_error is not None:
                    on_error(exc, detail)
                else:
                    if detail:
                        print(detail)
                    self.show_error(f"{key}失败", exc)
            except tk.TclError:
                pass
            except Exception as callback_exc:
                traceback.print_exc()
                try:
                    self.show_error(f"{key}完成处理失败", callback_exc)
                except tk.TclError:
                    pass

    if self._ui_close_requested and not self._ui_worker_close_wait:
        self.after_idle(self.on_close)
        return
    if (
        (self._ui_worker_handlers or self._ui_worker_close_wait or self._ui_worker_active)
        and not self._ui_worker_shutdown
    ):
        self._ui_worker_poll_job = self.after(
            8 if processed >= 48 else 60, self._poll_ui_worker_queue
        )


def _ui_worker_key_active(self, key: str, *, deps: dict[str, Any]) -> bool:
    return any(token[0] == key for token in self._ui_worker_active)


def _invalidate_ui_worker(self, key: str, *, deps: dict[str, Any]) -> None:
    self._ui_worker_generations[key] = int(self._ui_worker_generations.get(key, 0)) + 1
    stale = [token for token in self._ui_worker_handlers if token[0] == key]
    for token in stale:
        self._ui_worker_handlers.pop(token, None)
