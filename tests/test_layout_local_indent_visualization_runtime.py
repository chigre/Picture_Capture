from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_local_indent_visualization import (
    drift_corrected_indent_blocks,
)


def test_visualization_uses_local_baseline_not_fixed_column_origin(monkeypatch):
    line = SimpleNamespace(
        y0=10,
        y1=30,
        first_x=-12,
        anchor_x=None,
        role="body",
    )
    column = SimpleNamespace(
        index=0,
        left=50,
        lines=[line],
        body_mode=SimpleNamespace(center=24.0),
    )
    layout = SimpleNamespace(body_top=100, columns=[column])
    understanding = SimpleNamespace(layout=layout)

    monkeypatch.setattr(
        "picture_capture.layout_local_indent_visualization.normalized_physical_indents",
        lambda lines: {id(line): 18.0},
    )

    blocks = drift_corrected_indent_blocks(understanding)

    assert len(blocks) == 1
    block = blocks[0]
    # raw=-12, corrected=18 -> common drift=-30, so the physical local baseline
    # is x=20 even though the semantic/Profile column origin remains x=50.
    assert block["local_origin_x"] == 20.0
    assert block["x0"] == 20.0
    assert block["x1"] == 38.0
    assert block["indent_px"] == 18.0
    assert block["raw_first_x"] == -12.0
    assert block["corrected_indent_px"] == 18.0


def test_phase5i_static_owner_and_provenance_order():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    package = root / "src" / "picture_capture"
    shared = (package / "layout_visualization_shared.py").read_text(encoding="utf-8")
    gui = (package / "bootstrap" / "gui.py").read_text(encoding="utf-8")
    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")

    assert not (package / "layout_local_indent_visualization_runtime.py").exists()
    assert (package / "layout_local_indent_visualization.py").exists()
    assert "_indent_blocks_from_understanding = indent_blocks_with_entry_sources" in shared
    assert "install_local_indent_visualization" not in gui
    assert "layout_local_indent_visualization_runtime.py" not in guard
    assert "install_layout_role_provenance" not in gui
    role_theme_pos = gui.index("install_layout_role_theme()")
    lane_pos = gui.index("install_physical_lane_summary()")
    assert "install_layout_indent_visibility" not in gui
    assert "install_shared_layout_visualization_source" not in gui
    assert role_theme_pos < lane_pos
