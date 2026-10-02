from __future__ import annotations

"""True-alpha opacity for illustration-region fills plus shared 40% defaults.

Column guides and headword marker lines already use Pillow RGBA overlays for
true alpha. Illustration regions historically used Tk's ``gray50`` stipple,
which is a 50% bitmap pattern rather than real transparency. This runtime keeps
the editable Canvas polygon as the authoritative outline/hit target and places a
tightly bounded RGBA fill image immediately beneath it.

All three display overlays now default to 40% opacity. Existing projects that
explicitly saved guide/marker opacity keep their stored values; the new
illustration field also falls back to 40% when absent from older settings.json.
"""

from functools import wraps
import json
import math
from pathlib import Path
from typing import Any, Iterable
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageColor, ImageDraw, ImageTk

from . import overlay_opacity_runtime as line_opacity


DEFAULT_DISPLAY_OPACITY = 40.0
_DEFAULT_ILLUSTRATION_FILL_OPACITY = DEFAULT_DISPLAY_OPACITY
_ILLUSTRATION_VALUES: dict[int, float] = {}


def configure_overlay_opacity_defaults() -> None:
    """Set guide/marker defaults before their runtime properties are installed."""
    line_opacity._DEFAULT_GUIDE_OPACITY = DEFAULT_DISPLAY_OPACITY
    line_opacity._DEFAULT_MARKER_OPACITY = DEFAULT_DISPLAY_OPACITY


def _normalize(value: object, default: float = DEFAULT_DISPLAY_OPACITY) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    return max(0.0, min(100.0, number))


def _get_illustration_opacity(settings: Any) -> float:
    return _ILLUSTRATION_VALUES.setdefault(
        id(settings),
        _DEFAULT_ILLUSTRATION_FILL_OPACITY,
    )


def _set_illustration_opacity(settings: Any, value: object) -> None:
    _ILLUSTRATION_VALUES[id(settings)] = _normalize(
        value,
        _DEFAULT_ILLUSTRATION_FILL_OPACITY,
    )


def _install_settings_property(settings_class: type[Any]) -> None:
    if bool(getattr(settings_class, "_pc_illustration_fill_opacity_installed", False)):
        return

    native_fields = set(getattr(settings_class, "__dataclass_fields__", {}))
    native = "illustration_fill_opacity" in native_fields
    original_init = settings_class.__init__

    if not native:
        settings_class.illustration_fill_opacity = property(
            _get_illustration_opacity,
            _set_illustration_opacity,
        )

        @wraps(original_init)
        def wrapped_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            _ILLUSTRATION_VALUES[id(self)] = _DEFAULT_ILLUSTRATION_FILL_OPACITY

        settings_class.__init__ = wrapped_init

    original_to_json = settings_class.to_json
    original_from_json = settings_class.from_json

    @wraps(original_to_json)
    def to_json(self, path: Path) -> None:
        original_to_json(self, path)
        target = Path(path)
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        payload["illustration_fill_opacity"] = _normalize(
            getattr(
                self,
                "illustration_fill_opacity",
                _DEFAULT_ILLUSTRATION_FILL_OPACITY,
            ),
            _DEFAULT_ILLUSTRATION_FILL_OPACITY,
        )
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def from_json(cls, path: Path):
        result = original_from_json(path)
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        if isinstance(payload, dict):
            result.illustration_fill_opacity = payload.get(
                "illustration_fill_opacity",
                _DEFAULT_ILLUSTRATION_FILL_OPACITY,
            )
        return result

    settings_class.to_json = to_json
    settings_class.from_json = from_json
    settings_class._pc_illustration_fill_opacity_installed = True


def render_alpha_polygon_overlay(
    coordinates: Iterable[float],
    *,
    color: str,
    opacity: float,
) -> tuple[Image.Image, int, int]:
    """Render one tightly bounded anti-aliased RGBA polygon fill."""
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
    alpha = round(_normalize(opacity) * 255.0 / 100.0)
    aa = 2
    overlay = Image.new("RGBA", (width * aa, height * aa), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    shifted = [
        ((x - min_x) * aa, (y - min_y) * aa)
        for x, y in points
    ]
    draw.polygon(shifted, fill=(rgb[0], rgb[1], rgb[2], alpha))
    overlay = overlay.resize((width, height), Image.Resampling.LANCZOS)
    return overlay, int(min_x), int(min_y)


def _tags(options: dict[str, Any]) -> tuple[str, ...]:
    raw = options.get("tags", ())
    if isinstance(raw, str):
        return (raw,)
    try:
        return tuple(str(item) for item in raw)
    except TypeError:
        return ()


def _alpha_canvas_polygon(
    owner: Any,
    original_create_polygon,
    coordinates: tuple[Any, ...],
    options: dict[str, Any],
) -> int:
    """Create editable outline polygon plus an RGBA fill image underneath."""
    values = line_opacity._flatten_coordinates(coordinates)
    if len(values) < 6:
        return int(original_create_polygon(*coordinates, **options))

    opacity = _normalize(
        getattr(
            owner.settings,
            "illustration_fill_opacity",
            _DEFAULT_ILLUSTRATION_FILL_OPACITY,
        )
    )
    outline_options = dict(options)
    outline_options.pop("stipple", None)

    # 100% can stay a native Canvas polygon. For every lower value the Canvas
    # polygon remains only as outline/hit geometry while Pillow supplies fill.
    if opacity >= 100.0:
        return int(original_create_polygon(*coordinates, **outline_options))

    outline_options["fill"] = ""
    fill_item: int | None = None
    photo = None
    if opacity > 0.0:
        overlay, left, top = render_alpha_polygon_overlay(
            values,
            color=str(options.get("fill") or "#ffe66d"),
            opacity=opacity,
        )
        photo = ImageTk.PhotoImage(overlay)
        fill_tags = tuple(tag for tag in _tags(options) if tag) + (
            "pc-alpha-illustration-fill",
        )
        fill_item = int(owner.canvas.create_image(
            left,
            top,
            anchor="nw",
            image=photo,
            tags=fill_tags,
        ))

    polygon_item = int(original_create_polygon(*coordinates, **outline_options))
    if fill_item is not None:
        try:
            owner.canvas.tag_lower(fill_item, polygon_item)
        except tk.TclError:
            pass
        records = owner.__dict__.setdefault("_pc_alpha_polygon_records", {})
        records[polygon_item] = {
            "image_item": fill_item,
            "photo": photo,
        }
    return polygon_item


def _refresh_polygon_fill(owner: Any, region_index: int) -> None:
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
        for point in region.points
        for value in point
    ]
    if len(values) < 6:
        return
    overlay, left, top = render_alpha_polygon_overlay(
        values,
        color=str(getattr(owner.settings, "illustration_fill_color", "#ffe66d")),
        opacity=getattr(
            owner.settings,
            "illustration_fill_opacity",
            _DEFAULT_ILLUSTRATION_FILL_OPACITY,
        ),
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


def _install_settings_dialog_field(app_module: Any) -> None:
    dialog = app_module.SettingsDialog
    fields = list(getattr(dialog, "FIELDS", ()))
    if not any(name == "illustration_fill_opacity" for _label, name, _cast in fields):
        fields.append(("插图区域不透明度", "illustration_fill_opacity", float))
    dialog.FIELDS = tuple(fields)

    display = list(getattr(dialog, "DISPLAY_FIELDS", ()))
    if "illustration_fill_opacity" not in display:
        try:
            position = display.index("guide_opacity") + 1
        except ValueError:
            position = min(2, len(display))
        display.insert(position, "illustration_fill_opacity")
    dialog.DISPLAY_FIELDS = tuple(display)

    dialog.SETTING_LABELS = dict(getattr(dialog, "SETTING_LABELS", {}))
    dialog.SETTING_LABELS["illustration_fill_opacity"] = "插图区域不透明度"
    dialog.SETTING_UNITS = dict(getattr(dialog, "SETTING_UNITS", {}))
    dialog.SETTING_UNITS["illustration_fill_opacity"] = "%"
    dialog.SETTING_SPIN = dict(getattr(dialog, "SETTING_SPIN", {}))
    dialog.SETTING_SPIN["illustration_fill_opacity"] = (0.0, 100.0, 5.0)
    dialog.SETTING_HELP = dict(getattr(dialog, "SETTING_HELP", {}))
    dialog.SETTING_HELP["illustration_fill_opacity"] = (
        "作用：控制主画布插图区域背景填充覆盖在扫描图片上的真实不透明度，只改变显示。"
        "默认 40%；100% 为完全不透明，0% 为完全透明。插图轮廓线不受此值影响，"
        "也不会改变 PPP 区域坐标、插图切图范围或识别结果。"
    )


def _install_quick_control(app_class: type[Any]) -> None:
    original_init = app_class.__init__
    if bool(getattr(original_init, "_pc_illustration_fill_opacity", False)):
        return

    @wraps(original_init)
    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        finder = getattr(line_opacity, "_find_checkbutton")
        check = finder(self, "插图形状：轮廓")
        if check is None or "illustration_fill_opacity" in getattr(self, "quick_vars", {}):
            return
        row = check.master
        variable = tk.StringVar(value=f"{_get_illustration_opacity(self.settings):.0f}")
        self.quick_vars["illustration_fill_opacity"] = variable
        self.quick_field_casts["illustration_fill_opacity"] = float
        ttk.Label(row, text="区域不透明度：").pack(side="left", padx=(5, 0))
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
        variable.trace_add("write", lambda *_args: self._quick_parameter_changed())
        try:
            self._attach_tooltip(
                spin,
                "插图区域背景的真实透明度；默认40%，不改变轮廓或PPP坐标。",
            )
        except Exception:
            pass

    wrapped_init._pc_illustration_fill_opacity = True  # type: ignore[attr-defined]
    app_class.__init__ = wrapped_init


def _install_alpha_rendering(app_class: type[Any]) -> None:
    original_redraw = app_class.redraw
    original_update = app_class._update_polygon_canvas_geometry
    if bool(getattr(original_redraw, "_pc_illustration_fill_opacity", False)):
        return

    @wraps(original_redraw)
    def redraw(self, *args, **kwargs):
        self.__dict__["_pc_alpha_polygon_records"] = {}
        canvas = self.canvas
        original_create_polygon = canvas.create_polygon

        def create_polygon(*coordinates, **options):
            tags = _tags(options)
            is_illustration = (
                "ppp-overlay" in tags
                and str(options.get("fill") or "")
                == str(getattr(self.settings, "illustration_fill_color", "") or "")
            )
            if is_illustration:
                return _alpha_canvas_polygon(
                    self,
                    original_create_polygon,
                    coordinates,
                    options,
                )
            return original_create_polygon(*coordinates, **options)

        canvas.create_polygon = create_polygon
        try:
            return original_redraw(self, *args, **kwargs)
        finally:
            canvas.create_polygon = original_create_polygon

    @wraps(original_update)
    def update_polygon_canvas_geometry(self, region_index: int, *args, **kwargs):
        result = original_update(self, region_index, *args, **kwargs)
        _refresh_polygon_fill(self, int(region_index))
        return result

    redraw._pc_illustration_fill_opacity = True  # type: ignore[attr-defined]
    app_class.redraw = redraw
    app_class._update_polygon_canvas_geometry = update_polygon_canvas_geometry


def install_illustration_fill_opacity_runtime(app_module: Any) -> None:
    """Install persisted 40% illustration fill and true-alpha Canvas rendering."""
    app_class = app_module.PictureCaptureApp
    if bool(getattr(app_class, "_pc_illustration_fill_opacity_runtime_installed", False)):
        return
    _install_settings_property(app_module.AppSettings)
    _install_settings_dialog_field(app_module)
    _install_quick_control(app_class)
    _install_alpha_rendering(app_class)
    app_class._pc_illustration_fill_opacity_runtime_installed = True


__all__ = [
    "DEFAULT_DISPLAY_OPACITY",
    "configure_overlay_opacity_defaults",
    "install_illustration_fill_opacity_runtime",
    "render_alpha_polygon_overlay",
]
