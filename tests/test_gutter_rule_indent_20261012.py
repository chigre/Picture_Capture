"""A slightly slanted gutter line must not become the right column's body indent.

Real XDHYCD and Spanish scans have dividers around source X≈692 and X≈1275.
The historical unclipped-first-X safety margin included those vertical strokes,
and physical first_x collapsed to -20 / -36 rather than actual printed heads.
"""
from types import SimpleNamespace

import numpy as np

from picture_capture import dictionary_page_design as base
from picture_capture.layout_column_drift import (
    _gutter_divider_right_edge, remeasure_layout_indents_from_ink,
)
from picture_capture.layout_physical_indent import (
    physical_indent_modes, assign_binary_roles,
)


def _ruled_page(*, remove_rule: bool = False):
    height, width, left = 1000, 850, 430
    ink = np.zeros((height, width), dtype=bool)
    first_column = base.ColumnDesign(0, 30, 410, 20)
    second_column = base.ColumnDesign(1, left, 825, 0)
    for n in range(25):
        y = 30 + n * 36
        entry = n % 2 == 0
        start = left + (2 if entry else 31)
        # Printed glyph ink occupies only part of its line box. Solid 20px
        # blocks in every row would create fake vertical rules at each X.
        ink[y:y + 10, 40:110] = True  # genuine first-column text
        ink[y:y + 10, start:start + 70] = True
        line = base.LayoutLine(
            1, y, y + 20, -13, None, 0, 0, 0,
            np.zeros((0, 0), dtype=bool),
        )
        second_column.lines.append(line)
    if not remove_rule:
        for y in range(10, 980):
            # A diagonal vertical separator, moving 4 px along the page.
            x = 416 + int(4 * y / 1000)
            ink[y, x:x + 2] = True
    layout = SimpleNamespace(
        columns=[first_column, second_column],
        body_top=0, body_bottom=1000,
        ordinary_line_height=20., indent_type="body",
    )
    ops = base.LayoutPrimitiveOps(
        line_runs=lambda *_: [],
        line_feature=lambda *_: None,
        indent_modes=physical_indent_modes,
        assign_indent_semantics=assign_binary_roles,
    )
    return ink, layout, ops


def test_slanted_gutter_rule_detects_track_even_without_fixed_x_persistence():
    mask, _layout, _ops = _ruled_page()
    border = _gutter_divider_right_edge(
        mask, body_top=0, body_bottom=1000,
        corridor_left=411, corridor_right=427, reference=20.,
    )
    assert border is not None
    assert 420 <= border <= 424


def test_right_column_indents_survive_gutter_rule():
    mask, layout, ops = _ruled_page()
    positions = {}
    counts = remeasure_layout_indents_from_ink(
        layout, mask, ops=ops, divider_positions=positions,
    )
    assert counts[1] == 25
    assert 1 in positions
    measured = [row.first_x for row in layout.columns[1].lines]
    assert min(measured) >= 0  # nothing at divider X≈417 becomes X=-13
    assert all(abs(measured[i] - (2 if i % 2 == 0 else 31)) <= 1
               for i in range(25))
    assert len(layout.columns[1].indent_modes) >= 2
    # The print sample deliberately has MORE true heads than body starts.
    # Final semantics must select the rightmost *body* family by direction,
    # not the most populous physical indent family.
    from picture_capture.layout_core_understanding import _resolve_directional_body_lanes
    _resolve_directional_body_lanes(layout)
    assert sum(m.support for m in layout.columns[1].entry_modes) >= 12


def test_unruled_page_keeps_original_overhang_analysis():
    mask, layout, ops = _ruled_page(remove_rule=True)
    positions = {}
    counts = remeasure_layout_indents_from_ink(
        layout, mask, ops=ops, divider_positions=positions,
    )
    assert counts[1] == 25
    assert positions == {}
    assert len(layout.columns[1].indent_modes) >= 2


def test_short_text_marks_do_not_masquerade_as_slanted_rule():
    mask = np.zeros((800, 700), dtype=bool)
    for y in range(80, 750, 75):
        mask[y:y + 13, 340:344] = True
    assert _gutter_divider_right_edge(
        mask, body_top=0, body_bottom=800,
        corridor_left=320, corridor_right=370, reference=25.,
    ) is None


def test_column_geometry_ignores_slanted_gutter_divider_as_first_text():
    from picture_capture.dictionary_page_design import _refine_column_geometry

    mask, _layout, _ops = _ruled_page()
    starts, rights, gutters = _refine_column_geometry(
        mask, 10, 970, [30, 430], [410, 825], 20.,
    )
    assert starts[1] >= 429
    assert starts[1] < 440
    assert rights[0] < starts[1]
    assert len(gutters) == 2
