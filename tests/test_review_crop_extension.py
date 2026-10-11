"""Regression tests for active proofreading preview extension geometry."""
from PIL import Image

from picture_capture.review_crop_extension import (
    extended_review_crop_box,
    parse_review_crop_multiplier,
)


def test_larger_preview_starts_at_exact_same_source_y_as_ordinary_line():
    original = (10, 40, 100, 60)
    expanded = extended_review_crop_box(original, 180, 2.5)
    assert expanded == (10, 40, 100, 90)
    assert expanded[1] == original[1]
    assert expanded[0] == original[0]
    assert expanded[2] == original[2]


def test_near_bottom_crops_never_extend_beyond_source_image():
    original = (10, 120, 100, 140)
    assert extended_review_crop_box(original, 150, 2.5) == (10, 120, 100, 150)
    assert extended_review_crop_box(original, 140, 1.0) == original
    image = Image.new("RGB", (120, 150), "white")
    image.paste((0, 0, 0), (10, 120, 100, 140))
    ordinary = image.crop(original)
    extended = image.crop(extended_review_crop_box(original, image.height, 2.5))
    assert ordinary.getpixel((0, 0)) == extended.getpixel((0, 0))
    assert extended.height == 30


def test_multiplier_is_validated_as_finite_user_percentage_free_float():
    assert parse_review_crop_multiplier("2.5") == 2.5
    assert parse_review_crop_multiplier("1.25") == 1.25
