from pathlib import Path

from picture_capture.models import AppSettings
from picture_capture.illustration_fill_opacity import (
    DEFAULT_DISPLAY_OPACITY, render_alpha_polygon_overlay,
)


def test_shared_display_opacity_defaults_are_40_percent():
    assert DEFAULT_DISPLAY_OPACITY == 40.0
    assert AppSettings().guide_opacity == 40.0
    assert AppSettings().headword_marker_opacity == 40.0
    assert AppSettings().illustration_fill_opacity == 40.0


def test_illustration_polygon_uses_true_40_percent_alpha():
    overlay, left, top = render_alpha_polygon_overlay(
        (10, 10, 30, 10, 30, 30, 10, 30),
        color="#ffe66d",
        opacity=40.0,
    )
    try:
        # Well inside the polygon, antialiasing must not dilute the requested
        # opacity: 40% of 255 is 102.
        pixel = overlay.getpixel((20 - left, 20 - top))
        assert pixel[3] == 102
    finally:
        overlay.close()


def test_gui_composition_has_no_opacity_runtime_installer():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    assert "install_overlay_opacity_runtime" not in source
    assert "install_illustration_fill_opacity_runtime" not in source
    assert "configure_overlay_opacity_defaults" not in source


def test_illustration_fill_is_static_rgba_ownership():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")
    guard = (root / "scripts/architecture_guard.py").read_text(encoding="utf-8")
    assert "create_alpha_canvas_polygon" in app
    assert "refresh_alpha_polygon_fill(self, region_index)" in app
    assert "illustration_fill_color, stipple=" not in app
    assert not (root / "src/picture_capture/illustration_fill_opacity_runtime.py").exists()
    assert '"illustration_fill_opacity_runtime.py"' not in guard
