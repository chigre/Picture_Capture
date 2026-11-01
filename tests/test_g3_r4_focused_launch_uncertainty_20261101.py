"""G3/R4.2: a failed scheduler handoff may have already published pages.

All data is disposable synthetic PNG plus an injected no-I/O page writer.
This tests UI ownership, not real PDIC writes or operator acceptance.
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
        self.messages = []

    def set(self, value):
        self.messages.append(value)


def test_post_dispatch_launch_exception_requires_explicit_retry(tmp_path: Path):
    pages = [tmp_path / "001.png", tmp_path / "002.png"]
    for page in pages:
        Image.new("RGB", (8, 8), "white").save(page)
    pending = {}
    targets = []
    for index, page in enumerate(pages):
        x, y = index + 10, index + 20
        witness = focused_save_source_witness(page)
        pending[index] = {
            (x, y): {
                "page_index": index, "x": x, "y": y,
                "original_word": f"old-{index}",
                "new_word": f"human-{index}",
                "_focused_save_source_witness": witness,
            }
        }
        targets.append({
            "page_index": index, "x": x, "y": y,
            "original_word": f"old-{index}",
            "current_word": f"human-{index}",
            "_focused_save_source_witness": witness,
        })

    attempted = []
    dispatched = []
    status = _Status()
    review = SimpleNamespace(
        parent=SimpleNamespace(
            project=SimpleNamespace(images=pages), status_var=status,
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
        _apply_focused_review_page_updates=lambda _page, _pages, index, changes: (
            attempted.append(index) or [
                (index, int(change["x"]), int(change["y"]), change["new_word"])
                for change in changes
            ],
            [],
        ),
        messagebox=SimpleNamespace(
            showerror=lambda *a, **kw: None,
            showwarning=lambda *a, **kw: None,
        ),
    )

    def dispatch_then_throw(_key, worker, _done, _failed, **_kw):
        # The worker may complete page-level publication before a scheduler
        # detects a handoff error. Neither a returned payload nor the
        # exception can prove which pages are already durable on disk.
        worker()
        raise OSError("PRIVATE_SYNTHETIC_HANDOFF_FAILURE")

    review.parent._start_ui_worker = dispatch_then_throw
    workflow._flush_focused_changes(review, deps)

    assert attempted == [0, 1]
    assert not review._filter_save_running
    assert not review._filter_close_after_save
    assert review._filter_save_launch_failed is True
    assert set(review._filter_pending_changes) == {0, 1}
    assert [item["original_word"] for item in targets] == ["old-0", "old-1"]
    assert getattr(review, "_filter_save_uncertain_pages", set()) == {0, 1}

    # A timer-triggered attempt must not retry the ambiguous page writes.
    review.parent._start_ui_worker = (
        lambda *a, **kw: dispatched.append((a, kw))
    )
    workflow._flush_focused_changes(review, deps)
    assert dispatched == []
    assert set(review._filter_pending_changes) == {0, 1}

    # The existing explicit retry action is the only allowed new dispatch.
    review._flush_focused_changes = lambda: workflow._flush_focused_changes(
        review, deps,
    )
    workflow._flush_focused_changes_now(review, deps)
    assert len(dispatched) == 1
    assert review._filter_save_running is True
    assert review._filter_save_launch_failed is False
    assert review._filter_pending_changes == {}
