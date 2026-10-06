from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import picture_capture.overlay_opacity as opacity
from picture_capture.models import AppSettings
from picture_capture.overlay_line_anchor import one_sided_line_coordinates
from picture_capture.overlay_opacity import (
    clear_alpha_line_photos,
    create_alpha_canvas_line,
    normalize_opacity,
    release_alpha_line_photos,
    render_alpha_line_overlay,
)
from picture_capture.ui.settings import schema


def test_opacity_values_are_clamped_to_visible_percentage_range():
    assert normalize_opacity(-10) == 0.0
    assert normalize_opacity(0) == 0.0
    assert normalize_opacity(37.5) == 37.5
    assert normalize_opacity(100) == 100.0
    assert normalize_opacity(180) == 100.0


def test_true_alpha_line_overlay_uses_rgba_not_stipple_simulation():
    overlay, left, top = render_alpha_line_overlay(
        [10, 10, 90, 10], color="#ff0000", width=4, opacity=50,
    )
    assert overlay.mode == "RGBA"
    assert left < 10 and top < 10
    alpha = overlay.getchannel("A")
    assert alpha.getbbox() is not None
    assert 120 <= max(alpha.getdata()) <= 160


def test_headword_and_guide_one_sided_geometry_remains_unchanged():
    assert one_sided_line_coordinates(
        (10.0, 20.0, 90.0, 20.0), width=5, growth="down"
    ) == (10.0, 22.0, 90.0, 22.0)
    assert one_sided_line_coordinates(
        (30.0, 10.0, 30.0, 90.0), width=5, growth="right"
    ) == (32.0, 10.0, 32.0, 90.0)


def test_direct_canvas_line_anchors_full_opacity_before_native_render():
    calls = []

    class Canvas:
        def create_line(self, *coordinates, **options):
            calls.append((coordinates, dict(options)))
            return 17

    owner = SimpleNamespace(canvas=Canvas())
    result = create_alpha_canvas_line(
        owner,
        (100.0, 10.0, 100.0, 90.0),
        fill="#000",
        width=5.0,
        opacity=100.0,
        smooth=True,
    )
    assert result == 17
    assert calls == [((102.0, 10.0, 102.0, 90.0), {
        "fill": "#000", "width": 5.0, "smooth": True,
    })]


def test_direct_canvas_line_anchors_hidden_path_before_native_render():
    calls = []

    class Canvas:
        def create_line(self, *coordinates, **options):
            calls.append((coordinates, dict(options)))
            return 18

    owner = SimpleNamespace(canvas=Canvas())
    result = create_alpha_canvas_line(
        owner,
        (20.0, 50.0, 120.0, 50.0),
        fill="#000",
        width=5.0,
        opacity=0.0,
    )
    assert result == 18
    assert calls[0][0] == (20.0, 52.0, 120.0, 52.0)
    assert calls[0][1]["state"] == "hidden"


def test_direct_canvas_line_anchors_semitransparent_overlay(monkeypatch):
    seen = {}

    class Canvas:
        def create_image(self, left, top, **options):
            seen["image"] = (left, top, dict(options))
            return 19

    def fake_render(coordinates, **kwargs):
        seen["coordinates"] = list(coordinates)
        seen["render_kwargs"] = dict(kwargs)
        return Image.new("RGBA", (1, 1)), 3, 4

    monkeypatch.setattr(opacity, "render_alpha_line_overlay", fake_render)
    monkeypatch.setattr(opacity.ImageTk, "PhotoImage", lambda _image: object())
    owner = SimpleNamespace(canvas=Canvas())
    result = create_alpha_canvas_line(
        owner,
        (20.0, 50.0, 120.0, 50.0),
        fill="#000",
        width=5.0,
        opacity=40.0,
    )
    assert result == 19
    assert seen["coordinates"] == [20.0, 52.0, 120.0, 52.0]
    assert seen["render_kwargs"]["opacity"] == 40.0
    assert 19 in owner.__dict__["_pc_alpha_line_photos"]


def test_alpha_photo_lifetime_helpers_match_previous_cleanup_semantics():
    owner = SimpleNamespace()
    owner.__dict__["_pc_alpha_line_photos"] = {3: object(), 4: object()}
    release_alpha_line_photos(owner, [3])
    assert set(owner.__dict__["_pc_alpha_line_photos"]) == {4}
    clear_alpha_line_photos(owner)
    assert owner.__dict__["_pc_alpha_line_photos"] == {}


def test_native_opacity_fields_roundtrip_and_old_projects_default_to_40(tmp_path: Path):
    settings = AppSettings()
    assert settings.guide_opacity == 40.0
    assert settings.headword_marker_opacity == 40.0
    settings.guide_opacity = 42.5
    settings.headword_marker_opacity = 65
    path = tmp_path / "settings.json"
    settings.to_json(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["guide_opacity"] == 42.5
    assert payload["headword_marker_opacity"] == 65.0
    reopened = AppSettings.from_json(path)
    assert reopened.guide_opacity == 42.5
    assert reopened.headword_marker_opacity == 65.0

    payload.pop("guide_opacity")
    payload.pop("headword_marker_opacity")
    path.write_text(json.dumps(payload), encoding="utf-8")
    legacy = AppSettings.from_json(path)
    assert legacy.guide_opacity == 40.0
    assert legacy.headword_marker_opacity == 40.0


def test_native_json_persistence_preserves_runtime_clamping_contract(tmp_path: Path):
    settings = AppSettings(guide_opacity=-20, headword_marker_opacity=180)
    assert settings.guide_opacity == 0.0
    assert settings.headword_marker_opacity == 100.0
    settings.guide_opacity = 250
    settings.headword_marker_opacity = -5
    assert settings.guide_opacity == 100.0
    assert settings.headword_marker_opacity == 0.0
    settings.guide_opacity = -20
    settings.headword_marker_opacity = 180
    path = tmp_path / "settings.json"
    settings.to_json(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["guide_opacity"] == 0.0
    assert payload["headword_marker_opacity"] == 100.0
    reopened = AppSettings.from_json(path)
    assert reopened.guide_opacity == 0.0
    assert reopened.headword_marker_opacity == 100.0


def test_settings_center_owns_line_opacity_statically():
    fields = {name for _label, name, _cast in schema.FIELDS}
    assert {"guide_opacity", "headword_marker_opacity"} <= fields
    display = list(schema.DISPLAY_FIELDS)
    assert display.index("marker_height") < display.index("headword_marker_opacity")
    assert display.index("headword_marker_opacity") < display.index("guide_width")
    assert display.index("guide_width") < display.index("guide_opacity")
    assert schema.SETTING_UNITS["guide_opacity"] == "%"
    assert schema.SETTING_SPIN["headword_marker_opacity"] == (0.0, 100.0, 5.0)
    assert "只向下方扩展" in schema.SETTING_HELP["marker_height"]
    assert "只向右侧扩展" in schema.SETTING_HELP["guide_width"]


def test_app_and_bootstrap_have_direct_static_line_opacity_ownership():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    guard = (root / "scripts/architecture_guard.py").read_text(encoding="utf-8")
    illustration = (root / "src/picture_capture/illustration_fill_opacity.py").read_text(encoding="utf-8")
    assert "create_alpha_canvas_line" in app
    assert 'add_quick_opacity_control(self, line_row, name="guide_opacity")' in app
    assert 'add_quick_opacity_control(self, marker_row, name="headword_marker_opacity")' in app
    assert "install_overlay_opacity_runtime" not in gui
    assert not (root / "src/picture_capture/overlay_opacity_runtime.py").exists()
    assert '"overlay_opacity_runtime.py"' not in guard
    assert "render_alpha_polygon_overlay" in illustration
    assert "overlay_opacity_runtime" not in illustration
