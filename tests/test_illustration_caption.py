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


def test_single_character_caption_centered_below_wide_fish():
    # Regression: a wide fish drawing with a single Chinese title immediately
    # below its center. The previous >=10% width test dropped this caption.
    box = (100, 100, 580, 280)
    components = [(329, 287, 350, 306, 180)]
    assert _extend_box_to_caption(box, components, 1000) == (100, 100, 580, 306)


def test_single_character_in_left_aligned_body_is_not_caption():
    box = (100, 100, 580, 280)
    components = [(108, 287, 128, 306, 180)]
    assert _extend_box_to_caption(box, components, 1000) == box


def test_realistic_fish_caption_height_survives_filter():
    # Geometry measured from a scanned dictionary page: wide fish body
    # 236 x 77; centered one-character caption 13 x 14 directly below.
    box = (461, 390, 697, 467)
    caption = [(573, 467, 586, 481, 151)]
    assert _extend_box_to_caption(box, caption, 1000) == (461, 390, 697, 481)


def test_downscaled_fish_caption_height_survives_filter():
    # The production detector resizes columns for analysis.
    box = (330, 280, 500, 335)
    caption = [(410, 335, 420, 345, 75)]
    assert _extend_box_to_caption(box, caption, 720) == (330, 280, 500, 345)


def test_full_text_line_beneath_fish_remains_excluded():
    box = (461, 390, 697, 467)
    body = [(465, 470, 680, 486, 500)]
    assert _extend_box_to_caption(box, body, 1000) == box
