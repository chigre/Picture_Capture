from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageFilter

from picture_capture import image_utils, processing
from picture_capture.models import AppSettings, Entry


def _historical_generic_analysis_ink(gray_image: Image.Image) -> np.ndarray:
    gray = np.asarray(gray_image, dtype=np.int16)
    local = np.asarray(
        gray_image.filter(ImageFilter.BoxBlur(5)),
        dtype=np.int16,
    )
    return (gray <= 150) | ((gray <= 205) & (gray + 20 <= local))


def test_generic_analysis_ink_uint8_formula_matches_historical_int16() -> None:
    rng = np.random.default_rng(20261008)
    for shape in ((1, 1), (13, 17), (64, 91), (257, 193)):
        pixels = rng.integers(0, 256, size=shape, dtype=np.uint8)
        image = Image.fromarray(pixels, mode="L")
        try:
            expected = _historical_generic_analysis_ink(image)
            actual = image_utils._generic_analysis_ink(image, pixels)
        finally:
            image.close()
        np.testing.assert_array_equal(actual, expected)


def test_allowed_entries_reuses_already_normalized_source(monkeypatch) -> None:
    image = Image.new("RGB", (37, 53), "white")
    settings = AppSettings()
    entry = Entry(word="", x=5, y=7)
    seen_sizes: list[tuple[int, int]] = []

    monkeypatch.setattr(
        processing._core,
        "normalize_page_rgb",
        lambda _image: (_ for _ in ()).throw(
            AssertionError("_allowed_entries must not renormalize source")
        ),
    )
    monkeypatch.setattr(
        processing._core,
        "effective_page_settings",
        lambda page_settings, source_size, _page_index: (
            seen_sizes.append(tuple(source_size)) or page_settings
        ),
    )
    monkeypatch.setattr(
        processing._core,
        "entry_allowed_by_page_template",
        lambda _x, _y, source_size, _settings, _page_index: (
            seen_sizes.append(tuple(source_size)) or True
        ),
    )

    try:
        result = processing._allowed_entries(
            [entry],
            image,
            settings,
            SimpleNamespace(top=0, bottom=53),
            0,
            None,
        )
    finally:
        image.close()

    assert result == [entry]
    assert seen_sizes == [(37, 53), (37, 53)]
