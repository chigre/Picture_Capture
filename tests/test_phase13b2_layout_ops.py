"""Phase 13B2: explicit primitive dependencies retain legacy default behavior."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from PIL import Image

from picture_capture import dictionary_page_design as base
from picture_capture import page_x_registration as registration
from picture_capture import layout_column_drift as drift


def test_page_x_line_family_honors_explicit_ops(monkeypatch):
    seen = []
    ink = np.ones((180, 240), dtype=bool)
    def line_runs(_strip, _reference):
        seen.append("runs")
        return [(10, 20), (35, 45), (60, 70), (85, 95)]
    def line_feature(_column, _strip, y0, y1, _reference, _previous_end):
        seen.append("feature")
        return SimpleNamespace(y0=y0, y1=y1, height=y1-y0, first_x=45)
    mode = SimpleNamespace(support=4, lines=[SimpleNamespace(first_x=45)] * 4)
    def indent_modes(_lines, _reference):
        seen.append("modes")
        return [mode]
    ops = replace(base.RAW_LAYOUT_OPS, line_runs=line_runs,
                  line_feature=line_feature, indent_modes=indent_modes)
    # Registration's low-level candidate can be exercised without changing
    # policy, page geometry or mutable global callbacks.
    result = registration._line_family_candidate(
        ink, top=0, bottom=160, nominal_x=45, column_width=160,
        seed=20, semantics="other", ops=ops,
    )
    assert result is not None
    assert seen.count("runs") == 2
    assert seen.count("feature") == 4
    assert "modes" in seen


def test_drift_remeasurement_honors_explicit_ops(monkeypatch):
    import picture_capture.layout_physical_indent as physical

    seen = []
    monkeypatch.setattr(physical, "_credible_first_ink_x", lambda row, ref: 4)
    line = SimpleNamespace(y0=5, y1=15, first_x=0)
    column = SimpleNamespace(index=0, left=20, right=110, lines=[line],
                             indent_modes=[], entry_modes=[], body_mode=None)
    layout = SimpleNamespace(body_top=0, ordinary_line_height=18.0,
                             indent_type="body", columns=[column],
                             reason="base")
    def modes(lines, reference):
        seen.append(("modes", reference))
        return []
    def assign(col, semantics, reference):
        seen.append(("assign", semantics))
    ops = replace(base.RAW_LAYOUT_OPS, indent_modes=modes,
                  assign_indent_semantics=assign)
    ink = np.ones((60, 140), dtype=bool)
    assert drift.remeasure_layout_indents_from_ink(layout, ink, ops=ops) == {0: 1}
    assert [name for name, *_ in seen] == ["modes", "assign"]
    seen.clear()
    assert drift.finalize_layout_column_drift(
        Image.new("RGB", (140, 60)), SimpleNamespace(), layout,
        page_ink=ink, ops=ops,
    ) is layout
    assert [name for name, *_ in seen] == ["modes", "assign"]
    assert layout.reason == "base; unclipped_first_x=C1:1"
