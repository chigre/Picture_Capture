from __future__ import annotations

from PIL import Image

from picture_capture.layout_detection import LayoutEstimate
from picture_capture.models import AppSettings
import picture_capture.dictionary_page_layout_policy as policy


def _settings() -> AppSettings:
    return AppSettings(
        columns=2,
        start_y=30,
        manual_x=40,
        column_width=120,
        gutter=20,
        character_height=24,
        row_padding=3,
        layout_columns_policy="fixed",
        profile_header_mode="none",
        profile_footer_mode="none",
        profile_side_content_mode="none",
        ordinary_auto_layout=False,
        ordinary_auto_columns=False,
        ordinary_auto_start_y=False,
        ordinary_auto_manual_x=False,
        ordinary_auto_column_width=False,
        ordinary_auto_gutter=False,
        ordinary_auto_character_height=False,
        ordinary_auto_row_padding=False,
    )


def _estimate() -> LayoutEstimate:
    return LayoutEstimate(
        columns=3,
        start_y=77,
        column_width=90,
        gutter=15,
        manual_x=70,
        bottom_y=470,
        character_height=31,
        row_padding=7,
        source_boxes=20,
        method="projection_fallback",
        canonical_width=500,
        column_starts=(70, 230, 390),
        column_rights=(160, 320, 480),
    )


def test_master_off_uses_project_geometry_without_running_page_estimator(monkeypatch):
    settings = _settings()
    image = Image.new("RGB", (500, 520), "white")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("per-page estimator must not run when master switch is off")

    monkeypatch.setattr(policy, "_projection_layout_estimate", forbidden)
    resolved, estimate, applied = policy.resolve_page_layout_policy(image, settings)

    assert estimate is None
    assert applied == {}
    assert resolved.columns == 2
    assert resolved.start_y == 30
    assert resolved.manual_x == 40
    assert resolved.column_width == 120
    assert resolved.gutter == 20
    starts, rights, gutters = policy._policy_geometry(500, resolved, estimate)
    assert starts == [40, 180]
    assert rights == [160, 300]
    assert gutters == [20, 0]


def test_master_on_replaces_only_selected_fields(monkeypatch):
    settings = _settings()
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_start_y = True
    settings.ordinary_auto_manual_x = True
    image = Image.new("RGB", (500, 520), "white")
    fake = _estimate()

    monkeypatch.setattr(policy, "_projection_layout_estimate", lambda *_a, **_k: fake)
    resolved, estimate, applied = policy.resolve_page_layout_policy(image, settings)

    assert estimate is fake
    assert applied == {"start_y": 77, "manual_x": 70}
    assert resolved.start_y == 77
    assert resolved.manual_x == 70
    # Unselected fields remain the project/Profile baseline.
    assert resolved.columns == 2
    assert resolved.column_width == 120
    assert resolved.gutter == 20
    assert resolved.character_height == 24

    starts, rights, gutters = policy._policy_geometry(500, resolved, estimate)
    # Per-page X is selected, so actual detected column starts are used; width
    # and gutter stay fixed because their switches are off.
    assert starts == [70, 230]
    assert rights == [190, 350]
    assert gutters == [20, 0]


def test_unselected_first_column_x_stays_fixed_even_when_page_estimate_moves(monkeypatch):
    settings = _settings()
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_start_y = True
    settings.ordinary_auto_manual_x = False
    image = Image.new("RGB", (500, 520), "white")
    fake = _estimate()

    monkeypatch.setattr(policy, "_projection_layout_estimate", lambda *_a, **_k: fake)
    resolved, estimate, applied = policy.resolve_page_layout_policy(image, settings)
    starts, rights, _gutters = policy._policy_geometry(500, resolved, estimate)

    assert applied == {"start_y": 77}
    assert resolved.manual_x == 40
    assert starts == [40, 180]
    assert rights == [160, 300]
