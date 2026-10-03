from __future__ import annotations

"""Display-only visualization of the current page's inferred layout.

This module is installed by ``launcher.py`` after the main GUI module is loaded.
It deliberately keeps the visualization outside the detector implementation:
turning the overlay on or off must never change entry detection, PDIC output,
OCR results, or crop/export geometry.

The overlay is built from the same full-resolution analysis image and the same
auto-layout field-selection rules used by ordinary drawing, so users can see
both the raw layout estimate and the geometry that is actually consumed after
per-field automatic/manual choices are applied.
"""

from dataclasses import dataclass, replace
from typing import Any
import tkinter as tk
from tkinter import ttk

from .image_utils import build_analysis_image
from .layout_detection import detect_layout_parameters
from .processing import ORDINARY_AUTO_LAYOUT_FIELDS, derive_geometry
from .profile_semantics import page_template_analysis_image


_LAYOUT_TAG = "layout-visualization"


@dataclass(slots=True)
class LayoutVisualizationSnapshot:
    geometry: Any
    method: str
    confidence: float | None
    auto_enabled: bool
    applied_fields: dict[str, int]
    raw_estimate: dict[str, int]
    used_values: dict[str, int]


def _layout_cache_key(app: Any) -> tuple[Any, ...]:
    try:
        display_key = app._display_geometry_key()
    except Exception:
        display_key = None
    settings = app.settings
    controls = tuple(
        (field, bool(getattr(settings, switch, True)))
        for field, switch in ORDINARY_AUTO_LAYOUT_FIELDS
    )
    return (
        id(getattr(app, "image", None)),
        int(getattr(app, "current_index", -1)),
        display_key,
        bool(getattr(settings, "ordinary_auto_layout", False)),
        controls,
        str(getattr(settings, "layout_columns_policy", "") or ""),
        str(getattr(settings, "layout_column_separator_mode", "") or ""),
    )


def _snapshot_for_app(app: Any) -> LayoutVisualizationSnapshot:
    if getattr(app, "image", None) is None:
        raise RuntimeError("没有可显示的页面图像")

    key = _layout_cache_key(app)
    if (
        getattr(app, "_layout_visualization_snapshot_key", None) == key
        and getattr(app, "_layout_visualization_snapshot", None) is not None
    ):
        return app._layout_visualization_snapshot

    effective = app._current_effective_profile_settings()
    page_index = max(0, int(getattr(app, "current_index", 0)))
    masked = page_template_analysis_image(app.image, effective, page_index)
    analysis = build_analysis_image(masked, effective)
    try:
        used = replace(effective)
        auto_enabled = bool(getattr(used, "ordinary_auto_layout", False))
        estimate = None
        applied: dict[str, int] = {}
        raw: dict[str, int] = {}

        if auto_enabled:
            detector_settings = replace(used)
            if bool(getattr(used, "ordinary_auto_columns", True)):
                detector_settings.layout_columns_policy = "detect"
            estimate = detect_layout_parameters(analysis, detector_settings)
            for field, switch in ORDINARY_AUTO_LAYOUT_FIELDS:
                value = int(getattr(estimate, field))
                raw[field] = value
                if bool(getattr(used, switch, True)):
                    setattr(used, field, value)
                    applied[field] = value
            used.manual_columns = False

        geometry = derive_geometry(analysis, used)
        used_values = {
            "columns": int(getattr(used, "columns", len(geometry.column_starts))),
            "start_y": int(getattr(used, "start_y", geometry.top)),
            "manual_x": int(getattr(used, "manual_x", geometry.column_starts[0] if geometry.column_starts else 0)),
            "column_width": int(getattr(used, "column_width", geometry.column_widths[0] if geometry.column_widths else 0)),
            "gutter": int(getattr(used, "gutter", 0)),
            "character_height": int(getattr(used, "character_height", 0)),
            "row_padding": int(getattr(used, "row_padding", 0)),
            "bottom_y": int(getattr(geometry, "bottom", 0)),
        }
        snapshot = LayoutVisualizationSnapshot(
            geometry=geometry,
            method=(
                str(getattr(estimate, "method", "auto_layout"))
                if estimate is not None else "project/profile geometry"
            ),
            confidence=(
                float(getattr(estimate, "confidence"))
                if estimate is not None and getattr(estimate, "confidence", None) is not None
                else None
            ),
            auto_enabled=auto_enabled,
            applied_fields=applied,
            raw_estimate=raw,
            used_values=used_values,
        )
        app._layout_visualization_snapshot_key = key
        app._layout_visualization_snapshot = snapshot
        return snapshot
    finally:
        try:
            analysis.close()
        except Exception:
            pass
        try:
            if masked is not app.image:
                masked.close()
        except Exception:
            pass


def _source_polyline(geometry: Any, points: list[tuple[int, int]]) -> list[float]:
    values: list[float] = []
    for y, x in points:
        sx, sy = geometry.canonical_to_source(int(x), int(y))
        values.extend((float(sx), float(sy)))
    return values


def _summary_lines(snapshot: LayoutVisualizationSnapshot) -> list[str]:
    values = snapshot.used_values
    confidence = (
        f"{snapshot.confidence:.2f}" if snapshot.confidence is not None else "—"
    )
    lines = [
        f"Layout {'AUTO' if snapshot.auto_enabled else 'CURRENT'}",
        f"method: {snapshot.method}",
        f"confidence: {confidence}",
        f"columns: {values['columns']}   start_y: {values['start_y']}   bottom_y: {values['bottom_y']}",
        f"manual_x: {values['manual_x']}   column_width: {values['column_width']}   gutter: {values['gutter']}",
        f"character_height: {values['character_height']}   row_padding: {values['row_padding']}",
    ]
    if snapshot.auto_enabled:
        if snapshot.applied_fields:
            names = ", ".join(snapshot.applied_fields)
            lines.append(f"auto applied: {names}")
        disabled = [
            name for name in snapshot.raw_estimate
            if name not in snapshot.applied_fields
        ]
        if disabled:
            lines.append("raw only: " + ", ".join(disabled))
    return lines


def draw_layout_visualization(app: Any) -> None:
    """Draw the inferred/effective layout directly over the current page."""
    canvas = getattr(app, "canvas", None)
    if canvas is None:
        return
    try:
        canvas.delete(_LAYOUT_TAG)
    except tk.TclError:
        return

    var = getattr(app, "_layout_visualization_var", None)
    if var is None or not bool(var.get()):
        return
    if getattr(app, "image", None) is None:
        return
    try:
        if bool(app.hide_var.get()) or bool(app.crop_preview_var.get()):
            return
    except Exception:
        pass

    try:
        snapshot = _snapshot_for_app(app)
    except Exception as exc:
        # Visualization is diagnostic-only. Never let a failed overlay break the
        # ordinary GUI or detection workflow.
        try:
            canvas.create_text(
                12, 12,
                anchor="nw",
                text=f"Layout visualization unavailable: {type(exc).__name__}",
                fill="#b00020",
                tags=(_LAYOUT_TAG,),
            )
        except tk.TclError:
            pass
        return

    geometry = snapshot.geometry
    scale = float(getattr(app, "view_scale", 1.0) or 1.0)
    line_color = str(getattr(app.settings, "guide_color", "#1976d2") or "#1976d2")
    boundary_color = "#d32f2f"
    gutter_color = "#7b1fa2"

    # Body top/bottom are drawn across the complete inferred text block.
    if geometry.column_starts:
        left = min(int(geometry.x_at(i, geometry.top)) for i in range(len(geometry.column_starts)))
        right = max(
            int(geometry.x_at(i, geometry.bottom)) + int(geometry.column_widths[i])
            for i in range(len(geometry.column_starts))
        )
        for y, label in ((int(geometry.top), "body_top"), (int(geometry.bottom), "body_bottom")):
            p0 = geometry.canonical_to_source(left, y)
            p1 = geometry.canonical_to_source(right, y)
            canvas.create_line(
                p0[0] * scale, p0[1] * scale,
                p1[0] * scale, p1[1] * scale,
                fill=boundary_color, width=2, dash=(8, 4), tags=(_LAYOUT_TAG,),
            )
            canvas.create_text(
                p0[0] * scale + 4, p0[1] * scale - 3,
                anchor="sw", text=f"{label}={y}", fill=boundary_color,
                tags=(_LAYOUT_TAG,),
            )

    # Column left paths and right edges make the inferred geometry tangible even
    # when follow-column-deformation produces non-vertical tracks.
    for index, path in enumerate(geometry.column_paths):
        left_points = _source_polyline(geometry, list(path.points))
        left_coords = [value * scale for value in left_points]
        if len(left_coords) >= 4:
            canvas.create_line(
                *left_coords,
                fill=line_color, width=2, dash=(6, 3), tags=(_LAYOUT_TAG,),
            )

        width = int(geometry.column_widths[index])
        right_path = [(int(y), int(x) + width) for y, x in path.points]
        right_points = _source_polyline(geometry, right_path)
        right_coords = [value * scale for value in right_points]
        if len(right_coords) >= 4:
            canvas.create_line(
                *right_coords,
                fill=line_color, width=1, dash=(3, 3), tags=(_LAYOUT_TAG,),
            )

        label_y = int(geometry.top)
        label_x = int(geometry.x_at(index, label_y))
        sx, sy = geometry.canonical_to_source(label_x, label_y)
        canvas.create_text(
            sx * scale + 4,
            sy * scale + 5,
            anchor="nw",
            text=f"C{index + 1}  x={label_x}  w={width}",
            fill=line_color,
            tags=(_LAYOUT_TAG,),
        )

    # Gutter centre lines show whether the inferred pitch agrees with the scan.
    for index in range(max(0, len(geometry.column_paths) - 1)):
        top = int(geometry.top)
        bottom = int(geometry.bottom)
        left_right_top = int(geometry.x_at(index, top)) + int(geometry.column_widths[index])
        next_left_top = int(geometry.x_at(index + 1, top))
        left_right_bottom = int(geometry.x_at(index, bottom)) + int(geometry.column_widths[index])
        next_left_bottom = int(geometry.x_at(index + 1, bottom))
        top_mid = round((left_right_top + next_left_top) / 2)
        bottom_mid = round((left_right_bottom + next_left_bottom) / 2)
        p0 = geometry.canonical_to_source(top_mid, top)
        p1 = geometry.canonical_to_source(bottom_mid, bottom)
        canvas.create_line(
            p0[0] * scale, p0[1] * scale,
            p1[0] * scale, p1[1] * scale,
            fill=gutter_color, width=1, dash=(2, 4), tags=(_LAYOUT_TAG,),
        )

    summary = "\n".join(_summary_lines(snapshot))
    text_id = canvas.create_text(
        12, 12,
        anchor="nw",
        text=summary,
        fill="#111111",
        font=("TkDefaultFont", 9),
        tags=(_LAYOUT_TAG,),
    )
    bbox = canvas.bbox(text_id)
    if bbox is not None:
        pad = 5
        rect_id = canvas.create_rectangle(
            bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad,
            fill="#ffffff", outline=line_color, width=1, stipple="gray25",
            tags=(_LAYOUT_TAG,),
        )
        canvas.tag_lower(rect_id, text_id)


def _find_display_section(parent: Any) -> Any | None:
    stack = list(parent.winfo_children()) if hasattr(parent, "winfo_children") else []
    while stack:
        widget = stack.pop(0)
        try:
            if str(widget.cget("text")) == "二、显示设置":
                return widget
        except Exception:
            pass
        try:
            stack.extend(widget.winfo_children())
        except Exception:
            pass
    return None


def _install_display_toggle(app: Any, parent: Any) -> None:
    var = tk.BooleanVar(value=False)
    app._layout_visualization_var = var
    if hasattr(app, "quick_bool_vars"):
        app.quick_bool_vars["show_layout_visualization"] = var

    section = _find_display_section(parent)
    if section is None:
        return
    occupied_rows: list[int] = []
    for child in section.winfo_children():
        try:
            info = child.grid_info()
            if info:
                occupied_rows.append(int(info.get("row", 0)))
        except Exception:
            pass
    row = (max(occupied_rows) + 1) if occupied_rows else 0

    def toggle() -> None:
        app._layout_visualization_snapshot_key = None
        app._layout_visualization_snapshot = None
        app.redraw()

    checkbox = ttk.Checkbutton(
        section,
        text="显示Layout",
        variable=var,
        command=toggle,
    )
    checkbox.grid(row=row, column=0, columnspan=4, sticky="w", pady=(3, 0))
    try:
        app._attach_tooltip(
            checkbox,
            "在主图上显示当前页实际采用的版面推理：正文上下界、各栏左右边界、栏间中心、推理方法/置信度及自动字段采用情况。仅影响显示。",
        )
    except Exception:
        pass


def install_layout_visualization(app_module: Any) -> None:
    """Install the main-window switch and redraw overlay exactly once."""
    cls = app_module.PictureCaptureApp
    if getattr(cls, "_layout_visualization_installed", False):
        return

    original_build = cls._build_quick_settings
    original_redraw = cls.redraw

    def build_quick_settings(self: Any, parent: Any) -> Any:
        result = original_build(self, parent)
        _install_display_toggle(self, parent)
        return result

    def redraw(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_redraw(self, *args, **kwargs)
        draw_layout_visualization(self)
        return result

    cls._build_quick_settings = build_quick_settings
    cls.redraw = redraw
    cls._layout_visualization_installed = True
