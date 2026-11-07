"""Round 61: source-coordinate crop PNG pixel parity and repeat-export byte stability."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_real_tk_smoke_proves_exact_original_rgb_pixels():
    source = (ROOT / "scripts/gui_project_roundtrip_smoke.py").read_text(
        encoding="utf-8",
    )
    ast.parse(source)
    assert "ImageChops.difference(" in source
    assert "original_source.crop(record.box)" in source
    assert "difference.getbbox() is None" in source
    assert "any_ink = any_ink or" in source
    assert 'all produced crops lost the synthetic dark ink' in source
    assert 'record.box[2] - record.box[0]' in source
    assert "CropPlan" in source
    assert "rendered.size ==" in source


def test_two_real_production_exports_have_identical_png_manifest_bytes():
    source = (ROOT / "scripts/gui_project_roundtrip_smoke.py").read_text(
        encoding="utf-8",
    )
    assert source.count("split_whole_entries(") == 2
    assert "first_crop_hashes" in source
    assert "first_manifest = _source_hash(" in source
    assert "first_widths = _source_hash(" in source
    assert "identical export changed published PNG/manifest bytes" in source
    assert "_source_hash(path) == original_hashes[path.name]" in source
    assert "with tempfile.TemporaryDirectory(" in source
    assert "monkeypatch" not in source


def test_manual_scanned_page_gate_still_not_claimed():
    text = (
        ROOT / "docs/architecture/REAL_SCAN_ACCEPTANCE_GATE_20261025.md"
    ).read_text(encoding="utf-8")
    assert "MANUAL GATE OPEN / NOT PASSED" in text
    assert "pixel-for-pixel RGB" in text
    assert "second identical export" in text
    assert "original full-resolution dictionary" in text
