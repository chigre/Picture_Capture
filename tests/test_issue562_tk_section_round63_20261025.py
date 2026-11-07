"""Issue #562 Round 63: real Tk SECTION edit, source-XY evidence, gap and 0-section."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_smoke_uses_real_section_tk_callbacks_and_production_sidecars():
    script = (
        ROOT / "scripts/gui_project_roundtrip_smoke.py"
    ).read_text(encoding="utf-8")
    ast.parse(script)
    required = [
        "PageSection(50, 215)", "PageSection(230, 425)",
        'app._drag_section_boundary = (1, "top")',
        "app._drag_page_section_boundary_to(95, 242)",
        "app._set_section_editing(True)",
        "app._finish_section_editing() is True",
        "read_page_sections(first)",
        "page_sections_path_for_image(first)",
        "SOURCE_COORDINATE_SPACE",
        '[[0, 242], [639, 242]]',
        "section_snapshot_for_source_point(first, 85, 182)",
        "section_snapshot_for_source_point(first, 95, 300)",
        "section_snapshot_for_source_point(first, 95, 225) is None",
        'first_section[0] == "section:1"',
        'second_section[0] == "section:2"',
        "first_section[1] == second_section[1]",
        "app.load_page(1, skip_current_save=True)",
        "app.load_page(0, skip_current_save=True)",
        "pdic_before_section_navigation",
        "ppp_before_section_navigation",
        "not section_file.exists()",
        "section_snapshot_for_source_point(first, 85, 182) is None",
        "not app.page_sections",
    ]
    for snippet in required:
        assert snippet in script, snippet
    assert "mock_write_page_sections" not in script
    assert "monkeypatch" not in script


def test_section_smoke_retains_six_platform_matrix_and_unmet_manual_gate():
    yaml = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert yaml.count("scripts/gui_project_roundtrip_smoke.py") == 4
    assert yaml.count("Managed project PDIC/PPP Tk save-reopen") == 4
    manual = (
        ROOT / "docs/architecture/REAL_SCAN_ACCEPTANCE_GATE_20261025.md"
    ).read_text(encoding="utf-8")
    assert "MANUAL GATE OPEN / NOT PASSED" in manual
    assert "Round 63" in manual
    assert "SOURCE_COORDINATE_SPACE" in manual
    assert "human has dragged SECTION lines" in manual
    assert "real dictionary scan" in manual
