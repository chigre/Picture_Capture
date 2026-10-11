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


def test_attached_closing_and_opening_brackets_use_measured_print_template():
    """A connecting ink stroke must not hide a visibly paired 【...】 head."""
    image = Image.new("L", (680, 850), 255)
    x, width, height, separation = 44, 22, 55, 150
    rows = (100, 210, 320, 430, 540)
    for y in rows:
        _draw_bracket_pair(
            image, x, y, separation=separation, height=height, width=width,
        )
    pen = ImageDraw.Draw(image)
    # Glue the upper cap of the *closing* bracket to a Han-like blob.
    # Raw 8-connected components will merge the bracket and inner character.
    pen.rectangle((x + separation - 27, 430 + 2,
                   x + separation + width - 6, 430 + 4), fill=0)
    pen.rectangle((x + separation - 40, 430 + 3,
                   x + separation - 27, 430 + 30), fill=0)
    # Glue the upper cap of the *opening* bracket to the next glyph.
    pen.rectangle((x + 3, 540 + 2, x + width + 30, 540 + 4), fill=0)
    pen.rectangle((x + width + 27, 540 + 3,
                   x + width + 48, 540 + 28), fill=0)
    recovered = recover_bracketed_ordinary_entries(
        [], image, [SimpleNamespace(left=42, right=630)], 40, 790, 35,
    )
    assert len(recovered) == len(rows)
    for y in rows:
        assert any(abs(entry.y - y) <= 8 for entry in recovered)


def test_matched_visual_brackets_upgrade_existing_layout_entry_source():
    """Nearby accepted Layout entry retains its bracket proof through veto."""
    image = Image.new("L", (680, 620), 255)
    for y in (90, 220, 350, 480):
        _draw_bracket_pair(image, 44, y, separation=150, height=55, width=22)
    existing = Entry(
        "", 42, 345,
        ocr_source="page_understanding:ordinary_layout_role",
        issue_type="PAGE_UNDERSTANDING_ORDINARY_LAYOUT_ROLE",
    )
    recovered = recover_bracketed_ordinary_entries(
        [existing], image,
        [SimpleNamespace(left=42, right=630)], 30, 590, 35,
    )
    assert len(recovered) == 4
    assert recovered.count(existing) == 1
    assert existing.ocr_source == "ordinary_bracket_pair"
    assert existing.issue_type == "ORDINARY_VISUAL_BRACKET_PAIR"
    assert existing.entry_source == "symbol_sample"


def test_sticky_bracket_rescue_needs_repeated_intact_printed_template():
    image = Image.new("L", (680, 470), 255)
    _draw_bracket_pair(image, 44, 110, separation=150, height=55)
    _draw_bracket_pair(image, 44, 240, separation=150, height=55)
    pen = ImageDraw.Draw(image)
    pen.rectangle((44 + 150 - 27, 240 + 2,
                   44 + 150 + 16, 240 + 4), fill=0)
    pen.rectangle((44 + 150 - 36, 240 + 3,
                   44 + 150 - 27, 240 + 28), fill=0)
    found = recover_bracketed_ordinary_entries(
        [], image, [SimpleNamespace(left=42, right=630)], 35, 440, 35,
    )
    # One intact pair is insufficient to learn a reliable width/offset model.
    assert len(found) == 1


def test_one_pixel_white_gap_does_not_merge_real_bracket_with_neighbor():
    """Actual XDHYCD bracket case: the generic CC joins across white pixels.

    Printed left and right brackets are each separated from adjacent Han
    strokes by one genuinely white source pixel. A bracket-specific, exact
    8-neighbor component finder must preserve them.
    """
    image = Image.new("L", (660, 620), 255)
    _draw_bracket_pair(image, 44, 210, separation=150, height=55, width=22)
    pen = ImageDraw.Draw(image)
    # Left bracket occupies x=44..65, x=66 white, glyph at x=67.
    pen.rectangle((67, 215, 87, 259), fill=0)
    # Right bracket x=194..215; x=193 white; last glyph ends at x=192.
    pen.rectangle((172, 216, 192, 257), fill=0)
    recovered = recover_bracketed_ordinary_entries(
        [], image, [SimpleNamespace(left=42, right=630)],
        40, 600, 35,
    )
    assert len(recovered) == 1
    assert abs(recovered[0].y - 210) <= 8


def test_long_headword_attached_right_bracket_recovers_at_page_bottom():
    """A bracketed four-character lemma must not assume 2-char pair width."""
    image = Image.new("L", (670, 930), 255)
    for y in (85, 220, 355, 490):
        _draw_bracket_pair(image, 44, y, separation=150, height=55)
    last_y = 849
    _draw_bracket_pair(
        image, 44, last_y, separation=230, height=55, width=22,
    )
    pen = ImageDraw.Draw(image)
    # Connected Han stroke at the left cap of the closing bracket.
    last_close = 44 + 230
    pen.rectangle((last_close-21, last_y+3, last_close+5, last_y+5), fill=0)
    pen.rectangle((last_close-32, last_y+4, last_close-21, last_y+24), fill=0)
    recovered = recover_bracketed_ordinary_entries(
        [], image, [SimpleNamespace(left=42, right=640)],
        40, 930, 35,
    )
    assert len(recovered) == 5
    assert any(abs(entry.y - last_y) <= 8 for entry in recovered)


def test_unmatched_long_headword_requires_template_and_both_strokes():
    image = Image.new("L", (650, 700), 255)
    # No >=3 learned intact pairs: an opening glyph alone must not make
    # a separator even if an unrelated definition glyph is further right.
    _draw_bracket_pair(image, 44, 300, separation=220, height=55, width=22)
    # Whiten the entire right bracket, leaving the opening untouched.
    ImageDraw.Draw(image).rectangle((264, 297, 301, 360), fill=255)
    result = recover_bracketed_ordinary_entries(
        [], image, [SimpleNamespace(left=42, right=620)],
        40, 670, 35,
    )
    assert result == []
