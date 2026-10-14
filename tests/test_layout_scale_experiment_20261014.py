from dataclasses import replace

from PIL import Image

from picture_capture.layout_scale_experiment import (
    choose_layout_scale, detect_at_scale, restore_source_estimate,
)
from picture_capture.layout_detection import LayoutEstimate
from picture_capture.models import AppSettings


def test_size_based_scale_selection(monkeypatch):
    monkeypatch.setenv("PICTURE_CAPTURE_LAYOUT_SCALE_EXPERIMENT", "auto")
    assert choose_layout_scale((1600, 2200)) == 1.0
    assert choose_layout_scale((2400, 3500)) == 0.75
    assert choose_layout_scale((3240, 4600)) == 0.50
    monkeypatch.setenv("PICTURE_CAPTURE_LAYOUT_SCALE_EXPERIMENT", "off")
    assert choose_layout_scale((3240, 4600)) == 1.0
    monkeypatch.setenv("PICTURE_CAPTURE_LAYOUT_SCALE_EXPERIMENT", "50")
    assert choose_layout_scale((2300, 3200)) == 0.75


def test_original_geometry_is_restored_after_half_size_detection(monkeypatch):
    monkeypatch.setenv("PICTURE_CAPTURE_LAYOUT_SCALE_EXPERIMENT", "auto")
    source = Image.new("RGB", (3240, 4600), "white")
    settings = AppSettings(
        columns=2, column_width=1498, gutter=76,
        character_height=64, start_y=120, manual_x=84,
        layout_scale_start_y=True, layout_scale_manual_x=True,
        layout_scale_character_height=True, layout_scale_row_padding=True,
    )
    observed = []
    def mock_detector(image, candidate, backend):
        observed.append((image.size, candidate.column_width, candidate.character_height))
        return LayoutEstimate(
            columns=2, start_y=60, column_width=749, gutter=38,
            manual_x=42, bottom_y=100, character_height=32,
            row_padding=4, source_boxes=50, separator_x=820,
            canonical_width=1620, column_starts=(42, 829),
            column_rights=(790, 1600),
        )
    result, factor = detect_at_scale(source, settings, object(), mock_detector)
    assert factor == 0.5
    assert observed == [((1620, 2300), 749, 32)]
    assert result.columns == 2
    assert result.start_y == 120
    assert result.manual_x == 84
    assert result.column_width == 1498
    assert result.gutter == 76
    assert result.character_height == 64
    assert result.separator_x == 1640
    assert result.canonical_width == 3240
    assert result.column_starts == (84, 1658)
    assert result.column_rights == (1580, 3200)


def test_off_preserves_exact_original_detector_path(monkeypatch):
    monkeypatch.setenv("PICTURE_CAPTURE_LAYOUT_SCALE_EXPERIMENT", "off")
    original = Image.new("RGB", (3240, 4600), "white")
    calls = []
    def mock_detector(image, candidate, backend):
        calls.append((image is original, candidate is settings))
        return object()
    settings = AppSettings()
    estimate, scale = detect_at_scale(original, settings, None, mock_detector)
    assert calls == [(True, True)]
    assert scale == 1.0


def test_safe_default_scaled_fields(monkeypatch):
    monkeypatch.setenv("PICTURE_CAPTURE_LAYOUT_SCALE_EXPERIMENT", "auto")
    source = Image.new("RGB", (3240, 4600), "white")
    settings = AppSettings(
        columns=2, column_width=1498, gutter=76,
        character_height=64, start_y=120, manual_x=84, row_padding=11,
    )
    def detector(image, candidate, backend):
        return LayoutEstimate(
            columns=3, start_y=30, column_width=740, gutter=40,
            manual_x=55, bottom_y=120, character_height=21,
            row_padding=2, source_boxes=60,
            canonical_width=1620, column_starts=(55, 835),
            column_rights=(790, 1580),
        )
    result, scale = detect_at_scale(source, settings, None, detector)
    assert scale == 0.5
    assert result.columns == 3
    assert result.column_width == 1480
    assert result.gutter == 80
    assert result.manual_x == 84
    assert result.start_y == 120
    assert result.character_height == 64
    assert result.row_padding == 11
    assert result.column_starts == ()


def test_shared_and_layout_denoise_are_independent(tmp_path):
    from picture_capture.adaptive_denoise import resolve_denoise_strength
    from picture_capture.ui.settings import schema
    off = AppSettings(analysis_denoise_enabled=False, layout_denoise_enabled=True)
    assert resolve_denoise_strength(off) == "off"
    on = AppSettings(analysis_denoise_enabled=True, layout_denoise_enabled=False)
    assert resolve_denoise_strength(on) == "auto"
    path = tmp_path / "settings.json"
    on.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.layout_denoise_enabled is False
    assert reopened.analysis_denoise_enabled is True
    assert schema.SETTING_CHOICES["analysis_denoise_strength"]["强"] == "strong"
    assert "analysis_denoise_strength" in schema.NORMAL_ADVANCED_FIELDS


def test_safe_scale_allowlist_persists_and_is_visible():
    from picture_capture.ui.settings import schema
    current = AppSettings()
    assert current.layout_scale_enabled is False
    assert (current.layout_scale_columns, current.layout_scale_column_width,
            current.layout_scale_gutter) == (True, True, True)
    assert (current.layout_scale_start_y, current.layout_scale_manual_x,
            current.layout_scale_character_height, current.layout_scale_row_padding) == (
                False, False, False, False,
            )
    checks = {name for _, name in schema.NORMAL_CHECKS}
    assert {"analysis_denoise_enabled", "layout_denoise_enabled",
            "layout_scale_enabled", "layout_scale_manual_x"} <= checks
