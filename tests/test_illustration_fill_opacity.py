from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import picture_capture.illustration_fill_opacity as fill
from picture_capture.models import AppSettings, PolygonRegion
from picture_capture.ui.settings import schema


def test_native_field_defaults_clamps_roundtrips_and_legacy_falls_back(tmp_path: Path):
    settings = AppSettings(illustration_fill_opacity=180)
    assert settings.illustration_fill_opacity == 100.0
    settings.illustration_fill_opacity = -5
    assert settings.illustration_fill_opacity == 0.0
    settings.illustration_fill_opacity = 42.5
    path = tmp_path / "settings.json"
    settings.to_json(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["illustration_fill_opacity"] == 42.5
    assert AppSettings.from_json(path).illustration_fill_opacity == 42.5
    payload.pop("illustration_fill_opacity")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert AppSettings.from_json(path).illustration_fill_opacity == 40.0


def test_alpha_polygon_100_percent_stays_native_and_keeps_tags():
    calls = []
    class Canvas:
        def create_polygon(self, *coordinates, **options):
            calls.append((coordinates, options)); return 7
    owner = SimpleNamespace(canvas=Canvas())
    result = fill.create_alpha_canvas_polygon(
        owner, (10,10,30,10,30,30,10,30), outline="#00f", fill="#ff0",
        width=2, opacity=100, tags=("ppp-overlay", "ppp-polygon"),
    )
    assert result == 7
    assert calls[0][1]["fill"] == "#ff0"
    assert calls[0][1]["tags"] == ("ppp-overlay", "ppp-polygon")


def test_alpha_polygon_zero_percent_keeps_outline_hit_target_without_fill_image():
    class Canvas:
        def __init__(self): self.images = []
        def create_polygon(self, *coordinates, **options): self.options = options; return 8
        def create_image(self, *args, **kwargs): self.images.append((args, kwargs)); return 9
    canvas = Canvas(); owner = SimpleNamespace(canvas=canvas)
    result = fill.create_alpha_canvas_polygon(
        owner, (10,10,30,10,30,30,10,30), outline="#00f", fill="#ff0",
        width=2, opacity=0, tags=("ppp-overlay",),
    )
    assert result == 8
    assert canvas.options["fill"] == ""
    assert canvas.images == []
    assert owner.__dict__.get("_pc_alpha_polygon_records", {}) == {}


def test_alpha_polygon_semitransparent_fill_is_lowered_and_retained(monkeypatch):
    seen = {}
    class Canvas:
        def create_image(self, left, top, **options): seen["image"]=(left,top,options); return 9
        def create_polygon(self, *coordinates, **options): seen["polygon"]=(coordinates,options); return 8
        def tag_lower(self, image_item, polygon_item): seen["lower"]=(image_item,polygon_item)
    monkeypatch.setattr(fill, "render_alpha_polygon_overlay", lambda *a, **k: (Image.new("RGBA", (1,1)), 3, 4))
    monkeypatch.setattr(fill.ImageTk, "PhotoImage", lambda image: object())
    owner = SimpleNamespace(canvas=Canvas())
    result = fill.create_alpha_canvas_polygon(
        owner, (10,10,30,10,30,30,10,30), outline="#00f", fill="#ff0",
        width=2, opacity=40, tags=("ppp-overlay", "ppp-polygon"),
    )
    assert result == 8
    assert seen["polygon"][1]["fill"] == ""
    assert seen["lower"] == (9, 8)
    assert "pc-alpha-illustration-fill" in seen["image"][2]["tags"]
    assert owner.__dict__["_pc_alpha_polygon_records"][8]["image_item"] == 9


def test_refresh_tracks_live_polygon_geometry(monkeypatch):
    seen = {}
    class Canvas:
        def coords(self, item, left, top): seen["coords"]=(item,left,top)
        def itemconfigure(self, item, **kwargs): seen["configured"]=(item,kwargs)
        def tag_lower(self, a, b): seen["lower"]=(a,b)
    monkeypatch.setattr(fill, "render_alpha_polygon_overlay", lambda values, **k: (Image.new("RGBA", (1,1)), 11, 12))
    monkeypatch.setattr(fill.ImageTk, "PhotoImage", lambda image: object())
    owner = SimpleNamespace(
        canvas=Canvas(), view_scale=2.0,
        settings=AppSettings(illustration_fill_opacity=40),
        polygons=[PolygonRegion("", [(1,2),(3,2),(3,4),(1,4)])],
        _polygon_canvas_items={0:{"polygon":8}},
    )
    owner.__dict__["_pc_alpha_polygon_records"]={8:{"image_item":9,"photo":None}}
    fill.refresh_alpha_polygon_fill(owner, 0)
    assert seen["coords"] == (9,11,12)
    assert seen["lower"] == (9,8)
    assert owner.__dict__["_pc_alpha_polygon_records"][8]["photo"] is not None


def test_settings_schema_owns_illustration_opacity_statically():
    fields = {name for _label, name, _cast in schema.FIELDS}
    assert "illustration_fill_opacity" in fields
    display = list(schema.DISPLAY_FIELDS)
    assert display.index("guide_opacity") < display.index("illustration_fill_opacity")
    assert schema.SETTING_UNITS["illustration_fill_opacity"] == "%"
    assert schema.SETTING_SPIN["illustration_fill_opacity"] == (0.0,100.0,5.0)
    assert "PPP 区域坐标" in schema.SETTING_HELP["illustration_fill_opacity"]


def test_app_source_uses_direct_static_polygon_opacity_path():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")
    assert "clear_alpha_polygon_records(self)" in source
    assert "create_alpha_canvas_polygon(" in source
    assert "opacity=self.settings.illustration_fill_opacity" in source
    assert "refresh_alpha_polygon_fill(self, region_index)" in source
    assert "add_quick_illustration_fill_opacity_control(self, line_row)" in source
