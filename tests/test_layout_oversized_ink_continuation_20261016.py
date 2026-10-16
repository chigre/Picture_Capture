"""Generalized oversized-glyph fragment veto tests (no per-page XY constants)."""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.entry_classification import register_layout_line_classification
from picture_capture.layout_oversized_ink_continuation import (
    suppress_oversized_ink_continuation,
)
from picture_capture.models import Entry


def _setup(reference=40, *, separate=False, other_column=False):
    left = 25
    earlier = SimpleNamespace(role="entry", y0=30, y1=64)
    later = SimpleNamespace(role="entry", y0=85, y1=126)
    same = SimpleNamespace(left=left, right=260, lines=[earlier, later])
    if other_column:
        same.lines = [earlier]
        second = SimpleNamespace(left=280, right=520, lines=[later])
        columns = [same, second]
    else:
        columns = [same]
    layout = SimpleNamespace(
        ordinary_line_height=reference, body_top=0,
        columns=columns,
        transform=SimpleNamespace(canonical_image_for_analysis=lambda img: img),
    )
    image = Image.new("RGB", (540, 230), "white")
    draw = ImageDraw.Draw(image)
    # Observed ink shape, independent of Layout's initial role hypothesis.
    if separate:
        draw.rectangle((left + 27, 36, left + 115, 63), fill="black")
        draw.rectangle((left + 27, 96, left + 115, 125), fill="black")
    else:
        draw.rectangle((left + 27, 36, left + 115, 105), fill="black")
    return image, layout, earlier, later


def test_duplicate_inside_one_tall_printed_glyph_is_demoted():
    image, layout, earlier, later = _setup()
    result = suppress_oversized_ink_continuation(image, layout)
    assert result == {"candidate_pairs": 1, "demoted_fragments": 1}
    assert earlier.role == "entry"
    assert later.role == "body"


def test_distinct_adjacent_headwords_remain_separate():
    image, layout, earlier, later = _setup(separate=True)
    result = suppress_oversized_ink_continuation(image, layout)
    assert result["demoted_fragments"] == 0
    assert earlier.role == later.role == "entry"


def test_independently_verified_symbol_head_is_never_demoted():
    image, layout, earlier, later = _setup()
    register_layout_line_classification(later, Entry(
        word="", x=25, y=85, ocr_source="ordinary_bracket_pair",
        issue_type="ORDINARY_VISUAL_BRACKET_PAIR",
    ))
    result = suppress_oversized_ink_continuation(image, layout)
    assert result["candidate_pairs"] == 0
    assert later.role == "entry"


def test_unrelated_columns_must_not_suppress_one_another():
    image, layout, earlier, later = _setup(other_column=True)
    result = suppress_oversized_ink_continuation(image, layout)
    assert result["candidate_pairs"] == 0
    assert later.role == "entry"


def test_rule_is_scale_relative_and_does_not_use_fixed_y_pixels():
    image, layout, earlier, later = _setup()
    upscaled = image.resize((1080, 460), Image.Resampling.NEAREST)
    layout.ordinary_line_height *= 2
    column = layout.columns[0]
    column.left *= 2
    column.right *= 2
    for line in column.lines:
        line.y0 *= 2
        line.y1 *= 2
    result = suppress_oversized_ink_continuation(upscaled, layout)
    assert result["demoted_fragments"] == 1


def test_single_entry_and_blank_image_are_never_vetoed():
    image, layout, earlier, later = _setup()
    layout.columns[0].lines.remove(earlier)
    assert suppress_oversized_ink_continuation(image, layout)["demoted_fragments"] == 0
    layout.columns[0].lines.insert(0, earlier)
    blank = Image.new("RGB", image.size, "white")
    assert suppress_oversized_ink_continuation(blank, layout)["demoted_fragments"] == 0
