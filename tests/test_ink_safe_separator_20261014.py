"""Ink-safe OCR/layout separator correction: opt-in and no false movement."""
from __future__ import annotations

import numpy as np

from picture_capture.ink_safe_separator import refine_to_verified_white_gap
from picture_capture.models import AppSettings
from picture_capture.ui.settings import schema


def test_verified_real_gap_moves_only_when_old_separator_crosses_ink():
    gray = np.full((110, 55), 255, dtype=np.uint8)
    # Printed descender obstructs the original Y=50, but a three-row white
    # valley exists immediately above the glyphs.
    gray[48:53, :35] = 45
    corrected, evidence = refine_to_verified_white_gap(
        gray, 50, 50, 28,
    )
    assert corrected < 48
    assert abs(corrected - 50) <= 7
    assert evidence["gap_corrected"] is True
    assert evidence["gap_reason"] == "verified_gap"


def test_already_safe_location_keeps_precise_y_and_reports_no_correction():
    gray = np.full((110, 55), 255, dtype=np.uint8)
    gray[60:85, :] = 40
    y, record = refine_to_verified_white_gap(gray, 50, 50, 28)
    assert y == 50
    assert record["gap_corrected"] is False
    assert record["gap_reason"] == "already_ink_safe"


def test_dense_ink_without_safe_gap_abstains_instead_of_crossing_glyphs():
    gray = np.full((110, 55), 30, dtype=np.uint8)
    y, record = refine_to_verified_white_gap(gray, 50, 50, 28)
    assert y == 50
    assert record["gap_reason"] == "no_three_row_white_gap"


def test_outside_anchor_and_invalid_roi_are_noops():
    gray = np.full((120, 50), 80, dtype=np.uint8)
    assert refine_to_verified_white_gap(gray, 70, 50, 28)[0] == 70
    assert refine_to_verified_white_gap(gray[:5], 2, 2, 28)[0] == 2


def test_shared_refiner_is_reversible_and_does_not_change_candidate_classification(monkeypatch):
    import picture_capture.separator_y_refinement as shared

    ink = np.full((110, 55), 255, dtype=np.uint8)
    ink[48:53, :35] = 45
    monkeypatch.setattr(
        shared, "_ENGINE_REFINE_SEPARATOR_Y",
        lambda *a, **k: (50, {"reason": "original"}),
    )
    settings = AppSettings()
    assert settings.separator_y_ink_safe_gap is False
    legacy_y, legacy_diag = shared.refine_separator_y(ink, 50, 28, settings)
    assert legacy_y == 50 and "ink_gap_guard" not in legacy_diag

    settings.separator_y_ink_safe_gap = True
    experimental_y, info = shared.refine_separator_y(ink, 50, 28, settings)
    assert experimental_y < legacy_y
    assert info["ink_gap_guard"] and info["gap_corrected"]
    assert info["reason"] == "original"

    settings.separator_y_ink_safe_gap = False
    assert shared.refine_separator_y(ink, 50, 28, settings)[0] == legacy_y


def test_ink_gap_toggle_visible_in_settings_center_with_specific_explanation(tmp_path):
    assert any(name == "separator_y_ink_safe_gap"
               for _title, name in schema.SEPARATOR_Y_CHECKS)
    assert "默认关闭" in schema.CHECK_HELP["separator_y_ink_safe_gap"]
    settings = AppSettings(separator_y_ink_safe_gap=True)
    location = tmp_path / "settings.json"
    settings.to_json(location)
    assert AppSettings.from_json(location).separator_y_ink_safe_gap is True


def test_experimental_white_gap_thresholds_roundtrip_and_ui_help(tmp_path):
    from dataclasses import fields
    names = {
        "separator_y_ink_safe_max_fraction": 0.25,
        "separator_y_ink_safe_ink_threshold": 185,
        "separator_y_ink_safe_existing_ink_ratio": 0.045,
        "separator_y_ink_safe_gap_ink_ratio": 0.02,
    }
    defaults = AppSettings()
    assert names.items() <= {f.name: getattr(defaults, f.name) for f in fields(defaults)}.items()
    shown = {name for _, name, _ in schema.FIELDS}
    assert names.keys() <= shown
    assert names.keys() <= set(schema.SEPARATOR_Y_FIELDS)
    for name in names:
        assert name in schema.SETTING_HELP
        assert "默认" in schema.SETTING_HELP[name]
        assert name in schema.SETTING_SPIN
    changed = AppSettings(
        separator_y_ink_safe_gap=True,
        separator_y_ink_safe_max_fraction=0.12,
        separator_y_ink_safe_ink_threshold=125,
        separator_y_ink_safe_existing_ink_ratio=0.025,
        separator_y_ink_safe_gap_ink_ratio=0.01,
    )
    file = tmp_path / "settings.json"
    changed.to_json(file)
    restored = AppSettings.from_json(file)
    for name in names:
        assert getattr(restored, name) == getattr(changed, name)


def test_white_gap_search_fraction_and_grayscale_threshold_affect_runtime():
    gray = np.full((110, 55), 255, dtype=np.uint8)
    gray[48:53, :35] = 45
    original, _ = refine_to_verified_white_gap(gray, 50, 50, 28)
    assert original < 48
    narrower, _ = refine_to_verified_white_gap(gray, 50, 50, 28, max_fraction=0.05)
    assert narrower == 50
    ignored_ink, _ = refine_to_verified_white_gap(gray, 50, 50, 28, ink_threshold=20)
    assert ignored_ink == 50


def test_white_gap_thresholds_are_actually_consumed_by_shared_refiner(monkeypatch):
    import picture_capture.separator_y_refinement as shared

    gray = np.full((110, 55), 255, dtype=np.uint8)
    gray[48:53, :35] = 45
    monkeypatch.setattr(
        shared, "_ENGINE_REFINE_SEPARATOR_Y",
        lambda *args, **kwargs: (50, {"reason": "unchanged"}),
    )
    settings = AppSettings(separator_y_ink_safe_gap=True)
    default_y, _ = shared.refine_separator_y(gray, 50, 28, settings)
    assert default_y < 48
    settings.separator_y_ink_safe_max_fraction = 0.05
    assert shared.refine_separator_y(gray, 50, 28, settings)[0] == 50
    settings.separator_y_ink_safe_max_fraction = 0.25
    settings.separator_y_ink_safe_ink_threshold = 20
    assert shared.refine_separator_y(gray, 50, 28, settings)[0] == 50
    settings.separator_y_ink_safe_ink_threshold = 185
    settings.separator_y_ink_safe_existing_ink_ratio = 0.20
    assert shared.refine_separator_y(gray, 50, 28, settings)[0] < 48


def test_invalid_new_thresholds_rejected_even_outside_spinbox(tmp_path):
    import pytest

    defaults = AppSettings()
    for key, invalid in (
        ("separator_y_ink_safe_max_fraction", 0.5),
        ("separator_y_ink_safe_existing_ink_ratio", -0.001),
        ("separator_y_ink_safe_gap_ink_ratio", float("nan")),
        ("separator_y_ink_safe_ink_threshold", 300),
        ("separator_y_ink_safe_ink_threshold", 2.5),
    ):
        with pytest.raises(ValueError):
            setattr(defaults, key, invalid)
    path = tmp_path / "saved.json"
    defaults.to_json(path)
    assert AppSettings.from_json(path).separator_y_ink_safe_ink_threshold == 185


def test_existing_ink_ratio_controls_whether_previously_safe_line_is_moved():
    gray = np.full((110, 55), 255, dtype=np.uint8)
    gray[50, :2] = 35  # 2/55 = 3.6% dark ink: safe under 4.5% default.
    untouched, report = refine_to_verified_white_gap(gray, 50, 50, 28)
    assert untouched == 50 and report["gap_reason"] == "already_ink_safe"
    moved, report = refine_to_verified_white_gap(
        gray, 50, 50, 28, existing_ink_ratio=0.01,
    )
    assert moved < 50 and report["gap_corrected"]


def test_candidate_gap_ink_ratio_controls_three_row_acceptance():
    gray = np.full((110, 55), 255, dtype=np.uint8)
    gray[:, 0] = 45  # Every row has 1/55 (1.8%) dark ink.
    gray[48:53, :35] = 45  # Original separator definitely crosses text.
    found, report = refine_to_verified_white_gap(gray, 50, 50, 28)
    assert found < 48 and report["gap_corrected"]
    forbidden, report = refine_to_verified_white_gap(
        gray, 50, 50, 28, gap_ink_ratio=0.0,
    )
    assert forbidden == 50 and report["gap_reason"] == "no_three_row_white_gap"
