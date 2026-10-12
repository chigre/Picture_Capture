"""Regression from user-supplied 2606.json (4000x5760, CJK visual 3 columns).

These are real *measured* candidate/row coordinates from the diagnostic
snapshot, not arbitrary threshold examples. Source scan pixels were not
provided: the test freezes its existing detector geometry and the fusion
contract, and never claims end-to-end image accuracy.
"""
from __future__ import annotations

from types import SimpleNamespace

from picture_capture.models import Entry
from picture_capture.ordinary_large_head_role_guard import (
    strict_candidate_starts_at_row_front,
)
from picture_capture.ordinary_evidence_fusion import promote_evidence_to_layout_roles
from picture_capture.ordinary_unified_diagnostics import (
    compose_ordinary_evidence_report,
)


class _IdentityTransform:
    def source_to_canonical_point(self, x, y, _size):
        return x, y

    def canonical_to_source_point(self, x, y, _size):
        return x, y


def _physical(y0, y1, first_x, role="body", *, anchor_x=None):
    return SimpleNamespace(
        y0=y0, y1=y1, first_x=first_x, role=role, anchor_x=anchor_x,
    )


def test_2606_h018_large_square_head_passes_but_h019_off_front_does_not():
    # Exact 2606.json numbers: body_top=230, col2.left=1386, line_h=67.
    row1 = _physical(1475 - 230, 1553 - 230, 42)
    row2 = _physical(1553 - 230, 1631 - 230, 36)
    column = SimpleNamespace(left=1386, right=2596, lines=[row1, row2])

    # H018: x1422..1592, y1480..1631, 170x151 vs reference=67.
    assert strict_candidate_starts_at_row_front(
        column,
        (1422-1386, 1480-230, 1592-1386, 1631-230),
        67.0,
    )
    # The JSON does not store anchor_x. A displaced phonetic/definition
    # anchor must not eclipse the measured true first ink of this 2x glyph.
    row1.anchor_x = 110
    assert strict_candidate_starts_at_row_front(
        column,
        (1422-1386, 1480-230, 1592-1386, 1631-230),
        67.0,
    )

    # H019: x1706..1811 on same physical line, but *not* a second headword.
    assert not strict_candidate_starts_at_row_front(
        column,
        (1706-1386, 1488-230, 1811-1386, 1627-230),
        67.0,
    )


def test_widened_square_exception_does_not_reauthorize_definition_or_wide_run():
    row = _physical(100, 178, 42)
    col = SimpleNamespace(lines=[row])
    # The same 170x151 glyph deep in body text cannot create a new line.
    assert not strict_candidate_starts_at_row_front(
        col, (320, 105, 490, 256), 67.0,
    )
    # A 215x151 region spanning multiple printed body characters is too wide.
    assert not strict_candidate_starts_at_row_front(
        col, (40, 105, 255, 256), 67.0,
    )
    # A weak 1.30x broad shape must not bypass the strict body veto.
    assert not strict_candidate_starts_at_row_front(
        col, (40, 105, 210, 192), 67.0,
    )
    # An asymmetric 170x110 rectangle is not a nearly-square 2x head.
    assert not strict_candidate_starts_at_row_front(
        col, (40, 105, 210, 215), 67.0,
    )


def test_2606_one_oversized_head_spans_two_physical_rows_but_creates_one_entry():
    first = _physical(1475-230, 1553-230, 42)
    second = _physical(1553-230, 1631-230, 36, role="entry")
    third = _physical(1678-230, 1751-230, 15)
    col = SimpleNamespace(left=1386, right=2596, lines=[first, second, third])
    layout = SimpleNamespace(
        ordinary_line_height=67.0, body_top=230,
        source_size=(4000, 5760), transform=_IdentityTransform(),
        columns=[col],
    )
    accepted = Entry(
        "", x=1386, y=1480,
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=151,
        ocr_line_height_reference=67,
        ocr_leading_height_ratio=151/67,
        ocr_single_cjk=True, ocr_oversized_cjk=True,
    )
    assert promote_evidence_to_layout_roles(
        SimpleNamespace(layout=layout), [accepted],
    ) == 1
    assert (first.role, second.role, third.role) == ("entry", "body", "body")


def _row(id, col, left, y, role):
    return {
        "id": id, "column": col,
        "canonical_y0": y, "canonical_y1": y+78,
        "source_x": left, "source_y": y,
        "role": role, "entry_source": "large_head" if role == "entry" else "indent",
        "first_x": 42.0, "corrected_first_x": 41.4,
    }


def _glyph(col, box, status="accepted", detector=True):
    return {
        "column": col, "canonical_box": box, "source_box": box,
        "status": status, "height_ratio": (box[3]-box[1])/67.,
        "detector_output": detector,
    }


def _line(x, y):
    return {
        "x": x, "y": y,
        "source": "page_understanding:ordinary_layout_role",
        "oversized": True,
    }


def _2606_diagnostic_subset():
    # Accepted H018 after width fix, H019 remains rejected.
    # U0013/U0014/U0015 in the OLD JSON were not genuine missing lines:
    # source glyph x1424/2768/2776, but final separator is x1386/2736.
    rows = [
        _row("C02-R013", 1, 1386, 1475, "entry"),
        _row("C02-R014", 1, 1386, 1553, "body"),
        _row("C02-R047", 1, 1386, 4942, "entry"),
        _row("C03-R006", 2, 2736, 770, "entry"),
        _row("C03-R009", 2, 2736, 1075, "entry"),
    ]
    glyphs = [
        _glyph(1, (1422, 1480, 1592, 1631)),
        _glyph(1, (1706, 1488, 1811, 1627), "rejected_row_front", False),
        _glyph(1, (1424, 4942, 1592, 5100)),
        _glyph(2, (2768, 770, 2933, 936)),
        _glyph(2, (2776, 1075, 2930, 1238)),
    ]
    final = [
        _line(1386, 1475), _line(1386, 4942),
        _line(2736, 770), _line(2736, 1075),
    ]
    return compose_ordinary_evidence_report(
        {
            "ordinary_line_height": 67.,
            "physical_rows": rows,
            "columns": [
                {"left": 36}, {"left": 1386}, {"left": 2736},
            ],
        },
        glyphs,
        [{"stage": "final_reading_order", "entries": final}],
        [], final,
    )


def test_2606_accepted_glyphs_share_same_row_id_as_final_line():
    report = _2606_diagnostic_subset()
    indexed = {item["id"]: item for item in report["registry"]}
    assert not any(item["id"].startswith("U") for item in report["registry"])
    for key in ("C02-R013", "C02-R047", "C03-R006", "C03-R009"):
        candidate = indexed[key]
        assert candidate["final_entries"], key
        assert any(e["type"] == "verified_large_head"
                   for e in candidate["evidence"]), key
        assert "accepted_large_head_without_final_line" not in candidate["issues"]
        assert candidate["detector_matches"][0]["association"] == (
            "same_column_canonical_row_start_proximity"
        )
    assert len(indexed["C02-R013"]["final_entries"]) == 1
    assert [glyph["status"] for glyph in indexed["C02-R013"]["detector_matches"]] == [
        "accepted", "rejected_row_front",
    ]


def test_glyph_is_not_associated_across_columns_or_with_a_distant_row():
    # A visually similar glyph at the same Y but in another column is not
    # incorrectly given that column's final line.
    report = compose_ordinary_evidence_report(
        {
            "ordinary_line_height": 67.,
            "physical_rows": [_row("C02-R013", 1, 1386, 1475, "body")],
            "columns": [{"left": 36}, {"left": 1386}, {"left": 2736}],
        },
        [_glyph(2, (2768, 1480, 2933, 1631))],
        [], [], [],
    )
    row = next(item for item in report["registry"] if item["id"] == "C02-R013")
    assert not row["detector_matches"]
    orphan = next(item for item in report["registry"] if item["id"].startswith("U"))
    assert orphan["detector_matches"][0]["status"] == "accepted"
    assert "accepted_large_head_without_final_line" in orphan["issues"]
