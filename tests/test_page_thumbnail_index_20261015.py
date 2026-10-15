"""Page-index thumbnails: async identity, sorting and project-state guards."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.page_list_helpers import _sorted_page_list_rows
from picture_capture.page_thumbnail_tasks import ThumbnailResult
from picture_capture.project_storage import settings_path
from picture_capture.ui.page_thumbnails import (
    DEFAULT_THUMBNAIL_WIDTH, MAX_THUMBNAIL_WIDTH, MIN_THUMBNAIL_WIDTH,
    PageThumbnailController, normalized_thumbnail_width, preview_bounds,
)


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Tree:
    def __init__(self):
        self.images: dict[str, object] = {}
        self.texts: dict[str, str] = {}

    def exists(self, iid):
        return str(iid) in {"0", "1", "2", "3"}

    def item(self, iid, **kwargs):
        if "image" in kwargs:
            self.images[str(iid)] = kwargs["image"]
        if "text" in kwargs:
            self.texts[str(iid)] = kwargs["text"]

    def get_children(self, _parent=""):
        return ("0", "1", "2", "3")

    def heading(self, *args, **kwargs):
        return None


class _Tasks:
    """Deterministic worker double: no physical threads in Tk identity tests."""
    def __init__(self):
        self.calls = []
        self.waiting: list[ThumbnailResult] = []
        self.serial = 0
        self._closed = False

    @property
    def active(self):
        return len(self.waiting)

    def submit(self, index, key, root, path, names):
        assert names[str(path.resolve())].endswith(".png")
        self.serial += 1
        self.calls.append(index)
        image = Image.new("RGB", (320, 448), (index * 50, 30, 40))
        self.waiting.append(ThumbnailResult(self.serial, index, key, image))
        return self.serial

    def collect(self):
        waiting = list(self.waiting)
        self.waiting.clear()
        return waiting

    def cancel_pending(self):
        self.waiting.clear()

    def shutdown(self):
        self._closed = True


class _App:
    def __init__(self, paths):
        self.workspace_mode = "正常"
        self.settings = AppSettings(page_list_show_thumbnails=True)
        self.project = SimpleNamespace(root=paths[0].parent, images=paths)
        self.visible = ["3", "1"]
        self.current_index = 3
        self.jobs = []
        self.status_var = SimpleNamespace(set=lambda value: None)
        self._page_list_sort_column = None
        self._page_list_sort_descending = False

    def _visible_page_list_iids(self):
        return self.visible

    def after(self, milliseconds, callback):
        self.jobs.append((milliseconds, callback))
        return str(len(self.jobs))

    def after_idle(self, callback):
        return self.after(0, callback)

    def after_cancel(self, _job):
        pass


def _controller(app, monkeypatch):
    from picture_capture.ui import page_thumbnails as ui

    # The real ImageTk.PhotoImage is tested in scripts/gui_smoke.py. Here
    # identity can be inspected without a display server.
    monkeypatch.setattr(
        ui.ImageTk, "PhotoImage",
        lambda image, master=None: f"preview:{image.getpixel((0, 0))[0] // 50}",
    )
    result = PageThumbnailController.__new__(PageThumbnailController)
    result.app = app
    result.tree = _Tree()
    result.width = DEFAULT_THUMBNAIL_WIDTH
    result.enabled_var = _Var(True)
    result._tasks = _Tasks()
    result._photos = OrderedDict()
    result._attached = {}
    result._refresh_job = None
    result._poll_job = None
    result._worker_pending = {}
    result._worker_failures = {}
    result._generation = 0
    result._visible_order = []
    result._empty_view_retries = 0
    result._warm_project_key = None
    result._warm_priority_key = None
    result._warm_done = set()
    result._warm_order = []
    result._cache_project_key = None
    result._cache_names = {}
    return result


def _images(tmp_path):
    files = [tmp_path / f"page{n}.png" for n in range(4)]
    for f in files:
        f.write_bytes(b"test-source-content")
    return files


def test_thumb_size_validation_bounds_and_full_image_ratio():
    assert normalized_thumbnail_width(None) == 80
    assert normalized_thumbnail_width("bad") == 80
    assert normalized_thumbnail_width(-999) == MIN_THUMBNAIL_WIDTH
    assert normalized_thumbnail_width(999) == MAX_THUMBNAIL_WIDTH == 120
    assert preview_bounds(80) == (80, 112)
    assert preview_bounds(120) == (120, 120)
    assert preview_bounds(160) == (120, 120)


def test_preferences_round_trip_without_touching_legacy_fields(tmp_path):
    settings = AppSettings()
    assert settings.page_list_show_thumbnails is False
    assert settings.page_list_thumbnail_size == 80
    settings.page_list_show_thumbnails = True
    settings.page_list_thumbnail_size = 110
    path = tmp_path / "config.json"
    settings.to_json(path)
    saved = AppSettings.from_json(path)
    assert saved.page_list_show_thumbnails is True
    assert saved.page_list_thumbnail_size == 110
    assert saved.page_list_show_illustrations == settings.page_list_show_illustrations


def test_sorted_page_ids_keep_their_own_previews(tmp_path, monkeypatch):
    app = _App(_images(tmp_path))
    ctrl = _controller(app, monkeypatch)
    ctrl._render_visible()
    assert ctrl._tasks.calls == [3, 1]
    assert ctrl.tree.images.get("3") in (None, "")  # Nonblocking placeholder.
    ctrl._collect_results()
    assert ctrl.tree.images["3"] == "preview:3"
    assert ctrl.tree.images["1"] == "preview:1"
    ctrl._collect_results()  # Background-warm pages 0 and 2.
    ordered = _sorted_page_list_rows(
        [("1", ("", "page1", "", "", "", "1")),
         ("3", ("", "page3", "", "", "", "3"))],
        "illustrations", descending=True,
    )
    assert [iid for iid, _ in ordered] == ["3", "1"]
    app.visible = ["1", "0"]
    ctrl._render_visible()
    assert ctrl.tree.images["3"] == ""
    assert ctrl.tree.images["1"] == "preview:1"
    ctrl._collect_results()
    assert ctrl.tree.images["0"] == "preview:0"
    assert len(ctrl._photos) == 3


def test_preview_source_refreshes_when_scan_changes(tmp_path, monkeypatch):
    files = _images(tmp_path)
    app = _App(files)
    ctrl = _controller(app, monkeypatch)
    ctrl._render_visible()
    ctrl._collect_results()
    old_key = ctrl._attached["3"]
    files[3].write_bytes(b"updated-image-bytes-larger")
    ctrl._render_visible()
    # Two already-running cache-warm jobs may complete before the modified
    # visible page is enqueued; it must still be refreshed, not left blank.
    for _ in range(4):
        ctrl._collect_results()
        if "3" in ctrl._attached:
            break
    assert ctrl._attached["3"] != old_key


def test_compact_modes_hide_without_erasing_enabled_preference(tmp_path, monkeypatch):
    app = _App(_images(tmp_path))
    ctrl = _controller(app, monkeypatch)
    assert ctrl._visible_enabled() is True
    app.workspace_mode = "紧凑"
    assert ctrl._visible_enabled() is False
    app.workspace_mode = "极简"
    assert ctrl._visible_enabled() is False
    app.workspace_mode = "最大"
    assert ctrl._visible_enabled() is True
    assert app.settings.page_list_show_thumbnails is True


def test_failed_settings_write_rolls_back_without_touching_project_file(tmp_path, monkeypatch):
    app = _App(_images(tmp_path))
    ctrl = _controller(app, monkeypatch)
    destination = settings_path(tmp_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("original settings", encoding="utf-8")

    def error(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(AppSettings, "to_json", error)
    assert ctrl._save("page_list_thumbnail_size", 120) is False
    assert app.settings.page_list_thumbnail_size == 80
    assert destination.read_text(encoding="utf-8") == "original settings"
    assert not list(destination.parent.glob(".thumbnail-settings-*"))


def test_visible_render_begins_with_browsed_page_not_first_table_row(tmp_path, monkeypatch):
    app = _App(_images(tmp_path))
    app.visible = ["1", "3", "2"]
    app.current_index = 3
    ctrl = _controller(app, monkeypatch)
    ctrl._render_visible()
    assert ctrl._tasks.calls == [3, 2]
    ctrl._collect_results()
    assert ctrl.tree.images["3"] == "preview:3"
    assert ctrl.tree.images["2"] == "preview:2"


def test_old_project_result_is_discarded_after_new_project_loaded(tmp_path, monkeypatch):
    files = _images(tmp_path)
    app = _App(files)
    ctrl = _controller(app, monkeypatch)
    ctrl._render_visible()
    ctrl._clear_images()
    app.project = SimpleNamespace(root=tmp_path / "other", images=list(files))
    ctrl._collect_results()
    assert ctrl._attached == {}
    assert ctrl.tree.images.get("3") in (None, "")


def test_deleted_original_never_keeps_a_stale_thumbnail(tmp_path, monkeypatch):
    files = _images(tmp_path)
    app = _App(files)
    ctrl = _controller(app, monkeypatch)
    ctrl._render_visible()
    ctrl._collect_results()
    assert ctrl.tree.images["3"] == "preview:3"
    files[3].unlink()
    ctrl._render_visible()
    assert ctrl.tree.images["3"] == ""
    assert ctrl.tree.texts["3"] == "×"
    assert "3" not in ctrl._attached


def test_async_failed_image_reports_error_without_repeated_decode(tmp_path, monkeypatch):
    app = _App(_images(tmp_path))
    ctrl = _controller(app, monkeypatch)
    ctrl._tasks.failed_index = 3
    original_submit = ctrl._tasks.submit

    def broken(index, key, root, path, names):
        ticket = original_submit(index, key, root, path, names)
        if index == 3:
            result = ctrl._tasks.waiting[-1]
            ctrl._tasks.waiting[-1] = ThumbnailResult(
                result.ticket, result.page_index, result.identity, None, "unreadable",
            )
        return ticket

    ctrl._tasks.submit = broken
    ctrl._render_visible()
    ctrl._collect_results()
    assert ctrl.tree.images["3"] == ""
    assert ctrl.tree.texts["3"] == "×"
    calls = list(ctrl._tasks.calls)
    ctrl._render_visible()
    assert ctrl._tasks.calls == calls
