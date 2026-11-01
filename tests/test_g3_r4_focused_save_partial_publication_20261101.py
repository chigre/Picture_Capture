"""G3 R4.2: reconcile confirmed page commits when a later page fails.

Synthetic PNG/PDIC-source witnesses and an injected writer only. No real
project data, OCR or operator acceptance.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_save_source_witness,
)
from picture_capture.ui import focused_filter_workflow as workflow


class _Status:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


def test_partial_multi_page_save_does_not_requeue_confirmed_commit(tmp_path: Path):
    pages = [tmp_path / "001.png", tmp_path / "002.png"]
    for page in pages:
        Image.new("RGB", (8, 8), "white").save(page)

    targets = []
    pending = {}
    for index, page in enumerate(pages):
        x, y = 10 + index, 20 + index
        witness = focused_save_source_witness(page)
        target = {
            "page_index": index, "x": x, "y": y,
            "original_word": f"old-{index}",
            "current_word": f"human-{index}",
            "_focused_save_source_witness": witness,
        }
        change = {
            "page_index": index, "x": x, "y": y,
            "original_word": f"old-{index}",
            "new_word": f"human-{index}",
            "_focused_save_source_witness": witness,
        }
        targets.append(target)
        pending[index] = {(x, y): change}

    def apply_page(_page, _pages, page_index, changes):
        if page_index == 0:
            return [
                (0, int(change["x"]), int(change["y"]), change["new_word"])
                for change in changes
            ], []
        # Page 002 fails before its writer is invoked. Page 001 has already
        # returned a fully verified commit and must not be retried.
        raise OSError("PRIVATE_SYNTHETIC_PAGE_002_FAILURE")

    callbacks = []
    status = _Status()
    review = SimpleNamespace(
        parent=SimpleNamespace(
            project=SimpleNamespace(images=pages),
            status_var=status,
        ),
        _filter_rows_active=True,
        filtered_targets=targets,
        _filter_pending_changes=pending,
        _filter_save_job=None,
        _filter_save_running=False,
        _filter_close_after_save=True,
        _focused_timing_session=None,
        _filter_save_dispatch_serial=0,
    )
    deps = SimpleNamespace(
        _apply_focused_review_page_updates=apply_page,
        messagebox=SimpleNamespace(
            showerror=lambda *args, **kwargs: None,
            showwarning=lambda *args, **kwargs: None,
        ),
    )
    review.parent._start_ui_worker = lambda *args, **kwargs: callbacks.append(
        (args, kwargs)
    )

    workflow._flush_focused_changes(review, deps)
    args, kwargs = callbacks[0]
    assert kwargs == {"wait_on_close": True}
    _key, worker, _done, failed = args
    try:
        worker()
    except OSError as exc:
        failed(exc, "PRIVATE_SYNTHETIC_TRACE")
    else:
        raise AssertionError("the second page must fail in this fixture")

    # Page 001 was acknowledged by the writer and must not be retried.
    assert 0 not in review._filter_pending_changes
    assert targets[0]["original_word"] == "human-0"
    # Page 002 never reached publication and must remain available for retry.
    assert review._filter_pending_changes[1][(11, 21)]["new_word"] == "human-1"
    assert review._filter_save_running is False
    assert review._filter_close_after_save is False
