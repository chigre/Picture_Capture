from types import SimpleNamespace

from picture_capture.entry_classification import get_layout_line_classification
from picture_capture.models import Entry
from picture_capture.ordinary_evidence_fusion import promote_evidence_to_layout_roles


class _IdentityTransform:
    def source_to_canonical_point(self, x, y, _source_size):
        return x, y

    def canonical_to_source_point(self, x, y, _source_size):
        return x, y


def _line(y0, y1, first_x, role):
    return SimpleNamespace(y0=y0, y1=y1, first_x=first_x, role=role)


def test_oversized_head_forces_first_row_entry_even_with_tiny_indent():
    first = _line(100, 132, 2, "body")
    second = _line(138, 170, 28, "entry")
    third = _line(176, 208, 30, "entry")
    next_real_entry = _line(220, 252, 3, "entry")
    column = SimpleNamespace(left=10, right=310, lines=[
        first, second, third, next_real_entry,
    ])
    layout = SimpleNamespace(
        ordinary_line_height=40,
        body_top=0,
        source_size=(400, 400),
        transform=_IdentityTransform(),
        columns=[column],
    )
    understanding = SimpleNamespace(layout=layout)
    evidence = Entry(
        word="",
        x=10,
        y=102,
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=100,
        ocr_line_height_reference=40,
        ocr_leading_height_ratio=2.5,
        ocr_single_cjk=True,
        ocr_oversized_cjk=True,
    )

    promoted = promote_evidence_to_layout_roles(understanding, [evidence])

    assert promoted == 1
    assert first.role == "entry"
    assert second.role == "body"
    assert third.role == "body"
    assert next_real_entry.role == "entry"
    meta = get_layout_line_classification(first)
    assert meta.entry_source == "large_head"
    assert meta.entry_scale == "oversized"
    assert meta.detected_head_height == 100


def test_regular_evidence_keeps_nearest_row_promotion_semantics():
    first = _line(100, 132, 2, "body")
    second = _line(140, 172, 20, "body")
    column = SimpleNamespace(left=10, right=310, lines=[first, second])
    layout = SimpleNamespace(
        ordinary_line_height=40,
        body_top=0,
        source_size=(400, 400),
        transform=_IdentityTransform(),
        columns=[column],
    )
    understanding = SimpleNamespace(layout=layout)
    evidence = Entry(
        word="",
        x=10,
        y=142,
        ocr_source="ordinary_symbol_evidence",
        issue_type="VISUAL_ENTRY_MARKER_SAMPLE",
    )

    promoted = promote_evidence_to_layout_roles(understanding, [evidence])

    assert promoted == 1
    assert first.role == "body"
    assert second.role == "entry"
