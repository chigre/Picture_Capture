"""Collapsed C2 indentation must be fixed IN Layout before WW drawing.

These synthetic columns reproduce the observed XDHYCD and 新时代西汉 training-v3
column summaries; original copyrighted TIFF/PNG remains outside Git.
"""
from types import SimpleNamespace
import numpy as np
from PIL import Image

from picture_capture import dictionary_page_design as base
from picture_capture.models import AppSettings, Entry
from picture_capture.layout_column_indent_recovery import (
    _weak_columns, restore_proven_column_indents,
)


class Identity:
    kind = "identity"
    def source_to_canonical_point(self, x, y, size):
        return x, y
    def canonical_to_source_point(self, x, y, size):
        return x, y


def row(col, y, role="body"):
    return base.LayoutLine(
        column=col, y0=y, y1=y+18, first_x=0,
        anchor_x=0, anchor_width=18, anchor_height=18,
        gap_before=0, patch=np.zeros((0, 0), dtype=bool),
        role=role,
    )


def column(index, left, count, *, entries=0):
    lines = [row(index, 80 + 30*j, "entry" if j < entries else "body")
             for j in range(count)]
    body = base.IndentMode(0.0, 2.0, lines[entries:], role="body")
    return base.ColumnDesign(
        index=index, left=left, right=left+550, gutter_after=20,
        lines=lines, indent_modes=[body], body_mode=body,
        entry_modes=[],
    )


def layout(columns, *, height=2300, line_h=18):
    return SimpleNamespace(
        columns=columns, indent_type="body", body_top=40,
        body_bottom=height, ordinary_line_pitch=line_h,
        ordinary_line_height=float(line_h), source_size=(1400, height),
        transform=Identity(),
    )


def test_real_xdhycd_sparse_c2_is_classed_as_undersegmented_even_with_some_entries():
    # Measured saved diagnostic: C2 17 physical lines in >2,100px body area,
    # including 12 outer starts and 4 inward starts; 95 real printed rows.
    page = layout([column(0, 5, 10), column(1, 711, 17, entries=8)])
    assert _weak_columns(page, cjk=True) == [1]
    assert _weak_columns(page, cjk=False) == []


def test_cjk_brackets_rebuild_visible_indent_lanes_not_just_append_pdic(monkeypatch):
    from picture_capture import ordinary_bracket_pair

    page = layout([column(0, 5, 30, entries=8), column(1, 711, 17)])
    # Trusted independent visual bracket pair coordinates; these correspond to
    # real XDHYCD printed glyph geometry, not synthetic indentation guesses.
    monkeypatch.setattr(
        ordinary_bracket_pair, "recover_bracketed_ordinary_entries",
        lambda *_a, **_kw: [Entry("", 711, y) for y in (180, 480, 780, 1080, 1580)],
    )
    before = page.columns[1]
    stats = restore_proven_column_indents(
        Image.new("L", (1400, 2300), 255),
        AppSettings(dictionary_profile_id="cjk", ocr_language="chi_sim"),
        page,
    )
    assert stats["rescued_columns"] == 1
    assert stats["cjk_bracket_rows"] >= 5
    assert before.body_mode is not None
    assert before.entry_modes[0].role == "entry"
    assert before.body_mode.role == "body"
    assert sum(line.role == "entry" for line in before.lines) >= 5
    assert sum(mode.support for mode in before.entry_modes) >= 5
    assert page.columns[0].entry_modes == []  # unaffected column


def test_latin_spanish_genuine_independent_entry_body_family_repairs_c2(monkeypatch):
    from picture_capture import dictionary_page_design_refined

    body_page = layout([column(0, 25, 50, entries=4),
                        column(1, 1310, 55, entries=1)], height=3800, line_h=43)
    alt_rows = [row(1, 35 + j*45, role="entry") for j in range(26)]
    alt_body_lines = [row(1, 40 + j*45, role="body") for j in range(27)]
    alt_body = base.IndentMode(30, 5, alt_body_lines, role="body")
    alt_entry = base.IndentMode(0, 3, alt_rows, role="entry")
    alternate = SimpleNamespace(
        reliable=True, ordinary_line_height=40.5,
        body_top=874, source_size=(1400, 3800), transform=Identity(),
        columns=[
            SimpleNamespace(left=25, body_mode=None, entry_modes=[], lines=[]),
            SimpleNamespace(
                left=1325, body_mode=alt_body, entry_modes=[alt_entry],
                lines=alt_rows+alt_body_lines,
            ),
        ],
    )
    monkeypatch.setattr(
        dictionary_page_design_refined,
        "detect_entries_from_page_design",
        lambda *args, **kwargs: SimpleNamespace(layout=alternate),
    )
    stats = restore_proven_column_indents(
        Image.new("L", (1400, 3800), 255),
        AppSettings(dictionary_profile_id="latin", ocr_language="spa"),
        body_page, page_index=0,
    )
    assert stats["rescued_columns"] == 1
    assert stats["rescued_rows"] >= 20
    assert body_page.columns[1].entry_modes[0].support >= 20
    assert (body_page.columns[1].body_mode.center >
            body_page.columns[1].entry_modes[0].center)
    assert body_page.columns[0].entry_modes == []


def test_no_independent_evidence_must_not_invent_entries(monkeypatch):
    from picture_capture import dictionary_page_design_refined
    page = layout([column(0, 25, 25), column(1, 690, 40)])
    monkeypatch.setattr(dictionary_page_design_refined,
                        "detect_entries_from_page_design",
                        lambda *args, **kwargs: SimpleNamespace(
                            layout=SimpleNamespace(
                                reliable=False, columns=[],
                                transform=Identity(),
                            ),
                        ))
    assert restore_proven_column_indents(
        Image.new("L", (1400, 2300), 255),
        AppSettings(dictionary_profile_id="latin", ocr_language="spa"),
        page,
    )["rescued_rows"] == 0
    assert all(not col.entry_modes for col in page.columns)


def test_existing_correctly_parsed_page_skips_second_expensive_detector(monkeypatch):
    from picture_capture import dictionary_page_design_refined
    page = layout([column(0, 25, 25, entries=10),
                   column(1, 690, 28, entries=11)])
    monkeypatch.setattr(dictionary_page_design_refined,
                        "detect_entries_from_page_design",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("unneeded second layout pass")
                        ))
    stats = restore_proven_column_indents(
        Image.new("L", (1400, 2300), 255),
        AppSettings(dictionary_profile_id="latin", ocr_language="spa"), page,
    )
    assert stats["rescued_columns"] == 0
