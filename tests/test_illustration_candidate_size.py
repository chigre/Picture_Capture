"""Candidate width and height thresholds, including pixel and percentage units."""
from picture_capture.models import AppSettings
from picture_capture.illustration_candidate_size import illustration_candidate_min_dimensions


def test_percent_dimensions_follow_analysis_crop_axes():
    settings = AppSettings()
    assert illustration_candidate_min_dimensions(settings, 2000, 3000) == (110, 84)
    settings.illustration_detect_min_width = 5
    settings.illustration_detect_min_height = 3
    assert illustration_candidate_min_dimensions(settings, 2000, 3000) == (100, 90)


def test_pixel_dimensions_are_not_rescaled():
    settings = AppSettings()
    settings.illustration_detect_size_unit = "px"
    settings.illustration_detect_min_width = 120
    settings.illustration_detect_min_height = 85
    assert illustration_candidate_min_dimensions(settings, 2000, 3000) == (120, 85)
    assert illustration_candidate_min_dimensions(settings, 500, 800) == (120, 85)


def test_invalid_unit_falls_back_to_percent_and_negative_dimensions_clamp():
    settings = AppSettings()
    settings.illustration_detect_size_unit = "invalid"
    settings.illustration_detect_min_width = -10
    settings.illustration_detect_min_height = 3
    assert illustration_candidate_min_dimensions(settings, 2000, 3000) == (0, 90)
