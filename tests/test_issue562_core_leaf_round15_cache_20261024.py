"""Characterization for round 15 OCR cache source-coordinate leaf extraction."""

import hashlib

from PIL import Image

from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import source_coordinate_persistence as leaf


def test_source_only_projection_nested_and_aliases():
    raw = {
        "y": 999, "source_y": 42, "_axis_v": 12,
        "canonical_u": 3, "coordinate_spaces": ["transformed"],
        "paddle_y": 500, "paddle_source_y": 51,
        "tesseract_coarse_y": 333, "tesseract_coarse_source_y": 55,
        "lens_anchor_y": 222, "lens_anchor_source_y": 56,
        "nested": [{"y": 700, "source_y": 70, "_anchor_axis_v": 2}],
    }
    expected = {
        "y": 42, "source_y": 42,
        "paddle_y": 51, "paddle_source_y": 51,
        "tesseract_coarse_y": 55, "tesseract_coarse_source_y": 55,
        "lens_anchor_y": 56, "lens_anchor_source_y": 56,
        "nested": [{"y": 70, "source_y": 70}],
    }
    assert core._source_only_persistence(raw) == expected
    assert raw["y"] == 999  # Never mutate incoming OCR diagnostics.
    assert leaf.source_only_persistence((raw,))[0] == expected
    assert core._source_only_persistence.__module__ == "picture_capture.paddle_headwords_core"


def test_pixel_hash_is_identical_to_historical_digest():
    image = Image.new("RGB", (2, 1), (27, 99, 180))
    normalized = core.normalize_page_rgb(image)
    digest = hashlib.sha256()
    digest.update(b"2x1|RGB|")
    digest.update(normalized.tobytes())
    assert core._image_cache_fingerprint(image) == digest.hexdigest()
    assert core._image_cache_fingerprint.__module__ == "picture_capture.paddle_headwords_core"


def test_hash_uses_live_core_normalizer(monkeypatch):
    image = Image.new("RGB", (1, 1), "white")
    expected = Image.new("RGB", (1, 1), "black")
    monkeypatch.setattr(core, "normalize_page_rgb", lambda _img: expected)
    digest = hashlib.sha256(b"1x1|RGB|" + expected.tobytes()).hexdigest()
    assert core._image_cache_fingerprint(image) == digest
