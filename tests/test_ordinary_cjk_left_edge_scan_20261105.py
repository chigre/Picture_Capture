"""Regression for November 5 Chinese-English ordinary-mode scan diagnosis.

Three 4500px scanned pages showed stable, ~43px body continuation indents,
but valid neighboring left-edge headwords were demoted by an overly broad
'large ink continuation' test. The same scans had joined ~1.8x projection
bands; both conditions must remain distinguishable without OCR.
"""
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from picture_capture.layout.oversized_ink_continuation import (
    suppress_oversized_ink_continuation,
)
from picture_capture.layout.physical_indent import projection_line_runs


@pytest.mark.parametrize(
    "entry_x,body_x",
    [
        (17.96, 59.81), (15.61, 59.15), (12.33, 54.60),  # scan 0002
        (5.07, 47.82), (-2.51, 41.01), (-8.46, 34.90),  # scan 0003
        (15.97, 58.89), (16.00, 58.50), (15.28, 57.00),  # scan 0004
    ],
)
def test_proven_body_indent_preserves_two_independent_cjk_headwords(
    entry_x: float, body_x: float,
) -> None:
    """Distinct normal-height physical rows in the same left-edge lane survive."""
    reference = 64.0
    first = SimpleNamespace(role="entry", y0=30, y1=93, first_x=entry_x)
    second = SimpleNamespace(role="entry", y0=101, y1=164, first_x=entry_x)
    column = SimpleNamespace(
        left=20, right=440, lines=[first, second],
        body_mode=SimpleNamespace(center=body_x, support=35),
        entry_modes=[SimpleNamespace(center=entry_x, support=50)],
    )
    layout = SimpleNamespace(
        ordinary_line_height=reference, body_top=0, indent_type="body",
        columns=[column],
        transform=SimpleNamespace(canonical_image_for_analysis=lambda image: image),
    )
    image = Image.new("RGB", (500, 260), "white")
    draw = ImageDraw.Draw(image)
    # Deliberately hostile busy near-edge band: the old ink heuristic could
    # treat tight neighbouring words as one enlarged glyph.
    draw.rectangle((56, 40, 160, 150), fill="black")
    outcome = suppress_oversized_ink_continuation(image, layout)
    assert outcome["demoted_fragments"] == 0
    assert first.role == second.role == "entry"


def test_no_indent_real_oversized_glyph_can_still_be_deduplicated() -> None:
    """Do not globally disable suppression for genuine oversized glyphs."""
    first = SimpleNamespace(role="entry", y0=30, y1=64)
    second = SimpleNamespace(role="entry", y0=85, y1=126)
    column = SimpleNamespace(left=25, right=260, lines=[first, second])
    layout = SimpleNamespace(
        ordinary_line_height=40, body_top=0, indent_type="none",
        columns=[column],
        transform=SimpleNamespace(canonical_image_for_analysis=lambda image: image),
    )
    image = Image.new("RGB", (280, 180), "white")
    ImageDraw.Draw(image).rectangle((52, 36, 140, 105), fill="black")
    outcome = suppress_oversized_ink_continuation(image, layout)
    assert outcome["demoted_fragments"] == 1
    assert second.role == "body"


def test_two_printed_rows_joined_into_1_875x_band_split_at_real_valley() -> None:
    """Normal adjacent text rows are recoverable without faking blank space."""
    ink = np.zeros((180, 350), dtype=bool)
    ink[5:60, 20:200] = True
    ink[70:125, 20:200] = True
    # Weak (but projection-active) scan noise bridges the two row bands.
    ink[60:70, 45:47] = True
    result = projection_line_runs(ink, 64.0)
    assert len(result) == 2
    assert result[0][0] == 5
    assert result[0][1] <= 70
    assert result[1][0] >= 60
    assert result[1][1] == 125


def test_one_solid_oversized_glyph_not_forcibly_cut_in_half() -> None:
    ink = np.zeros((180, 350), dtype=bool)
    ink[5:125, 20:200] = True
    assert projection_line_runs(ink, 64.0) == [(5, 125)]
