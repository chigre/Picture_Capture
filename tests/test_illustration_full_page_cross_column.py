"""Full-page cross-column reconciliation regression tests."""
from PIL import Image, ImageDraw

from picture_capture.illustration_cross_column import spanning_figure_boxes


def test_continuous_ink_figure_crossing_real_gutter_reunites_split_boxes():
    image = Image.new("L", (650, 310), 255)
    draw = ImageDraw.Draw(image)
    # Left column ends at 300, right column starts at 350.
    # The same architectural drawing crosses the 50-pixel gutter.
    draw.rectangle((130, 75, 540, 230), outline=0, width=5)
    for x in range(160, 540, 45):
        draw.line((x, 85, x, 220), fill=0, width=3)
    pieces = [(125, 70, 310, 235), (340, 70, 545, 235)]
    result, consumed = spanning_figure_boxes(
        image, [(40, 300), (350, 610)], pieces,
    )
    assert consumed == {0, 1}
    assert len(result) == 1
    assert result[0][0] <= 130 and result[0][2] >= 540


def test_separate_drawings_across_gutter_remain_independent():
    image = Image.new("L", (650, 310), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((130, 75, 280, 230), outline=0, width=5)
    draw.rectangle((370, 75, 540, 230), outline=0, width=5)
    pieces = [(125, 70, 285, 235), (365, 70, 545, 235)]
    result, consumed = spanning_figure_boxes(
        image, [(40, 300), (350, 610)], pieces,
    )
    assert consumed == set()
    assert result == pieces
