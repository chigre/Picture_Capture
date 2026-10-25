"""Issue #562: crop vertical bounds and Paddle band preprocessing leaf bridges."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from picture_capture import processing as processing_public
from picture_capture import processing_core
from picture_capture import paddle_headwords as paddle_public
from picture_capture import paddle_headwords_core as paddle_core
from picture_capture.crop import entry_vertical_bounds
from picture_capture.ocr import band_preprocessing

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def _geometry(width=100, height=200):
    return SimpleNamespace(
        top=12, bottom=178,
        transform=SimpleNamespace(canonical_size=lambda size: (width, height)),
    )


def test_original_core_path_and_contracts():
    assert len(list(PKG.glob("*.py"))) == 7
    assert (PKG / "crop/entry_vertical_bounds.py").is_file()
    assert (PKG / "ocr/band_preprocessing.py").is_file()
    assert not (PKG / "entry_vertical_bounds.py").exists()
    assert not (PKG / "band_preprocessing.py").exists()
    for fn in (processing_core._special_bounds, processing_core.entry_crop_bounds):
        assert fn.__module__ == "picture_capture.processing_core"
    for fn in (paddle_core.prepare_ocr_band, paddle_core._otsu_threshold):
        assert fn.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(processing_core.entry_crop_bounds).parameters) == [
        "image", "settings", "top_y", "bottom_y", "root", "page_stem",
    ]
    assert list(inspect.signature(paddle_core.prepare_ocr_band).parameters) == [
        "band", "max_long_side", "mode",
    ]


def test_special_pages_source_bounds_and_override_order(tmp_path, monkeypatch):
    image = Image.new("RGB", (100, 200), "white")
    settings = SimpleNamespace(start_y=40, bottom_y=150, crop_to_bottom_y=True)
    geom = _geometry()
    special = tmp_path / "special.tsv"
    special.write_text("page\t30\t170\n", encoding="utf-8")
    def special_bounds(root, page_stem, geometry):
        return entry_vertical_bounds.special_bounds(
            root, page_stem, geometry, special_path_fn=lambda p: special,
        )
    for kwargs, expected in (
        ({}, (40, 150)),
        ({"top_y": 15, "bottom_y": 0}, (15, 200)),
        ({"top_y": 180, "bottom_y": 100}, (180, 181)),
        ({"root": tmp_path, "page_stem": "page"}, (30, 170)),
    ):
        actual = entry_vertical_bounds.entry_crop_bounds(
            image, settings, **kwargs, geometry_fn=lambda *_: geom,
            source_px_fn=round, special_bounds_fn=special_bounds,
        )
        assert actual == expected
    assert special_bounds(tmp_path, "unknown", geom) == (12, 178)


def test_entry_bounds_call_time_geometry_and_source_px_hooks(monkeypatch):
    image = Image.new("RGB", (100, 200), "white")
    settings = SimpleNamespace(start_y=30, bottom_y=0, crop_to_bottom_y=False)
    old_geo = processing_core.derive_geometry
    old_px = processing_core._source_px
    monkeypatch.setattr(processing_public, "derive_geometry", lambda *_: _geometry())
    monkeypatch.setattr(processing_public, "_source_px", lambda x: int(x) + 5)
    assert processing_core.entry_crop_bounds(image, settings) == (35, 200)
    monkeypatch.setattr(processing_public, "_source_px", old_px)
    monkeypatch.setattr(processing_public, "derive_geometry", old_geo)


def test_paddle_otsu_empty_bimodal_and_source_scale():
    empty = np.empty((0, 0), dtype=np.uint8)
    assert paddle_core._otsu_threshold(empty) == band_preprocessing.otsu_threshold(empty) == 180
    gray = np.tile(np.array([0, 0, 255, 255], dtype=np.uint8), (100, 1))
    assert paddle_core._otsu_threshold(gray) == band_preprocessing.otsu_threshold(gray)
    image = Image.new("RGB", (800, 400), "white")
    for mode in ("original", "gray", "grayscale", "auto_contrast", "binary"):
        actual, scale = paddle_core.prepare_ocr_band(image, max_long_side=400, mode=mode)
        other, other_scale = band_preprocessing.prepare_ocr_band(
            image, max_long_side=400, mode=mode,
            normalize_rgb_fn=paddle_core.normalize_page_rgb,
            otsu_fn=paddle_core._otsu_threshold,
        )
        assert actual.size == other.size == (400, 200)
        assert actual.mode == other.mode == "RGB"
        assert scale == other_scale == 0.5
        assert np.array_equal(np.asarray(actual), np.asarray(other))
        actual.close()
        other.close()


def test_binary_band_uses_current_public_otsu_patch(monkeypatch):
    image = Image.new("RGB", (32, 32), "white")
    for x in range(16):
        for y in range(32):
            image.putpixel((x, y), (0, 0, 0))
    original = paddle_core._otsu_threshold
    monkeypatch.setattr(paddle_public, "_otsu_threshold", lambda gray: 255)
    black, scale = paddle_core.prepare_ocr_band(image, mode="binary")
    assert black.getpixel((25, 20)) == (0, 0, 0)
    assert scale == 1.0
    black.close()
    monkeypatch.setattr(paddle_public, "_otsu_threshold", lambda gray: -1)
    white, scale = paddle_core.prepare_ocr_band(image, mode="binary")
    assert white.getpixel((0, 0)) == (255, 255, 255)
    white.close()
    monkeypatch.setattr(paddle_public, "_otsu_threshold", original)
