"""Geometry-only regression from user-reported page 080127 (no page image).

The first numbered display head is genuine although its glyph ink begins
17 px below the physical row start and it has only one continuation row.
The second head was admitted already, but was anchored to its SECOND row.
Both must own their first row before normal boundary placement.
"""
from types import SimpleNamespace

from PIL import Image

from picture_capture import ordinary_large_head_evidence as detector
from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_evidence_fusion import promote_evidence_to_layout_roles
from picture_capture.ordinary_large_head_role_guard import (
    _nearest_row,
    strict_candidate_starts_at_row_front,
)


class _IdentityTransform:
    def canonical_image_for_analysis(self, image):
        return image.copy()

    def canonical_to_source_point(self, x, y, _source_size):
        return x, y

    def source_to_canonical_point(self, x, y, _source_size):
        return x, y

    def canonical_box_to_source(self, box, _source_size):
        return box


def _row(y0, y1, first_x, role):
    return SimpleNamespace(
        y0=y0, y1=y1, first_x=first_x, role=role, anchor_x=None,
    )


def _layout(rows, *, left=1672, height=4600):
    column = SimpleNamespace(left=left, right=left + 1486, lines=rows)
    layout = SimpleNamespace(
        columns=[column], source_size=(3240, height),
        transform=_IdentityTransform(), ordinary_line_height=58.0,
        body_top=0, body_bottom=height,
    )
    return SimpleNamespace(layout=layout), column


def _promote(understanding, glyph_top, glyph_height, row_top):
    evidence = Entry(
        word="", x=1672, y=row_top,
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=glyph_height,
        ocr_line_height_reference=58.0,
        ocr_oversized_cjk=True,
    )
    return promote_evidence_to_layout_roles(understanding, [evidence])


def test_page_080127_first_numbered_head_uses_early_body_row():
    first = _row(828, 885, 7.0, "body")
    continuation = _row(885, 966, 68.0, "entry")
    following = _row(991, 1049, 7.0, "body")
    understanding, column = _layout([first, continuation, following])
    # OCR-free physical ink evidence: box at x=1740..1875, y=845..963.
    local = (68, 845, 203, 963)
    assert strict_candidate_starts_at_row_front(column, local, 58.0)
    assert _nearest_row(column, local, 58.0) is first

    assert _promote(understanding, 845, 118, 828) == 1
    assert [r.role for r in column.lines] == ["entry", "body", "body"]


def test_page_080127_second_head_also_anchors_to_first_row():
    first = _row(2216, 2273, 66.0, "entry")
    continuation = _row(2273, 2355, 65.0, "body")
    following = _row(2379, 2436, 103.0, "entry")
    understanding, column = _layout([first, continuation, following])
    local = (65, 2240, 200, 2352)
    assert strict_candidate_starts_at_row_front(column, local, 58.0)
    assert _nearest_row(column, local, 58.0) is first

    assert _promote(understanding, 2240, 112, 2216) == 0
    assert [r.role for r in column.lines] == ["entry", "body", "entry"]


def test_compact_prefix_exception_needs_a_real_aligned_continuation():
    first = _row(828, 885, 7.0, "body")
    following = _row(885, 966, 7.0, "body")
    _understanding, column = _layout([first, following])
    # Second character in ordinary prose must not be promoted by size alone.
    assert not strict_candidate_starts_at_row_front(
        column, (68, 845, 203, 963), 58.0,
    )
    # One full row late cannot impersonate the initial physical row.
    following.first_x = 68.0
    assert not strict_candidate_starts_at_row_front(
        column, (68, 856, 203, 974), 58.0,
    )


def test_detector_emits_printed_row_start_not_glyph_ink_top(monkeypatch):
    first = _row(128, 185, 7.0, "body")
    continuation = _row(185, 266, 68.0, "entry")
    following = _row(291, 350, 7.0, "body")
    column = SimpleNamespace(left=100, right=350, lines=[
        first, continuation, following,
    ])
    layout = SimpleNamespace(
        columns=[column], source_size=(550, 400),
        transform=_IdentityTransform(), ordinary_line_height=58.0,
        body_top=0, body_bottom=400,
    )
    understanding = SimpleNamespace(layout=layout)
    monkeypatch.setattr(
        detector, "_candidate_boxes",
        lambda ink, line_height, diagnostics=None: [(68, 145, 203, 263)],
    )
    monkeypatch.setattr(
        "picture_capture.layout_column_drift._analysis_left_for_column",
        lambda columns, position, reference: 100,
    )
    settings = AppSettings(
        dictionary_profile_id="cjk_visual",
        ocr_language="chi_tra",
        profile_cjk_allow_single_headword=True,
    )
    with Image.new("RGB", (550, 400), "white") as image:
        entries = detector.detect_ordinary_large_head_entries(
            image, understanding, settings,
        )
    assert [(e.x, e.y) for e in entries] == [(100, 128)]
