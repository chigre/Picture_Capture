"""Issue #562 Phase 14: AppSettings value assignment physically owned by Profile."""
from __future__ import annotations

import inspect
import math
import pickle

import pytest

import picture_capture.models as models
from picture_capture.models import AppSettings
from picture_capture.profile import settings_value_policy


def test_physical_owner_and_exact_historical_entrypoints():
    assert "object.__setattr__(settings, name, value)" in inspect.getsource(
        settings_value_policy.assign_setting_value
    )
    assert "separator_y_ink_safe_ink_threshold" in inspect.getsource(
        settings_value_policy.assign_setting_value
    )
    assert "_settings_value_policy.assign_setting_value" in inspect.getsource(
        AppSettings.__setattr__
    )
    assert "_settings_value_policy.normalize_display_opacity" in inspect.getsource(
        models._normalize_display_opacity
    )
    assert "_settings_value_policy.app_settings_storage_alias" in inspect.getsource(
        models._app_settings_storage_alias
    )
    assert AppSettings.__module__ == "picture_capture.models"
    assert pickle.loads(pickle.dumps(AppSettings)) is AppSettings


def test_assigned_opacity_values_are_normalized_in_constructor_and_afterwards():
    s = AppSettings(guide_opacity=-10, headword_marker_opacity=200)
    assert (s.guide_opacity, s.headword_marker_opacity) == (0.0, 100.0)
    s.guide_opacity = float("nan")
    assert s.guide_opacity == 40.0
    s.illustration_fill_opacity = 75.25
    assert s.illustration_fill_opacity == 75.25
    s.guide_opacity = "invalid"
    assert s.guide_opacity == 40.0


def test_crop_and_projection_rejections_leave_original_values_intact():
    s = AppSettings()
    for bad in (0, 101, float("nan"), float("inf"), "invalid"):
        with pytest.raises(ValueError, match="1–100%"):
            s.crop_width_percent = bad
    assert s.crop_width_percent == 100.0
    for bad in (0, 101, float("nan"), float("inf"), "invalid"):
        with pytest.raises(ValueError, match="10–100%"):
            s.physical_row_projection_width_percent = bad
    assert s.physical_row_projection_width_percent == 42.0
    s.crop_width_percent = "69.25"
    assert s.crop_width_percent == 69.25


@pytest.mark.parametrize("name,valid,bad", [
    ("separator_y_ink_safe_max_fraction", 0.15, 0.35),
    ("separator_y_ink_safe_ink_threshold", 155.0, 155.5),
    ("separator_y_ink_safe_existing_ink_ratio", 0.06, 0.30),
    ("separator_y_ink_safe_gap_ink_ratio", 0.04, 0.15),
])
def test_separator_gap_values_enforce_limits_and_retain_previous_state(name, valid, bad):
    s = AppSettings()
    setattr(s, name, valid)
    previous = getattr(s, name)
    with pytest.raises(ValueError):
        setattr(s, name, bad)
    assert getattr(s, name) == previous
    if name.endswith("_threshold"):
        assert type(previous) is int


def test_runtime_monkeypatch_root_normalizer_is_live(monkeypatch):
    s = AppSettings()
    seen = []
    def hook(value):
        seen.append(value)
        return 27.75
    monkeypatch.setattr(models, "_normalize_display_opacity", hook)
    s.guide_opacity = "patched"
    assert seen == ["patched"]
    assert s.guide_opacity == 27.75


def test_static_alias_routes_through_validation_and_survives_pickle():
    s = AppSettings(separator_y_search_ratio=0.27, entry_ocr_right_ratio=62.0)
    assert s.paddle_separator_search_ratio == 0.27
    assert s.crop_width_percent == 62.0
    s.entry_ocr_right_ratio = 73.0
    assert s.crop_width_percent == 73.0
    with pytest.raises(ValueError, match="1–100%"):
        s.entry_ocr_right_ratio = 0
    assert s.crop_width_percent == 73.0
    restored = pickle.loads(pickle.dumps(s))
    assert restored.entry_ocr_right_ratio == 73.0


def test_finite_normalization_uses_original_math_module_at_invocation(monkeypatch):
    calls = []
    real = math.isfinite
    monkeypatch.setattr(models.math, "isfinite", lambda value: calls.append(value) or real(value))
    assert models._normalize_display_opacity(17.5) == 17.5
    assert calls == [17.5]
