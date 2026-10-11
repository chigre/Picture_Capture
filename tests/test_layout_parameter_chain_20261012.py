"""Regressions for Profile/per-page parameter provenance and composition."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.layout_character_height import apply_character_height_fallback
from picture_capture.layout_detection_legacy import (
    LayoutEstimate,
    VerticalRuleEstimate,
    _projection_layout_estimate,
)
from picture_capture.models import AppSettings


class _InkBackend:
    @staticmethod
    def analysis_ink_mask(gray, _settings):
        return np.asarray(gray, dtype=np.uint8) < 128


def test_projection_only_page_recovers_physical_height_without_fallback_label():
    image = Image.new("RGB", (320, 720), "white")
    draw = ImageDraw.Draw(image)
    for top in range(20, 660, 82):
        draw.rectangle((30, top, 190, top + 57), fill="black")
    estimate = LayoutEstimate(
        columns=1, start_y=0, column_width=220, gutter=0, manual_x=20,
        bottom_y=720, character_height=37, row_padding=1,
        source_boxes=1, method="reliable_fusion+projection_only+paddle_error=RuntimeError",
        column_starts=(20,),
    )
    corrected = apply_character_height_fallback(image, AppSettings(), estimate, _InkBackend)
    assert corrected.character_height == 58
    assert "observed_character_height=58" in corrected.method
    assert estimate.character_height == 37
    image.close()


def test_projection_column_discovery_can_report_a_real_separator(monkeypatch):
    """The 'detect' path must not drop all separator evidence by construction."""
    from picture_capture import layout_detection_legacy as detector

    image = Image.new("RGB", (800, 1200), "white")
    draw = ImageDraw.Draw(image)
    for y in range(110, 1120, 42):
        draw.rectangle((60, y, 325, y + 25), fill="black")
        draw.rectangle((470, y, 730, y + 25), fill="black")

    observed_intervals = []

    def fake_confirmed_rule(_ink, left, right, top, bottom, mode="auto"):
        observed_intervals.append((left, right))
        if right - left < 200:
            return None
        return VerticalRuleEstimate(400, 403, 380, 420, 0.98)

    monkeypatch.setattr(detector, "_detect_persistent_vertical_rule", fake_confirmed_rule)
    settings = AppSettings(layout_columns_policy="detect", columns=2)
    measured = _projection_layout_estimate(image, settings)
    assert measured.columns >= 2
    assert observed_intervals
    assert measured.separator_x == 402
    image.close()


def test_composed_policy_preserves_ink_height_evidence(monkeypatch):
    from picture_capture import layout_composition as composition
    from picture_capture import dictionary_page_layout_policy as policy

    image = Image.new("RGB", (320, 500), "white")
    settings = AppSettings(character_height=17, ordinary_auto_character_height=True)
    estimate = SimpleNamespace(
        character_height=30, method="reliable_fusion+projection_only"
        "+observed_character_height=30(n=40)",
    )

    def fake_resolve(_image, profile_settings, **_kwargs):
        return replace(profile_settings, character_height=30), estimate, {"character_height": 30}

    def fake_infer(_image, profile_settings, *, policy_resolver, **_kwargs):
        resolved, _estimate, applied = policy_resolver(_image, profile_settings)
        return SimpleNamespace(columns=[]), resolved, applied

    monkeypatch.setattr(policy, "_RAW_RESOLVE_PAGE_LAYOUT_POLICY", fake_resolve)
    monkeypatch.setattr(policy, "_RAW_INFER_DICTIONARY_PAGE_LAYOUT", fake_infer)
    monkeypatch.setattr(composition, "normalize_layout_roles", lambda *_args: None)
    layout, page_settings, applied = composition.infer_composed_physical_page_layout(
        image, settings, ops=SimpleNamespace(),
    )
    assert page_settings.character_height == 30
    assert applied["character_height"] == 30
    image.close()
