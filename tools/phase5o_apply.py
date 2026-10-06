from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def remove_once(path: str, text_to_remove: str) -> None:
    replace_once(path, text_to_remove, "")


# ---------------------------------------------------------------------------
# 1. Static non-runtime line-opacity implementation.
# ---------------------------------------------------------------------------
overlay_module = ROOT / "src/picture_capture/overlay_opacity.py"
if overlay_module.exists():
    raise SystemExit("overlay_opacity.py already exists")
overlay_module.write_text(
    '''from __future__ import annotations

"""Static display-opacity helpers for column guides and headword marker lines.

Line opacity is presentation-only. AppSettings owns the persisted percentages;
this module owns rendering and the small quick-control constructor. No class or
module is patched at import/startup time.
"""

import math
import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable

from PIL import Image, ImageColor, ImageDraw, ImageTk

from .overlay_line_anchor import one_sided_line_coordinates


DEFAULT_DISPLAY_OPACITY = 40.0


def normalize_opacity(value: object, default: float = DEFAULT_DISPLAY_OPACITY) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    return max(0.0, min(100.0, number))


def flatten_coordinates(values: tuple[Any, ...]) -> list[float]:
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        values = tuple(values[0])
    coords: list[float] = []
    for value in values:
        try:
            coords.append(float(value))
        except (TypeError, ValueError):
            return []
    return coords


def _smooth_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    current = list(points)
    for _ in range(2):
        output = [current[0]]
        for first, second in zip(current, current[1:]):
            q = (
                0.75 * first[0] + 0.25 * second[0],
                0.75 * first[1] + 0.25 * second[1],
            )
            r = (
                0.25 * first[0] + 0.75 * second[0],
                0.25 * first[1] + 0.75 * second[1],
            )
            output.extend((q, r))
        output.append(current[-1])
        current = output
    return current


def render_alpha_line_overlay(
    coordinates: Iterable[float],
    *,
    color: str,
    width: float,
    opacity: float,
    smooth: bool = False,
) -> tuple[Image.Image, int, int]:
    """Return a tightly bounded RGBA line image and its Canvas top-left."""
    values = [float(value) for value in coordinates]
    if len(values) < 4 or len(values) % 2:
        raise ValueError("line coordinates must contain at least two XY points")
    points = list(zip(values[0::2], values[1::2]))
    if smooth:
        points = _smooth_points(points)

    line_width = max(1, int(round(float(width or 1.0))))
    pad = max(3, int(math.ceil(line_width / 2.0)) + 2)
    min_x = math.floor(min(point[0] for point in points)) - pad
    min_y = math.floor(min(point[1] for point in points)) - pad
    max_x = math.ceil(max(point[0] for point in points)) + pad
    max_y = math.ceil(max(point[1] for point in points)) + pad
    image_width = max(1, int(max_x - min_x + 1))
    image_height = max(1, int(max_y - min_y + 1))

    rgb = ImageColor.getrgb(str(color or "#000000"))[:3]
    alpha = round(normalize_opacity(opacity) * 255.0 / 100.0)
    aa = 2
    overlay = Image.new("RGBA", (image_width * aa, image_height * aa), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    shifted = [((x - min_x) * aa, (y - min_y) * aa) for x, y in points]
    draw.line(
        shifted,
        fill=(rgb[0], rgb[1], rgb[2], alpha),
        width=max(1, line_width * aa),
        joint="curve",
    )
    overlay = overlay.resize((image_width, image_height), Image.Resampling.LANCZOS)
    return overlay, int(min_x), int(min_y)


def create_alpha_canvas_line(
    owner: Any,
    coordinates: tuple[Any, ...] | list[Any],
    *,
    fill: str,
    width: float,
    opacity: float,
    smooth: bool = False,
    tags: Any | None = None,
    state: str | None = None,
) -> int:
    """Draw one anchored line directly, using Canvas or Pillow by opacity."""
    growth = "right" if bool(smooth) else "down"
    shifted = one_sided_line_coordinates(
        tuple(coordinates),
        width=float(width or 1.0),
        growth=growth,
    )
    options: dict[str, Any] = {
        "fill": fill,
        "width": width,
    }
    if smooth:
        options["smooth"] = True
    if tags is not None:
        options["tags"] = tags
    if state is not None:
        options["state"] = state

    normalized = normalize_opacity(opacity)
    if normalized >= 100.0:
        return int(owner.canvas.create_line(*shifted, **options))
    if normalized <= 0.0:
        hidden = dict(options)
        hidden["state"] = "hidden"
        return int(owner.canvas.create_line(*shifted, **hidden))

    flattened = flatten_coordinates(tuple(shifted))
    if len(flattened) < 4:
        return int(owner.canvas.create_line(*shifted, **options))

    overlay, left, top = render_alpha_line_overlay(
        flattened,
        color=str(fill or "#000000"),
        width=float(width or 1.0),
        opacity=normalized,
        smooth=bool(smooth),
    )
    photo = ImageTk.PhotoImage(overlay)
    image_options: dict[str, Any] = {"anchor": "nw", "image": photo}
    if tags is not None:
        image_options["tags"] = tags
    if state in {"hidden", "disabled", "normal"}:
        image_options["state"] = state
    item = int(owner.canvas.create_image(left, top, **image_options))
    photos = owner.__dict__.setdefault("_pc_alpha_line_photos", {})
    photos[item] = photo
    return item


def clear_alpha_line_photos(owner: Any) -> None:
    owner.__dict__["_pc_alpha_line_photos"] = {}


def release_alpha_line_photos(owner: Any, item_ids: Iterable[int]) -> None:
    photos = owner.__dict__.get("_pc_alpha_line_photos", {})
    if not isinstance(photos, dict):
        return
    for item in item_ids:
        photos.pop(item, None)


def add_quick_opacity_control(app: Any, row: tk.Misc, *, name: str) -> None:
    """Create one final-position opacity Spinbox during normal app UI build."""
    if name in getattr(app, "quick_vars", {}):
        return
    current = normalize_opacity(getattr(app.settings, name, DEFAULT_DISPLAY_OPACITY))
    rendered = f"{current:.0f}" if abs(current - round(current)) < 1e-9 else f"{current:g}"
    variable = tk.StringVar(value=rendered)
    app.quick_vars[name] = variable
    app.quick_field_casts[name] = float
    ttk.Label(row, text="不透明度：").pack(side="left")
    spin = ttk.Spinbox(
        row,
        textvariable=variable,
        from_=0,
        to=100,
        increment=5,
        width=5,
    )
    spin.pack(side="left", padx=(2, 1))
    ttk.Label(row, text="%").pack(side="left", padx=(0, 8))
    variable.trace_add("write", lambda *_args: app._quick_parameter_changed())
    try:
        app._attach_tooltip(
            spin,
            "100%=完全不透明，0%=完全透明；只改变主画布显示，不改变识别、坐标或切图。",
        )
    except Exception:
        pass


def _descendants(root: tk.Misc):
    for child in root.winfo_children():
        yield child
        yield from _descendants(child)


def find_checkbutton(root: tk.Misc, text: str):
    """Compatibility helper retained for the separate illustration-fill seam."""
    for widget in _descendants(root):
        if not isinstance(widget, (ttk.Checkbutton, tk.Checkbutton)):
            continue
        try:
            if str(widget.cget("text") or "") == text:
                return widget
        except tk.TclError:
            continue
    return None


__all__ = [
    "DEFAULT_DISPLAY_OPACITY",
    "add_quick_opacity_control",
    "clear_alpha_line_photos",
    "create_alpha_canvas_line",
    "find_checkbutton",
    "flatten_coordinates",
    "normalize_opacity",
    "release_alpha_line_photos",
    "render_alpha_line_overlay",
]
''',
    encoding="utf-8",
)


# ---------------------------------------------------------------------------
# 2. Native AppSettings ownership and native JSON persistence.
# ---------------------------------------------------------------------------
replace_once(
    "src/picture_capture/models.py",
    "import json\nimport re\n",
    "import json\nimport math\nimport re\n",
)
replace_once(
    "src/picture_capture/models.py",
    'PROJECT_COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")\n\n\n',
    '''PROJECT_COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")\n\n\ndef _normalize_display_opacity(value: object, default: float = 40.0) -> float:\n    try:\n        number = float(value)\n    except (TypeError, ValueError):\n        number = float(default)\n    if not math.isfinite(number):\n        number = float(default)\n    return max(0.0, min(100.0, number))\n\n\n''',
)
replace_once(
    "src/picture_capture/models.py",
    '''    marker_height: int = 2\n    guide_width: int = 2\n    # Main overlay colours: headword markers stay red; other structural lines use blue.\n''',
    '''    marker_height: int = 2\n    guide_width: int = 2\n    guide_opacity: float = 40.0\n    headword_marker_opacity: float = 40.0\n    # Main overlay colours: headword markers stay red; other structural lines use blue.\n''',
)
replace_once(
    "src/picture_capture/models.py",
    '''    def to_json(self, path: Path) -> None:\n        path.parent.mkdir(parents=True, exist_ok=True)\n        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")\n\n    @classmethod\n    def from_json(cls, path: Path) -> "AppSettings":\n        raw = json.loads(path.read_text(encoding="utf-8"))\n''',
    '''    def to_json(self, path: Path) -> None:\n        path.parent.mkdir(parents=True, exist_ok=True)\n        payload = asdict(self)\n        for name in ("guide_opacity", "headword_marker_opacity"):\n            payload[name] = _normalize_display_opacity(payload.get(name, 40.0))\n        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")\n\n    @classmethod\n    def from_json(cls, path: Path) -> "AppSettings":\n        raw = json.loads(path.read_text(encoding="utf-8"))\n        for name in ("guide_opacity", "headword_marker_opacity"):\n            raw[name] = _normalize_display_opacity(raw.get(name, 40.0))\n''',
)


# ---------------------------------------------------------------------------
# 3. Static Settings Center metadata.
# ---------------------------------------------------------------------------
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '''        ("微调判距", "horizontal_tolerance", float), ("标记线高", "marker_height", int),\n        ("垂直线宽", "guide_width", int), ("黑色阈值 RGB 和", "darkness_threshold", int),\n''',
    '''        ("微调判距", "horizontal_tolerance", float), ("标记线高", "marker_height", int),\n        ("词头横线不透明度", "headword_marker_opacity", float),\n        ("垂直线宽", "guide_width", int), ("栏左垂线不透明度", "guide_opacity", float),\n        ("黑色阈值 RGB 和", "darkness_threshold", int),\n''',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '        ("词条线显示", ["marker_height", "guide_width"]),\n',
    '        ("词条线显示", ["marker_height", "headword_marker_opacity", "guide_width", "guide_opacity"]),\n',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '        "horizontal_tolerance": "微调判距",\n',
    '        "horizontal_tolerance": "微调判距",\n        "guide_opacity": "栏左垂线不透明度",\n        "headword_marker_opacity": "词头横线不透明度",\n',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '''        "marker_height": "作用：主界面词头横线的显示线宽/可视厚度，绘制时会按当前界面缩放和旧项目兼容比例调整。它影响视觉与点击辨识，不改变词头 Y 坐标或 OCR 判定。\\n\\n调整：高 DPI/高缩放下看不清可适当增大；过粗会遮挡文字。属于纯显示参数。",\n        "guide_width": "作用：主界面栏左参考线/列路径的显示宽度。只控制视觉叠加层，不改变列跟踪、栏位置或切图数据。\\n\\n调整：为了在高分辨率屏幕上更易观察可增大；如果参考线遮挡正文则减小。识别结果不应随它变化。",\n''',
    '''        "marker_height": "作用：主界面词头横线的显示线宽/可视厚度，绘制时会按当前界面缩放和旧项目兼容比例调整。它影响视觉与点击辨识，不改变词头 Y 坐标或 OCR 判定。\\n\\n调整：高 DPI/高缩放下看不清可适当增大；过粗会遮挡文字。属于纯显示参数。\\n\\n粗细方向：词头横线的原始 Y 为上边界锚点；宽度增加时只向下方扩展，不向上遮挡词头。",\n        "headword_marker_opacity": "作用：控制主画布词头/词条横线覆盖在扫描图片上的不透明度，只改变显示。100% 为完全不透明，0% 为完全透明；不会改变横线 Y 坐标、PDIC、OCR、校对或切图。\\n\\n调整：横线遮挡字形时降低；需要快速检查漏线、错线时提高。",\n        "guide_width": "作用：主界面栏左参考线/列路径的显示宽度。只控制视觉叠加层，不改变列跟踪、栏位置或切图数据。\\n\\n调整：为了在高分辨率屏幕上更易观察可增大；如果参考线遮挡正文则减小。识别结果不应随它变化。\\n\\n粗细方向：栏左路径为左边界锚点；宽度增加时只向右侧扩展，不向栏外扩展。",\n        "guide_opacity": "作用：控制主画布【栏左垂线】覆盖在扫描图片上的不透明度，只改变显示。100% 为完全不透明，0% 为完全透明；不会改变栏位检测、栏左路径、画线结果或切图。\\n\\n调整：扫描文字较密时可适当降低，使参考垂线不遮挡原文；需要强调栏路径时再提高。",\n''',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '''DISPLAY_FIELDS = (\n        "marker_height", "guide_width",\n''',
    '''DISPLAY_FIELDS = (\n        "marker_height", "headword_marker_opacity", "guide_width", "guide_opacity",\n''',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '''SETTING_UNITS = {\n        "columns": "栏",\n''',
    '''SETTING_UNITS = {\n        "columns": "栏",\n        "guide_opacity": "%", "headword_marker_opacity": "%",\n''',
)
replace_once(
    "src/picture_capture/ui/settings/schema.py",
    '''SETTING_SPIN = {\n        "columns": (1, 12, 1),\n''',
    '''SETTING_SPIN = {\n        "columns": (1, 12, 1),\n        "guide_opacity": (0.0, 100.0, 5.0),\n        "headword_marker_opacity": (0.0, 100.0, 5.0),\n''',
)


# ---------------------------------------------------------------------------
# 4. PictureCaptureApp owns quick controls and calls rendering helper directly.
# ---------------------------------------------------------------------------
replace_once(
    "src/picture_capture/app.py",
    '''from .unicode_nonbmp_input import (\n    attach_nonbmp_unicode_input, close_nonbmp_unicode_input,\n)\n''',
    '''from .unicode_nonbmp_input import (\n    attach_nonbmp_unicode_input, close_nonbmp_unicode_input,\n)\nfrom .overlay_opacity import (\n    add_quick_opacity_control, clear_alpha_line_photos,\n    create_alpha_canvas_line, release_alpha_line_photos,\n)\n''',
)
replace_once(
    "src/picture_capture/app.py",
    '''        ttk.Entry(\n            line_row, textvariable=guide_value, width=5, justify="left"\n        ).pack(side="left", padx=(2, 10))\n        ttk.Checkbutton(line_row, text="插图形状：轮廓", variable=self.polygon_var, command=self.redraw).pack(side="left")\n''',
    '''        ttk.Entry(\n            line_row, textvariable=guide_value, width=5, justify="left"\n        ).pack(side="left", padx=(2, 10))\n        add_quick_opacity_control(self, line_row, name="guide_opacity")\n        ttk.Checkbutton(line_row, text="插图形状：轮廓", variable=self.polygon_var, command=self.redraw).pack(side="left")\n''',
)
replace_once(
    "src/picture_capture/app.py",
    '''        ttk.Entry(\n            marker_row, textvariable=marker_value, width=5, justify="left"\n        ).pack(side="left", padx=(2, 10))\n        label_visible_var = tk.BooleanVar(value=bool(self.settings.show_illustration_labels))\n''',
    '''        ttk.Entry(\n            marker_row, textvariable=marker_value, width=5, justify="left"\n        ).pack(side="left", padx=(2, 10))\n        add_quick_opacity_control(self, marker_row, name="headword_marker_opacity")\n        label_visible_var = tk.BooleanVar(value=bool(self.settings.show_illustration_labels))\n''',
)
replace_once(
    "src/picture_capture/app.py",
    '''            item = self.canvas.create_line(\n                marker_start[0] * self.view_scale,\n                marker_start[1] * self.view_scale,\n                marker_end[0] * self.view_scale,\n                marker_end[1] * self.view_scale,\n                fill=self.settings.headword_marker_color,\n                width=marker_line_width,\n            )\n''',
    '''            item = create_alpha_canvas_line(\n                self,\n                (\n                    marker_start[0] * self.view_scale,\n                    marker_start[1] * self.view_scale,\n                    marker_end[0] * self.view_scale,\n                    marker_end[1] * self.view_scale,\n                ),\n                fill=self.settings.headword_marker_color,\n                width=marker_line_width,\n                opacity=self.settings.headword_marker_opacity,\n            )\n''',
)
replace_once(
    "src/picture_capture/app.py",
    '''                        self.canvas.create_line(\n                            *coords,\n                            fill=self.settings.guide_color,\n                            width=scaled_overlay_line_width(self.settings.guide_width, overlay_scale),\n                            smooth=True,\n                        )\n''',
    '''                        create_alpha_canvas_line(\n                            self,\n                            tuple(coords),\n                            fill=self.settings.guide_color,\n                            width=scaled_overlay_line_width(self.settings.guide_width, overlay_scale),\n                            opacity=self.settings.guide_opacity,\n                            smooth=True,\n                        )\n''',
)
replace_once(
    "src/picture_capture/app.py",
    '''    def redraw(self) -> None:\n        self._sync_polygon_label_texts()\n''',
    '''    def redraw(self) -> None:\n        clear_alpha_line_photos(self)\n        self._sync_polygon_label_texts()\n''',
)
replace_once(
    "src/picture_capture/app.py",
    '''        widgets = list(record.get("widgets") or [])\n        for item in list(record.get("canvas_items") or []):\n            try:\n                self.canvas.delete(item)\n''',
    '''        widgets = list(record.get("widgets") or [])\n        canvas_items = list(record.get("canvas_items") or [])\n        release_alpha_line_photos(self, canvas_items)\n        for item in canvas_items:\n            try:\n                self.canvas.delete(item)\n''',
)


# ---------------------------------------------------------------------------
# 5. Separate illustration-fill seam: only remove its dependency on runtime line
#    ownership. Its installer/persistence/rendering behavior otherwise stays put.
# ---------------------------------------------------------------------------
replace_once(
    "src/picture_capture/illustration_fill_opacity_runtime.py",
    '''from PIL import Image, ImageColor, ImageDraw, ImageTk\n\nfrom . import overlay_opacity_runtime as line_opacity\n''',
    '''from PIL import Image, ImageColor, ImageDraw, ImageTk\n\nfrom .overlay_opacity import find_checkbutton, flatten_coordinates\n''',
)
replace_once(
    "src/picture_capture/illustration_fill_opacity_runtime.py",
    '''def configure_overlay_opacity_defaults() -> None:\n    """Set guide/marker defaults before their runtime properties are installed."""\n    line_opacity._DEFAULT_GUIDE_OPACITY = DEFAULT_DISPLAY_OPACITY\n    line_opacity._DEFAULT_MARKER_OPACITY = DEFAULT_DISPLAY_OPACITY\n''',
    '''def configure_overlay_opacity_defaults() -> None:\n    """Compatibility no-op: native AppSettings now owns the 40% line defaults."""\n    return None\n''',
)
replace_once(
    "src/picture_capture/illustration_fill_opacity_runtime.py",
    '    values = line_opacity._flatten_coordinates(coordinates)\n',
    '    values = flatten_coordinates(coordinates)\n',
)
replace_once(
    "src/picture_capture/illustration_fill_opacity_runtime.py",
    '''        finder = getattr(line_opacity, "_find_checkbutton")\n        check = finder(self, "插图形状：轮廓")\n''',
    '''        check = find_checkbutton(self, "插图形状：轮廓")\n''',
)


# ---------------------------------------------------------------------------
# 6. Bootstrap and architecture ratchet.
# ---------------------------------------------------------------------------
remove_once(
    "src/picture_capture/bootstrap/gui.py",
    '    from ..overlay_opacity_runtime import install_overlay_opacity_runtime\n',
)
remove_once(
    "src/picture_capture/bootstrap/gui.py",
    '    install_overlay_opacity_runtime(app_module)\n',
)
remove_once(
    "scripts/architecture_guard.py",
    '    "overlay_opacity_runtime.py",\n',
)

old_runtime = ROOT / "src/picture_capture/overlay_opacity_runtime.py"
if not old_runtime.exists():
    raise SystemExit("overlay_opacity_runtime.py missing before migration")
old_runtime.unlink()


# ---------------------------------------------------------------------------
# 7. Focused characterization/migration tests.
# ---------------------------------------------------------------------------
old_test = ROOT / "tests/test_overlay_opacity_runtime.py"
if not old_test.exists():
    raise SystemExit("test_overlay_opacity_runtime.py missing before migration")
old_test.unlink()

(ROOT / "tests/test_overlay_opacity.py").write_text(
    '''from __future__ import annotations

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
    illustration = (
        root / "src/picture_capture/illustration_fill_opacity_runtime.py"
    ).read_text(encoding="utf-8")
    assert "create_alpha_canvas_line" in app
    assert 'add_quick_opacity_control(self, line_row, name="guide_opacity")' in app
    assert 'add_quick_opacity_control(self, marker_row, name="headword_marker_opacity")' in app
    assert "install_overlay_opacity_runtime" not in gui
    assert not (root / "src/picture_capture/overlay_opacity_runtime.py").exists()
    assert '"overlay_opacity_runtime.py"' not in guard
    assert "from .overlay_opacity import find_checkbutton, flatten_coordinates" in illustration
    assert "overlay_opacity_runtime" not in illustration
''',
    encoding="utf-8",
)

replace_once(
    "tests/test_display_opacity_defaults.py",
    '''from picture_capture import overlay_opacity_runtime\nfrom picture_capture.illustration_fill_opacity_runtime import (\n''',
    '''from picture_capture.models import AppSettings\nfrom picture_capture.illustration_fill_opacity_runtime import (\n''',
)
replace_once(
    "tests/test_display_opacity_defaults.py",
    '''    assert DEFAULT_DISPLAY_OPACITY == 40.0\n    assert overlay_opacity_runtime._DEFAULT_GUIDE_OPACITY == 40.0\n    assert overlay_opacity_runtime._DEFAULT_MARKER_OPACITY == 40.0\n''',
    '''    assert DEFAULT_DISPLAY_OPACITY == 40.0\n    assert AppSettings().guide_opacity == 40.0\n    assert AppSettings().headword_marker_opacity == 40.0\n''',
)
replace_once(
    "tests/test_display_opacity_defaults.py",
    '''def test_gui_composition_sets_defaults_before_installing_line_opacity():\n    root = Path(__file__).resolve().parents[1]\n    source = (\n        root / "src/picture_capture/bootstrap/gui.py"\n    ).read_text(encoding="utf-8")\n    assert source.index("configure_overlay_opacity_defaults()") < source.index(\n        "install_overlay_opacity_runtime(app_module)"\n    )\n    assert source.index("install_overlay_opacity_runtime(app_module)") < source.index(\n        "install_illustration_fill_opacity_runtime(app_module)"\n    )\n\n\n''',
    '''def test_gui_composition_keeps_only_illustration_opacity_runtime():\n    root = Path(__file__).resolve().parents[1]\n    source = (\n        root / "src/picture_capture/bootstrap/gui.py"\n    ).read_text(encoding="utf-8")\n    assert "install_overlay_opacity_runtime" not in source\n    assert "configure_overlay_opacity_defaults()" in source\n    assert "install_illustration_fill_opacity_runtime(app_module)" in source\n\n\n''',
)

print("Phase 5O migration applied")
