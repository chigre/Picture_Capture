"""Audit regression: LayoutRows sidecars must match the actual source image."""
import json
import os

import pytest

from picture_capture import layout_rows_cache as cache
from picture_capture.models import AppSettings


def test_same_stem_different_extension_is_not_same_cached_image(tmp_path):
    png = tmp_path / "page.png"
    jpg = tmp_path / "page.jpg"
    png.write_bytes(b"abcde")
    jpg.write_bytes(b"vwxyz")
    os.utime(jpg, ns=(png.stat().st_atime_ns, png.stat().st_mtime_ns))
    payload = {"image": cache._image_fingerprint(png, (100, 200))}
    assert cache._same_image_fingerprint(payload, png, (100, 200))
    assert cache.layout_rows_cache_path(tmp_path, png) == cache.layout_rows_cache_path(tmp_path, jpg)
    assert not cache._same_image_fingerprint(payload, jpg, (100, 200))


@pytest.mark.parametrize("bad_field,bad_value", [
    ("algorithm_version", "not-a-number"),
    ("page_index", {}),
    ("page_index", None),
])
def test_malformed_sidecar_metadata_is_cache_miss(tmp_path, bad_field, bad_value):
    image = tmp_path / "page.png"
    image.write_bytes(b"scan")
    path = cache.layout_rows_cache_path(tmp_path, image)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": cache.CACHE_FORMAT,
        "algorithm_version": cache.CACHE_ALGORITHM_VERSION,
        "page_index": 0,
        "settings_fingerprint": cache._settings_fingerprint(AppSettings()),
        "image": cache._image_fingerprint(image, (100, 200)),
        "layout": {},
    }
    payload[bad_field] = bad_value
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert cache.load_layout_rows_cache(tmp_path, image, 0, AppSettings(), source_size=(100, 200)) is None


@pytest.mark.parametrize("bad_value", ["invalid", None, {}, 1e999])
def test_corrupt_image_metadata_returns_cache_miss(tmp_path, bad_value):
    image = tmp_path / "page.png"
    image.write_bytes(b"abcd")
    payload = {"image": cache._image_fingerprint(image, (100, 200))}
    payload["image"]["size_bytes"] = bad_value
    assert not cache._same_image_fingerprint(payload, image, (100, 200))
