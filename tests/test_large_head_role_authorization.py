from types import SimpleNamespace

from picture_capture.models import Entry
from picture_capture.ordinary_evidence_fusion import promote_evidence_to_layout_roles
from picture_capture.ordinary_large_head_role_guard import (
    HARD_ROLE_OVERRIDE_RATIO,
    strict_candidate_starts_at_row_front,
)


class _IdentityTransform:
    def source_to_canonical_point(self, x, y, _source_size):
        return x, y

    def canonical_to_source_point(self, x, y, _source_size):
        return x, y


def _line(y0, y1, first_x=0, role="body", anchor_x=None):
    return SimpleNamespace(
        y0=y0,
        y1=y1,
        first_x=first_x,
        role=role,
        anchor_x=anchor_x,
    )


def _understanding(lines, line_height=40):
    column = SimpleNamespace(left=10, right=310, lines=list(lines))
    layout = SimpleNamespace(
        ordinary_line_height=line_height,
        body_top=0,
        source_size=(400, 400),
        transform=_IdentityTransform(),
        columns=[column],
    )
    return SimpleNamespace(layout=layout), column


def _large_evidence(height, reference=40, y=100):
    return Entry(
        word="",
        x=10,
        y=y,
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=height,
        ocr_line_height_reference=reference,
        ocr_leading_height_ratio=height / reference,
        ocr_single_cjk=True,
        ocr_oversized_cjk=True,
    )


def test_weak_oversized_candidate_cannot_manufacture_entry():
    first = _line(100, 138, first_x=1, role="body")
    second = _line(145, 183, first_x=2, role="body")
    understanding, _column = _understanding([first, second], line_height=40)

    promoted = promote_evidence_to_layout_roles(
        understanding,
        [_large_evidence(height=60, reference=40)],  # 1.50x: suspicious, not strong
    )

    assert HARD_ROLE_OVERRIDE_RATIO > 1.50
    assert promoted == 0
    assert first.role == "body"
    assert second.role == "body"


def test_strong_oversized_candidate_can_override_body_and_collapse_continuation():
    first = _line(100, 138, first_x=1, role="body")
    second = _line(145, 183, first_x=22, role="entry")
    understanding, _column = _understanding([first, second], line_height=40)

    promoted = promote_evidence_to_layout_roles(
        understanding,
        [_large_evidence(height=70, reference=40)],  # 1.75x: strong
    )

    assert promoted == 1
    assert first.role == "entry"
    assert second.role == "body"


def test_second_or_third_body_character_is_not_row_front_large_head():
    _understanding_obj, column = _understanding([
        _line(100, 158, first_x=0, role="body", anchor_x=3),
    ], line_height=58)

    # x=65 is already about one ordinary character to the right of the actual
    # row start. The old 2.5x allowance accepted this; the strict guard must not.
    assert not strict_candidate_starts_at_row_front(
        column,
        (65, 100, 145, 205),
        58.0,
    )


def test_small_prefix_can_still_lead_into_true_large_head_anchor():
    _understanding_obj, column = _understanding([
        _line(100, 158, first_x=0, role="body", anchor_x=44),
    ], line_height=58)

    assert strict_candidate_starts_at_row_front(
        column,
        (40, 98, 125, 205),
        58.0,
    )
