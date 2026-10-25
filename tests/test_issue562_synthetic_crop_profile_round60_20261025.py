"""Round 60: ensure synthetic Tk export/Profile checks are executable and never mocks."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_real_crop_and_profile_production_calls_in_synthetic_tk_smoke():
    source = (ROOT / "scripts/gui_project_roundtrip_smoke.py").read_text(
        encoding="utf-8",
    )
    ast.parse(source)
    assert "from picture_capture.processing import split_whole_entries" in source
    assert "crop_records = split_whole_entries(" in source
    assert "integrate_illustrations=False" in source
    assert "output_dir / f\"{first.stem}.PWWords\"" in source
    assert "f\"{first.stem}.PWWWidths.json\"" in source
    assert 'qt_root(root) / "CropPlan"' in source
    assert "record.box[2] - record.box[0]" in source
    assert 'not list(output_dir.glob("*.tmp"))' in source
    assert "_source_hash(profile_file) == profile_sha" in source
    assert "write_project_profile(profile_file, app.settings, force=True)" in source
    assert "load_dictionary_profile(profile_file)" in source
    assert "AppSettings.from_json(settings_path(root))" in source
    assert "with patch.object(module.messagebox" in source
    assert "unittest.mock import patch" in source
    assert "monkeypatch" not in source
    assert "mock_split_whole_entries" not in source


def test_six_matrix_invocations_preserved_and_manual_gate_remains_open():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.count("scripts/gui_project_roundtrip_smoke.py") == 4
    assert workflow.count("Managed project PDIC/PPP Tk save-reopen") == 4
    doc = (
        ROOT / "docs/architecture/REAL_SCAN_ACCEPTANCE_GATE_20261025.md"
    ).read_text(encoding="utf-8")
    assert "MANUAL GATE OPEN / NOT PASSED" in doc
    assert "production crop export" in doc
    assert "Profile v3" in doc
    assert "real scanner" in doc
