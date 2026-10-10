"""Cross-column illustration grouping and caption regression."""
from PIL import Image, ImageDraw

from picture_capture.illustration_detection import (
    _merge_cross_column_boxes,
    _extend_cross_column_caption,
)


def test_cross_column_building_joins_at_seam():
    # Two detector rectangles from the supplied historical building image.
    left = (31, 12, 366, 235)
    right = (377, 43, 706, 232)
    assert _merge_cross_column_boxes([left, right], [377], 16) == [
        (31, 12, 706, 235)
    ]


def test_separate_column_figures_do_not_merge():
    left = (31, 12, 180, 235)
    right = (470, 43, 706, 232)
    assert _merge_cross_column_boxes([left, right], [377], 16) == [left, right]


def test_cross_column_caption_included_in_parent_region():
    image = Image.new("L", (740, 310), 255)
    draw = ImageDraw.Draw(image)
    # Small glyph-like rectangles under the center of the joined drawing.
    for x in (315, 335, 355, 375):
        draw.rectangle((x, 245, x + 10, 257), fill=0)
    result = _extend_cross_column_caption((31, 12, 706, 235), image, 8)
    assert result[3] >= 257


def test_cross_column_caption_does_not_swallow_far_below_text():
    image = Image.new("L", (740, 420), 255)
    ImageDraw.Draw(image).rectangle((315, 350, 420, 365), fill=0)
    assert _extend_cross_column_caption((31, 12, 706, 235), image, 8)[3] == 235
