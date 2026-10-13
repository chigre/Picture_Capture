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
               for _title, name in schema.OCR_ADVANCED_CHECKS)
    assert "默认关闭" in schema.CHECK_HELP["separator_y_ink_safe_gap"]
    settings = AppSettings(separator_y_ink_safe_gap=True)
    location = tmp_path / "settings.json"
    settings.to_json(location)
    assert AppSettings.from_json(location).separator_y_ink_safe_gap is True
