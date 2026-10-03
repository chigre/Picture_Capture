from types import SimpleNamespace

import numpy as np

from picture_capture.models import Entry
from picture_capture.ordinary_evidence_fusion import promote_evidence_to_layout_roles
from picture_capture.ordinary_large_head_evidence import _candidate_boxes


class _IdentityTransform:
    def source_to_canonical_point(self, x, y, _source_size):
        return x, y

    def canonical_to_source_point(self, x, y, _source_size):
        return x, y


def _line(y0, y1, role="body"):
    return SimpleNamespace(y0=y0, y1=y1, first_x=2, role=role)


def test_two_stacked_large_heads_split_after_fragment_grouping():
    line_height = 40.0
    ink = np.zeros((170, 90), dtype=bool)
    # Two individually valid 1.5-line-height display glyphs. Their 8 px gap is
    # deliberately small enough that _fragment_neighbors() groups them first.
    ink[10:70, 10:60] = True
    ink[78:138, 10:60] = True

    boxes = _candidate_boxes(ink, line_height)

    assert len(boxes) == 2
    boxes = sorted(boxes, key=lambda box: box[1])
    assert boxes[0][1] == 10
    assert boxes[0][3] == 70
    assert boxes[1][1] == 78
    assert boxes[1][3] == 138


def test_one_tall_head_with_small_internal_gap_is_not_split():
    line_height = 40.0
    ink = np.zeros((150, 90), dtype=bool)
    # Two short disconnected pieces belong to one tall glyph. Each half is too
    # short to be an independently valid oversized head, so the grouped object
    # must remain one evidence region.
    ink[10:58, 10:60] = True
    ink[62:110, 10:60] = True

    boxes = _candidate_boxes(ink, line_height)

    assert len(boxes) == 1
    assert boxes[0][1] == 10
    assert boxes[0][3] == 110


def test_two_large_head_evidence_regions_assign_entry_body_per_head():
    first_head_top = _line(100, 132, "body")
    first_head_continuation = _line(140, 172, "entry")
    second_head_top = _line(180, 212, "body")
    second_head_continuation = _line(220, 252, "entry")
    after = _line(270, 302, "entry")
    column = SimpleNamespace(
        left=10,
        right=310,
        lines=[
            first_head_top,
            first_head_continuation,
            second_head_top,
            second_head_continuation,
            after,
        ],
    )
    layout = SimpleNamespace(
        ordinary_line_height=40,
        body_top=0,
        source_size=(400, 400),
        transform=_IdentityTransform(),
        columns=[column],
    )
    understanding = SimpleNamespace(layout=layout)
    evidence = [
        Entry(
            word="",
            x=10,
            y=100,
            ocr_source="ordinary_large_head_evidence",
            issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
            ocr_visual_run_height=70,
            ocr_line_height_reference=40,
            ocr_single_cjk=True,
            ocr_oversized_cjk=True,
        ),
        Entry(
            word="",
            x=10,
            y=180,
            ocr_source="ordinary_large_head_evidence",
            issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
            ocr_visual_run_height=70,
            ocr_line_height_reference=40,
            ocr_single_cjk=True,
            ocr_oversized_cjk=True,
        ),
    ]

    promoted = promote_evidence_to_layout_roles(understanding, evidence)

    assert promoted == 2
    assert first_head_top.role == "entry"
    assert first_head_continuation.role == "body"
    assert second_head_top.role == "entry"
    assert second_head_continuation.role == "body"
    assert after.role == "entry"
