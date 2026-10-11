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


def test_profile_bootstrap_uses_printed_ink_height_not_page_height_guess(monkeypatch) -> None:
    from PIL import ImageDraw
    from picture_capture.layout_detection import LayoutEstimate

    clear_profile_layout_bootstrap_cache()

    def fake_projection(image, settings):
        return LayoutEstimate(
            columns=2, start_y=38, column_width=660,
            gutter=32, manual_x=4, bottom_y=2090,
            character_height=17, row_padding=1,
            source_boxes=4, method="projection_fallback",
            column_starts=(4, 711), column_rights=(667, 1374),
        )

    monkeypatch.setattr(layout_detection, "_projection_layout_estimate", fake_projection)
    # Exact original XDHYCD_0001 dimensions and approximate printed geometry;
    # actual ink rows are 29 pixels, spaced 43 pixels apart.
    image = Image.new("RGB", (1388, 2156), "white")
    draw = ImageDraw.Draw(image)
    for top in range(83, 2040, 43):
        draw.rectangle((26, top, 187, top + 28), fill="black")
        draw.rectangle((743, top, 904, top + 28), fill="black")

    try:
        estimate = detect_profile_layout_parameters(image, AppSettings())
    finally:
        image.close()
        clear_profile_layout_bootstrap_cache()

    assert estimate.character_height == 29
    assert estimate.row_padding == 1
    assert "profile_bootstrap+projection_fallback+observed_character_height=29(" in estimate.method
    assert estimate.column_starts == (4, 711)


def test_unverifiable_profile_height_is_explicitly_marked_not_measured(monkeypatch) -> None:
    clear_profile_layout_bootstrap_cache()
    monkeypatch.setattr(
        layout_detection, "_projection_layout_estimate",
        lambda image, settings: _estimate(),
    )
    blank = Image.new("RGB", (1800, 1300), "white")
    try:
        result = detect_profile_layout_parameters(blank, AppSettings())
        assert result.character_height == 32
        assert result.method.endswith("+unverified_character_height")
    finally:
        blank.close()
        clear_profile_layout_bootstrap_cache()


def test_multi_page_profile_height_does_not_average_real_ink_and_page_ratio_guesses() -> None:
    from picture_capture.profile_layout_bootstrap import robust_profile_ink_height

    real = [
        SimpleNamespace(character_height=29, method="profile_bootstrap+projection_fallback+observed_character_height=29(n=60)")
        for _ in range(3)
    ]
    guesses = [
        SimpleNamespace(character_height=17, method="profile_bootstrap+projection_fallback+unverified_character_height")
        for _ in range(3)
    ]
    assert robust_profile_ink_height(real + guesses) == (29, 3)
    assert robust_profile_ink_height(real[:1] + guesses) == (None, 1)
    assert robust_profile_ink_height(guesses) == (None, 0)
    assert robust_profile_ink_height(real) == (29, 3)


def test_profile_setup_does_not_auto_apply_unverified_height() -> None:
    from pathlib import Path
    import picture_capture.profile_setup as wizard
    from picture_capture.profile_layout_bootstrap import apply_profile_ink_height_suggestion

    source = Path(wizard.__file__).read_text(encoding="utf-8")
    assert "height_note = apply_profile_ink_height_suggestion(aggregate, estimates)" in source

    aggregate = {"character_height": 17}
    notice = apply_profile_ink_height_suggestion(aggregate, [])
    assert "character_height" not in aggregate
    assert "未自动修改字高" in notice

    verified = [
        SimpleNamespace(character_height=29, method="profile_bootstrap+observed_character_height=29(n=70)")
    ]
    notice = apply_profile_ink_height_suggestion(aggregate, verified)
    assert aggregate["character_height"] == 29
    assert "真实墨迹" in notice
