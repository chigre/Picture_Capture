from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from picture_capture import dictionary_page_layout_policy as policy
from picture_capture import layout_detection
from picture_capture.models import AppSettings
from picture_capture.processing import _ordinary_settings_for_shared_geometry


def test_page_policy_uses_reliable_layout_estimate(monkeypatch) -> None:
    settings = AppSettings()
    settings.columns = 2
    settings.start_y = 100
    settings.manual_x = 30
    settings.column_width = 1000
    settings.gutter = 50
    settings.character_height = 40
    settings.row_padding = 2
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_columns = False
    settings.ordinary_auto_start_y = True
    settings.ordinary_auto_manual_x = False
    settings.ordinary_auto_column_width = True
    settings.ordinary_auto_gutter = True
    settings.ordinary_auto_character_height = True
    settings.ordinary_auto_row_padding = True

    estimate = SimpleNamespace(
        columns=2,
        start_y=134,
        manual_x=33,
        column_width=1204,
        gutter=65,
        character_height=51,
        row_padding=1,
        method="reliable_fusion",
        confidence=0.93,
    )
    # Exercise the explicit raw-policy contract, independently of installed
    # Product/Profile anchoring wrappers.
    # Policy intentionally resolves the detector through the live module binding;
    # patch that authoritative seam rather than the policy module's old by-value import.
    monkeypatch.setattr(layout_detection, "detect_layout_parameters", lambda image, s: estimate)

    page_settings, returned_estimate, applied = policy._RAW_RESOLVE_PAGE_LAYOUT_POLICY(
        Image.new("RGB", (2536, 3765), "white"),
        settings,
    )

    assert returned_estimate is estimate
    assert page_settings.columns == 2  # auto-columns was deliberately disabled
    assert page_settings.start_y == 134
    assert page_settings.column_width == 1204
    assert page_settings.gutter == 65
    assert page_settings.character_height == 51
    assert page_settings.row_padding == 1
    assert applied["column_width"] == 1204
    assert applied["gutter"] == 65


def test_ordinary_settings_freeze_shared_column_geometry() -> None:
    settings = AppSettings()
    settings.ordinary_auto_layout = True
    settings.follow_column_deformation = True
    settings.columns = 2
    settings.manual_x = 10
    settings.column_width = 900
    settings.gutter = 20

    geometry = SimpleNamespace(
        column_starts=[33, 1302],
        column_widths=[1204, 1204],
        top=134,
        bottom=3765,
    )

    frozen = _ordinary_settings_for_shared_geometry(
        settings,
        geometry,
        method="left_edge",
    )

    assert frozen.ordinary_auto_layout is False
    assert frozen.follow_column_deformation is False
    assert frozen.columns == 2
    assert frozen.start_y == 134
    assert frozen.manual_x == 33
    assert frozen.column_width == 1204
    assert frozen.gutter == 65

    starts = [
        frozen.manual_x
        + index * (frozen.column_width + frozen.gutter)
        + frozen.column_start_offsets[index]
        for index in range(frozen.columns)
    ]
    assert starts == [33, 1302]
