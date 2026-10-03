from __future__ import annotations

from PIL import Image, ImageDraw

from picture_capture.generic_block_roles import generic_entry_candidates
from picture_capture.models import AppSettings
from picture_capture.page_understanding import understand_page
from picture_capture.profile_indent_ui import apply_indent_type_label


def _settings() -> AppSettings:
    settings = AppSettings(
        columns=1,
        layout_columns_policy="fixed",
        start_y=10,
        manual_x=20,
        column_width=310,
        gutter=20,
        character_height=20,
        ordinary_auto_layout=False,
        dictionary_profile_id="latin_regular",
        ocr_language="eng",
        paddle_language="en",
        profile_header_mode="none",
        profile_footer_mode="none",
        profile_side_content_mode="none",
    )
    apply_indent_type_label(settings, "正文缩进")
    return settings


def _line(draw: ImageDraw.ImageDraw, x: int, y: int, width: int) -> None:
    draw.rectangle((x, y, x + width, y + 11), fill="black")


def test_proven_outer_lane_absorbs_nearby_sparse_headword_variant():
    image = Image.new("RGB", (360, 520), "white")
    draw = ImageDraw.Draw(image)
    # Three rows prove the outer family at x=20.  The final headword starts only
    # three pixels inward.  At the observed ~12 px ink height this is outside the
    # base clustering radius (~0.24h) but still inside the *already proven*
    # family's conservative sparse-extension radius (~0.32h).  This models a
    # short/superscript headword without turning distant body starts into entries.
    for x, y in ((20, 50), (20, 170), (20, 290), (23, 410)):
        _line(draw, x, y, 250)
    for y in (82, 114, 202, 234, 322, 354, 442, 474):
        _line(draw, 70, y, 205)

    understanding = understand_page(image, _settings())
    assert understanding.generic_body_indent_reliable

    candidates = generic_entry_candidates(understanding)
    assert len(candidates) == 4
