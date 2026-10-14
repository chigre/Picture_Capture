"""Smoke-execute the whole-source parameter inventory in CI without GUI startup."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from picture_capture.models import AppSettings
from picture_capture.ui.settings import schema

ROOT = Path(__file__).resolve().parents[1]


def test_full_repo_settings_audit_runs_and_outputs_matrix(tmp_path):
    script = ROOT / "scripts" / "audit_settings_runtime.py"
    result = subprocess.run(
        [sys.executable, str(script), "--out", str(tmp_path)],
        capture_output=True, text=True, check=True, timeout=90,
    )
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["all_appsettings_fields"] > 150
    assert summary["numeric_comparison_candidates"] > 0
    assert (tmp_path / "appsettings_field_matrix.csv").is_file()
    assert (tmp_path / "hardcoded_threshold_candidates.json").is_file()


def test_shared_y_shift_limit_persists_and_is_in_dedicated_tab(tmp_path):
    s = AppSettings(separator_y_max_shift_ratio=0.65)
    path = tmp_path / "settings.json"
    s.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.separator_y_max_shift_ratio == 0.65
    assert AppSettings().separator_y_max_shift_ratio == 0.45
    assert "separator_y_max_shift_ratio" in schema.SEPARATOR_Y_FIELDS
    assert "separator_y_max_shift_ratio" not in schema.OCR_ADVANCED_FIELDS


def test_help_panel_has_initial_wraplength():
    source = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    label = source[source.index("help_body = ttk.Label("):]
    assert "wraplength=300" in label[:300]
