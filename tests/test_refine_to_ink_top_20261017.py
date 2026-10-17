"""Regression: explicit PDIC refinement targets current first-row ink, not valley centre."""
from dataclasses import replace

import numpy as np

from picture_capture.marker_refinement_top_edge import refine_existing_marker_to_ink_top
from picture_capture.models import AppSettings
from picture_capture.ui.settings import schema


def _settings(**changes):
    settings = AppSettings()
    settings.paddle_separator_search_ratio = 0.30
    settings.separator_y_max_shift_ratio = 0.45
    settings.paddle_separator_safety_px = 2
    settings.paddle_separator_roi_width_ratio = 100.0
    settings.paddle_separator_column_margin = 0
    settings.paddle_separator_band_radius = 2
    for name, value in changes.items():
        setattr(settings, name, value)
    return settings


def _page(top=40, *, prior=None, row_height=26):
    gray = np.full((170, 130), 255, dtype=np.uint8)
    if prior is not None:
        gray[prior[0]:prior[1], 15:85] = 0
    gray[top:top + row_height - 5, 15:85] = 0
    return gray


def _refine(gray, old_y, settings=None, *, row_height=26):
    return refine_existing_marker_to_ink_top(
        gray, old_y, row_height, _settings() if settings is None else settings,
        anchor_x=15, column_left=10, column_right=110,
    )


def test_large_and_small_blank_gaps_use_same_true_ink_top_margin():
    # Neither a wide previous-line gap nor a small one should decide the
    # separator's distance to the *current* headword.
    wide = _page(40, prior=(6, 25))
    tight = _page(74, prior=(38, 59))
    assert _refine(wide, 32)[0] == 38
    assert _refine(wide, 37)[0] == 38
    assert _refine(tight, 65)[0] == 72
    assert _refine(tight, 68)[0] == 72


def test_marker_within_printed_glyph_can_move_up_to_safe_top():
    position, details = _refine(_page(40, prior=(6, 25)), 42)
    assert position == 38
    assert details["reason"] == "verified_ink_top"
    assert details["ink_top"] == 40


def test_safety_distance_controls_gap_and_zero_still_never_cuts_ink():
    image = _page(40, prior=(6, 25))
    assert _refine(image, 36, _settings(paddle_separator_safety_px=4))[0] == 36
    assert _refine(image, 36, _settings(paddle_separator_safety_px=2))[0] == 38
    assert _refine(image, 36, _settings(paddle_separator_safety_px=0))[0] == 39


def test_no_ink_or_isolated_scratch_does_not_move():
    white = np.full((170, 130), 255, dtype=np.uint8)
    assert _refine(white, 35)[0] == 35
    white[40, 15:85] = 0
    value, details = _refine(white, 35)
    assert value == 35
    assert details["reason"] == "no_verified_headword_top"


def test_neighbouring_row_beyond_allowed_shift_is_not_used():
    distant = _page(100, prior=(10, 30))
    refined, details = _refine(distant, 48)
    assert refined == 48
    assert details["reason"] == "no_verified_headword_top"


def test_when_previous_descender_occupies_safe_gap_keep_original():
    image = _page(40, prior=(21, 38))
    position, details = _refine(image, 33)
    assert position == 33
    assert details["reason"] == "no_verified_headword_top"


def test_zero_max_shift_is_explicit_noop():
    image = _page(40)
    pos, details = _refine(
        image, 32, _settings(separator_y_max_shift_ratio=0),
    )
    assert pos == 32
    assert details["reason"] == "max_shift_zero"


def test_settings_center_explains_automatic_and_manual_scope_accurately():
    assert "字顶" in schema.SETTING_HELP["paddle_separator_safety_px"]
    assert "最大" in schema.SETTING_HELP["separator_y_max_shift_ratio"]
    assert "已保存 PDIC" in schema.SETTING_HELP["paddle_refine_separator_y"]
    assert "与此实验开关无关" in schema.SETTING_HELP["separator_y_ink_safe_gap"]
    assert any("手动按钮独立" in label for label, _ in schema.SEPARATOR_Y_CHECKS)
