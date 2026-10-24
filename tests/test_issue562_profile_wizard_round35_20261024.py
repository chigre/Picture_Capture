"""Round 35: canonical owner and live compatibility of remaining large Wizard methods."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from picture_capture.profile import setup, wizard_template_preview, wizard_settings_assembly, wizard_workspace_builder, wizard_validation_diagnostics

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture/profile"


def test_original_wizard_methods_remain_delegate_seams():
    original = (ROOT / "setup.py").read_text(encoding="utf-8")
    cls = next(n for n in ast.parse(original).body if isinstance(n, ast.ClassDef) and n.name == "ProjectProfileWizard")
    for method, target in (
        ("_refresh_template_preview", "_wizard_template_preview.refresh_template_preview("),
        ("_settings_from_ui", "_wizard_settings_assembly.settings_from_ui("),
        ("_build_right_image_workspace", "_wizard_workspace_builder.build_right_image_workspace("),
        ("_validation_coverage_summary", "_wizard_validation_diagnostics.validation_coverage_summary("),
    ):
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method)
        code = ast.get_source_segment(original, node)
        assert target in code
        assert len(code.splitlines()) < 30
    for name in ("wizard_template_preview", "wizard_settings_assembly", "wizard_workspace_builder", "wizard_validation_diagnostics"):
        assert "from .setup import" not in (ROOT / (name + ".py")).read_text(encoding="utf-8")


def test_legacy_wizard_calls_preserve_live_dependency_references(monkeypatch):
    assert str(inspect.signature(setup.ProjectProfileWizard._refresh_template_preview)) == "(self) -> 'None'"
    assert str(inspect.signature(setup.ProjectProfileWizard._settings_from_ui)) == "(self) -> 'AppSettings'"
    assert isinstance(inspect.getattr_static(setup.ProjectProfileWizard, "_validation_coverage_summary"), staticmethod)
    calls = []
    monkeypatch.setattr(wizard_template_preview, "refresh_template_preview", lambda obj, *, deps: calls.append(("preview", obj, deps)))
    monkeypatch.setattr(wizard_settings_assembly, "settings_from_ui", lambda obj, *, deps: calls.append(("settings", obj, deps)))
    monkeypatch.setattr(wizard_workspace_builder, "build_right_image_workspace", lambda obj, parent, *, deps: calls.append(("workspace", obj, parent, deps)))
    monkeypatch.setattr(wizard_validation_diagnostics, "validation_coverage_summary", lambda *args, deps: calls.append(("coverage", args, deps)))
    obj = setup.ProjectProfileWizard.__new__(setup.ProjectProfileWizard)
    tab = object()
    obj._refresh_template_preview()
    obj._settings_from_ui()
    obj._build_right_image_workspace(tab)
    setup.ProjectProfileWizard._validation_coverage_summary(None, [], tab, tab)
    assert [call[0] for call in calls] == ["preview", "settings", "workspace", "coverage"]
    assert calls[0][1] is obj and calls[0][2]["derive_geometry"] is setup.derive_geometry
    assert calls[0][2]["themed_display_image"] is setup.themed_display_image
    assert calls[1][1] is obj and calls[1][2]["apply_headword_tuning"] is setup.apply_headword_tuning
    assert calls[1][2]["PROFILE_SETUP_VERSION"] == setup.PROFILE_SETUP_VERSION
    assert calls[2][1:3] == (obj, tab) and calls[2][3]["ttk"] is setup.ttk
    assert calls[3][1] == (None, [], tab, tab) and calls[3][2]["json"] is setup.json


def test_extracted_preview_worker_has_no_tk_photo_and_callbacks_stay_on_ui_thread():
    source = (ROOT / "wizard_template_preview.py").read_text(encoding="utf-8")
    worker = source[source.index("    def worker():"):source.index("    def done(")]
    done = source[source.index("    def done("):source.index("    def failed(")]
    assert "with Image.open(path) as opened:" in worker
    assert "page_template_analysis_image(source, effective, index)" in worker
    assert "ImageTk.PhotoImage" not in worker
    assert "themed_display_image(" in done
    assert "self.parent._start_ui_worker(worker_key, worker, done, failed)" in source


def test_moved_settings_and_coverage_keep_original_profile_decision_guards():
    settings = (ROOT / "wizard_settings_assembly.py").read_text(encoding="utf-8")
    assert 's.layout_columns_policy = "fixed"' in settings
    assert 'if profile_key == "cjk_visual":' in settings
    assert "s.profile_allow_marker_prefix = False" in settings
    assert "serialize_visual_marker_samples(" in settings
    assert "apply_headword_tuning(s, profile_key, s.profile_headword_tuning_level)" in settings
    diagnostics = (ROOT / "wizard_validation_diagnostics.py").read_text(encoding="utf-8")
    assert "json.loads(cache_path.read_text" in diagnostics
    assert "geometry.source_to_canonical(" in diagnostics
    assert "原始OCR完整但词头在中途停止" in diagnostics
