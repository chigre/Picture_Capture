"""The Settings Center's physical-row projection width changes REAL Layout sampling."""
from __future__ import annotations

import json
from dataclasses import fields

from PIL import Image, ImageDraw
import pytest

from picture_capture.dictionary_page_design import _leading_width
from picture_capture.layout_composition import infer_composed_physical_page_layout
from picture_capture.layout_step_trace import LayoutStepTrace
from picture_capture.models import AppSettings
from picture_capture.ui.settings import schema


NAME = "physical_row_projection_width_percent"


def _page() -> Image.Image:
    # Only the full-column pass sees the four distant, valid rows.
    image = Image.new("RGB", (700, 365), "white")
    draw = ImageDraw.Draw(image)
    for i in range(8):
        y = 24 + 25 * i
        draw.rectangle((32, y, 138, y + 16), fill="black")
    for i in range(4):
        y = 24 + 25 * (8 + i)
        draw.rectangle((460, y, 558, y + 16), fill="black")
    return image


def _settings(percent: float) -> AppSettings:
    return AppSettings(
        columns=1, manual_x=20, column_width=600, start_y=8,
        character_height=18, ordinary_auto_layout=False,
        physical_row_projection_width_percent=percent,
    )


def test_old_default_exact_and_actual_percentage_wider():
    assert AppSettings().physical_row_projection_width_percent == 42.0
    assert _leading_width(600, 35) == 252
    assert _leading_width(600, 35, 42.0) == 252
    assert _leading_width(600, 35, 75.0) == 450
    assert _leading_width(600, 35, 100.0) == 600
    assert _leading_width(600, 35, 10.0) == 245  # historical 7H safeguard
    assert _leading_width(600, 35, float("nan")) == 252


def test_persisted_project_json_round_trip_and_older_project(tmp_path):
    path = tmp_path / "settings.json"
    settings = _settings(85.0)
    settings.to_json(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw[NAME] == 85.0
    assert AppSettings.from_json(path).physical_row_projection_width_percent == 85.0
    del raw[NAME]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert AppSettings.from_json(path).physical_row_projection_width_percent == 42.0
    assert NAME in {item.name for item in fields(AppSettings)}


@pytest.mark.parametrize("bad", [0, 9.9, 100.1, 101, float("nan"), float("inf"), "invalid"])
def test_invalid_percentage_is_rejected_before_project_persistence(bad):
    settings = AppSettings()
    with pytest.raises(ValueError, match="10–100%"):
        settings.physical_row_projection_width_percent = bad
    assert settings.physical_row_projection_width_percent == 42.0
    with pytest.raises(ValueError, match="10–100%"):
        AppSettings(physical_row_projection_width_percent=bad)


def test_settings_center_ordinary_advanced_not_ocr():
    assert NAME in schema.NORMAL_ADVANCED_FIELDS
    assert NAME not in schema.OCR_ADVANCED_FIELDS
    assert schema.SETTING_UNITS[NAME] == "% 单栏宽"
    assert schema.SETTING_SPIN[NAME] == (10.0, 100.0, 1.0)
    assert "42%" in schema.SETTING_HELP[NAME]
    assert any(name == NAME and cast is float for _label, name, cast in schema.FIELDS)


def test_actual_production_rows_and_replay_strip_follow_setting():
    image = _page()
    try:
        low_trace = LayoutStepTrace()
        high_trace = LayoutStepTrace()
        low, _, _ = infer_composed_physical_page_layout(
            image, _settings(42.0), trace=low_trace,
        )
        high, _, _ = infer_composed_physical_page_layout(
            image, _settings(100.0), trace=high_trace,
        )
        # Diagnostics must not change the actual production rows or roles.
        low_plain, _, _ = infer_composed_physical_page_layout(
            image, _settings(42.0),
        )
        high_plain, _, _ = infer_composed_physical_page_layout(
            image, _settings(100.0),
        )
        def rows(layout):
            return [(int(line.y0), int(line.y1), str(line.role))
                    for col in layout.columns for line in col.lines]
        assert rows(low) == rows(low_plain)
        assert rows(high) == rows(high_plain)
        def sample(trace):
            return next(item for item in trace.stages
                        if item["key"] == "projection_gap_bridge")["details"]["columns"][0]
        l = sample(low_trace)
        h = sample(high_trace)
        assert l["requested_width_percent"] == 42.0
        assert h["requested_width_percent"] == 100.0
        assert l["sample_strip_width"] == 252
        assert h["sample_strip_width"] == 600
        assert l["effective_width_percent"] == 42.0
        assert h["effective_width_percent"] == 100.0
        assert l["output_rows"] < h["output_rows"]
        assert len(low.columns[0].lines) < len(high.columns[0].lines)
        assert [x["key"] for x in high_trace.stages].index(
            "projection_tall_split",
        ) < [x["key"] for x in high_trace.stages].index("physical_rows")
    finally:
        image.close()
