"""Page-index thumbnails: identity, lazy loading, persistence and mode guards."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

from picture_capture.models import AppSettings
from picture_capture.page_list_helpers import _sorted_page_list_rows
from picture_capture.project_storage import settings_path
from picture_capture.ui.page_thumbnails import (
    DEFAULT_THUMBNAIL_WIDTH,
    MAX_THUMBNAIL_WIDTH,
    MIN_THUMBNAIL_WIDTH,
    PageThumbnailController,
    normalized_thumbnail_width,
    preview_bounds,
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
        self.images = {}

    def exists(self, iid):
        return iid in {"0", "1", "2", "3"}

    def item(self, iid, **kwargs):
        if "image" in kwargs:
            self.images[iid] = kwargs["image"]

    def heading(self, *args, **kwargs):
        return None


class _App:
    def __init__(self, paths):
        self.workspace_mode = "正常"
        self.settings = AppSettings(page_list_show_thumbnails=True)
        self.project = SimpleNamespace(root=paths[0].parent, images=paths)
        self.visible = ["3", "1"]
        self.jobs = []
        self.status_var = SimpleNamespace(set=lambda value: None)

    def _visible_page_list_iids(self):
        return self.visible

    def after(self, milliseconds, callback):
        self.jobs.append((milliseconds, callback))
        return str(len(self.jobs))

    def after_cancel(self, job):
        pass


def _controller(app):
    result = PageThumbnailController.__new__(PageThumbnailController)
    result.app = app
    result.tree = _Tree()
    result.width = DEFAULT_THUMBNAIL_WIDTH
    result.enabled_var = _Var(True)
    result._photos = OrderedDict()
    result._attached = {}
    result._refresh_job = None
    result._generation = 0
    result._make_photo = lambda path: f"preview:{path.stem}"
    return result


def test_thumb_size_validation_bounds_and_full_image_ratio():
    assert normalized_thumbnail_width(None) == 80
    assert normalized_thumbnail_width("bad") == 80
    assert normalized_thumbnail_width(-999) == MIN_THUMBNAIL_WIDTH
    assert normalized_thumbnail_width(999) == MAX_THUMBNAIL_WIDTH
    assert preview_bounds(80) == (80, 112)
    assert preview_bounds(160) == (160, 224)


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


def test_sorted_page_ids_keep_their_own_previews(tmp_path):
    files = [tmp_path / f"page{n}.png" for n in range(4)]
    for f in files:
        f.write_bytes(b"fake-preview-source")
    app = _App(files)
    ctrl = _controller(app)
    ctrl._render_visible()
    assert ctrl.tree.images["3"] == "preview:page3"
    assert ctrl.tree.images["1"] == "preview:page1"
    ordered = _sorted_page_list_rows(
        [("1", ("", "page1", "", "", "", "1")),
         ("3", ("", "page3", "", "", "", "3"))],
        "illustrations", descending=True,
    )
    assert [iid for iid, _ in ordered] == ["3", "1"]
    app.visible = ["1", "0"]
    ctrl._render_visible()
    assert ctrl.tree.images["3"] == ""
    assert ctrl.tree.images["1"] == "preview:page1"
    assert ctrl.tree.images["0"] == "preview:page0"
    assert len(ctrl._photos) == 3


def test_preview_source_refreshes_when_scan_changes(tmp_path):
    files = [tmp_path / f"page{n}.png" for n in range(4)]
    for f in files:
        f.write_bytes(b"original")
    app = _App(files)
    ctrl = _controller(app)
    ctrl._render_visible()
    old_key = ctrl._attached["3"]
    files[3].write_bytes(b"updated-image-bytes")
    ctrl._render_visible()
    assert ctrl._attached["3"] != old_key


def test_compact_modes_hide_without_erasing_enabled_preference(tmp_path):
    files = [tmp_path / f"page{n}.png" for n in range(4)]
    app = _App(files)
    ctrl = _controller(app)
    assert ctrl._visible_enabled() is True
    app.workspace_mode = "紧凑"
    assert ctrl._visible_enabled() is False
    app.workspace_mode = "极简"
    assert ctrl._visible_enabled() is False
    app.workspace_mode = "最大"
    assert ctrl._visible_enabled() is True
    assert app.settings.page_list_show_thumbnails is True


def test_failed_settings_write_rolls_back_without_touching_project_file(tmp_path, monkeypatch):
    files = [tmp_path / f"page{n}.png" for n in range(4)]
    app = _App(files)
    ctrl = _controller(app)
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
