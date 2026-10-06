from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:90]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def remove_once(path: str, old: str) -> None:
    replace_once(path, old, "")


# 1. Static illustration-fill opacity helper.
module = ROOT / "src/picture_capture/illustration_fill_opacity.py"
if module.exists():
    raise SystemExit("illustration_fill_opacity.py already exists")
module.write_text('''from __future__ import annotations

"""Static true-alpha rendering for editable PPP illustration fills."""

import math
import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable

from PIL import Image, ImageColor, ImageDraw, ImageTk

from .overlay_opacity import flatten_coordinates, normalize_opacity

DEFAULT_DISPLAY_OPACITY = 40.0


def render_alpha_polygon_overlay(
    coordinates: Iterable[float], *, color: str, opacity: float,
) -> tuple[Image.Image, int, int]:
    values = [float(value) for value in coordinates]
    if len(values) < 6 or len(values) % 2:
        raise ValueError("polygon coordinates must contain at least three XY points")
    points = list(zip(values[0::2], values[1::2]))
    min_x = math.floor(min(x for x, _y in points)) - 2
    min_y = math.floor(min(y for _x, y in points)) - 2
    max_x = math.ceil(max(x for x, _y in points)) + 2
    max_y = math.ceil(max(y for _x, y in points)) + 2
    width = max(1, int(max_x - min_x + 1))
    height = max(1, int(max_y - min_y + 1))
    rgb = ImageColor.getrgb(str(color or "#ffe66d"))[:3]
    alpha = round(normalize_opacity(opacity) * 255.0 / 100.0)
    aa = 2
    overlay = Image.new("RGBA", (width * aa, height * aa), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    shifted = [((x - min_x) * aa, (y - min_y) * aa) for x, y in points]
    draw.polygon(shifted, fill=(rgb[0], rgb[1], rgb[2], alpha))
    overlay = overlay.resize((width, height), Image.Resampling.LANCZOS)
    return overlay, int(min_x), int(min_y)


def create_alpha_canvas_polygon(
    owner: Any,
    coordinates: tuple[Any, ...] | list[Any],
    *,
    outline: str,
    fill: str,
    width: float,
    opacity: float,
    tags: Any | None = None,
) -> int:
    """Create the authoritative editable polygon and optional RGBA fill below it."""
    values = flatten_coordinates(tuple(coordinates))
    options: dict[str, Any] = {"outline": outline, "fill": fill, "width": width}
    if tags is not None:
        options["tags"] = tags
    if len(values) < 6:
        return int(owner.canvas.create_polygon(*coordinates, **options))

    normalized = normalize_opacity(opacity)
    if normalized >= 100.0:
        return int(owner.canvas.create_polygon(*coordinates, **options))

    outline_options = dict(options)
    outline_options["fill"] = ""
    fill_item: int | None = None
    photo = None
    if normalized > 0.0:
        overlay, left, top = render_alpha_polygon_overlay(
            values, color=str(fill or "#ffe66d"), opacity=normalized,
        )
        photo = ImageTk.PhotoImage(overlay)
        fill_tags = tuple(tags) if tags and not isinstance(tags, str) else ((tags,) if tags else ())
        fill_tags = tuple(tag for tag in fill_tags if tag) + ("pc-alpha-illustration-fill",)
        fill_item = int(owner.canvas.create_image(
            left, top, anchor="nw", image=photo, tags=fill_tags,
        ))

    polygon_item = int(owner.canvas.create_polygon(*coordinates, **outline_options))
    if fill_item is not None:
        try:
            owner.canvas.tag_lower(fill_item, polygon_item)
        except tk.TclError:
            pass
        owner.__dict__.setdefault("_pc_alpha_polygon_records", {})[polygon_item] = {
            "image_item": fill_item,
            "photo": photo,
        }
    return polygon_item


def clear_alpha_polygon_records(owner: Any) -> None:
    owner.__dict__["_pc_alpha_polygon_records"] = {}


def refresh_alpha_polygon_fill(owner: Any, region_index: int) -> None:
    records = owner.__dict__.get("_pc_alpha_polygon_records", {})
    canvas_records = getattr(owner, "_polygon_canvas_items", {})
    canvas_record = canvas_records.get(region_index) if isinstance(canvas_records, dict) else None
    if not isinstance(canvas_record, dict):
        return
    polygon_item = canvas_record.get("polygon")
    if polygon_item is None or not isinstance(records, dict):
        return
    record = records.get(polygon_item)
    if not isinstance(record, dict):
        return
    if not (0 <= int(region_index) < len(getattr(owner, "polygons", []))):
        return
    region = owner.polygons[int(region_index)]
    values = [
        float(value) * float(getattr(owner, "view_scale", 1.0) or 1.0)
        for point in region.points for value in point
    ]
    if len(values) < 6:
        return
    overlay, left, top = render_alpha_polygon_overlay(
        values,
        color=str(getattr(owner.settings, "illustration_fill_color", "#ffe66d")),
        opacity=getattr(owner.settings, "illustration_fill_opacity", DEFAULT_DISPLAY_OPACITY),
    )
    photo = ImageTk.PhotoImage(overlay)
    image_item = record.get("image_item")
    try:
        owner.canvas.coords(image_item, left, top)
        owner.canvas.itemconfigure(image_item, image=photo)
        owner.canvas.tag_lower(image_item, polygon_item)
    except tk.TclError:
        return
    record["photo"] = photo


def add_quick_illustration_fill_opacity_control(app: Any, row: tk.Misc) -> None:
    name = "illustration_fill_opacity"
    if name in getattr(app, "quick_vars", {}):
        return
    current = normalize_opacity(getattr(app.settings, name, DEFAULT_DISPLAY_OPACITY))
    variable = tk.StringVar(value=f"{current:.0f}" if abs(current - round(current)) < 1e-9 else f"{current:g}")
    app.quick_vars[name] = variable
    app.quick_field_casts[name] = float
    ttk.Label(row, text="区域不透明度：").pack(side="left", padx=(5, 0))
    spin = ttk.Spinbox(row, textvariable=variable, from_=0, to=100, increment=5, width=5)
    spin.pack(side="left", padx=(2, 1))
    ttk.Label(row, text="%").pack(side="left", padx=(0, 8))
    variable.trace_add("write", lambda *_args: app._quick_parameter_changed())
    try:
        app._attach_tooltip(spin, "插图区域背景的真实透明度；默认40%，不改变轮廓或PPP坐标。")
    except Exception:
        pass


__all__ = [
    "DEFAULT_DISPLAY_OPACITY",
    "add_quick_illustration_fill_opacity_control",
    "clear_alpha_polygon_records",
    "create_alpha_canvas_polygon",
    "refresh_alpha_polygon_fill",
    "render_alpha_polygon_overlay",
]
''', encoding="utf-8")

# 2. Native settings ownership.
replace_once(
    "src/picture_capture/models.py",
    '    illustration_fill_color: str = "#ffe66d"\n',
    '    illustration_fill_color: str = "#ffe66d"\n    illustration_fill_opacity: float = 40.0\n',
)
replace_once(
    "src/picture_capture/models.py",
    '        if name in {"guide_opacity", "headword_marker_opacity"}:\n',
    '        if name in {"guide_opacity", "headword_marker_opacity", "illustration_fill_opacity"}:\n',
)
# Preserve save/load normalization contract for all display opacity fields.
text_path = ROOT / "src/picture_capture/models.py"
text = text_path.read_text(encoding="utf-8")
needle = '("guide_opacity", "headword_marker_opacity")'
if text.count(needle) != 2:
    raise SystemExit(f"models.py: expected two persistence opacity tuples, found {text.count(needle)}")
text_path.write_text(text.replace(needle, '("guide_opacity", "headword_marker_opacity", "illustration_fill_opacity")'), encoding="utf-8")

# 3. Static Settings Center schema.
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '("垂直线宽", "guide_width", int), ("栏左垂线不透明度", "guide_opacity", float),\n',
    '("垂直线宽", "guide_width", int), ("栏左垂线不透明度", "guide_opacity", float),\n        ("插图区域不透明度", "illustration_fill_opacity", float),\n',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '("词条线显示", ["marker_height", "headword_marker_opacity", "guide_width", "guide_opacity"]),\n',
    '("词条线显示", ["marker_height", "headword_marker_opacity", "guide_width", "guide_opacity", "illustration_fill_opacity"]),\n',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '        "headword_marker_opacity": "词头横线不透明度",\n',
    '        "headword_marker_opacity": "词头横线不透明度",\n        "illustration_fill_opacity": "插图区域不透明度",\n',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '        "guide_opacity": "%", "headword_marker_opacity": "%",\n',
    '        "guide_opacity": "%", "headword_marker_opacity": "%", "illustration_fill_opacity": "%",\n',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '        "headword_marker_opacity": (0.0, 100.0, 5.0),\n',
    '        "headword_marker_opacity": (0.0, 100.0, 5.0),\n        "illustration_fill_opacity": (0.0, 100.0, 5.0),\n',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '    "marker_height", "headword_marker_opacity", "guide_width", "guide_opacity",\n',
    '    "marker_height", "headword_marker_opacity", "guide_width", "guide_opacity", "illustration_fill_opacity",\n',
)
# Add help next to other opacity help entries.
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '        "headword_marker_opacity": (\n            "作用：控制主画布词头/词条横线覆盖在扫描图片上的不透明度，只改变显示。"\n            "100% 为完全不透明，0% 为完全透明；不会改变横线 Y 坐标、PDIC、OCR、校对或切图。\\n\\n"\n            "调整：横线遮挡字形时降低；需要快速检查漏线、错线时提高。"\n        ),\n',
    '        "headword_marker_opacity": (\n            "作用：控制主画布词头/词条横线覆盖在扫描图片上的不透明度，只改变显示。"\n            "100% 为完全不透明，0% 为完全透明；不会改变横线 Y 坐标、PDIC、OCR、校对或切图。\\n\\n"\n            "调整：横线遮挡字形时降低；需要快速检查漏线、错线时提高。"\n        ),\n        "illustration_fill_opacity": (\n            "作用：控制主画布插图区域背景填充覆盖在扫描图片上的真实不透明度，只改变显示。"\n            "默认 40%；100% 为完全不透明，0% 为完全透明。插图轮廓线不受此值影响，"\n            "也不会改变 PPP 区域坐标、插图切图范围或识别结果。"\n        ),\n',
)

# 4. Direct app ownership.
replace_once(
    "src/picture_capture/app.py",
    'from .overlay_opacity import (\n    add_quick_opacity_control, clear_alpha_line_photos,\n    create_alpha_canvas_line, release_alpha_line_photos,\n)\n',
    'from .overlay_opacity import (\n    add_quick_opacity_control, clear_alpha_line_photos,\n    create_alpha_canvas_line, release_alpha_line_photos,\n)\nfrom .illustration_fill_opacity import (\n    add_quick_illustration_fill_opacity_control, clear_alpha_polygon_records,\n    create_alpha_canvas_polygon, refresh_alpha_polygon_fill,\n)\n',
)
replace_once(
    "src/picture_capture/app.py",
    '        ttk.Label(line_row, text="背景").pack(side="left")\n        color_button(line_row, "illustration_fill_color")\n',
    '        ttk.Label(line_row, text="背景").pack(side="left")\n        color_button(line_row, "illustration_fill_color")\n        add_quick_illustration_fill_opacity_control(self, line_row)\n',
)
replace_once(
    "src/picture_capture/app.py",
    '    def redraw(self) -> None:\n        clear_alpha_line_photos(self)\n',
    '    def redraw(self) -> None:\n        clear_alpha_line_photos(self)\n        clear_alpha_polygon_records(self)\n',
)
replace_once(
    "src/picture_capture/app.py",
    '''                polygon_item = self.canvas.create_polygon(\n                    points,\n                    outline=self.settings.illustration_outline_color,\n                    fill=self.settings.illustration_fill_color,\n                    width=scaled_overlay_line_width(self.settings.illustration_outline_width, overlay_scale),\n                    stipple="gray50",\n                    tags=("ppp-overlay", "ppp-polygon", f"ppp-region-{region_index}"),\n                )\n''',
    '''                polygon_item = create_alpha_canvas_polygon(\n                    self,\n                    tuple(points),\n                    outline=self.settings.illustration_outline_color,\n                    fill=self.settings.illustration_fill_color,\n                    width=scaled_overlay_line_width(self.settings.illustration_outline_width, overlay_scale),\n                    opacity=self.settings.illustration_fill_opacity,\n                    tags=("ppp-overlay", "ppp-polygon", f"ppp-region-{region_index}"),\n                )\n''',
)
replace_once(
    "src/picture_capture/app.py",
    '''                    self.canvas.coords(record["label_window"], label_x, label_y)\n        except tk.TclError:\n            pass\n\n    def _persist_current_page_sections''',
    '''                    self.canvas.coords(record["label_window"], label_x, label_y)\n            refresh_alpha_polygon_fill(self, region_index)\n        except tk.TclError:\n            pass\n\n    def _persist_current_page_sections''',
)

# 5. Remove installer/bootstrap/guard debt.
remove_once(
    "src/picture_capture/bootstrap/gui.py",
    '    from ..illustration_fill_opacity_runtime import (\n        configure_overlay_opacity_defaults,\n        install_illustration_fill_opacity_runtime,\n    )\n',
)
remove_once(
    "src/picture_capture/bootstrap/gui.py",
    '    # Set all display-overlay defaults before the line opacity runtime creates\n    # AppSettings properties. Existing settings.json values remain authoritative.\n    configure_overlay_opacity_defaults()\n',
)
remove_once(
    "src/picture_capture/bootstrap/gui.py",
    '    # Illustration fill uses a real RGBA image under the editable Canvas polygon,\n    # rather than Tk\'s historical gray50 stipple approximation.\n    install_illustration_fill_opacity_runtime(app_module)\n',
)
remove_once("scripts/architecture_guard.py", '    "illustration_fill_opacity_runtime.py",\n')
old_runtime = ROOT / "src/picture_capture/illustration_fill_opacity_runtime.py"
if not old_runtime.exists():
    raise SystemExit("illustration_fill_opacity_runtime.py missing")
old_runtime.unlink()

# 6. Migrate tests and add focused characterization.
replace_once(
    "tests/test_display_opacity_defaults.py",
    'from picture_capture.illustration_fill_opacity_runtime import (\n    DEFAULT_DISPLAY_OPACITY,\n    configure_overlay_opacity_defaults,\n    render_alpha_polygon_overlay,\n)\n',
    'from picture_capture.illustration_fill_opacity import (\n    DEFAULT_DISPLAY_OPACITY, render_alpha_polygon_overlay,\n)\n',
)
replace_once(
    "tests/test_display_opacity_defaults.py",
    '    configure_overlay_opacity_defaults()\n    assert DEFAULT_DISPLAY_OPACITY == 40.0\n',
    '    assert DEFAULT_DISPLAY_OPACITY == 40.0\n',
)
replace_once(
    "tests/test_display_opacity_defaults.py",
    '    assert AppSettings().headword_marker_opacity == 40.0\n',
    '    assert AppSettings().headword_marker_opacity == 40.0\n    assert AppSettings().illustration_fill_opacity == 40.0\n',
)
replace_once(
    "tests/test_display_opacity_defaults.py",
    '''def test_gui_composition_keeps_only_illustration_opacity_runtime():\n    root = Path(__file__).resolve().parents[1]\n    source = (\n        root / "src/picture_capture/bootstrap/gui.py"\n    ).read_text(encoding="utf-8")\n    assert "install_overlay_opacity_runtime" not in source\n    assert "configure_overlay_opacity_defaults()" in source\n    assert "install_illustration_fill_opacity_runtime(app_module)" in source\n\n\ndef test_illustration_runtime_replaces_gray50_with_rgba_fill_at_runtime():\n    root = Path(__file__).resolve().parents[1]\n    source = (\n        root / "src/picture_capture/illustration_fill_opacity_runtime.py"\n    ).read_text(encoding="utf-8")\n    assert 'outline_options.pop("stipple", None)' in source\n    assert "ImageTk.PhotoImage" in source\n    assert "illustration_fill_opacity" in source\n''',
    '''def test_gui_composition_has_no_opacity_runtime_installer():\n    root = Path(__file__).resolve().parents[1]\n    source = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")\n    assert "install_overlay_opacity_runtime" not in source\n    assert "install_illustration_fill_opacity_runtime" not in source\n    assert "configure_overlay_opacity_defaults" not in source\n\n\ndef test_illustration_fill_is_static_rgba_ownership():\n    root = Path(__file__).resolve().parents[1]\n    app = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")\n    guard = (root / "scripts/architecture_guard.py").read_text(encoding="utf-8")\n    assert "create_alpha_canvas_polygon" in app\n    assert "refresh_alpha_polygon_fill(self, region_index)" in app\n    assert "stipple=\"gray50\"" not in app\n    assert not (root / "src/picture_capture/illustration_fill_opacity_runtime.py").exists()\n    assert '\"illustration_fill_opacity_runtime.py\"' not in guard\n''',
)
replace_once(
    "tests/test_overlay_opacity.py",
    '''    illustration = (\n        root / "src/picture_capture/illustration_fill_opacity_runtime.py"\n    ).read_text(encoding="utf-8")\n''',
    '    illustration = (root / "src/picture_capture/illustration_fill_opacity.py").read_text(encoding="utf-8")\n',
)
replace_once(
    "tests/test_overlay_opacity.py",
    '''    assert "from .overlay_opacity import find_checkbutton, flatten_coordinates" in illustration\n    assert "overlay_opacity_runtime" not in illustration\n''',
    '''    assert "render_alpha_polygon_overlay" in illustration\n    assert "overlay_opacity_runtime" not in illustration\n''',
)

(ROOT / "tests/test_illustration_fill_opacity.py").write_text('''from __future__ import annotations

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
''', encoding="utf-8")

print("Phase 5P migration applied")
