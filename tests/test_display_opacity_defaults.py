from pathlib import Path

from picture_capture import overlay_opacity_runtime
from picture_capture.illustration_fill_opacity_runtime import (
    DEFAULT_DISPLAY_OPACITY,
    configure_overlay_opacity_defaults,
    render_alpha_polygon_overlay,
)


def test_shared_display_opacity_defaults_are_40_percent():
    configure_overlay_opacity_defaults()
    assert DEFAULT_DISPLAY_OPACITY == 40.0
    assert overlay_opacity_runtime._DEFAULT_GUIDE_OPACITY == 40.0
    assert overlay_opacity_runtime._DEFAULT_MARKER_OPACITY == 40.0


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


def test_launcher_sets_defaults_before_installing_line_opacity():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/picture_capture/launcher.py").read_text(encoding="utf-8")
    assert source.index("configure_overlay_opacity_defaults()") < source.index(
        "install_overlay_opacity_runtime(app_module)"
    )
    assert source.index("install_overlay_opacity_runtime(app_module)") < source.index(
        "install_illustration_fill_opacity_runtime(app_module)"
    )


def test_illustration_runtime_replaces_gray50_with_rgba_fill_at_runtime():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src/picture_capture/illustration_fill_opacity_runtime.py"
    ).read_text(encoding="utf-8")
    assert 'outline_options.pop("stipple", None)' in source
    assert "ImageTk.PhotoImage" in source
    assert "illustration_fill_opacity" in source
