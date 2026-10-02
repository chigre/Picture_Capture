from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_core_understanding import (
    _suppress_large_evidence_duplicate_entries,
)
from picture_capture.models import Entry


class _IdentityTransform:
    def source_to_canonical_point(self, x, y, source_size):
        return int(x), int(y)


def _line(y0: int, y1: int, role: str = "entry"):
    return SimpleNamespace(y0=y0, y1=y1, role=role)


def test_three_logical_entry_rows_inside_one_oversized_head_collapse_to_top_marker():
    lines = [
        _line(100, 120),
        _line(125, 145),
        _line(150, 170),
        _line(200, 220),  # next physical entry, outside the large glyph
    ]
    column = SimpleNamespace(left=40, right=180, lines=lines)
    layout = SimpleNamespace(
        columns=[column],
        body_top=100,
        ordinary_line_height=25.0,
        source_size=(500, 800),
        transform=_IdentityTransform(),
    )
    evidence = Entry(
        word="",
        x=40,
        y=200,  # canonical row-relative top = 100
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=75.0,
        ocr_oversized_cjk=True,
    )

    removed = _suppress_large_evidence_duplicate_entries(layout, [evidence])

    assert removed == 2
    assert [line.role for line in lines] == ["entry", "body", "body", "entry"]


def test_two_row_display_head_collapses_without_touching_row_at_glyph_bottom():
    lines = [
        _line(50, 70),
        _line(75, 95),
        _line(100, 120),  # starts exactly at glyph bottom; must survive
    ]
    column = SimpleNamespace(left=20, right=160, lines=lines)
    layout = SimpleNamespace(
        columns=[column],
        body_top=0,
        ordinary_line_height=25.0,
        source_size=(400, 600),
        transform=_IdentityTransform(),
    )
    evidence = Entry(
        word="",
        x=20,
        y=50,
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=50.0,
        ocr_oversized_cjk=True,
    )

    removed = _suppress_large_evidence_duplicate_entries(layout, [evidence])

    assert removed == 1
    assert [line.role for line in lines] == ["entry", "body", "entry"]


def test_non_oversized_evidence_does_not_widen_generic_y_deduplication():
    lines = [_line(50, 70), _line(75, 95)]
    column = SimpleNamespace(left=20, right=160, lines=lines)
    layout = SimpleNamespace(
        columns=[column],
        body_top=0,
        ordinary_line_height=25.0,
        source_size=(400, 600),
        transform=_IdentityTransform(),
    )
    evidence = Entry(
        word="",
        x=20,
        y=50,
        ocr_visual_run_height=20.0,
        ocr_oversized_cjk=False,
    )

    removed = _suppress_large_evidence_duplicate_entries(layout, [evidence])

    assert removed == 0
    assert [line.role for line in lines] == ["entry", "entry"]
