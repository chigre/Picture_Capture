"""Issue #562: physically move native AppSettings fields while preserving models API."""
from __future__ import annotations

from dataclasses import asdict, fields, replace
from pathlib import Path
import json
import pickle

import pytest

import picture_capture.models as models
from picture_capture.profile import settings_model


def test_exact_native_appsettings_owner_and_old_pickle_identity():
    cls = models.AppSettings
    assert cls is settings_model.AppSettings
    assert cls.__module__ == "picture_capture.models"
    assert settings_model._AppSettingsMeta is models._AppSettingsMeta
    assert pickle.loads(pickle.dumps(cls)) is cls
    assert pickle.loads(pickle.dumps(cls())) == cls()
    assert len(fields(cls)) > 150
    # __module__ intentionally points to the historical pickle path, so
    # inspect.getsource(class) resolves there. Verify the physical AST owner.
    source = Path(settings_model.__file__).read_text(encoding="utf-8")
    assert "class AppSettings(metaclass=_AppSettingsMeta):" in source
    assert "dictionary_index_language" in source
    assert "class AppSettings" not in Path(models.__file__).read_text(encoding="utf-8")


def test_native_field_order_compat_aliases_and_replace():
    original = models.AppSettings(
        crop_width_percent=61.5,
        separator_y_search_ratio=0.27,
        entry_regular_crop_height=42,
    )
    field_order = [field.name for field in fields(original)]
    assert field_order.index("columns") < field_order.index("crop_width_percent")
    assert field_order.index("crop_width_percent") < field_order.index("paddle_separator_search_ratio")
    assert original.separator_y_search_ratio == original.paddle_separator_search_ratio == 0.27
    assert original.entry_regular_crop_height == original.review_regular_crop_height == 42
    cloned = replace(original)
    assert asdict(cloned) == asdict(original)
    assert type(cloned) is type(original)


def test_original_module_migration_hook_still_live(monkeypatch):
    captured = []
    previous = models.normalize_app_settings_compat_keys
    def translator(kwargs):
        captured.append(dict(kwargs))
        return previous(kwargs)
    monkeypatch.setattr(models, "normalize_app_settings_compat_keys", translator)
    instance = models.AppSettings(entry_ocr_right_ratio=58.25)
    assert captured and captured[-1]["entry_ocr_right_ratio"] == 58.25
    assert instance.crop_width_percent == 58.25


def test_original_module_setter_and_storage_hooks_still_live(monkeypatch, tmp_path):
    opacity = []
    def normalizer(value):
        opacity.append(value)
        return 31.5
    monkeypatch.setattr(models, "_normalize_display_opacity", normalizer)
    s = models.AppSettings()
    s.guide_opacity = "modified"
    assert opacity and opacity[-1] == "modified" and s.guide_opacity == 31.5
    path = tmp_path / "settings.json"
    s.to_json(path)
    assert json.loads(path.read_text(encoding="utf-8"))["guide_opacity"] == 31.5
    assert models.AppSettings.from_json(path).guide_opacity == 31.5


def test_native_invalid_assignment_rolls_back_and_pickle_is_stable():
    s = models.AppSettings(crop_width_percent=60.0)
    with pytest.raises(ValueError):
        s.crop_width_percent = 105
    assert s.crop_width_percent == 60.0
    assert pickle.loads(pickle.dumps(s)).crop_width_percent == 60.0
