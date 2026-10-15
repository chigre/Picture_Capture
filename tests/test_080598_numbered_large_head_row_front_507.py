"""Page 080598 oversized-head regression from user-provided diagnostic JSON.

Only geometry/physical-row measurements are stored here: no scan pixels, OCR
transcription or private PDIC contents enter the repository.  This verifies
the row-front authorization and role-fusion contract, not a full pixel rerun.
"""
from types import SimpleNamespace

import pytest

from picture_capture.models import Entry
from picture_capture.ordinary_evidence_fusion import promote_evidence_to_layout_roles
from picture_capture.ordinary_large_head_role_guard import (
    strict_candidate_starts_at_row_front,
)


class _IdentityTransform:
    def source_to_canonical_point(self, x, y, _source_size):
        return x, y

    def canonical_to_source_point(self, x, y, _source_size):
        return x, y


# Column left, glyph source box, actual physical rows: (y0, y1, first_x, role).
# Rejected strong heads are associated spatially, NOT assigned an OCR identity.
PAGE_080598 = [
    (96, (144, 832, 280, 959), [
        (828, 862, -12, "body"), (862, 895, -11, "body"),
        (895, 929, 54, "entry"), (929, 963, 48, "entry"),
    ]),
    (1679, (1729, 1068, 1916, 1203), [
        (1069, 1104, -10, "body"), (1104, 1139, -8, "body"),
        (1139, 1174, 51, "entry"), (1174, 1209, 50, "entry"),
    ]),
    (1679, (1746, 3929, 1940, 4061), [
        (3926, 3961, 1, "body"), (3961, 3995, 1, "body"),
        (3995, 4029, 67, "entry"), (4029, 4064, 63, "entry"),
    ]),
    (1679, (1744, 4338, 1876, 4470), [
        (4334, 4369, 1, "body"), (4369, 4403, 1, "body"),
        (4403, 4438, 74, "entry"), (4438, 4473, 65, "entry"),
    ]),
]


def _case(left, box, physical):
    rows = [
        SimpleNamespace(y0=a, y1=b, first_x=x, anchor_x=None, role=role)
        for a, b, x, role in physical
    ]
    column = SimpleNamespace(left=left, right=left + 1500, lines=rows)
    layout = SimpleNamespace(
        columns=[column], ordinary_line_height=57.0, body_top=0,
        source_size=(3240, 4600), transform=_IdentityTransform(),
    )
    local_box = (box[0] - left, box[1], box[2] - left, box[3])
    return SimpleNamespace(layout=layout), column, rows, local_box


@pytest.mark.parametrize("case", PAGE_080598)
def test_numbered_display_head_authorization_and_single_marker(case):
    left, box, physical = case
    understanding, column, rows, local_box = _case(left, box, physical)
    assert strict_candidate_starts_at_row_front(column, local_box, 57.0)

    # The detector emits the semantic column X, never a guessed OCR word ID.
    evidence = Entry(
        word="", x=left, y=box[1],
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=box[3] - box[1],
        ocr_line_height_reference=57.0,
        ocr_oversized_cjk=True,
    )
    assert promote_evidence_to_layout_roles(understanding, [evidence]) == 1
    assert [row.role for row in rows] == ["entry", "body", "body", "body"]


def test_same_size_second_character_without_continuation_alignment_stays_rejected():
    left, box, physical = PAGE_080598[1]
    understanding, col, rows, local = _case(left, box, physical)
    for row in rows[2:]:
        row.first_x = -8  # a normal body paragraph, not parts of one large glyph
    assert not strict_candidate_starts_at_row_front(col, local, 57.0)


def test_prefix_exception_is_not_blanket_width_or_offset_relaxation():
    left, box, physical = PAGE_080598[1]
    _understanding, col, _rows, local = _case(left, box, physical)
    assert not strict_candidate_starts_at_row_front(
        col, (local[0] + 90, local[1], local[2] + 90, local[3]), 57.0,
    )
    assert not strict_candidate_starts_at_row_front(
        col, (local[0], local[1], local[0] + 215, local[3]), 57.0,
    )


def test_prefix_candidate_requires_a_row_at_its_actual_top():
    left, box, physical = PAGE_080598[1]
    _understanding, col, _rows, local = _case(left, box, physical)
    assert not strict_candidate_starts_at_row_front(
        col, (local[0], local[1] + 28, local[2], local[3] + 28), 57.0,
    )
