"""OCR-free restoration of missing CJK entries with matched 【...】 prints."""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.models import Entry
from picture_capture.ordinary_bracket_pair import (
    _bracket_side, recover_bracketed_ordinary_entries,
)


def _draw_bracket_pair(image, x, y, separation=150, height=55, width=22):
    pen = ImageDraw.Draw(image)
    for is_close, base in ((False, x), (True, x + separation)):
        if is_close:
            pen.rectangle((base + width - 7, y, base + width - 1, y + height), fill=0)
            pen.polygon([(base, y), (base + width - 1, y),
                         (base + width - 1, y + 9)], fill=0)
            pen.polygon([(base, y + height), (base + width - 1, y + height),
                         (base + width - 1, y + height - 9)], fill=0)
        else:
            pen.rectangle((base, y, base + 6, y + height), fill=0)
            pen.polygon([(base, y), (base + width - 1, y),
                         (base, y + 9)], fill=0)
            pen.polygon([(base, y + height), (base + width - 1, y + height),
                         (base, y + height - 9)], fill=0)


def test_recovers_two_numbered_bracket_headwords_without_duplicate():
    image = Image.new("L", (760, 660), 255)
    _draw_bracket_pair(image, 115, 170)
    _draw_bracket_pair(image, 125, 330)
    lines = [Entry("", 20, 164)]
    recovered = recover_bracketed_ordinary_entries(
        lines, image, [SimpleNamespace(left=20, right=660)],
        40, 610, 35,
    )
    assert len(recovered) == 2
    assert abs(recovered[-1].y - 330) <= 6
    assert recovered[-1].ocr_source == "ordinary_bracket_pair"


def test_unpaired_and_body_embedded_brackets_are_not_promoted():
    image = Image.new("L", (760, 660), 255)
    _draw_bracket_pair(image, 340, 200)
    ImageDraw.Draw(image).rectangle((135, 390, 141, 445), fill=0)
    assert recover_bracketed_ordinary_entries(
        [], image, [SimpleNamespace(left=20, right=660)], 40, 610, 35,
    ) == []


def test_open_close_shapes_are_directional():
    import numpy as np
    canvas = Image.new("L", (360, 110), 255)
    _draw_bracket_pair(canvas, 30, 20)
    image = np.asarray(canvas, dtype=np.uint8) < 170
    assert _bracket_side(image[20:76, 30:52], True)
    assert not _bracket_side(image[20:76, 30:52], False)
    assert _bracket_side(image[20:76, 180:202], False)
