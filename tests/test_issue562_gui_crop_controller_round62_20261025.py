"""Issue #562 Round 62: real public GUI crop callback, threaded batch and Tk completion."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts/gui_project_roundtrip_smoke.py"


def test_tk_smoke_uses_real_public_crop_controller_not_mocked_worker():
    text = SMOKE.read_text(encoding="utf-8")
    ast.parse(text)
    assert "app.split_whole_current()" in text
    assert "app._batch_active" in text
    assert "app.batch_progress_var.get() == 100.0" in text
    assert "app._ui_worker_key_active(\"crop-width-normalization\")" in text
    assert "GUI CropController asynchronous crop and width callback" in text
    assert "from picture_capture.crop.settings import normalize_crop_settings_payload" in text
    assert 'qt_root(root) / "_CropSettings.json"' in text
    assert "app._load_crop_settings()" in text
    assert '"entry_width_mode": "off"' in text
    assert '"integrate_illustrations": False' in text
    assert "GUI CropController export differs from direct production output" in text
    assert "GUI crop altered PPP vertices" in text
    assert "GUI crop altered source PDIC marker identities" in text
    assert "GUI crop unexpectedly rewrote project Profile v3" in text
    assert "patch.object(module.messagebox" in text
    assert "patch.object(module.PictureCaptureApp, \"split_whole_current\"" not in text
    assert "monkeypatch" not in text


def test_runner_remains_in_all_six_cross_platform_jobs_and_manual_gate_stays_open():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.count("scripts/gui_project_roundtrip_smoke.py") == 4
    assert workflow.count("Managed project PDIC/PPP Tk save-reopen") == 4
    doc = (
        ROOT / "docs/architecture/REAL_SCAN_ACCEPTANCE_GATE_20261025.md"
    ).read_text(encoding="utf-8")
    assert "MANUAL GATE OPEN / NOT PASSED" in doc
    assert "PictureCaptureApp.split_whole_current()" in doc
    assert "human button click" in doc
    assert "real dictionary" in doc
