"""Serial coordinator for expensive Y refinement with per-page Auto Layout.

Reuse the same one-persistent-spawn-worker + background page-by-page scheduler
as safe ordinary drawing. Only the parent coordinator commits validated PDIC.
No child may mutate a project file; manual-locked pending pages are skipped.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path
from typing import Any, Callable, Sequence

from .marker_refinement_parallel import (
    commit_refined_page_result, refine_page_job,
)


def start_layout_refinement_batch(
    app: Any,
    indices: Sequence[int],
    pages: Sequence[Path],
    settings: Any,
    on_done: Callable[..., None],
) -> bool:
    """Keep a single model process while using the proven serial page scheduler.

    The background runner owns each per-page wait and publishes the original
    batch-progress events; the Tk thread never runs Paddle/IO/PDIC commits.
    """
    executor = ProcessPoolExecutor(
        max_workers=1, mp_context=multiprocessing.get_context("spawn"),
    )

    def page_owned(index: int) -> bool:
        with app._batch_state_lock:
            return app._batch_page_states.get(index) == "processing"

    def compute(index: int, _position: int, _total: int) -> dict:
        # The model instance is reused by a single persistent child.
        calculated = executor.submit(
            refine_page_job, str(pages[index]), settings, index,
        ).result()
        return commit_refined_page_result(index, calculated, page_owned)

    def finish(completed, total, stopped, results, error) -> None:
        # The serial coordinator has no outstanding page futures at this point.
        executor.shutdown(wait=False, cancel_futures=True)
        on_done(completed, total, stopped, results, error)

    try:
        started = app._start_batch_task(
            "精修画线", indices, compute, finish,
            item_label=lambda i: pages[i].name,
            foreground_page_edit=True,
            allow_pdic_edits=True,
        )
    except BaseException:
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    if not started:
        executor.shutdown(wait=False, cancel_futures=True)
    return bool(started)
