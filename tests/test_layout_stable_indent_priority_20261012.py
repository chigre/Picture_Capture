"""Stable physical indentation is primary evidence for CJK ordinary entries.

Protect XDHYCD-style outer-lane word starts while correcting individual rows
whose *actual* first ink disagrees with a contaminated mode. No page-specific
coordinates, sample words, OCR, or saved user PDIC data enter production.
"""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.layout_core_understanding import _resolve_directional_body_lanes
from picture_capture.layout_indent_authority import (
    reconcile_stable_indent_rows,
    stable_indent_grammar,
    stable_indent_row_ids,
)
from picture_capture.layout_role_visual_consistency import (
    suppress_contradictory_cjk_body_lane_entries,
)
from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_final_visual_consistency import (
    correct_anomalous_final_ordinary_entries,
)
from picture_capture import processing


class Identity:
    kind = "identity"

    def canonical_image_for_analysis(self, image):
        return image.copy()

    def canonical_to_source_point(self, x, y, _size):
        return int(x), int(y)


def _mode(center, rows, tolerance=3.0):
    return SimpleNamespace(
        center=float(center), lines=rows, support=len(rows),
        tolerance=float(tolerance), role="unknown",
    )


def _layout(*, reversed_polarity=False, include_mixed=True):
    columns = []
    for col_no, left in enumerate((35, 715)):
        outer = []
        inner = []
        for i in range(24):
            outer.append(SimpleNamespace(
                y0=70 + i * 78, y1=99 + i * 78,
                first_x=42 if reversed_polarity else 4,
                role="unknown",
            ))
        for i in range(18):
            inner.append(SimpleNamespace(
                y0=107 + i * 98, y1=136 + i * 98,
                first_x=4 if reversed_polarity else 42,
                role="unknown",
            ))
        bad_mode_member = None
        good_mode_member = None
        if include_mixed:
            # Membership was contaminated by projection/anchor clustering:
            # these actual first-X measurements remain independently valid.
            bad_mode_member = outer[2]
            bad_mode_member.first_x = 4 if reversed_polarity else 42
            good_mode_member = inner[4]
            good_mode_member.first_x = 42 if reversed_polarity else 4
        entries = _mode(42 if reversed_polarity else 4, outer)
        bodies = _mode(4 if reversed_polarity else 42, inner)
        column = SimpleNamespace(
            index=col_no, left=left, right=left + 630,
            lines=sorted(outer + inner, key=lambda row: row.y0),
            indent_modes=sorted([entries, bodies], key=lambda m: m.center),
            entry_modes=[], body_mode=None,
            mixed_false=bad_mode_member, mixed_real=good_mode_member,
        )
        columns.append(column)
    return SimpleNamespace(
        columns=columns, indent_type="headword" if reversed_polarity else "body",
        ordinary_line_height=30.0, body_top=30, body_bottom=2080,
        source_size=(1388, 2156), transform=Identity(), display_heads=[],
    )


def test_individual_first_ink_overrides_contaminated_indent_cluster():
    layout = _layout()
    _resolve_directional_body_lanes(layout)
    assert layout.columns[0].mixed_false.role == "entry"
    assert layout.columns[0].mixed_real.role == "body"
    stats = reconcile_stable_indent_rows(layout, cjk=True)
    assert stats == {
        "trusted_columns": 2, "entry_promoted": 2, "body_demoted": 2,
    }
    for col in layout.columns:
        assert col.mixed_false.role == "body"
        assert col.mixed_real.role == "entry"
        grammar = stable_indent_grammar(
            col, layout.indent_type, layout.ordinary_line_height,
        )
        assert grammar is not None
        assert id(col.mixed_real) in stable_indent_row_ids(col, grammar)
        assert id(col.mixed_false) not in stable_indent_row_ids(col, grammar)


def test_headword_indentation_reverses_the_lane_direction():
    layout = _layout(reversed_polarity=True)
    _resolve_directional_body_lanes(layout)
    stats = reconcile_stable_indent_rows(layout, cjk=True)
    assert stats["trusted_columns"] == 2
    assert stats["entry_promoted"] == 2
    assert stats["body_demoted"] == 2


def test_no_authority_without_repeated_independent_body_and_entry_lanes():
    layout = _layout(include_mixed=False)
    col = layout.columns[0]
    col.indent_modes[0].lines[:] = col.indent_modes[0].lines[:2]
    assert stable_indent_grammar(
        col, layout.indent_type, layout.ordinary_line_height,
    ) is None
    assert reconcile_stable_indent_rows(
        _layout(), cjk=False,
    ) == {
        "trusted_columns": 0, "entry_promoted": 0, "body_demoted": 0,
    }


def test_final_entry_carries_stable_indent_proof():
    layout = _layout()
    _resolve_directional_body_lanes(layout)
    reconcile_stable_indent_rows(layout, cjk=True)
    understanding = SimpleNamespace(
        layout=layout, page_settings=AppSettings(ocr_language="chi_sim"),
    )
    actual = processing._ordinary_entries_from_layout_roles(understanding)
    assert len(actual) >= 40
    assert all(
        "STABLE_INDENT" in entry.issue_type for entry in actual
    )


def test_last_mile_cannot_veto_proven_indent_head_when_definition_is_inset():
    layout = _layout()
    _resolve_directional_body_lanes(layout)
    reconcile_stable_indent_rows(layout, cjk=True)
    settings = AppSettings(ocr_language="chi_sim")
    understanding = SimpleNamespace(layout=layout, page_settings=settings)
    accepted = processing._ordinary_entries_from_layout_roles(understanding)
    image = Image.new("RGB", layout.source_size, "white")
    draw = ImageDraw.Draw(image)
    # At every emitted separator, the following glyph in the test bitmap
    # starts in the BODY band. This is insufficient reason to reject a
    # physically established entry row: the marker was refined in Y.
    for entry in accepted:
        draw.rectangle(
            (entry.x + 43, entry.y + 1, entry.x + 83, entry.y + 24),
            fill="black",
        )
    after, stats = correct_anomalous_final_ordinary_entries(
        image, settings, layout, accepted,
    )
    assert stats["removed_false_entries"] == 0
    assert {(e.x, e.y) for e in after} == {(e.x, e.y) for e in accepted}


def test_unproved_layout_cautions_still_can_be_filtered():
    layout = _layout(include_mixed=False)
    _resolve_directional_body_lanes(layout)
    reconcile_stable_indent_rows(layout, cjk=True)
    settings = AppSettings(ocr_language="chi_sim")
    baseline = processing._ordinary_entries_from_layout_roles(
        SimpleNamespace(layout=layout, page_settings=settings)
    )
    image = Image.new("RGB", layout.source_size, "white")
    draw = ImageDraw.Draw(image)
    fake = []
    for i in range(14):
        marker = Entry(
            "", 35, 110 + i * 110,
            ocr_source="page_understanding:ordinary_layout_role",
            issue_type="PAGE_UNDERSTANDING_ORDINARY_LAYOUT_ROLE",
        )
        fake.append(marker)
        draw.rectangle((35 + 44, marker.y + 1, 35 + 85, marker.y + 22), fill="black")
    # Existing stable entries are immune to the last-mile mass veto, but
    # genuinely unproven entry markers still receive the original check.
    after, stats = correct_anomalous_final_ordinary_entries(
        image, settings, layout, baseline + fake,
    )
    assert all(any(item is surviving for surviving in after) for item in baseline)
    assert stats["removed_false_entries"] >= 6


def test_raw_row_pixel_veto_respects_printed_stable_indent_evidence():
    layout = _layout(include_mixed=False)
    _resolve_directional_body_lanes(layout)
    reconcile_stable_indent_rows(layout, cjk=True)
    image = Image.new("RGB", layout.source_size, "white")
    draw = ImageDraw.Draw(image)
    # Deliberately disagree with earlier physical first-X measurements:
    # these simulated analysis pixels show only the following inset ink.
    # The confirmed physical entry lane must not be erased by a short crop.
    for column in layout.columns:
        for line in column.lines:
            if line.role == "entry":
                y = layout.body_top + line.y0
                draw.rectangle(
                    (column.left + 44, y, column.left + 90, y + 23),
                    fill="black",
                )
    stats = suppress_contradictory_cjk_body_lane_entries(
        image, AppSettings(ocr_language="chi_sim"), layout,
    )
    assert stats["repaired_columns"] == 0
    assert stats["demoted_rows"] == 0
    assert sum(line.role == "entry" for column in layout.columns
               for line in column.lines) == 48
