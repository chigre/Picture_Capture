"""Issue #562: retire the image_utils root without changing source pixel semantics."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image

from picture_capture.preprocess import analysis_image, page_pixels


def test_analysis_image_is_one_physical_owner_with_no_root_shim():
    package_root = Path(analysis_image.__file__).resolve().parents[1]
    assert not (package_root / "image_utils.py").exists()
    assert importlib.util.find_spec("picture_capture.image_utils") is None
    assert (package_root / "preprocess/analysis_image.py").is_file()
    assert sum(1 for p in package_root.glob("*.py") if p.is_file()) == 9
    assert analysis_image.normalize_page_rgb is page_pixels.normalize_page_rgb
    assert analysis_image._box_sum is page_pixels._box_sum
    assert analysis_image._generic_analysis_ink is page_pixels._generic_analysis_ink


def test_shared_analysis_image_keeps_image_pixels_and_source_dimensions():
    pixels = np.full((22, 13, 3), 255, dtype=np.uint8)
    image = Image.fromarray(pixels, mode="RGB")
    baseline = image.tobytes()
    prepared = analysis_image.build_analysis_image(image)
    assert prepared.size == image.size
    assert prepared.mode == "RGB"
    assert prepared.tobytes() == baseline
    assert image.tobytes() == baseline
    assert prepared is not image
    prepared.close()
    image.close()
