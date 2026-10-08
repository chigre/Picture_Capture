from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from picture_capture import layout_detection, profile_setup
from picture_capture.models import AppSettings
from picture_capture.profile_layout_bootstrap import (
    clear_profile_layout_bootstrap_cache,
    detect_profile_layout_parameters,
    install_profile_layout_bootstrap,
)


def _estimate() -> SimpleNamespace:
    return SimpleNamespace(
        columns=2,
        start_y=40,
        column_width=800,
        gutter=60,
        manual_x=30,
        bottom_y=1200,
        character_height=32,
        row_padding=1,
        source_boxes=0,
        method="projection",
        canonical_transform="identity",
        confidence=0.8,
        column_starts=(30, 890),
        column_rights=(830, 1690),
    )


def test_profile_bootstrap_uses_projection_without_mutating_settings(monkeypatch) -> None:
    clear_profile_layout_bootstrap_cache()
    seen: list[tuple[str, int]] = []

    def fake_projection(image, settings):
        seen.append((settings.layout_columns_policy, settings.columns))
        return _estimate()

    monkeypatch.setattr(layout_detection, "_projection_layout_estimate", fake_projection)
    settings = AppSettings(layout_columns_policy="fixed", columns=3)
    image = Image.new("RGB", (1800, 1300), "white")
    try:
        result = detect_profile_layout_parameters(image, settings)
    finally:
        image.close()

    assert seen == [("detect", 3)]
    assert settings.layout_columns_policy == "fixed"
    assert settings.columns == 3
    assert result.method.startswith("profile_bootstrap+projection")


def test_profile_bootstrap_reuses_identical_page_result(monkeypatch) -> None:
    clear_profile_layout_bootstrap_cache()
    calls = 0

    def fake_projection(image, settings):
        nonlocal calls
        calls += 1
        return _estimate()

    monkeypatch.setattr(layout_detection, "_projection_layout_estimate", fake_projection)
    settings = AppSettings()
    image = Image.new("RGB", (1200, 900), "white")
    try:
        first = detect_profile_layout_parameters(image, settings)
        second = detect_profile_layout_parameters(image, settings)
    finally:
        image.close()

    assert calls == 1
    assert second is first


def test_profile_setup_owns_bootstrap_detector_statically() -> None:
    assert profile_setup.detect_layout_parameters is detect_profile_layout_parameters

    before = profile_setup.detect_layout_parameters
    assert install_profile_layout_bootstrap() is None
    assert profile_setup.detect_layout_parameters is before


def test_gui_bootstrap_no_longer_installs_profile_detector() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    profile = (root / "src/picture_capture/profile_setup.py").read_text(encoding="utf-8")

    assert "install_profile_layout_bootstrap" not in gui
    assert "detect_profile_layout_parameters as detect_layout_parameters" in profile
