"""Round 59 — synthetic GUI project roundtrip must be a real CI job, not a claimed manual pass."""
from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_smoke_runs_in_both_real_tk_ci_python_matrices():
    yaml = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    script = "scripts/gui_project_roundtrip_smoke.py"
    assert yaml.count("run: xvfb-run -a uv run --locked python " + script) == 1
    assert yaml.count("run: uv run --locked python " + script) == 1
    assert yaml.count("run: xvfb-run -a uv run --locked --python 3.10 python " + script) == 1
    assert yaml.count("run: uv run --locked --python 3.10 python " + script) == 1
    assert yaml.count("scripts/gui_smoke.py") == 4
    assert "scripts/gui_proofreading_evidence_smoke.py" in yaml
    assert "scripts/gui_r3_candidate_delete_smoke.py" in yaml


def test_synthetic_smoke_proves_source_immutability_and_disk_reload():
    path = ROOT / "scripts/gui_project_roundtrip_smoke.py"
    source = path.read_text(encoding="utf-8")
    ast.parse(source)
    assert "build_application()" in source
    assert "app._load_project(root)" in source
    assert "app.save_pdic(silent=True, sync_editors=False)" in source
    assert "app._save_normalized_ppp()" in source
    assert "app.load_page(1, skip_current_save=True)" in source
    assert "app.load_page(0, skip_current_save=True)" in source
    assert "_source_hash(path) == original_hashes[path.name]" in source
    assert "AppSettings.from_json(settings_path(root))" in source
    assert "with tempfile.TemporaryDirectory(" in source
    assert "from picture_capture.app import" not in source
    assert "Real dictionary" not in source
    assert "NOT PASSED" in (
        ROOT / "docs/architecture/REAL_SCAN_ACCEPTANCE_GATE_20261025.md"
    ).read_text(encoding="utf-8")
