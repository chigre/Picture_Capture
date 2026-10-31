"""Issue #562: shared source-space page pixels have one preprocess owner."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from picture_capture.preprocess import analysis_image as image_utils
from picture_capture.preprocess import page_pixels as pixels


def test_one_physical_owner_and_historical_function_identity() -> None:
    root = Path(image_utils.__file__).resolve().parents[1]
    assert Path(pixels.__file__).resolve() == root / "preprocess" / "page_pixels.py"
    for name in ("normalize_page_rgb", "_box_sum", "_generic_analysis_ink"):
        assert getattr(image_utils, name) is getattr(pixels, name)
        assert getattr(pixels, name).__module__ == "picture_capture.preprocess.page_pixels"
    source = (root / "preprocess/analysis_image.py").read_text(encoding="utf-8")
    assert not (root / "image_utils.py").exists()
    assert "def normalize_page_rgb(" not in source
    assert "def _box_sum(" not in source
    assert "def _generic_analysis_ink(" not in source


def test_alpha_and_palette_transparency_use_white_backed_source_pixels() -> None:
    rgba = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
    rgba.putpixel((1, 0), (255, 0, 0, 255))
    rgba.putpixel((2, 0), (0, 0, 255, 128))
    before = rgba.tobytes()
    normalized = image_utils.normalize_page_rgb(rgba)
    try:
        assert normalized.mode == "RGB" and normalized.size == (3, 2)
        assert normalized.getpixel((0, 0)) == (255, 255, 255)
        assert normalized.getpixel((1, 0)) == (255, 0, 0)
        assert normalized.getpixel((2, 0)) == (127, 127, 255)
        assert rgba.mode == "RGBA" and rgba.tobytes() == before
    finally:
        normalized.close()
        rgba.close()

    indexed = Image.new("P", (2, 1), 0)
    indexed.putpalette([0, 0, 0, 255, 0, 0] + [0, 0, 0] * 254)
    indexed.info["transparency"] = 0
    indexed.putpixel((1, 0), 1)
    converted = image_utils.normalize_page_rgb(indexed)
    try:
        assert list(converted.getdata()) == [(255, 255, 255), (255, 0, 0)]
        assert indexed.mode == "P" and indexed.getpixel((0, 0)) == 0
    finally:
        converted.close()
        indexed.close()


def test_exif_orientation_is_detached_and_keeps_exact_reoriented_pixels() -> None:
    image = Image.new("RGB", (2, 3))
    colors = [
        (255, 0, 0), (0, 255, 0),
        (0, 0, 255), (255, 255, 0),
        (0, 255, 255), (255, 0, 255),
    ]
    image.putdata(colors)
    original = image.tobytes()
    orientation = image.getexif()
    orientation[274] = 6
    image.info["exif"] = orientation.tobytes()
    expected = ImageOps.exif_transpose(image)
    normalized = pixels.normalize_page_rgb(image)
    try:
        assert normalized.size == expected.size == (3, 2)
        assert np.array_equal(np.asarray(normalized), np.asarray(expected))
        assert image.size == (2, 3) and image.tobytes() == original
        assert normalized is not image
    finally:
        normalized.close()
        expected.close()
        image.close()


def test_opaque_rgb_is_copied_and_unchanged() -> None:
    image = Image.fromarray(
        np.random.default_rng(562).integers(0, 256, (13, 19, 3), dtype=np.uint8),
        mode="RGB",
    )
    source_bytes = image.tobytes()
    clone = image_utils.normalize_page_rgb(image)
    try:
        assert clone is not image and clone.tobytes() == source_bytes
        clone.putpixel((0, 0), (0, 0, 0))
        assert image.tobytes() == source_bytes
    finally:
        clone.close()
        image.close()


def test_ink_predicate_agrees_exactly_with_historical_signed_arithmetic() -> None:
    rng = np.random.default_rng(20261022)
    for shape in ((1, 1), (13, 17), (64, 35)):
        gray = rng.integers(0, 256, shape, dtype=np.uint8)
        im = Image.fromarray(gray, mode="L")
        try:
            signed = np.asarray(im, dtype=np.int16)
            local = np.asarray(im.filter(ImageFilter.BoxBlur(5)), dtype=np.int16)
            expected = (signed <= 150) | ((signed <= 205) & (signed + 20 <= local))
            np.testing.assert_array_equal(image_utils._generic_analysis_ink(im), expected)
            np.testing.assert_array_equal(pixels._generic_analysis_ink(im, gray), expected)
        finally:
            im.close()


def test_box_sum_preserves_zero_border_counts() -> None:
    source = np.asarray([[1, 0, 1, 0], [0, 1, 0, 1], [1, 1, 0, 0]], dtype=bool)
    expected = np.asarray(
        [
            [
                sum(
                    int(source[y, x])
                    for y in range(max(0, row - 1), min(source.shape[0], row + 2))
                    for x in range(max(0, col - 1), min(source.shape[1], col + 2))
                )
                for col in range(source.shape[1])
            ]
            for row in range(source.shape[0])
        ],
        dtype=np.int32,
    )
    np.testing.assert_array_equal(image_utils._box_sum(source, 1, 1), expected)


def test_leaf_import_before_preprocess_analysis_image_has_no_runtime_dependency_cycle() -> None:
    code = """
import importlib, sys
leaf = importlib.import_module('picture_capture.preprocess.page_pixels')
assert 'picture_capture.preprocess.analysis_image' not in sys.modules
root = importlib.import_module('picture_capture.preprocess.analysis_image')
assert root.normalize_page_rgb is leaf.normalize_page_rgb
assert root._generic_analysis_ink is leaf._generic_analysis_ink
"""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
