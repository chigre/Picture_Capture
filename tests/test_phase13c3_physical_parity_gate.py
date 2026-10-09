"""Phase 13C final gate: explicit physical primitives reproduce the installed chain.

The temporary hook binding is isolated by monkeypatch. Production installers
remain active and no normal consumer is re-routed in Phase 13C.
"""
from __future__ import annotations

import numpy as np
import pytest

from picture_capture import dictionary_page_design as base
from picture_capture import layout_line_start_refinement as robust
from picture_capture import layout_physical_indent as physical


def _synthetic_ink() -> np.ndarray:
    ink = np.zeros((155, 120), dtype=bool)
    for index, y in enumerate((9, 31, 53, 75, 97, 119)):
        x = 4 if index in (1, 4) else 12
        ink[y:y + 12, x:x + 7] = True
        ink[y:y + 12, 28:40] = True
    return ink


def _snapshot(ops: base.LayoutPrimitiveOps, ink: np.ndarray, semantics: str):
    reference = 14.0
    runs = ops.line_runs(ink, reference)
    column = base.ColumnDesign(index=0, left=0, right=120, gutter_after=0)
    previous_end = 0
    for y0, y1 in runs:
        line = ops.line_feature(0, ink, y0, y1, reference, previous_end)
        previous_end = max(previous_end, y1)
        if line is not None:
            column.lines.append(line)
    column.indent_modes = ops.indent_modes(column.lines, reference)
    ops.assign_indent_semantics(column, semantics, reference)
    rows = [
        (line.y0, line.y1, line.first_x, line.anchor_x,
         line.has_small_prefix, line.role)
        for line in column.lines
    ]
    modes = sorted(
        (round(float(mode.center), 5), mode.support, mode.role)
        for mode in column.indent_modes
    )
    return runs, rows, modes, len(column.entry_modes), (
        round(float(column.body_mode.center), 5)
        if column.body_mode is not None else None
    )


@pytest.mark.parametrize("semantics", ["body", "headword"])
def test_explicit_physical_ops_match_legacy_installed_chain(monkeypatch, semantics):
    ink = _synthetic_ink()
    explicit = physical.explicit_physical_layout_ops()
    legacy_robust = robust.compose_robust_line_feature(base.RAW_LAYOUT_OPS.line_feature)
    monkeypatch.setattr(physical, "_BASE_LINE_FEATURE", legacy_robust)
    # Match the legacy installer assignments, without calling installers or
    # changing module globals beyond the lifetime of this test.
    monkeypatch.setattr(base, "_line_runs", physical.projection_line_runs)
    monkeypatch.setattr(base, "_line_feature", physical.physical_line_feature)
    monkeypatch.setattr(base, "_indent_modes", physical.physical_indent_modes)
    monkeypatch.setattr(base, "_assign_indent_semantics", physical.assign_binary_roles)
    legacy = base.current_layout_ops()
    assert _snapshot(explicit, ink, semantics) == _snapshot(legacy, ink, semantics)


def test_explicit_ops_do_not_change_mutable_page_design_hooks():
    before = base.current_layout_ops()
    explicit = physical.explicit_physical_layout_ops()
    after = base.current_layout_ops()
    assert before == after
    assert explicit.line_feature is not before.line_feature
