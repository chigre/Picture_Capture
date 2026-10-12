"""Paddle row-leading must be computed within each physical print column."""
from picture_capture.layout_textbox_leading import estimate_row_padding_from_boxes


def _boxes(x, first_y, rows=24, step=43, height=29):
    return [(x, first_y + i*step, x+240, first_y + i*step+height) for i in range(rows)]


def test_two_staggered_columns_cannot_halve_line_pitch():
    # Same true line pitch 43px but right column starts halfway between left
    # rows. Old global sort saw ~21px increments, always producing padding=1.
    groups = [_boxes(10, 80), _boxes(720, 101)]
    padding, support = estimate_row_padding_from_boxes(groups, 29)
    assert padding == 7  # existing legacy convention (43-29)/2
    assert support >= 40


def test_sparse_disordered_text_boxes_are_not_trusted():
    assert estimate_row_padding_from_boxes([
        [(10, 20, 100, 49), (10, 67, 100, 96)],
    ], 29)[0] is None
    # Print lines of contradictory pitch cannot be treated as one template.
    mixed = [_boxes(10, 80, rows=24, step=43),
             _boxes(720, 110, rows=24, step=76)]
    assert estimate_row_padding_from_boxes(mixed, 29)[0] is None


def test_multiple_boxes_in_same_print_line_count_only_once():
    groups = [
        [(10+(j%3)*60, 60+(j//3)*43+(j%3), 55+(j%3)*60,
          60+(j//3)*43+(j%3)+29) for j in range(72)]
    ]
    padding, support = estimate_row_padding_from_boxes(groups, 29)
    assert padding == 7
    assert support >= 20
