from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageOps

from picture_capture.models import Entry
from picture_capture import processing_core as core


def test_separator_whitespace_score_reuses_precomputed_gray_exactly(monkeypatch) -> None:
    image = Image.new("RGB", (96, 80), "white")
    pixels = np.asarray(image).copy()
    pixels[38:43, 18:55] = 230
    pixels[40, 20:52] = 255
    image.close()
    image = Image.fromarray(pixels, mode="RGB")

    geometry = SimpleNamespace(
        transform=SimpleNamespace(kind="identity"),
        column_widths=[60],
    )
    settings = SimpleNamespace(character_height=20, column_width=60)
    entry = Entry(word="", x=18, y=40)

    monkeypatch.setattr(core, "column_index_for_click", lambda *_args: 0)
    monkeypatch.setattr(
        core,
        "_ordinary_source_column_edge",
        lambda *_args: (18, 1),
    )

    try:
        expected = core._separator_whitespace_score(
            image, entry, geometry, settings,
        )
        gray = np.asarray(
            ImageOps.grayscale(core.normalize_page_rgb(image)),
            dtype=np.uint8,
        )
        actual = core._separator_whitespace_score(
            image, entry, geometry, settings, gray,
        )
    finally:
        image.close()

    assert actual == expected
