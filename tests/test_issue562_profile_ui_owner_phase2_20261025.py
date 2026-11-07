"""Issue #562: Profile Wizard native UI methods and live legacy providers."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture.profile import setup
from picture_capture.profile import wizard_headword_explanations, wizard_profile_events
from picture_capture.profile import wizard_tab_builders, wizard_settings_assembly


class Value:
    def __init__(self, value=""):
        self.value=value
    def get(self):
        return self.value
    def set(self, value):
        self.value=value


def test_profile_label_fallback_observes_runtime_preset_patch(monkeypatch):
    calls=[]
    def preset(key):
        calls.append(key)
        return SimpleNamespace(display_name={"legacy":"Alpha","other":"Alpha","third":"Beta"}[key])
    monkeypatch.setattr(setup, "dictionary_profile_preset", preset)
    stub=SimpleNamespace(profile_choices=[("other label","other"),("third label","third")])
    assert setup.ProjectProfileWizard._profile_label_for_key(stub,"legacy") == "other label"
    assert calls == ["legacy","other"]
    assert setup.ProjectProfileWizard._profile_label_for_key(stub,"third") == "third label"
    assert "dictionary_profile_preset" in inspect.getsource(wizard_profile_events.profile_label_for_key)


def test_headword_example_asset_uses_original_data_root_and_patchable_catalog(monkeypatch):
    root=Path(setup.__file__).resolve().parent.parent
    monkeypatch.setattr(setup,"HEADWORD_EXAMPLE_FILES",{"unit":"not-a-real-image-562.png"})
    assert setup.ProjectProfileWizard._headword_example_asset(object(),"unit") is None
    assert setup.ProjectProfileWizard._headword_example_asset(object(),"missing") is None
    assert root.name == "picture_capture"
    assert "data_root" in inspect.getsource(wizard_headword_explanations.headword_example_asset)


def test_profile_summary_preserves_invalid_edit_tolerance():
    result=Value("before")
    stub=SimpleNamespace(summary_var=result,_settings_from_ui=lambda:object())
    setup.ProjectProfileWizard._refresh_summary(stub)
    assert result.get() == "before"
    assert "profile_summary_tags" in inspect.getsource(wizard_settings_assembly.refresh_summary)


def test_profile_mode_row_remains_original_staticmethod():
    assert isinstance(setup.ProjectProfileWizard.__dict__["_mode_row"],staticmethod)
    assert callable(wizard_tab_builders.mode_row)
    assert "ttk.Combobox(" in inspect.getsource(wizard_tab_builders.mode_row)
