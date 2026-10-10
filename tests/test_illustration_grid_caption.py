"""Regression: a two-row dictionary illustration is one PPP region."""
from picture_capture.illustration_detection import _merge_illustration_grid, _extend_box_to_caption


def test_eight_panel_figure_merges_into_one_box_before_caption():
    # Box geometry transcribed from the eight blue rectangles in the sample.
    panels = [
        (20, 20, 96, 111), (107, 10, 145, 121),
        (178, 14, 241, 106), (250, 20, 335, 128),
        (22, 138, 96, 228), (98, 124, 147, 231),
        (158, 129, 230, 241), (238, 147, 336, 236),
    ]
    joined = _merge_illustration_grid(panels)
    assert joined == [(20, 10, 336, 241)]
    caption = [
        (144, 245, 164, 257, 40), (166, 245, 185, 257, 40),
        (187, 245, 204, 257, 40),
        (99, 265, 134, 279, 60), (135, 265, 180, 279, 80),
        (181, 265, 223, 279, 70), (224, 265, 269, 279, 80),
    ]
    assert _extend_box_to_caption(joined[0], caption, 285) == (20, 10, 336, 279)


def test_independent_figures_not_joined_without_two_aligned_rows():
    figures = [(0, 0, 50, 60), (80, 0, 130, 60),
               (200, 0, 250, 60), (290, 0, 340, 60)]
    assert _merge_illustration_grid(figures) == figures
