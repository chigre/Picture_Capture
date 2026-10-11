"""Physical oversized head recovery after a confirmed role anomaly.

Synthesizes separate giant CJK lead glyphs, ordinary 29px rows and a
stray second 'entry' row inside each large glyph. No real dictionary scan
is committed to this public repository.
"""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.layout_verified_oversized_heads import (
    recover_verified_oversized_heads,
)


class _Identity:
    def canonical_image_for_analysis(self, img):
        return img.copy()

    def canonical_to_source_point(self, x, y, _size):
        return int(x), int(y)


def _fixture(number=3):
    image = Image.new("RGB", (410, 850), "white")
    draw = ImageDraw.Draw(image)
    rows = [
        SimpleNamespace(y0=100, y1=129, role="entry"),
        SimpleNamespace(y0=141, y1=170, role="entry"),
        SimpleNamespace(y0=300, y1=329, role="body"),
        SimpleNamespace(y0=350, y1=379, role="entry"),
        SimpleNamespace(y0=700, y1=729, role="entry"),
    ]
    for y in (100, 300, 500)[:number]:
        draw.rectangle((40, y, 108, y + 71), fill="black")
    layout = SimpleNamespace(
        transform=_Identity(),
        source_size=image.size,
        body_top=0, body_bottom=image.height,
        ordinary_line_height=29.0,
        columns=[SimpleNamespace(left=40, right=390, lines=rows)],
    )
    # Preserve row identities even if the production code sorts column.lines.
    return image, layout, list(rows)


def test_detects_tall_glyphs_and_keeps_only_their_top_entry_rows():
    image, layout, old_rows = _fixture()
    stats = recover_verified_oversized_heads(image, layout, [0])
    assert stats == {
        "verified_glyphs": 3, "promoted_heads": 2,
        "demoted_fragments": 2,
    }
    assert old_rows[0].role == "entry"
    assert old_rows[1].role == "body"
    assert old_rows[2].role == "entry"
    assert old_rows[3].role == "body"
    assert old_rows[4].role == "entry"
    assert any(
        row.role == "entry" and abs(row.y0 - 500) <= 8
        for row in layout.columns[0].lines
    )


def test_never_changes_columns_without_anomaly_confirmation():
    image, layout, rows = _fixture()
    original = [row.role for row in rows]
    assert recover_verified_oversized_heads(image, layout, []) == {
        "verified_glyphs": 0, "promoted_heads": 0,
        "demoted_fragments": 0,
    }
    assert [row.role for row in rows] == original


def test_one_oversized_fragment_is_not_enough_to_rewrite_layout():
    image, layout, rows = _fixture(number=1)
    stats = recover_verified_oversized_heads(image, layout, [0])
    assert stats["verified_glyphs"] == 0
    assert [row.role for row in rows] == [
        "entry", "entry", "body", "entry", "entry",
    ]
