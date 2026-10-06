from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import picture_capture.layout_role_provenance as provenance


def test_indent_blocks_are_annotated_from_matching_layout_lines(monkeypatch):
    entry_line = SimpleNamespace(y0=10, y1=20)
    body_line = SimpleNamespace(y0=30, y1=40)
    layout = SimpleNamespace(
        body_top=100,
        columns=[SimpleNamespace(index=2, lines=[entry_line, body_line])],
    )
    understanding = SimpleNamespace(layout=layout)
    blocks = [
        {"column": 2, "y0": 110, "y1": 120, "role": "entry"},
        {"column": 2, "y0": 130, "y1": 140, "role": "body"},
        {"column": 2, "y0": 150, "y1": 160, "role": "headword"},
    ]

    monkeypatch.setattr(
        provenance, "drift_corrected_indent_blocks", lambda value: [dict(item) for item in blocks]
    )
    monkeypatch.setattr(
        provenance,
        "get_layout_line_classification",
        lambda line: SimpleNamespace(entry_source="large_head" if line is entry_line else "ocr"),
    )

    result = provenance.indent_blocks_with_entry_sources(understanding)
    assert result[0]["entry_source"] == "large_head"
    assert result[1]["entry_source"] == "body"
    # Unmatched entry/headword blocks retain the historical indent default.
    assert result[2]["entry_source"] == "indent"


def test_entry_source_summary_inserts_after_line_indents_and_orders_sources():
    app = SimpleNamespace(
        _layout_visualization_indent_blocks=[
            {"role": "entry", "entry_source": "custom_z"},
            {"role": "entry", "entry_source": "manual"},
            {"role": "headword", "entry_source": "large_head"},
            {"role": "entry", "entry_source": "indent"},
            {"role": "entry", "entry_source": "custom_a"},
            {"role": "body", "entry_source": "ocr"},
        ]
    )
    base = "Layout AUTO\nline indents: 6   roles: x\nrole strips: x"
    text = provenance.add_entry_source_summary(base, app)
    assert text.splitlines() == [
        "Layout AUTO",
        "line indents: 6   roles: x",
        "entry sources: indent=1, large_head=1, manual=1, custom_a=1, custom_z=1",
        "role strips: x",
    ]


def test_entry_source_summary_returns_base_text_when_no_entry_counts():
    app = SimpleNamespace(_layout_visualization_indent_blocks=[{"role": "body"}])
    base = "Layout CURRENT\nline indents: 1   roles: body"
    assert provenance.add_entry_source_summary(base, app) == base


def test_phase5j_static_provenance_and_later_wrapper_order():
    root = Path(__file__).resolve().parents[1]
    package = root / "src" / "picture_capture"
    gui = (package / "bootstrap" / "gui.py").read_text(encoding="utf-8")
    shared = (package / "layout_visualization_shared.py").read_text(encoding="utf-8")
    summary = (package / "layout_visualization_summary.py").read_text(encoding="utf-8")
    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")

    assert not (package / "layout_role_provenance_runtime.py").exists()
    assert (package / "layout_role_provenance.py").exists()
    assert "_indent_blocks_from_understanding = indent_blocks_with_entry_sources" in shared
    assert "add_entry_source_summary" in summary
    assert "install_layout_role_provenance" not in gui
    assert "layout_role_provenance_runtime.py" not in guard

    shared_pos = gui.index("install_shared_layout_visualization_source()")
    role_theme_pos = gui.index("install_layout_role_theme()")
    lane_pos = gui.index("install_physical_lane_summary()")
    assert "install_layout_indent_visibility" not in gui
    assert shared_pos < role_theme_pos < lane_pos
