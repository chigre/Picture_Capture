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
    assert details["reason"] == "verified_whole_column_blank"
    assert details["ink_top"] == 40


def test_safety_distance_controls_gap_and_zero_still_never_cuts_ink():
    image = _page(40, prior=(6, 25))
    assert _refine(image, 36, _settings(paddle_separator_safety_px=4))[0] == 36
    assert _refine(image, 36, _settings(paddle_separator_safety_px=2))[0] == 38
    assert _refine(image, 36, _settings(paddle_separator_safety_px=0))[0] == 38


def test_larger_configured_clearance_tracks_real_ink_top_instead_of_sticking():
    page = _page(40, prior=(6, 25))
    # Re-running on an already-refined marker must obey newly saved settings.
    for safety_px, expected in ((2, 38), (3, 37), (6, 34), (8, 32)):
        refined, details = _refine(
            page, 38, _settings(paddle_separator_safety_px=safety_px),
        )
        assert refined == expected
        assert details["gap"] == safety_px
        assert details["ink_top"] == 40


def test_nearest_configured_safe_gap_beats_an_unnecessarily_farther_clean_row():
    page = _page(40, prior=(6, 25))
    # One isolated pixel is within the full-column admission tolerance. The
    # former score-first ranking picked a farther perfectly white Y instead.
    page[32, 96] = 0
    refined, details = _refine(
        page, 36, _settings(paddle_separator_safety_px=8),
    )
    assert refined == 32
    assert details["gap"] == 8
    assert details["whole_column_ink_score"] == 1


def test_no_ink_or_isolated_scratch_does_not_move():
    white = np.full((170, 130), 255, dtype=np.uint8)
    assert _refine(white, 35)[0] == 35
    white[40, 15:85] = 0
    value, details = _refine(white, 35)
    assert value == 35
    assert details["reason"] == "no_whole_column_blank_y"


def test_neighbouring_row_beyond_allowed_shift_is_not_used():
    distant = _page(100, prior=(10, 30))
    refined, details = _refine(distant, 48)
    assert refined == 48
    assert details["reason"] == "no_whole_column_blank_y"


def test_when_previous_descender_occupies_safe_gap_keep_original():
    image = _page(40, prior=(21, 38))
    position, details = _refine(image, 33)
    assert position == 33
    assert details["reason"] == "no_whole_column_blank_y"


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
    assert "已有 PDIC 横线" in schema.CHECK_HELP["paddle_refine_separator_y"]
    assert "不依赖此实验开关" in schema.CHECK_HELP["separator_y_ink_safe_gap"]
    assert any("手动按钮独立" in label for label, _ in schema.SEPARATOR_Y_CHECKS)


def test_far_right_tall_character_requires_a_whiter_full_column_y():
    # The word-head anchor is blank at Y38, but another tall glyph far to
    # the right occupies Y37–39. Fixed ink_top-2 would slice that glyph.
    image = _page(40, prior=(6, 25))
    image[37:40, 96:100] = 0
    refined, details = _refine(image, 36)
    assert refined == 35
    assert details["reason"] == "verified_whole_column_blank"
    assert details["full_roi_x1"] > details["anchor_roi_x1"]
    assert details["whole_column_ink_score"] == 0
    # All three verification rows must have no black pixels across the column.
    assert not np.any(image[refined - 1:refined + 2, 10:110] < 185)


def test_no_whole_column_white_position_must_not_force_a_local_only_line():
    # A vertical extension on the far right occupies *all* feasible Y rows
    # above the detected headword. A locally blank word ROI is not enough.
    image = _page(40)
    image[26:40, 95:105] = 0
    refined, details = _refine(image, 34)
    assert refined == 34
    assert details["reason"] == "no_whole_column_blank_y"


def test_whole_column_selection_moves_up_or_down_from_saved_marker():
    image = _page(40, prior=(6, 25))
    assert _refine(image, 32)[0] == 38    # downward towards the first line
    assert _refine(image, 42)[0] == 38    # upward out of the first-line glyph


def test_full_column_whiteness_is_preferred_to_fixed_safety_offset():
    image = _page(40, prior=(6, 25))
    image[38, 96:100] = 0
    image[37, 96:100] = 0
    refined, diagnostics = _refine(image, 36)
    assert refined == 35
    assert diagnostics["gap"] == 5
    assert diagnostics["whole_column_ink_score"] == 0
