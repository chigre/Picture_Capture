"""Issue #562: processing analysis pixels and OCR band box ownership."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from picture_capture import processing as public_processing
from picture_capture import processing_core as pc
from picture_capture import paddle_headwords as public_paddle
from picture_capture import paddle_headwords_core as ph
from picture_capture.geometry.layout_transform import LayoutTransform
from picture_capture.ocr.headword_models import OCRRecord
from picture_capture.ocr import band_coordinates
from picture_capture.preprocess import core_analysis_pixels

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_leaf_inventory_and_historical_core_callables():
    assert len(list(PKG.glob("*.py"))) == 10
    assert (PKG / "preprocess/core_analysis_pixels.py").is_file()
    assert (PKG / "ocr/band_coordinates.py").is_file()
    assert not (PKG / "core_analysis_pixels.py").exists()
    assert not (PKG / "band_coordinates.py").exists()
    for fn in (pc._analysis_image, pc._adaptive_dark_mask):
        assert fn.__module__ == "picture_capture.processing_core"
    assert ph._records_to_canonical_band.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(pc._analysis_image).parameters) == ["image", "max_width"]
    assert list(inspect.signature(pc._adaptive_dark_mask).parameters) == [
        "gray_image", "block_size", "c_value",
    ]
    assert list(inspect.signature(ph._records_to_canonical_band).parameters) == [
        "records", "source_band_size", "transform_kind",
    ]
    assert ph.OCRRecord is OCRRecord
    assert OCRRecord.__module__ == "picture_capture.paddle_headwords_core"


def test_analysis_image_resizes_only_if_wider_than_limit():
    source = Image.new("RGBA", (200, 90), (0, 0, 0, 0))
    for limit, size, expected_scale in (
        (200, (200, 90), 1.0),
        (100, (100, 45), 0.5),
    ):
        result, scale = pc._analysis_image(source, limit)
        other, other_scale = core_analysis_pixels.analysis_image(
            source, limit, normalize_rgb_fn=pc.normalize_page_rgb,
        )
        assert result.mode == other.mode == "RGB"
        assert result.size == other.size == size
        assert (scale, other_scale) == (expected_scale, expected_scale)
        assert result.getpixel((0, 0)) == (255, 255, 255)
        assert np.array_equal(np.asarray(result), np.asarray(other))
        assert result is not source
        result.close()
        other.close()
    source.close()


def test_analysis_image_observes_public_normalizer_patch(monkeypatch):
    original = pc.normalize_page_rgb
    seen = []
    def normalize(image):
        seen.append(image.size)
        return Image.new("RGB", image.size, (47, 89, 121))
    monkeypatch.setattr(public_processing, "normalize_page_rgb", normalize)
    img = Image.new("RGB", (80, 60), "black")
    result, ratio = pc._analysis_image(img, 100)
    assert seen == [(80, 60)]
    assert result.getpixel((10, 10)) == (47, 89, 121)
    assert ratio == 1.0
    result.close()
    monkeypatch.setattr(public_processing, "normalize_page_rgb", original)


def test_adaptive_dark_ink_leaf_and_public_numpy_patch(monkeypatch):
    array = np.full((25, 21), 240, dtype=np.uint8)
    array[12, 10] = 0
    image = Image.fromarray(array, mode="L")
    for block, c in ((2, 0), (5, 12), (10, 20), (19, -2)):
        got = pc._adaptive_dark_mask(image, block, c)
        direct = core_analysis_pixels.adaptive_dark_mask(image, block, c)
        assert got.shape == array.shape
        assert got.dtype == np.bool_
        assert np.array_equal(got, direct)
        assert bool(got[12, 10])
    original = pc.ImageFilter
    calls = []
    class Filter:
        @staticmethod
        def BoxBlur(radius):
            calls.append(radius)
            return original.BoxBlur(radius)
    monkeypatch.setattr(public_processing, "ImageFilter", Filter)
    pc._adaptive_dark_mask(image, 4, 7)
    assert calls == [2]
    monkeypatch.setattr(public_processing, "ImageFilter", original)


def test_ocr_canonical_records_preserve_recovery_and_parent_box():
    record = OCRRecord(
        "漢", 0.92, (10, 20, 35, 42),
        recovery="cjk_visual", recovery_source_text="漢1",
        parent_box=(8, 18, 80, 55),
    )
    plain = OCRRecord("word", 0.61, (40, 50, 70, 65))
    for kind in ("identity", "mirror_x", "rotate_ccw90", "rotate_cw90"):
        orig = [record, plain]
        got = ph._records_to_canonical_band(orig, (100, 120), kind)
        direct = band_coordinates.records_to_canonical_band(orig, (100, 120), kind)
        transform = LayoutTransform(kind)
        assert got == direct
        assert got is not orig
        assert all(type(r) is OCRRecord for r in got)
        assert got[0].box == transform.source_box_to_canonical(record.box, (100, 120))
        assert got[0].parent_box == transform.source_box_to_canonical(record.parent_box, (100, 120))
        assert got[0].recovery == record.recovery
        assert got[0].recovery_source_text == record.recovery_source_text
        assert got[1].parent_box is None
        assert orig[0].box == (10, 20, 35, 42)


def test_ocr_record_bridge_observes_historical_public_record_class_patch(monkeypatch):
    original = ph.OCRRecord
    calls = []
    def constructor(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(public_paddle, "OCRRecord", constructor)
    got = ph._records_to_canonical_band([original("a", 0.5, (1, 2, 3, 4))], (20, 30), "mirror_x")
    assert len(calls) == 1
    assert got[0].box == (17, 2, 19, 4)
    monkeypatch.setattr(public_paddle, "OCRRecord", original)
