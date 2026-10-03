from __future__ import annotations

import json
from pathlib import Path

from picture_capture.illustration_fill_opacity_runtime import configure_overlay_opacity_defaults
from picture_capture.overlay_line_anchor_runtime import one_sided_line_coordinates
from picture_capture.overlay_opacity_runtime import (
    _install_settings_properties,
    _normalize_opacity,
    render_alpha_line_overlay,
)


def test_opacity_values_are_clamped_to_visible_percentage_range():
    assert _normalize_opacity(-10) == 0.0
    assert _normalize_opacity(0) == 0.0
    assert _normalize_opacity(37.5) == 37.5
    assert _normalize_opacity(100) == 100.0
    assert _normalize_opacity(180) == 100.0


def test_true_alpha_line_overlay_uses_rgba_not_stipple_simulation():
    overlay, left, top = render_alpha_line_overlay(
        [10, 10, 90, 10],
        color="#ff0000",
        width=4,
        opacity=50,
    )
    assert overlay.mode == "RGBA"
    assert left < 10
    assert top < 10
    alpha = overlay.getchannel("A")
    assert alpha.getbbox() is not None
    # Lanczos antialiasing can overshoot the nominal 128 alpha at the centre
    # slightly; it must still remain clearly semi-transparent rather than opaque.
    assert 120 <= max(alpha.getdata()) <= 160


def test_full_opacity_overlay_has_opaque_line_pixels():
    overlay, _left, _top = render_alpha_line_overlay(
        [5, 5, 40, 40],
        color="#1976d2",
        width=3,
        opacity=100,
        smooth=True,
    )
    assert max(overlay.getchannel("A").getdata()) >= 250


def test_headword_line_added_thickness_grows_down_only():
    baseline = (10.0, 20.0, 90.0, 20.0)
    assert one_sided_line_coordinates(baseline, width=1, growth="down") == baseline
    assert one_sided_line_coordinates(baseline, width=5, growth="down") == (
        10.0, 22.0, 90.0, 22.0,
    )


def test_column_guide_added_thickness_grows_right_only():
    baseline = (30.0, 10.0, 30.0, 90.0)
    assert one_sided_line_coordinates(baseline, width=1, growth="right") == baseline
    assert one_sided_line_coordinates(baseline, width=5, growth="right") == (
        32.0, 10.0, 32.0, 90.0,
    )


class _FakeSettings:
    __slots__ = ()
    __dataclass_fields__ = {}

    def to_json(self, path: Path) -> None:
        Path(path).write_text(json.dumps({"base": 1}), encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path):
        json.loads(Path(path).read_text(encoding="utf-8"))
        return cls()


def test_runtime_opacity_properties_roundtrip_in_project_json(tmp_path: Path):
    # Production startup establishes the requested 40% display defaults before
    # the dynamic line-opacity properties are installed.
    configure_overlay_opacity_defaults()
    _install_settings_properties(_FakeSettings)
    settings = _FakeSettings()
    assert settings.guide_opacity == 40.0
    assert settings.headword_marker_opacity == 40.0

    settings.guide_opacity = 42.5
    settings.headword_marker_opacity = 65
    path = tmp_path / "settings.json"
    settings.to_json(path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["guide_opacity"] == 42.5
    assert payload["headword_marker_opacity"] == 65.0

    reopened = _FakeSettings.from_json(path)
    assert reopened.guide_opacity == 42.5
    assert reopened.headword_marker_opacity == 65.0


def test_gui_composition_installs_opacity_after_other_drawing_wrappers():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "bootstrap"
        / "gui.py"
    ).read_text(encoding="utf-8")
    assert "install_overlay_opacity_runtime" in source
    assert "install_overlay_line_anchor_runtime" in source
    opacity = source.index("install_overlay_opacity_runtime(app_module)")
    anchor = source.index("install_overlay_line_anchor_runtime(app_module)")
    layout = source.index("install_layout_visualization(app_module)")
    lanes = source.index("install_physical_lane_summary()")
    assert layout < opacity
    assert lanes < opacity
    assert opacity < anchor


def test_opacity_runtime_exposes_independent_guide_and_marker_controls():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "overlay_opacity_runtime.py"
    ).read_text(encoding="utf-8")
    assert '"guide_opacity": "栏左垂线不透明度"' in source
    assert '"headword_marker_opacity": "词头横线不透明度"' in source
    assert "ImageTk.PhotoImage" in source
    assert 'name="guide_opacity"' in source
    assert 'name="headword_marker_opacity"' in source


def test_marker_opacity_control_is_moved_before_illustration_label_controls():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "overlay_line_anchor_runtime.py"
    ).read_text(encoding="utf-8")
    assert 'target = _find_checkbutton(row, "插图标签：外框")' in source
    assert 'widget.pack_configure(before=target)' in source
    assert 'growth = "right" if bool(options.get("smooth", False)) else "down"' in source
