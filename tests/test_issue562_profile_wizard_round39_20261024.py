"""Round 39 Profile Wizard extracted persistence, revision events and marker controls."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture.profile import (
    setup, wizard_persistence, wizard_profile_events, wizard_visual_markers,
)

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture/profile"

PERSISTENCE_METHODS = (
    "_persist_current_profile", "_save_profile_progress", "_move_step",
    "save_and_close", "_close_without_save",
)
EVENT_METHODS = (
    "_mark_validation_stale", "_profile_input_changed", "_reading_changed",
    "_set_structure_defaults_for_profile", "_set_tail_defaults_for_profile",
    "_set_symbol_defaults_for_profile", "_specificity_defaults_for_profile",
    "_reset_specificity_for_profile", "_headword_changed",
    "_headword_structure_changed", "_headword_specificity_changed",
    "_refresh_headword_tuning_status", "_custom_name_changed",
    "_ocr_language_changed",
)
MARKER_METHODS = (
    "_refresh_symbol_template_summary", "_capture_visual_marker_sample",
    "_visual_marker_sample_saved", "_replace_visual_marker_samples",
    "_show_visual_marker_samples", "_clear_visual_marker_samples",
)


def test_round39_original_entrypoints_and_owner_location():
    source = (ROOT / "setup.py").read_text(encoding="utf-8")
    cls = next(x for x in ast.parse(source).body if isinstance(x, ast.ClassDef) and x.name == "ProjectProfileWizard")
    class_methods = {x.name: x for x in cls.body if isinstance(x, ast.FunctionDef)}
    for names, module in (
        (PERSISTENCE_METHODS, "persistence"),
        (EVENT_METHODS, "profile_events"),
        (MARKER_METHODS, "visual_markers"),
    ):
        owner_text = (ROOT / ("wizard_" + module + ".py")).read_text(encoding="utf-8")
        assert "from .setup import" not in owner_text
        owner_nodes = {x.name for x in ast.parse(owner_text).body if isinstance(x, ast.FunctionDef)}
        for name in names:
            migrated_name = name.lstrip("_")
            assert migrated_name in owner_nodes
            block = ast.get_source_segment(source, class_methods[name])
            assert "_wizard_" + module + "." + migrated_name + "(" in block
            assert len(block.splitlines()) < 28
    assert "finalize" in inspect.signature(setup.ProjectProfileWizard._persist_current_profile).parameters
    assert inspect.signature(setup.ProjectProfileWizard._persist_current_profile).parameters["finalize"].kind is inspect.Parameter.KEYWORD_ONLY
    assert "apply_runtime" in inspect.signature(setup.ProjectProfileWizard._save_profile_progress).parameters
    assert "status" in inspect.signature(setup.ProjectProfileWizard._save_profile_progress).parameters


def test_round39_live_binding_compatibility_for_persistence_events_and_markers(monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_persistence, "persist_current_profile", lambda obj, *, finalize, apply_runtime, deps: calls.append(("persist", obj, finalize, apply_runtime, deps)))
    monkeypatch.setattr(wizard_persistence, "save_and_close", lambda obj, *, deps: calls.append(("close", obj, deps)))
    monkeypatch.setattr(wizard_profile_events, "headword_changed", lambda obj, *, deps: calls.append(("headword", obj, deps)))
    monkeypatch.setattr(wizard_profile_events, "specificity_defaults_for_profile", lambda obj, key, *, deps: calls.append(("specificity", obj, key, deps)))
    monkeypatch.setattr(wizard_visual_markers, "capture_visual_marker_sample", lambda obj, *, deps: calls.append(("capture", obj, deps)))
    monkeypatch.setattr(wizard_visual_markers, "replace_visual_marker_samples", lambda obj, samples, *, deps: calls.append(("replace", obj, samples, deps)))
    wizard = setup.ProjectProfileWizard.__new__(setup.ProjectProfileWizard)
    wizard._persist_current_profile(finalize=True, apply_runtime=False)
    wizard.save_and_close()
    wizard._headword_changed()
    wizard._specificity_defaults_for_profile("latin_regular")
    wizard._capture_visual_marker_sample()
    wizard._replace_visual_marker_samples([])
    assert [call[0] for call in calls] == ["persist", "close", "headword", "specificity", "capture", "replace"]
    assert calls[0][1:4] == (wizard, True, False)
    assert calls[0][4]["copy_settings"] is setup.copy_settings
    assert calls[0][4]["write_project_profile"] is setup.write_project_profile
    assert calls[0][4]["settings_path"] is setup.settings_path
    assert calls[0][4]["project_profile_path"] is setup.project_profile_path
    assert calls[1][2]["messagebox"] is setup.messagebox
    assert calls[2][2]["_normalize_cjk_visual_symbol_roles"] is setup._normalize_cjk_visual_symbol_roles
    assert calls[3][3]["apply_headword_profile"] is setup.apply_headword_profile
    assert calls[4][2]["VisualMarkerCaptureDialog"] is setup.VisualMarkerCaptureDialog
    assert calls[5][3]["serialize_visual_marker_samples"] is setup.serialize_visual_marker_samples


def test_round39_persistence_keeps_partial_save_id_and_confirm_cancel_semantics():
    saved = (ROOT / "wizard_persistence.py").read_text(encoding="utf-8")
    assert "settings.profile_setup_version = int(" in saved
    assert "settings.profile_last_validated_pages = list(" in saved
    assert "copy_settings(self.parent.settings, settings)" in saved
    assert "self.parent.settings.to_json(settings_path(self.project.root))" in saved
    assert "write_project_profile(" in saved
    assert "force=True" in saved
    assert "self.parent.sync_quick_settings()" in saved
    assert "self.parent.redraw()" in saved
    assert 'if not self._save_profile_progress():' in saved
    assert "self.working.dictionary_layout_kind != \"illustrated\"" in saved
    assert "self.analyze_representative_pages(auto_apply=True)" in saved
    assert '"Profile 尚未完整验证"' in saved
    assert "self._validation_close_requested = True" in saved
    assert "self._validation_stop_event.set()" in saved
    assert "self.destroy()" in saved
    assert "PROFILE_SETUP_VERSION" in saved


def test_round39_headword_event_revision_and_tail_defaults_behavior():
    events = (ROOT / "wizard_profile_events.py").read_text(encoding="utf-8")
    assert "self.working.profile_last_validated_pages = []" in events
    assert "self._profile_revision += 1" in events
    assert "self._mark_validation_stale()" in events
    assert "self._refresh_summary()" in events
    assert 'key == "cjk_visual"' in events
    assert "_normalize_cjk_visual_symbol_roles(" in events
    assert "self.visual_marker_samples = normalized_samples" in events
    assert "self.tail_allow_visual_rescue_var.set(" in events
    assert "self.symbol_lane_tolerance_var.set(" in events
    assert "self._refresh_headword_description()" in events
    assert "self._refresh_headword_tuning_status()" in events
    assert "self._refresh_language_summary()" in events


def test_round39_visual_marker_capturing_and_sample_serialization_contracts():
    marker = (ROOT / "wizard_visual_markers.py").read_text(encoding="utf-8")
    assert "split_configured_symbols(self.entry_marker_symbols_var.get())" in marker
    assert "initial_index = int(self.sample_indices[0])" in marker
    assert "VisualMarkerCaptureDialog(" in marker
    assert "on_saved=self._visual_marker_sample_saved" in marker
    assert "sample_id = str(sample.get(\"id\") or \"\")" in marker
    assert "self.working.profile_symbol_template_version = 1" in marker
    assert "self.working.profile_symbol_templates_json = (" in marker
    assert "self._headword_specificity_changed()" in marker
    assert "VisualMarkerSamplesDialog(" in marker
    assert 'self._replace_visual_marker_samples([])' in marker


def test_round39_stale_validation_clears_safely_without_tk_root():
    changed = []
    class Variable:
        def __init__(self): self.value = None
        def set(self, value): self.value = value
    class Button:
        def configure(self, **kwargs): changed.append(kwargs)
    working = SimpleNamespace(profile_last_validated_pages=["already"], dictionary_profile_id="latin_regular")
    stub = SimpleNamespace(
        working=working, _validation_running=False, validation_status_var=Variable(),
        feedback_too_many_button=Button(), feedback_good_button=Button(),
        feedback_too_few_button=Button(),
    )
    wizard_profile_events.mark_validation_stale(stub)
    assert working.profile_last_validated_pages == []
    assert stub.validation_status_var.value == "设置已修改，需要重新测试"
    assert changed == [{"state": "disabled"}] * 3
