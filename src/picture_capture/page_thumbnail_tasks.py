"""Bounded background thumbnail I/O. No Tk or GUI objects in worker threads.

The GUI owns selection, priority and PhotoImage creation. Only decoded small PIL
images and immutable identity tickets cross back through a thread-safe queue.
Every file generation and cache validation runs off the Tk event loop.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, CancelledError
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Mapping

from picture_capture.page_thumbnail_cache import get_page_thumbnail


@dataclass(frozen=True)
class ThumbnailResult:
    ticket: int
    page_index: int
    identity: tuple
    image: object | None
    error: str | None = None


class ThumbnailTasks:
    """Max two running jobs; no unbounded backlog under rapid page scrolling."""

    def __init__(self, *, workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, min(2, workers)), thread_name_prefix="pc-thumb",
        )
        self._completed: Queue[ThumbnailResult] = Queue()
        self._futures: dict[int, Future] = {}
        self._serial = 0
        self._closed = False

    @property
    def active(self) -> int:
        return len(self._futures)

    def submit(
        self, page_index: int, identity: tuple, project_root: Path,
        source_path: Path, names: Mapping[str, str],
    ) -> int | None:
        if self._closed or len(self._futures) >= 2:
            return None
        self._serial += 1
        ticket = self._serial
        # The worker owns scan I/O, source hashing and image decoding.
        future = self._pool.submit(
            get_page_thumbnail, project_root, source_path, names,
        )
        self._futures[ticket] = future

        def finished(fut: Future) -> None:
            try:
                image = fut.result()
                result = ThumbnailResult(ticket, page_index, identity, image)
            except CancelledError:
                result = ThumbnailResult(ticket, page_index, identity, None, "cancelled")
            except Exception as exc:
                result = ThumbnailResult(ticket, page_index, identity, None, str(exc))
            # Queue is thread-safe. NEVER call tkinter/after from this callback.
            self._completed.put(result)

        future.add_done_callback(finished)
        return ticket

    def collect(self) -> list[ThumbnailResult]:
        results: list[ThumbnailResult] = []
        while True:
            try:
                item = self._completed.get_nowait()
            except Empty:
                return results
            self._futures.pop(item.ticket, None)
            results.append(item)

    def cancel_pending(self) -> None:
        """Cancel waiting jobs; running ones may finish and are discarded by UI."""
        for future in self._futures.values():
            future.cancel()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.cancel_pending()
        self._pool.shutdown(wait=False, cancel_futures=True)


__all__ = ["ThumbnailTasks", "ThumbnailResult"]
