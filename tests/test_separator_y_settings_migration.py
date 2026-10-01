from __future__ import annotations

import json

from picture_capture.models import AppSettings
from picture_capture.separator_y_settings import (
    CANONICAL_TO_LEGACY,
    canonical_separator_y_values,
)


def test_canonical_separator_y_names_work_in_constructor_and_runtime():
    settings = AppSettings(
        separator_y_refine_enabled=False,
        separator_y_search_ratio=0.24,
        separator_y_band_radius=3,
        separator_y_safety_px=4,
        separator_y_roi_width_ratio=52.5,
        separator_y_column_margin=6,
    )

    assert settings.separator_y_refine_enabled is False
    assert settings.separator_y_search_ratio == 0.24
    assert settings.separator_y_band_radius == 3
    assert settings.separator_y_safety_px == 4
    assert settings.separator_y_roi_width_ratio == 52.5
    assert settings.separator_y_column_margin == 6

    # Historical engine slots remain synchronized behind the compatibility
    # bridge, but new application code does not need to reference them.
    assert settings.paddle_refine_separator_y is False
    assert settings.paddle_separator_search_ratio == 0.24


def test_old_project_json_loads_and_resaves_with_only_canonical_keys(tmp_path):
    old_path = tmp_path / "old.json"
    old_path.write_text(
        json.dumps({
            "paddle_refine_separator_y": True,
            "paddle_separator_search_ratio": 0.27,
            "paddle_separator_band_radius": 4,
            "paddle_separator_safety_px": 3,
            "paddle_separator_roi_width_ratio": 55.5,
            "paddle_separator_column_margin": 7,
        }),
        encoding="utf-8",
    )

    settings = AppSettings.from_json(old_path)
    assert settings.separator_y_search_ratio == 0.27
    assert settings.separator_y_band_radius == 4
    assert settings.separator_y_roi_width_ratio == 55.5

    saved_path = tmp_path / "saved.json"
    settings.to_json(saved_path)
    payload = json.loads(saved_path.read_text(encoding="utf-8"))

    assert payload["separator_y_refine_enabled"] is True
    assert payload["separator_y_search_ratio"] == 0.27
    assert payload["separator_y_band_radius"] == 4
    assert payload["separator_y_safety_px"] == 3
    assert payload["separator_y_roi_width_ratio"] == 55.5
    assert payload["separator_y_column_margin"] == 7
    for legacy in CANONICAL_TO_LEGACY.values():
        assert legacy not in payload


def test_new_project_json_loads_through_existing_settings_migrations(tmp_path):
    path = tmp_path / "new.json"
    path.write_text(
        json.dumps({
            "separator_y_refine_enabled": False,
            "separator_y_search_ratio": 0.21,
            "separator_y_band_radius": 5,
            "separator_y_safety_px": 1,
            "separator_y_roi_width_ratio": 48.0,
            "separator_y_column_margin": 9,
            "ocr_language": "chi_tra",
        }),
        encoding="utf-8",
    )

    settings = AppSettings.from_json(path)
    values = canonical_separator_y_values(settings)
    assert values == {
        "separator_y_refine_enabled": False,
        "separator_y_search_ratio": 0.21,
        "separator_y_band_radius": 5,
        "separator_y_safety_px": 1,
        "separator_y_roi_width_ratio": 48.0,
        "separator_y_column_margin": 9,
    }
    assert settings.ocr_language == "chi_tra"


def test_canonical_value_wins_when_old_and_new_keys_both_exist(tmp_path):
    path = tmp_path / "mixed.json"
    path.write_text(
        json.dumps({
            "paddle_separator_search_ratio": 0.40,
            "separator_y_search_ratio": 0.23,
        }),
        encoding="utf-8",
    )

    settings = AppSettings.from_json(path)
    assert settings.separator_y_search_ratio == 0.23
