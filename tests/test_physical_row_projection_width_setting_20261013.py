"""Projection strip width is a persisted per-project *column* percentage.

Tests cover UI placement, legacy defaults, real policy projection and trace
geometry, and typed-value validation. No annotated PPP/PDIC is modified.
"""
from __future__ import annotations

from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.dictionary_page_design import _leading_width
from picture_capture.layout_core_understanding import (
    clear_layout_understanding_cache, understand_layout_core,
)
from picture_capture.layout_step_trace import LayoutStepTrace
from picture_capture.layout_step_replay_ui import _format_stage
from picture_capture.models import AppSettings
from picture_capture.ui.settings import schema


FIELD = "physical_row_projection_width_percent"


def test_setting_is_in_exact_requested_advanced_panel():
    assert FIELD in dict((name, cast) for _, name, cast in schema.FIELDS)
    assert FIELD in schema.NORMAL_ADVANCED_FIELDS
    assert FIELD not in schema.NORMAL_COMMON_FIELDS
    assert FIELD not in schema.OCR_ADVANCED_FIELDS
    assert FIELD not in schema.PROFILE_FIELD_GROUPS[0][1]
    assert schema.SETTING_UNITS[FIELD] == "% 单栏宽"
    assert schema.SETTING_SPIN[FIELD] == (10.0, 100.0, 1.0)
    assert "42%" in schema.SETTING_HELP[FIELD]
    assert AppSettings().physical_row_projection_width_percent == 42.0


def test_legacy_sampling_width_and_full_width_override():
    assert _leading_width(600, 20) == 252
    assert _leading_width(600, 20, 42) == 252
    assert _leading_width(600, 20, 80) == 480
    assert _leading_width(600, 20, 100) == 600
    # Existing text-height guard remains authoritative when larger than
    # requested percentage. This must be transparently shown in replay.
    assert _leading_width(600, 35, 10) == 245


def test_settings_json_roundtrip_and_missing_legacy_field(tmp_path):
    path = tmp_path / "settings.json"
    original = AppSettings(physical_row_projection_width_percent=75.0)
    original.to_json(path)
    restored = AppSettings.from_json(path)
    assert restored.physical_row_projection_width_percent == 75.0
    text = path.read_text(encoding="utf-8")
    assert '"physical_row_projection_width_percent": 75.0' in text

    import json
    obj = json.loads(text)
    del obj[FIELD]
    path.write_text(json.dumps(obj), encoding="utf-8")
    old_project = AppSettings.from_json(path)
    assert old_project.physical_row_projection_width_percent == 42.0


def _page():
    image = Image.new("RGB", (720, 440), "white")
    d = ImageDraw.Draw(image)
    for index in range(14):
        y = 14 + 26 * index
        d.rectangle((30, y, 42, y + 12), fill="black")
        d.rectangle((59, y, 192, y + 12), fill="black")
    return image


def _trace(width_percent):
    page = _page()
    settings = AppSettings(
        columns=1, column_width=550, manual_x=20, start_y=8,
        character_height=15, ordinary_auto_layout=False,
        layout_columns_policy="fixed",
        physical_row_projection_width_percent=width_percent,
    )
    trace = LayoutStepTrace()
    clear_layout_understanding_cache()
    try:
        result = understand_layout_core(page, settings, page_index=0, trace=trace)
        stages = {stage["key"]: stage for stage in trace.stages}
        assert result.layout.columns
        gap = stages["projection_gap_bridge"]
        split = stages["projection_tall_split"]
        column = gap["details"]["columns"][0]
        assert split["details"]["columns"][0] == column
        assert stages["physical_rows"]["rows"]
        return column, _format_stage(gap)
    finally:
        clear_layout_understanding_cache()
        page.close()


def test_live_projection_width_follows_saved_percentage_and_replay_reports_it():
    default, default_text = _trace(42.0)
    more, more_text = _trace(80.0)
    full, full_text = _trace(100.0)
    assert default["requested_width_percent"] == 42.0
    assert more["requested_width_percent"] == 80.0
    assert full["requested_width_percent"] == 100.0
    assert default["sample_strip_width"] < more["sample_strip_width"]
    assert more["sample_strip_width"] < full["sample_strip_width"]
    assert full["sample_strip_width"] == full["configured_column_width"]
    assert full["effective_width_percent"] == 100.0
    assert "设置采样 42.0% 栏宽" in default_text
    assert "设置采样 80.0% 栏宽" in more_text
    assert "设置采样 100.0% 栏宽" in full_text


def test_settings_dialog_rejects_bad_input_without_mutating_existing_project():
    from picture_capture.app import SettingsDialog

    for value in ["9", "101", "nan", "inf", "-inf", "invalid"]:
        settings = AppSettings(physical_row_projection_width_percent=42.0)
        fake = SimpleNamespace(
            parent=SimpleNamespace(settings=settings),
            vars={FIELD: SimpleNamespace(get=lambda v=value: v)},
        )
        assert SettingsDialog.save(fake, close=False, show_errors=False) is False
        assert settings.physical_row_projection_width_percent == 42.0
