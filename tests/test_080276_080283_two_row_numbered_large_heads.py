"""User-confirmed 080276/080283 oversized-head false-negative regression.

Only four measured large-glyph rectangles and neighboring physical row
geometry are checked in. The uploaded original image pixels, manuscript text,
private PDIC contents and exported training ZIP are NOT checked in.

The original algorithm rejected these 2.207-2.298x glyphs because it switched
from one to two required aligned continuation rows at 2.20x, even though each
printed head spans exactly two segmentation rows. The lower half was then
mistaken for a new entry. Correct anchors were verified against user-edited
final PDIC and actual capture baseline.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.models import Entry
from picture_capture.ordinary_evidence_fusion import promote_evidence_to_layout_roles
from picture_capture.ordinary_large_head_role_guard import (
    strict_candidate_starts_at_row_front,
)


class _Identity:
    def source_to_canonical_point(self, x, y, _size):
        return x, y

    def canonical_to_source_point(self, x, y, _size):
        return x, y


# (page, column left, box in source image, ordinary line height,
#  first physical row [top,bottom,first ink], continuation row,
#  previously wrong marker Y, user-confirmed marker Y)
EXAMPLES = (
    ("080276", 1672, (1743, 2635, 1869, 2764), 58.0,
     (2630, 2697, 3.0), (2697, 2764, 73.0), 2690, 2624),
    ("080276", 1672, (1741, 2798, 1869, 2926), 58.0,
     (2793, 2858, 4.0), (2858, 2933, 71.0), 2859, 2788),
    ("080283", 1672, (1731, 761, 1867, 888), 57.0,
     (755, 824, -3.0), (824, 893, 59.0), 828, 750),
    ("080283", 1672, (1731, 1086, 1866, 1217), 57.0,
     (1085, 1155, -3.0), (1155, 1224, 59.0), 1149, 1079),
)


def _case(case):
    page, left, box, reference, first, second, old_y, final_y = case
    rows = [
        SimpleNamespace(
            y0=top, y1=bottom, first_x=x, anchor_x=None, role=role,
        )
        for (top, bottom, x), role in (
            (first, "body"), (second, "entry"),
        )
    ]
    column = SimpleNamespace(left=left, right=left+1486, lines=rows)
    layout = SimpleNamespace(
        columns=[column], ordinary_line_height=reference,
        body_top=0, source_size=(3240, 4600), transform=_Identity(),
    )
    local_box = (box[0]-left, box[1], box[2]-left, box[3])
    return page, column, layout, rows, local_box, reference, old_y, final_y


@pytest.mark.parametrize("sample", EXAMPLES, ids=[
    "080276-head-at-2635", "080276-head-at-2798",
    "080283-head-at-761", "080283-head-at-1086",
])
def test_numbered_two_row_display_glyph_is_promoted_on_first_row_not_second(sample):
    page, column, layout, rows, local, ref, old_y, confirmed_y = _case(sample)
    assert 2.20 < (local[3]-local[1])/ref < 2.35
    assert rows[0].role == "body" and rows[1].role == "entry"
    assert strict_candidate_starts_at_row_front(column, local, ref), (page, local)

    evidence = Entry(
        "", x=column.left, y=rows[0].y0,
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=local[3]-local[1],
        ocr_line_height_reference=ref,
        ocr_oversized_cjk=True,
    )
    assert promote_evidence_to_layout_roles(
        SimpleNamespace(layout=layout), [evidence],
    ) == 1
    assert [row.role for row in rows] == ["entry", "body"]
    # The user's final marker is near the true top, not the lower fragment.
    assert abs(confirmed_y-rows[0].y0) <= 10
    assert old_y >= rows[1].y0-12


@pytest.mark.parametrize("sample", EXAMPLES)
def test_no_matching_continuation_cannot_authorize_a_random_large_body_shape(sample):
    _, column, _layout, rows, box, reference, *_ = _case(sample)
    # Retain the prefix, physical row and shape, but erase the only aligned
    # continuation proof. This must NOT use the relaxed height alone.
    rows[1].first_x = -4.0
    assert not strict_candidate_starts_at_row_front(column, box, reference)


def test_one_continuation_not_enough_for_genuinely_three_row_display_height():
    _page, column, _layout, _rows, box, reference, *_ = _case(EXAMPLES[0])
    taller = (box[0], box[1], box[2], box[1] + round(2.50 * reference))
    assert not strict_candidate_starts_at_row_front(column, taller, reference)
