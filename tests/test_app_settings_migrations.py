from __future__ import annotations

import json
from pathlib import Path

import picture_capture.app_settings_migrations as migrations
import picture_capture.models as models
from picture_capture.models import AppSettings


def test_phase11a_migration_owner_is_one_way() -> None:
    migration_source = Path(migrations.__file__).read_text(encoding="utf-8")
    model_source = Path(models.__file__).read_text(encoding="utf-8")

    assert "from .models" not in migration_source
    assert "import picture_capture.models" not in migration_source
    assert "migrate_app_settings_payload(raw, cls)" in model_source
    assert 'old_v158_headword_regex = (' not in model_source
    assert 'profile_symbol_role_semantics_version", 0' not in model_source


def test_migration_helper_preserves_native_right_ratio_upgrade() -> None:
    raw = {
        "right_ratio_percent_version": 0,
        "right_ratio": 2.0,
        "profile_side_percent": 9.0,
        "layout_behavior_defaults_version": 1,
        "ui_workflow_defaults_version": 1,
        "profile_symbol_role_semantics_version": 1,
    }

    result = migrations.migrate_app_settings_payload(raw, AppSettings)

    assert result is raw
    assert raw["ordinary_right_divisor"] == 2.0
    assert raw["right_ratio"] == 50.0
    assert raw["right_ratio_percent_version"] == 1
    assert raw["profile_side_percent_a"] == 9.0
    assert raw["profile_side_percent_b"] == 9.0


def test_composed_compatibility_wrappers_still_cross_native_migration(
    tmp_path: Path,
) -> None:
    settings = AppSettings(
        separator_y_search_ratio=0.27,
        entry_regular_crop_height=41,
        entry_oversized_crop_height=93,
    )
    path = tmp_path / "settings.json"
    settings.to_json(path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["separator_y_search_ratio"] == 0.27
    assert raw["entry_regular_crop_height"] == 41
    assert raw["entry_oversized_crop_height"] == 93
    assert "paddle_separator_search_ratio" not in raw
    assert "review_regular_crop_height" not in raw
    assert "review_single_cjk_line_height" not in raw

    # Force one native historical migration in the same payload. The two
    # compatibility wrappers delegate through their captured predecessor chain
    # before the extracted native migration owner runs.
    raw["right_ratio_percent_version"] = 0
    raw["right_ratio"] = 2.0
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    restored = AppSettings.from_json(path)
    assert restored.separator_y_search_ratio == 0.27
    assert restored.entry_regular_crop_height == 41
    assert restored.entry_oversized_crop_height == 93
    assert restored.ordinary_right_divisor == 2.0
    assert restored.right_ratio == 50.0
