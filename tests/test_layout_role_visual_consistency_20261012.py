"""Regression for XDHYCD page 0009: entry-mode contamination by body rows.

The original copyrighted scan stays outside the public repository. These
small synthetic rows model its observed ~29px glyph height and ~37px gap
between the outer entry start and inner body start. No GT coordinates are
used by the production algorithm.
"""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.layout_role_visual_consistency import (
    suppress_contradictory_cjk_body_lane_entries,
)
from picture_capture.models import AppSettings


class _Identity:
    def canonical_image_for_analysis(self, image):
        return image.copy()


def _test_page(*, polluted=8, body_indent=True):
    image = Image.new("RGB", (600, 1300), "white")
    draw = ImageDraw.Draw(image)
    lines = []
    for i in range(23):
        y = 45 + i * 49
        # Some detected entry-mode members physically begin in the body
        # lane (in the real scan: consecutive definition rows). They must
        # not inherit the role of the enclosing indent cluster.
        false_entry = i < polluted
        x = 78 if false_entry else 40
        draw.rectangle((x, y, x + 70, y + 28), fill="black")
        lines.append(SimpleNamespace(y0=y, y1=y + 29, role="entry"))
    for i in range(7):
        y = 58 + i * 49
        draw.rectangle((78, y, 155, y + 28), fill="black")
        lines.append(SimpleNamespace(y0=y, y1=y + 29, role="body"))

    entry_mode = SimpleNamespace(center=0.0, support=23)
    body_mode = SimpleNamespace(center=38.0, support=7)
    column = SimpleNamespace(
        left=40, right=390,
        lines=lines, entry_modes=[entry_mode], body_mode=body_mode,
    )
    layout = SimpleNamespace(
        indent_type="body" if body_indent else "headword",
        ordinary_line_height=29.0, body_top=0,
        columns=[column], transform=_Identity(),
    )
    settings = AppSettings(ocr_language="chi_sim")
    return image, settings, layout, lines


def test_suppresses_repeated_real_body_starts_inside_entry_cluster():
    image, settings, layout, lines = _test_page(polluted=8)
    stats = suppress_contradictory_cjk_body_lane_entries(
        image, settings, layout,
    )
    assert stats == {
        "checked_columns": 1, "repaired_columns": 1, "demoted_rows": 8,
        "repaired_indices": [0],
    }
    assert all(line.role == "body" for line in lines[:8])
    assert all(line.role == "entry" for line in lines[8:23])


def test_does_not_rewrite_a_column_for_one_ambiguous_start():
    image, settings, layout, lines = _test_page(polluted=1)
    stats = suppress_contradictory_cjk_body_lane_entries(
        image, settings, layout,
    )
    assert stats["demoted_rows"] == 0
    assert all(line.role == "entry" for line in lines[:23])


def test_no_change_to_other_indent_semantics_or_non_cjk():
    image, settings, layout, lines = _test_page(polluted=9, body_indent=False)
    assert suppress_contradictory_cjk_body_lane_entries(
        image, settings, layout,
    )["demoted_rows"] == 0
    layout.indent_type = "body"
    latin = AppSettings(ocr_language="eng", paddle_language="en")
    assert suppress_contradictory_cjk_body_lane_entries(
        image, latin, layout,
    )["demoted_rows"] == 0
    assert all(line.role == "entry" for line in lines[:23])
