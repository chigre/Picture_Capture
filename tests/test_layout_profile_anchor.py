from __future__ import annotations

from dataclasses import replace

from picture_capture.layout_profile_anchor import anchor_resolved_layout_to_profile
from picture_capture.models import AppSettings


def _profile() -> AppSettings:
    settings = AppSettings()
    settings.columns = 2
    settings.start_y = 134
    settings.manual_x = 32
    settings.column_width = 1204
    settings.gutter = 65
    settings.character_height = 51
    settings.row_padding = 1
    return settings


def test_sparse_page_cannot_replace_stable_profile_width_directly() -> None:
    profile = _profile()
    resolved = replace(profile)
    resolved.column_width = 1182

    anchored, applied = anchor_resolved_layout_to_profile(
        profile,
        resolved,
        {"column_width": 1182},
    )

    # A page such as the first dictionary page may contain too few headwords to
    # estimate the true column width.  The page observation is therefore only a
    # small adjustment around the multi-page Profile baseline, never a direct
    # replacement.
    assert anchored.column_width == 1200
    assert applied["column_width"] == 1200
    assert abs(anchored.column_width - profile.column_width) < abs(1182 - profile.column_width)


def test_large_single_page_width_outlier_is_bounded_by_profile_anchor() -> None:
    profile = _profile()
    resolved = replace(profile)
    resolved.column_width = 900

    anchored, applied = anchor_resolved_layout_to_profile(
        profile,
        resolved,
        {"column_width": 900},
    )

    # Width movement is capped at 1.5% of the Profile baseline (18 px here).
    assert anchored.column_width == 1186
    assert applied["column_width"] == 1186


def test_stable_fields_anchor_but_page_registration_remains_adaptive() -> None:
    profile = _profile()
    resolved = replace(profile)
    resolved.columns = 3
    resolved.start_y = 872
    resolved.manual_x = 59
    resolved.column_width = 1182
    resolved.gutter = 67
    resolved.character_height = 49
    resolved.row_padding = 4

    anchored, applied = anchor_resolved_layout_to_profile(
        profile,
        resolved,
        {
            "columns": 3,
            "start_y": 872,
            "manual_x": 59,
            "column_width": 1182,
            "gutter": 67,
            "character_height": 49,
            "row_padding": 4,
        },
    )

    # Dictionary-template facts come from the multi-page Profile.
    assert anchored.columns == 2
    assert anchored.column_width == 1200
    assert anchored.gutter == 65
    assert anchored.character_height == 50
    assert anchored.row_padding == 1

    # Scan placement remains page-specific.
    assert anchored.start_y == 872
    assert anchored.manual_x == 59
    assert applied["start_y"] == 872
    assert applied["manual_x"] == 59


def test_unselected_stable_fields_are_not_modified() -> None:
    profile = _profile()
    resolved = replace(profile)
    resolved.column_width = 1182

    anchored, applied = anchor_resolved_layout_to_profile(
        profile,
        resolved,
        {"manual_x": 59},
    )

    # The anchor only acts on fields that the user explicitly enabled for auto.
    assert anchored.column_width == 1182
    assert applied == {"manual_x": 59}
