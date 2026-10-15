"""Ordering of thumbnail generation, independent of scan-data availability."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import page_thumbnails as ui


class _FakeTree:
    def __init__(self, rows):
        self.rows = tuple(str(v) for v in rows)

    def get_children(self, _parent=""):
        return self.rows


class _FakeApp:
    def __init__(self, root, count):
        self.current_index = 3
        self._page_list_sort_column = "illustrations"
        self._page_list_sort_descending = True
        self.project = SimpleNamespace(
            root=root,
            images=[root / f"page-{index:04}.png" for index in range(count)],
        )
        self.workspace_mode = "正常"
        self.jobs = []

    def after(self, interval_ms, callback):
        self.jobs.append((interval_ms, callback))
        return str(len(self.jobs))

    def after_cancel(self, _job):
        return None


class _Checked:
    def get(self):
        return True


def _controller(app, rows):
    preview = ui.PageThumbnailController.__new__(ui.PageThumbnailController)
    preview.app = app
    preview.tree = _FakeTree(rows)
    preview.enabled_var = _Checked()
    preview._warm_job = None
    preview._warm_cursor = 0
    preview._warm_project_key = None
    preview._warm_priority_key = None
    preview._warm_done = set()
    preview._warm_order = []
    preview._cache_project_key = None
    preview._cache_names = {}
    return preview


def _run_next(app):
    assert app.jobs
    _, callback = app.jobs.pop(0)
    callback()


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


def test_first_enable_warms_current_downward_then_other_rows(tmp_path, monkeypatch):
    app = _FakeApp(tmp_path, 6)
    preview = _controller(app, ("2", "4", "1", "3", "5", "0"))
    generated = []

    def record(root, source, names=None):
        assert root == tmp_path
        assert names[str(Path(source).resolve())] == f"{Path(source).stem}.png"
        generated.append(app.project.images.index(source))
        return None

    monkeypatch.setattr(ui, "get_page_thumbnail", record)
    preview._schedule_warm_cache()
    for _ in range(6):
        _run_next(app)
    assert generated == [3, 5, 0, 2, 4, 1]
    assert app.jobs == []


def test_navigation_reprioritizes_pending_and_preserves_completed(tmp_path, monkeypatch):
    app = _FakeApp(tmp_path, 6)
    app.current_index = 1
    app._page_list_sort_column = None
    app._page_list_sort_descending = False
    preview = _controller(app, range(6))
    generated = []
    monkeypatch.setattr(
        ui, "get_page_thumbnail",
        lambda _root, source, _names=None: generated.append(app.project.images.index(source)),
    )
    preview._schedule_warm_cache()
    _run_next(app)
    assert generated == [1]
    app.current_index = 4
    for _ in range(5):
        _run_next(app)
    assert generated == [1, 4, 5, 0, 2, 3]
    assert len(set(generated)) == 6 and not app.jobs


def test_sort_reprioritizes_pending_in_display_order(tmp_path, monkeypatch):
    app = _FakeApp(tmp_path, 5)
    app.current_index = 0
    app._page_list_sort_column = None
    app._page_list_sort_descending = False
    preview = _controller(app, range(5))
    generated = []
    monkeypatch.setattr(
        ui, "get_page_thumbnail",
        lambda _root, source, _names=None: generated.append(app.project.images.index(source)),
    )
    preview._schedule_warm_cache()
    _run_next(app)
    assert generated == [0]
    preview.tree.rows = ("2", "0", "3", "1", "4")
    app._page_list_sort_column = "illustrations"
    for _ in range(4):
        _run_next(app)
    assert generated == [0, 3, 1, 4, 2]
    assert not app.jobs


def test_unavailable_source_does_not_block_next_pages(tmp_path, monkeypatch):
    app = _FakeApp(tmp_path, 3)
    app.current_index = 1
    preview = _controller(app, range(3))
    seen = []

    def failure_then_good(_root, source, _names=None):
        idx = app.project.images.index(source)
        seen.append(idx)
        if idx == 1:
            raise OSError("corrupt scan")

    monkeypatch.setattr(ui, "get_page_thumbnail", failure_then_good)
    preview._schedule_warm_cache()
    for _ in range(3):
        _run_next(app)
    assert seen == [1, 2, 0]
    assert len(preview._warm_done) == 3
