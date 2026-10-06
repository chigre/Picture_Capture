from dataclasses import fields, replace
import json
from pathlib import Path
import pickle

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

    # ProcessPool spawn serializes AppSettings. The native dataclass field
    # resolves without any bootstrap subclass/rebinding.
    spawned = pickle.loads(pickle.dumps(enabled))
    assert type(spawned) is AppSettings
    assert spawned.layout_mask_illustrations is True

    path = tmp_path / "settings.json"
    enabled.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.layout_mask_illustrations is True

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("layout_mask_illustrations", None)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    reopened_legacy = AppSettings.from_json(path)
    assert reopened_legacy.layout_mask_illustrations is False


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


def test_static_path_and_in_memory_detectors_share_one_processing_core_owner(tmp_path: Path):
    from picture_capture import processing_core

    image = Image.new("RGB", (320, 280), "white")
    path = tmp_path / "page.png"
    image.save(path)
    settings = AppSettings(columns=1, manual_x=20, column_width=260, start_y=0)
    try:
        from_image = processing_core.detect_illustration_regions_from_image(
            image, settings
        )
        from_path = processing_core.detect_illustration_regions(path, settings)
    finally:
        image.close()

    assert from_path == from_image
    assert processing_core.detect_illustration_regions.__module__.endswith(
        "processing_core"
    )
    assert processing_core.detect_illustration_regions_from_image.__module__.endswith(
        "processing_core"
    )


def test_core_composition_keeps_static_detector_and_installs_only_layout_wrapper():
    from picture_capture import processing, processing_core
    from picture_capture.bootstrap.core import build_core_services

    before = processing.detect_illustration_regions
    assert before is processing_core.detect_illustration_regions

    build_core_services()

    assert processing.detect_illustration_regions is before
    assert processing.detect_illustration_regions is processing_core.detect_illustration_regions
    assert bool(getattr(processing, "_pc_layout_illustration_mask_installed", False))

    root = Path(__file__).resolve().parents[1]
    runtime_source = (
        root / "src" / "picture_capture" / "layout_illustration_mask_runtime.py"
    ).read_text(encoding="utf-8")
    core_source = (
        root / "src" / "picture_capture" / "bootstrap" / "core.py"
    ).read_text(encoding="utf-8")
    assert "def install_layout_illustration_mask_settings(" not in runtime_source
    assert "def detect_illustration_regions_from_image(" not in runtime_source
    assert "detect_illustration_regions = detect_illustration_regions_from_path" not in runtime_source
    assert "install_layout_illustration_mask_settings" not in core_source
    assert "install_layout_illustration_mask_runtime(processing_module)" in core_source


def test_gui_composition_exposes_switch_before_generic_settings_help_scan():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "picture_capture" / "bootstrap" / "gui.py"
    ).read_text(encoding="utf-8")
    ui_install = source.index("install_layout_illustration_mask_ui(app_module)")
    help_install = source.index("install_settings_parameter_help(app_module)")
    assert ui_install < help_install
