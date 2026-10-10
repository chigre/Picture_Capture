"""Regression tests for illustration-caption inclusion."""
from picture_capture.illustration_detection import _extend_box_to_caption


def test_centered_caption_below_illustration_is_included():
    box = (100, 100, 300, 300)
    # Connected glyphs form a centered title line below the drawing.
    components = [
        (145, 308, 159, 320, 50),
        (162, 308, 175, 320, 48),
        (178, 308, 191, 320, 45),
        (194, 308, 207, 320, 49),
        (210, 308, 225, 320, 55),
    ]
    assert _extend_box_to_caption(box, components, 1000) == (100, 100, 300, 320)


def test_left_aligned_body_text_not_included():
    box = (100, 100, 300, 300)
    components = [
        (100, 308, 130, 320, 40),
        (133, 308, 163, 320, 40),
    ]
    assert _extend_box_to_caption(box, components, 1000) == box


def test_distant_or_oversized_text_not_included():
    box = (100, 100, 300, 300)
    assert _extend_box_to_caption(box, [(150, 345, 230, 358, 100)], 1000) == box
    assert _extend_box_to_caption(box, [(150, 307, 230, 370, 100)], 1000) == box
