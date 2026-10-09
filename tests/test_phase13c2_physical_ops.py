"""Phase 13C2 characterization of installed and explicitly composed physical ops."""
from dataclasses import replace

import numpy as np

from picture_capture import dictionary_page_design as base
from picture_capture import layout_physical_indent as physical


def _ink():
    ink = np.zeros((80, 110), dtype=bool)
    ink[8:20, 5:12] = True
    ink[8:20, 23:33] = True
    ink[28:40, 6:13] = True
    ink[28:40, 25:34] = True
    return ink


def _snapshot(line):
    if line is None:
        return None
    return (line.y0, line.y1, line.first_x, line.anchor_x,
            line.anchor_width, line.anchor_height, line.has_small_prefix)


def test_explicit_physical_ops_match_installed_feature(monkeypatch):
    ink = _ink()
    ops = physical.explicit_physical_layout_ops()
    # The installed product chain supplies the robust wrapper as its inner op.
    # A temporary local binding enables direct legacy comparison without
    # changing installer order or production module state after this test.
    from picture_capture.layout_line_start_refinement import compose_robust_line_feature
    robust = compose_robust_line_feature(base.RAW_LAYOUT_OPS.line_feature)
    monkeypatch.setattr(physical, "_BASE_LINE_FEATURE", robust)
    assert _snapshot(ops.line_feature(0, ink, 8, 20, 14., 0)) == _snapshot(
        physical.physical_line_feature(0, ink, 8, 20, 14., 0))
    assert _snapshot(ops.line_feature(0, ink, 28, 40, 14., 20)) == _snapshot(
        physical.physical_line_feature(0, ink, 28, 40, 14., 20))


def test_explicit_physical_ops_bind_expected_primitives():
    ops = physical.explicit_physical_layout_ops()
    assert ops.line_runs is physical.projection_line_runs
    assert ops.indent_modes is physical.physical_indent_modes
    assert ops.assign_indent_semantics is physical.assign_binary_roles
    assert ops.line_feature is not physical.physical_line_feature


def test_explicit_physical_inner_none_fallback(monkeypatch):
    monkeypatch.setattr(physical, "_credible_first_ink_x", lambda *args: 4)
    fn = physical.compose_physical_line_feature(lambda *args: None)
    result = fn(0, _ink(), 8, 20, 14., 0)
    assert result.first_x == 4
    assert result.anchor_x is None
