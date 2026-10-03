from __future__ import annotations

"""True-alpha display opacity for column guides and headword marker lines.

Tk Canvas line items do not support RGBA alpha.  For opacity values below 100%,
this module renders only the requested line into a small transparent Pillow image
and places that image on the canvas at the same z-order.  At 100% opacity the
original Canvas line path is preserved exactly.

The two opacity values are display-only and intentionally remain outside the
large AppSettings dataclass for this compatibility stage.  Lightweight runtime
properties plus JSON read/write hooks keep the values project-persistent without
changing detection, PDIC, cropping, OCR, or geometry semantics.
"""

from functools import wraps
import json
import math
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable

from PIL import Image, ImageColor, ImageDraw, ImageTk


_DEFAULT_GUIDE_OPACITY = 100.0
_DEFAULT_MARKER_OPACITY = 100.0
_OPACITY_VALUES: dict[int, dict[str, float]] = {}


def _normalize_opacity(value: object, default: float = 100.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    return max(0.0, min(100.0, number))


def _settings_values(settings: Any) -> dict[str, float]:
    return _OPACITY_VALUES.setdefault(
        id(settings),
        {
            "guide_opacity": _DEFAULT_GUIDE_OPACITY,
            "headword_marker_opacity": _DEFAULT_MARKER_OPACITY,
        },
    )


def _install_settings_properties(settings_class: type[Any]) -> None:
    if bool(getattr(settings_class, "_pc_overlay_opacity_installed", False)):
        return

    # If a future native model adds these fields, defer to it completely.
    native_fields = set(getattr(settings_class, "__dataclass_fields__", {}))
    if {"guide_opacity", "headword_marker_opacity"}.issubset(native_fields):
        settings_class._pc_overlay_opacity_installed = True
        return

    original_init = settings_class.__init__

    @wraps(original_init)
    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _OPACITY_VALUES[id(self)] = {
            "guide_opacity": _DEFAULT_GUIDE_OPACITY,
            "headword_marker_opacity": _DEFAULT_MARKER_OPACITY,
        }

    settings_class.__init__ = wrapped_init

    if "guide_opacity" not in native_fields:
        def get_guide(self) -> float:
            return _settings_values(self)["guide_opacity"]

        def set_guide(self, value: object) -> None:
            _settings_values(self)["guide_opacity"] = _normalize_opacity(value)

        settings_class.guide_opacity = property(get_guide, set_guide)

    if "headword_marker_opacity" not in native_fields:
        def get_marker(self) -> float:
            return _settings_values(self)["headword_marker_opacity"]

        def set_marker(self, value: object) -> None:
            _settings_values(self)["headword_marker_opacity"] = _normalize_opacity(value)

        settings_class.headword_marker_opacity = property(get_marker, set_marker)

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
        payload["guide_opacity"] = _normalize_opacity(
            getattr(self, "guide_opacity", _DEFAULT_GUIDE_OPACITY)
        )
        payload["headword_marker_opacity"] = _normalize_opacity(
            getattr(self, "headword_marker_opacity", _DEFAULT_MARKER_OPACITY)
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
            result.guide_opacity = payload.get(
                "guide_opacity", _DEFAULT_GUIDE_OPACITY
            )
            result.headword_marker_opacity = payload.get(
                "headword_marker_opacity", _DEFAULT_MARKER_OPACITY
            )
        return result

    settings_class.to_json = to_json
    settings_class.from_json = from_json
    settings_class._pc_overlay_opacity_installed = True


def _flatten_coordinates(values: tuple[Any, ...]) -> list[float]:
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
    """Small Chaikin pass approximating the Canvas smooth display path."""
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
    """Return a tightly bounded RGBA image and its canvas top-left position."""
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
    alpha = round(_normalize_opacity(opacity) * 255.0 / 100.0)

    # Render at 2x then downsample so thin diagonal/curved overlays stay smooth.
    aa = 2
    overlay = Image.new("RGBA", (image_width * aa, image_height * aa), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    shifted = [
        ((x - min_x) * aa, (y - min_y) * aa)
        for x, y in points
    ]
    draw.line(
        shifted,
        fill=(rgb[0], rgb[1], rgb[2], alpha),
        width=max(1, line_width * aa),
        joint="curve",
    )
    if aa != 1:
        overlay = overlay.resize(
            (image_width, image_height),
            Image.Resampling.LANCZOS,
        )
    return overlay, int(min_x), int(min_y)


def _alpha_canvas_line(
    owner: Any,
    original_create_line,
    coordinates: tuple[Any, ...],
    options: dict[str, Any],
    *,
    opacity: float,
) -> int:
    normalized = _normalize_opacity(opacity)
    if normalized >= 100.0:
        return int(original_create_line(*coordinates, **options))
    if normalized <= 0.0:
        hidden = dict(options)
        hidden["state"] = "hidden"
        return int(original_create_line(*coordinates, **hidden))

    flattened = _flatten_coordinates(coordinates)
    if len(flattened) < 4:
        return int(original_create_line(*coordinates, **options))

    overlay, left, top = render_alpha_line_overlay(
        flattened,
        color=str(options.get("fill") or "#000000"),
        width=float(options.get("width") or 1.0),
        opacity=normalized,
        smooth=bool(options.get("smooth", False)),
    )
    photo = ImageTk.PhotoImage(overlay)
    image_options: dict[str, Any] = {"anchor": "nw", "image": photo}
    if "tags" in options:
        image_options["tags"] = options["tags"]
    if options.get("state") in {"hidden", "disabled", "normal"}:
        image_options["state"] = options["state"]
    item = int(owner.canvas.create_image(left, top, **image_options))
    photos = owner.__dict__.setdefault("_pc_alpha_line_photos", {})
    photos[item] = photo
    return item


def _install_settings_dialog_fields(app_module: Any) -> None:
    dialog = app_module.SettingsDialog
    fields = list(getattr(dialog, "FIELDS", ()))
    names = {name for _label, name, _cast in fields}
    if "guide_opacity" not in names:
        fields.append(("栏左垂线不透明度", "guide_opacity", float))
    if "headword_marker_opacity" not in names:
        fields.append(("词头横线不透明度", "headword_marker_opacity", float))
    dialog.FIELDS = tuple(fields)

    display = list(getattr(dialog, "DISPLAY_FIELDS", ()))
    for name, after in (
        ("guide_opacity", "guide_width"),
        ("headword_marker_opacity", "marker_height"),
    ):
        if name in display:
            continue
        try:
            position = display.index(after) + 1
        except ValueError:
            position = len(display)
        display.insert(position, name)
    dialog.DISPLAY_FIELDS = tuple(display)

    dialog.SETTING_LABELS = dict(getattr(dialog, "SETTING_LABELS", {}))
    dialog.SETTING_LABELS.update({
        "guide_opacity": "栏左垂线不透明度",
        "headword_marker_opacity": "词头横线不透明度",
    })
    dialog.SETTING_UNITS = dict(getattr(dialog, "SETTING_UNITS", {}))
    dialog.SETTING_UNITS.update({
        "guide_opacity": "%",
        "headword_marker_opacity": "%",
    })
    dialog.SETTING_SPIN = dict(getattr(dialog, "SETTING_SPIN", {}))
    dialog.SETTING_SPIN.update({
        "guide_opacity": (0.0, 100.0, 5.0),
        "headword_marker_opacity": (0.0, 100.0, 5.0),
    })
    dialog.SETTING_HELP = dict(getattr(dialog, "SETTING_HELP", {}))
    dialog.SETTING_HELP.update({
        "guide_opacity": (
            "作用：控制主画布【栏左垂线】覆盖在扫描图片上的不透明度，只改变显示。"
            "100% 为完全不透明，0% 为完全透明；不会改变栏位检测、栏左路径、画线结果或切图。\n\n"
            "调整：扫描文字较密时可适当降低，使参考垂线不遮挡原文；需要强调栏路径时再提高。"
        ),
        "headword_marker_opacity": (
            "作用：控制主画布词头/词条横线覆盖在扫描图片上的不透明度，只改变显示。"
            "100% 为完全不透明，0% 为完全透明；不会改变横线 Y 坐标、PDIC、OCR、校对或切图。\n\n"
            "调整：横线遮挡字形时降低；需要快速检查漏线、错线时提高。"
        ),
    })


def _descendants(root: tk.Misc):
    for child in root.winfo_children():
        yield child
        yield from _descendants(child)


def _find_checkbutton(root: tk.Misc, text: str):
    for widget in _descendants(root):
        if not isinstance(widget, (ttk.Checkbutton, tk.Checkbutton)):
            continue
        try:
            if str(widget.cget("text") or "") == text:
                return widget
        except tk.TclError:
            continue
    return None


def _add_quick_opacity_control(
    app: Any,
    row: tk.Misc,
    *,
    name: str,
    before: tk.Misc | None = None,
) -> None:
    if name in getattr(app, "quick_vars", {}):
        return
    current = _normalize_opacity(getattr(app.settings, name, 100.0))
    rendered = f"{current:.0f}" if abs(current - round(current)) < 1e-9 else f"{current:g}"
    variable = tk.StringVar(value=rendered)
    app.quick_vars[name] = variable
    app.quick_field_casts[name] = float

    pack_options: dict[str, Any] = {"side": "left"}
    if before is not None:
        pack_options["before"] = before

    label = ttk.Label(row, text="不透明度：")
    label.pack(**pack_options)
    spin = ttk.Spinbox(
        row,
        textvariable=variable,
        from_=0,
        to=100,
        increment=5,
        width=5,
    )
    spin.pack(side="left", before=before, padx=(2, 1)) if before is not None else spin.pack(side="left", padx=(2, 1))
    percent = ttk.Label(row, text="%")
    percent.pack(side="left", before=before, padx=(0, 8)) if before is not None else percent.pack(side="left", padx=(0, 8))

    variable.trace_add("write", lambda *_args: app._quick_parameter_changed())
    try:
        app._attach_tooltip(
            spin,
            "100%=完全不透明，0%=完全透明；只改变主画布显示，不改变识别、坐标或切图。",
        )
    except Exception:
        pass


def _install_quick_controls(app_class: type[Any]) -> None:
    original_init = app_class.__init__
    if bool(getattr(original_init, "_pc_overlay_opacity", False)):
        return

    @wraps(original_init)
    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        guide_check = _find_checkbutton(self, "栏左垂线")
        if guide_check is not None:
            row = guide_check.master
            before = _find_checkbutton(row, "插图形状：轮廓")
            _add_quick_opacity_control(
                self,
                row,
                name="guide_opacity",
                before=before,
            )
        marker_check = _find_checkbutton(self, "词头横线")
        if marker_check is not None:
            _add_quick_opacity_control(
                self,
                marker_check.master,
                name="headword_marker_opacity",
            )

    wrapped_init._pc_overlay_opacity = True  # type: ignore[attr-defined]
    app_class.__init__ = wrapped_init


def _install_alpha_rendering(app_class: type[Any]) -> None:
    original_redraw = app_class.redraw
    original_entry_overlay = app_class._draw_entry_overlay
    original_remove_entry = app_class._remove_entry_overlay

    if bool(getattr(original_redraw, "_pc_overlay_opacity", False)):
        return

    @wraps(original_entry_overlay)
    def draw_entry_overlay(self, *args, **kwargs):
        canvas = self.canvas
        original_create_line = canvas.create_line

        def create_line(*coordinates, **options):
            if str(options.get("fill") or "") == str(
                getattr(self.settings, "headword_marker_color", "") or ""
            ):
                return _alpha_canvas_line(
                    self,
                    original_create_line,
                    coordinates,
                    options,
                    opacity=getattr(
                        self.settings,
                        "headword_marker_opacity",
                        _DEFAULT_MARKER_OPACITY,
                    ),
                )
            return original_create_line(*coordinates, **options)

        canvas.create_line = create_line
        try:
            return original_entry_overlay(self, *args, **kwargs)
        finally:
            canvas.create_line = original_create_line

    @wraps(original_redraw)
    def redraw(self, *args, **kwargs):
        self.__dict__["_pc_alpha_line_photos"] = {}
        canvas = self.canvas
        original_create_line = canvas.create_line

        def create_line(*coordinates, **options):
            is_guide = bool(options.get("smooth", False)) and str(
                options.get("fill") or ""
            ) == str(getattr(self.settings, "guide_color", "") or "")
            if is_guide:
                return _alpha_canvas_line(
                    self,
                    original_create_line,
                    coordinates,
                    options,
                    opacity=getattr(
                        self.settings,
                        "guide_opacity",
                        _DEFAULT_GUIDE_OPACITY,
                    ),
                )
            return original_create_line(*coordinates, **options)

        canvas.create_line = create_line
        try:
            return original_redraw(self, *args, **kwargs)
        finally:
            canvas.create_line = original_create_line

    @wraps(original_remove_entry)
    def remove_entry_overlay(self, entry, *args, **kwargs):
        record = dict(self.__dict__.get("_entry_visuals", {})).get(id(entry), {})
        item_ids = list(record.get("canvas_items") or []) if isinstance(record, dict) else []
        try:
            return original_remove_entry(self, entry, *args, **kwargs)
        finally:
            photos = self.__dict__.get("_pc_alpha_line_photos", {})
            if isinstance(photos, dict):
                for item in item_ids:
                    photos.pop(item, None)

    redraw._pc_overlay_opacity = True  # type: ignore[attr-defined]
    app_class.redraw = redraw
    app_class._draw_entry_overlay = draw_entry_overlay
    app_class._remove_entry_overlay = remove_entry_overlay


def install_overlay_opacity_runtime(app_module: Any) -> None:
    """Install project-persistent opacity controls and true-alpha rendering."""
    app_class = app_module.PictureCaptureApp
    if bool(getattr(app_class, "_pc_overlay_opacity_runtime_installed", False)):
        return

    _install_settings_properties(app_module.AppSettings)
    _install_settings_dialog_fields(app_module)
    _install_quick_controls(app_class)
    _install_alpha_rendering(app_class)
    app_class._pc_overlay_opacity_runtime_installed = True


__all__ = [
    "_normalize_opacity",
    "install_overlay_opacity_runtime",
    "render_alpha_line_overlay",
]
