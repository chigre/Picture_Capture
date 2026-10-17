"""Use the known-good PR #543 serial dispatcher for Auto Layout Y refinement.

The background batch thread owns one page at a time and calls the existing
read-only computation followed by the guarded PDIC coordinator. No spawned
Paddle/model pool is created by this explicit refinement path.
"""
from __future__ import annotations

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
    """Restore serial in-process per-page execution while retaining safe commits.

    This matches the successful PR #543 scheduling/lifetime semantics; newer
    cross-file version and manual-page ownership checks remain authoritative.
    """
    def page_owned(index: int) -> bool:
        with app._batch_state_lock:
            return app._batch_page_states.get(int(index)) == "processing"

    def compute(index: int, _position: int, _total: int) -> dict:
        result = refine_page_job(str(pages[index]), settings, int(index))
        return commit_refined_page_result(int(index), result, page_owned)

    return bool(app._start_batch_task(
        "精修画线", indices, compute, on_done,
        item_label=lambda i: pages[i].name,
        foreground_page_edit=True, allow_pdic_edits=True,
    ))
