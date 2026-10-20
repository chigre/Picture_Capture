"""Cross-column illustration grouping and caption regression."""
from PIL import Image, ImageDraw

from picture_capture.illustration.detection import (
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


def test_illustration_implementation_physically_owned_by_package():
    from pathlib import Path
    import picture_capture
    from picture_capture.illustration.detection import detect_illustration_regions_from_image
    from picture_capture.illustration.labels import illustration_labels
    from picture_capture.illustration.batch_association import associate_existing_ppp_page
    package_root = Path(picture_capture.__file__).resolve().parent
    for former in ("illustration_detection.py", "illustration_labels.py", "illustration_batch_association.py"):
        assert not (package_root / former).exists(), former
    assert detect_illustration_regions_from_image.__module__ == "picture_capture.illustration.detection"
    assert illustration_labels.__module__ == "picture_capture.illustration.labels"
    assert associate_existing_ppp_page.__module__ == "picture_capture.illustration.batch_association"
