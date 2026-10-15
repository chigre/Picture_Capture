"""Thumbnail scheduling: current/below-first, reprioritization, bounded async jobs."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace
from PIL import Image

from picture_capture.page_thumbnail_tasks import ThumbnailResult
from picture_capture.ui import page_thumbnails as ui


class _FakeTree:
    def __init__(self, rows):
        self.rows = tuple(str(v) for v in rows)

    def get_children(self, _parent=""):
        return self.rows

    def exists(self, iid):
        return str(iid) in self.rows


class _FakeApp:
    def __init__(self, root, count):
        self.current_index = 3
        self._page_list_sort_column = "illustrations"
        self._page_list_sort_descending = True
        paths = [root / f"page-{index:04}.png" for index in range(count)]
        for path in paths:
            path.write_bytes(b"synthetic-stat-test")
        self.project = SimpleNamespace(root=root, images=paths)
        self.workspace_mode = "正常"
        self.jobs = []

    def after(self, interval_ms, callback):
        self.jobs.append((interval_ms, callback))
        return str(len(self.jobs))

    def after_cancel(self, _job):
        return None


class _Tasks:
    def __init__(self, *, failed=()):
        self.calls = []
        self.pending = []
        self.failed = set(failed)
        self.serial = 0

    @property
    def active(self):
        return len(self.pending)

    def submit(self, index, token, root, source, names):
        assert names[str(source.resolve())] == source.stem + ".png"
        assert self.active < 2
        self.calls.append(index)
        self.serial += 1
        self.pending.append(ThumbnailResult(
            self.serial, index, token,
            Image.new("RGB", (320, 448), (index, 0, 0)),
            "bad scan" if index in self.failed else None,
        ))
        return self.serial

    def collect(self):
        items = list(self.pending)
        self.pending.clear()
        return items

    def cancel_pending(self):
        self.pending.clear()


class _Checked:
    def get(self):
        return True


def _controller(app, rows, failed=()):
    preview = ui.PageThumbnailController.__new__(ui.PageThumbnailController)
    preview.app = app
    preview.tree = _FakeTree(rows)
    preview.enabled_var = _Checked()
    preview.width = ui.DEFAULT_THUMBNAIL_WIDTH
    preview._tasks = _Tasks(failed=failed)
    preview._photos = OrderedDict()
    preview._attached = {}
    preview._generation = 0
    preview._worker_pending = {}
    preview._worker_failures = {}
    preview._refresh_job = None
    preview._poll_job = None
    preview._visible_order = []
    preview._empty_view_retries = 0
    preview._warm_project_key = None
    preview._warm_priority_key = None
    preview._warm_done = set()
    preview._warm_order = []
    preview._cache_project_key = None
    preview._cache_names = {}
    return preview


def _finish_all(preview, expected):
    for _ in range(expected):
        if not preview._tasks.pending:
            break
        preview._collect_results()


def test_prioritize_current_then_rows_below_in_sorted_index():
    assert ui.prioritized_page_indices(
        6, 3, ("2", "4", "1", "3", "5", "0"),
    ) == [3, 5, 0, 2, 4, 1]


def test_unsorted_index_resumes_above_after_current():
    assert ui.prioritized_page_indices(6, 4, tuple(str(n) for n in range(6))) == [
        4, 5, 0, 1, 2, 3,
    ]


def test_filtered_rows_still_eventually_cover_all_pages():
    order = ui.prioritized_page_indices(6, 4, ("1", "4", "2", "garbled", "4"))
    assert order[:2] == [4, 2]
    assert sorted(order) == list(range(6))


def test_first_enable_queues_current_downward_then_other_rows(tmp_path):
    app = _FakeApp(tmp_path, 6)
    preview = _controller(app, ("2", "4", "1", "3", "5", "0"))
    preview._schedule_warm_cache()
    assert preview._tasks.calls == [3, 5]  # Only two jobs outstanding.
    _finish_all(preview, 10)
    assert preview._tasks.calls == [3, 5, 0, 2, 4, 1]
    assert preview._warm_done == set(range(6))
    assert not preview._tasks.pending


def test_navigation_reprioritizes_unsubmitted_work_and_keeps_completed(tmp_path):
    app = _FakeApp(tmp_path, 6)
    app.current_index = 1
    app._page_list_sort_column = None
    app._page_list_sort_descending = False
    preview = _controller(app, range(6))
    preview._schedule_warm_cache()
    assert preview._tasks.calls == [1, 2]
    app.current_index = 4
    _finish_all(preview, 10)
    assert preview._tasks.calls == [1, 2, 4, 5, 0, 3]
    assert preview._warm_done == set(range(6))


def test_sort_reprioritizes_pending_in_new_display_order(tmp_path):
    app = _FakeApp(tmp_path, 5)
    app.current_index = 0
    app._page_list_sort_column = None
    app._page_list_sort_descending = False
    preview = _controller(app, range(5))
    preview._schedule_warm_cache()
    assert preview._tasks.calls == [0, 1]
    preview.tree.rows = ("2", "0", "3", "1", "4")
    app._page_list_sort_column = "illustrations"
    _finish_all(preview, 10)
    assert preview._tasks.calls == [0, 1, 3, 4, 2]
    assert preview._warm_done == set(range(5))


def test_failed_scan_is_quarantined_until_identity_changes(tmp_path):
    app = _FakeApp(tmp_path, 3)
    app.current_index = 1
    preview = _controller(app, range(3), failed=(1,))
    preview._schedule_warm_cache()
    _finish_all(preview, 10)
    assert preview._tasks.calls == [1, 2, 0]
    assert len(preview._warm_done) == 3
    assert 1 in preview._worker_failures
    preview._dispatch_jobs()
    assert preview._tasks.calls == [1, 2, 0]


def test_worker_completion_exposes_no_tk_callback():
    import threading
    import time
    from picture_capture import page_thumbnail_tasks as jobs

    # Stub only file generation; prove worker code runs on another thread and
    # the result is delivered by polling, not a Tk call from worker thread.
    names = {}
    observed = []
    original = jobs.get_page_thumbnail
    jobs.get_page_thumbnail = lambda *_args: (
        observed.append(threading.current_thread().name)
        or Image.new("RGB", (12, 16), "red")
    )
    task = jobs.ThumbnailTasks(workers=2)
    try:
        assert task.submit(7, ("identity",), Path("."), Path("no-scan"), names) == 1
        deadline = time.monotonic() + 5
        out = []
        while time.monotonic() < deadline and not out:
            out = task.collect()
            if not out:
                time.sleep(0.005)
        assert len(out) == 1 and out[0].image.getpixel((0, 0)) == (255, 0, 0)
        assert observed and observed[0].startswith("pc-thumb")
        assert task.active == 0
    finally:
        task.shutdown()
        jobs.get_page_thumbnail = original
