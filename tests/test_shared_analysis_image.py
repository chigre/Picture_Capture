from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.image_utils import build_analysis_image


def _pixel(image: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    value = np.asarray(image, dtype=np.uint8)[y, x]
    return tuple(int(v) for v in value)


def test_shared_analysis_image_removes_truly_isolated_speck() -> None:
    image = Image.new("RGB", (80, 60), "white")
    image.putpixel((8, 8), (0, 0, 0))

    cleaned = build_analysis_image(image)

    assert cleaned.size == image.size
    assert _pixel(cleaned, 8, 8) == (255, 255, 255)


def test_shared_analysis_image_preserves_thin_vertical_rule() -> None:
    image = Image.new("RGB", (80, 60), "white")
    draw = ImageDraw.Draw(image)
    draw.line((15, 5, 15, 50), fill="black", width=1)

    cleaned = build_analysis_image(image)

    assert _pixel(cleaned, 15, 25) == (0, 0, 0)
    assert _pixel(cleaned, 15, 10) == (0, 0, 0)


def test_shared_analysis_image_preserves_thin_horizontal_rule() -> None:
    image = Image.new("RGB", (80, 60), "white")
    draw = ImageDraw.Draw(image)
    draw.line((5, 25, 70, 25), fill="black", width=1)

    cleaned = build_analysis_image(image)

    assert _pixel(cleaned, 20, 25) == (0, 0, 0)
    assert _pixel(cleaned, 60, 25) == (0, 0, 0)


def test_shared_analysis_image_preserves_detached_mark_near_glyph() -> None:
    image = Image.new("RGB", (80, 60), "white")
    draw = ImageDraw.Draw(image)
    # A simple synthetic stem plus a detached accent/dot close enough to be part
    # of the same printed character neighborhood.
    draw.rectangle((30, 24, 32, 42), fill="black")
    draw.rectangle((30, 18, 31, 19), fill="black")

    cleaned = build_analysis_image(image)

    assert _pixel(cleaned, 30, 18) == (0, 0, 0)
    assert _pixel(cleaned, 31, 19) == (0, 0, 0)


def test_shared_analysis_image_does_not_change_coordinates_or_source() -> None:
    image = Image.new("RGB", (51, 73), "white")
    image.putpixel((4, 6), (0, 0, 0))
    before = image.copy()

    cleaned = build_analysis_image(image)

    assert cleaned.size == (51, 73)
    assert np.array_equal(np.asarray(image), np.asarray(before))
