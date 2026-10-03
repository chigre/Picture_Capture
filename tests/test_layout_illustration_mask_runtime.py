from dataclasses import fields, replace
from pathlib import Path

from PIL import Image

from picture_capture.models import AppSettings, PolygonRegion
from picture_capture.layout_illustration_mask_runtime import (
    SETTING_NAME,
    layout_mask_region_is_large_enough,
    mask_large_illustrations_for_layout,
)


def _rect(x0: int, y0: int, x1: int, y1: int) -> PolygonRegion:
    return PolygonRegion("", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_layout_illustration_mask_is_native_persistable_setting(tmp_path: Path):
    names = {item.name for item in fields(AppSettings)}
    assert SETTING_NAME in names

    defaults = AppSettings()
    assert defaults.layout_mask_illustrations is False

    enabled = AppSettings(layout_mask_illustrations=True)
    copied = replace(enabled)
    assert copied.layout_mask_illustrations is True

    path = tmp_path / "settings.json"
    enabled.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.layout_mask_illustrations is True


def test_layout_mask_rejects_display_head_sized_square_candidate():
    # 4 ordinary glyph-heights square: large enough to be visually prominent,
    # but still compatible with an oversized dictionary display head.
    allowed, reason = layout_mask_region_is_large_enough(
        _rect(10, 10, 90, 90),
        character_height=20,
        column_width=300,
    )
    assert allowed is False
    assert reason == "headlike"


def test_layout_mask_accepts_substantially_larger_illustration_candidate():
    allowed, reason = layout_mask_region_is_large_enough(
        _rect(20, 30, 180, 230),
        character_height=20,
        column_width=300,
    )
    assert allowed is True
    assert reason == "ok"


def test_mask_whitens_only_safe_large_candidates():
    image = Image.new("RGB", (320, 280), (120, 120, 120))
    small_head = _rect(10, 10, 90, 90)
    illustration = _rect(120, 40, 300, 250)
    settings = AppSettings(
        layout_mask_illustrations=True,
        character_height=20,
        column_width=300,
        columns=1,
    )

    def detector(_image, _settings, **_kwargs):
        return [small_head, illustration]

    masked, stats = mask_large_illustrations_for_layout(
        image,
        settings,
        detector=detector,
    )
    try:
        assert masked is not image
        assert stats.detected == 2
        assert stats.masked == 1
        assert stats.rejected_headlike == 1
        assert masked.getpixel((50, 50)) == (120, 120, 120)
        assert masked.getpixel((200, 150)) == (255, 255, 255)
    finally:
        if masked is not image:
            masked.close()
        image.close()


def test_disabled_switch_is_zero_cost_identity_path():
    image = Image.new("RGB", (100, 100), "white")
    settings = AppSettings(layout_mask_illustrations=False)
    called = False

    def detector(*_args, **_kwargs):
        nonlocal called
        called = True
        return []

    masked, stats = mask_large_illustrations_for_layout(
        image,
        settings,
        detector=detector,
    )
    try:
        assert masked is image
        assert called is False
        assert stats.detected == 0
        assert stats.masked == 0
    finally:
        image.close()


def test_processing_uses_shared_in_memory_illustration_detector_and_wrapper():
    from picture_capture import processing

    assert processing.detect_illustration_regions.__module__.endswith(
        "layout_illustration_mask_runtime"
    )
    assert bool(getattr(processing, "_pc_layout_illustration_mask_installed", False))


def test_launcher_exposes_switch_before_generic_settings_help_scan():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "picture_capture" / "launcher.py").read_text(
        encoding="utf-8"
    )
    ui_install = source.index("install_layout_illustration_mask_ui(app_module)")
    help_install = source.index("install_settings_parameter_help(app_module)")
    assert ui_install < help_install
