from picture_capture.overlay_line_anchor_runtime import one_sided_line_coordinates


def test_column_guide_width_grows_to_right_only():
    # Width=5 is a centred 5px stroke. Shifting the centre path right by 2px
    # keeps the original x=100 pixel as the left edge and puts all added width
    # inside/right of the column boundary.
    shifted = one_sided_line_coordinates(
        (100.0, 10.0, 100.0, 90.0),
        width=5.0,
        growth="right",
    )
    assert shifted == (102.0, 10.0, 102.0, 90.0)


def test_headword_marker_height_grows_down_only():
    # Existing top-anchor behavior remains unchanged.
    shifted = one_sided_line_coordinates(
        (20.0, 50.0, 120.0, 50.0),
        width=5.0,
        growth="down",
    )
    assert shifted == (20.0, 52.0, 120.0, 52.0)


def test_width_one_keeps_structural_anchor_exactly():
    coords = (100.0, 10.0, 100.0, 90.0)
    assert one_sided_line_coordinates(
        coords,
        width=1.0,
        growth="right",
    ) == coords
