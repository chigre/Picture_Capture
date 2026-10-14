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


def test_every_appsettings_value_roundtrips_through_json(tmp_path):
    """Exercise persistence for every dataclass field in a real runtime."""
    from dataclasses import asdict, fields
    initial = AppSettings()
    destination = tmp_path / "full_settings.json"
    initial.to_json(destination)
    reopened = AppSettings.from_json(destination)
    current = asdict(initial)
    restored = asdict(reopened)
    assert set(current) == set(restored)
    mismatches = {key: (value, restored[key])
                  for key, value in current.items() if restored[key] != value}
    assert not mismatches, mismatches


def test_audit_maps_all_fields_and_new_separator_controls(tmp_path):
    from dataclasses import fields
    import csv
    # The test runner only injects src/ into sys.path; import the audit
    # script by its repository path without requiring a scripts package.
    spec = importlib.util.spec_from_file_location(
        "settings_runtime_audit", ROOT / "scripts" / "audit_settings_runtime.py"
    )
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    field_names = {f.name for f in fields(AppSettings())}
    assert field_names == set(audit.field_defaults())
    groups = audit.schema_locations(field_names)
    help_keys = audit.schema_help_keys()
    refs, candidates = audit.scan_reads_writes(field_names)
    names = {
        "separator_y_ink_safe_max_fraction",
        "separator_y_ink_safe_ink_threshold",
        "separator_y_ink_safe_existing_ink_ratio",
        "separator_y_ink_safe_gap_ink_ratio",
    }
    for name in names:
        assert "SEPARATOR_Y_FIELDS" in groups[name]
        ui_path, status = audit.user_ui_path(groups[name])
        assert "横线Y精修" in ui_path and status == "static_schema_location"
        assert name in help_keys["SETTING_HELP"]
        assert any("separator_y_refinement.py" in x
                   for x in audit.source_runtime_refs(refs[name]["reads"]))
    assert candidates and any(item["kind"] == "numeric_keyword_default" for item in candidates)

    # No more blanket 'runtime verified' labels: all paths record evidence.
    import sys
    previous = sys.argv
    try:
        sys.argv = ["audit_settings_runtime.py", "--out", str(tmp_path)]
        audit.main()
    finally:
        sys.argv = previous
    with (tmp_path / "appsettings_field_matrix.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(field_names)
    assert {row["name"] for row in rows} == field_names
    assert all(row["load_mechanism"] and row["gui_save_mechanism"] for row in rows)
    for row in rows:
        if row["name"] in names:
            assert "横线Y精修" in row["settings_center_path"]
            assert row["dedicated_help"] == "True"
            assert "separator_y_refinement.py" in row["runtime_static_read_sites"]
            assert row["runtime_status"] == "targeted_behavior_test"
            assert "test_ink_safe_separator_20261014.py" in row["targeted_algorithm_runtime_test"]
            assert "test_every_appsettings_value_roundtrips_through_json" in row["persistence_runtime_test"]
    review = json.loads(
        (tmp_path / "hardcoded_threshold_candidates.json").read_text(encoding="utf-8")
    )
    assert review and all(item["reviewed"] is False for item in review)
    triage = json.loads(
        (tmp_path / "threshold_triage_summary.json").read_text(encoding="utf-8")
    )
    assert names <= set(triage["resolved_experimental_white_gap_thresholds"])


def test_invalid_typed_separator_values_rejected_before_gui_save():
    import pytest
    from picture_capture.ui.settings import lifecycle

    class Var:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    for name, value in (
        ("separator_y_ink_safe_max_fraction", "NaN"),
        ("separator_y_ink_safe_ink_threshold", "256"),
        ("separator_y_ink_safe_ink_threshold", "2.5"),
        ("separator_y_ink_safe_existing_ink_ratio", "-1"),
        ("separator_y_ink_safe_gap_ink_ratio", "0.5"),
    ):
        with pytest.raises(ValueError):
            lifecycle.validate_separator_gap_controls({name: Var(value)})
    lifecycle.validate_separator_gap_controls({
        "separator_y_ink_safe_max_fraction": Var("0.25"),
        "separator_y_ink_safe_ink_threshold": Var("185"),
        "separator_y_ink_safe_existing_ink_ratio": Var("0.045"),
        "separator_y_ink_safe_gap_ink_ratio": Var("0.02"),
    })


def test_help_panel_has_real_scroll_region_and_live_wrapping():
    source = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    panel = source.split("    def _scrollable_settings_page(", 1)[1].split(
        "    def _settings_intro(", 1
    )[0]
    assert "help_canvas = tk.Canvas(help_view" in panel
    assert 'orient="vertical", command=help_canvas.yview' in panel
    assert "scrollregion=cv.bbox(" in panel
    assert "textvariable=self._settings_help_body_var" in panel
    assert "help_canvas.yview_scroll(" in panel
    assert '("<MouseWheel>", "<Button-4>", "<Button-5>")' in panel
