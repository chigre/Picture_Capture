"""Persistent page-index thumbnails: synthetic scans only (no private pixels)."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import picture_capture.page_thumbnail_cache as disk
from picture_capture.ui.page_thumbnails import PageThumbnailController


def make_scan(path: Path, color: tuple[int, int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (480, 680), color).save(path)
    return path


def test_cache_is_project_local_and_contains_real_pixels(tmp_path):
    scan = make_scan(tmp_path / "scans" / "001.png", (245, 21, 31))
    original = scan.read_bytes()
    preview = disk.get_page_thumbnail(tmp_path, scan)
    assert preview.size == (158, 224)
    assert preview.getpixel((5, 5)) == (245, 21, 31)
    cache = disk.thumbnail_cache_path(tmp_path, scan)
    assert cache.is_file()
    assert disk.thumbnail_cache_dir(tmp_path) in cache.parents
    with Image.open(cache) as saved:
        assert saved.info[disk.FINGERPRINT_KEY] == disk.source_fingerprint(scan)
        assert saved.getpixel((5, 5)) == (245, 21, 31)
    assert scan.read_bytes() == original


def test_second_open_and_size_changes_read_cache_not_original(tmp_path, monkeypatch):
    scan = make_scan(tmp_path / "a.png", (15, 220, 48))
    disk.get_page_thumbnail(tmp_path, scan)

    def should_not_decode(_source):
        raise AssertionError("Full resolution scan was decoded again")

    monkeypatch.setattr(disk, "_build_thumbnail", should_not_decode)
    for width in (40, 80, 120, 160):
        thumb = disk.display_page_thumbnail(tmp_path, scan, width)
        assert thumb.getpixel((1, 1)) == (15, 220, 48)
        assert thumb.width <= width
        assert thumb.height <= round(width * 1.4)


def test_modified_scan_invalidates_cache_and_rebuilds(tmp_path):
    scan = make_scan(tmp_path / "a.png", (245, 21, 31))
    disk.get_page_thumbnail(tmp_path, scan)
    cached = disk.thumbnail_cache_path(tmp_path, scan)
    old_signature = disk.source_fingerprint(scan)
    make_scan(scan, (15, 30, 245))
    assert disk.source_fingerprint(scan) != old_signature
    fresh = disk.get_page_thumbnail(tmp_path, scan)
    assert fresh.getpixel((5, 5)) == (15, 30, 245)
    with Image.open(cached) as saved:
        assert saved.info[disk.FINGERPRINT_KEY] == disk.source_fingerprint(scan)


def test_corrupt_thumbnail_rebuilds_without_touching_original(tmp_path):
    scan = make_scan(tmp_path / "a.png", (110, 40, 180))
    original = scan.read_bytes()
    disk.get_page_thumbnail(tmp_path, scan)
    cached = disk.thumbnail_cache_path(tmp_path, scan)
    cached.write_bytes(b"interrupted png")
    fresh = disk.get_page_thumbnail(tmp_path, scan)
    assert fresh.getpixel((5, 5)) == (110, 40, 180)
    with Image.open(cached) as saved:
        assert saved.format == "PNG"
    assert scan.read_bytes() == original
    assert not list(cached.parent.glob(".thumbnail-*.tmp"))


def test_read_only_cache_falls_back_to_real_preview(tmp_path, monkeypatch):
    scan = make_scan(tmp_path / "a.png", (22, 80, 180))
    def deny_cache(*_args, **_kwargs):
        raise PermissionError("read only")
    monkeypatch.setattr(disk, "_publish_cache", deny_cache)
    image = disk.get_page_thumbnail(tmp_path, scan)
    assert image.getpixel((5, 5)) == (22, 80, 180)
    assert not disk.thumbnail_cache_path(tmp_path, scan).exists()


class FakeApp:
    def __init__(self, root, images):
        self.project = SimpleNamespace(root=root, images=images)
        self.workspace_mode = "正常"
        self.jobs = []

    def after(self, delay, callback):
        self.jobs.append((delay, callback))
        return str(len(self.jobs))

    def after_cancel(self, _job):
        return None


class FakeBoolean:
    def get(self):
        return True


def test_progressively_caches_all_pages_not_only_visible_ones(tmp_path):
    scans = [
        make_scan(tmp_path / "pages" / f"page{i}.png", (20 + i, 40 + i, 60 + i))
        for i in range(7)
    ]
    app = FakeApp(tmp_path, scans)
    controller = PageThumbnailController.__new__(PageThumbnailController)
    controller.app = app
    controller.enabled_var = FakeBoolean()
    controller._warm_job = None
    controller._warm_cursor = 0
    controller._warm_project_key = None
    controller._schedule_warm_cache()
    steps = 0
    while app.jobs:
        _delay, callback = app.jobs.pop(0)
        controller._warm_job = None
        callback()
        steps += 1
        assert steps <= len(scans) + 2
    assert controller._warm_cursor == len(scans)
    assert all(disk.thumbnail_cache_path(tmp_path, page).exists() for page in scans)


def test_filename_identity_prevents_cache_swap_between_same_stems(tmp_path):
    a = make_scan(tmp_path / "volume1" / "001.png", (255, 0, 0))
    b = make_scan(tmp_path / "volume2" / "001.png", (0, 0, 255))
    assert disk.thumbnail_cache_path(tmp_path, a) != disk.thumbnail_cache_path(tmp_path, b)
    assert disk.get_page_thumbnail(tmp_path, a).getpixel((0, 0)) == (255, 0, 0)
    assert disk.get_page_thumbnail(tmp_path, b).getpixel((0, 0)) == (0, 0, 255)
