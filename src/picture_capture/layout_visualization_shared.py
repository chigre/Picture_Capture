from __future__ import annotations

"""Make the Layout diagnostic overlay show the exact geometry ordinary drawing uses.

Both visualization and ordinary drawing resolve the same cached Layout Core
through the processing facade. This prevents stale imported callables,
launcher/worker differences, and duplicate physical page analysis from producing
two role assignments for one page.
"""

from pathlib import Path
from typing import Any

from .dictionary_page_layout_policy import resolve_page_layout_policy
from .layout_rows_cache import capture_layout_rows
from .image_utils import build_analysis_image
from .layout_physical_indent import normalized_physical_indents
from .processing import (
    ORDINARY_AUTO_LAYOUT_FIELDS,
    _geometry_from_page_understanding,
    _understand_page_current,
)


def _indent_blocks_from_understanding(understanding: Any) -> list[dict[str, Any]]:
    """Return canonical per-line actual-indent spans for diagnostics."""
    layout = understanding.layout
    blocks: list[dict[str, Any]] = []
    body_top = int(layout.body_top)

    for column in layout.columns:
        column_left = int(column.left)
        body = getattr(column, "body_mode", None)
        body_local_x = float(body.center) if body is not None else None
        for line in list(getattr(column, "lines", []) or []):
            first_local_x = max(0.0, float(getattr(line, "first_x", 0) or 0))
            anchor = getattr(line, "anchor_x", None)
            anchor_local_x = float(anchor) if anchor is not None else None
            x0 = float(column_left)
            x1 = float(column_left) + first_local_x
            y0 = body_top + int(getattr(line, "y0", 0) or 0)
            y1 = body_top + int(getattr(line, "y1", 0) or 0)
            if y1 <= y0:
                continue
            blocks.append({
                "column": int(getattr(column, "index", 0) or 0),
                "x0": x0,
                "x1": x1,
                "y0": int(y0),
                "y1": int(y1),
                "first_x": x1,
                "anchor_x": (
                    float(column_left) + anchor_local_x
                    if anchor_local_x is not None else None
                ),
                "body_x": (
                    float(column_left) + body_local_x
                    if body_local_x is not None else None
                ),
                "indent_px": first_local_x,
                "role": str(getattr(line, "role", "") or "unknown"),
            })
    return blocks


def _indent_lanes_from_understanding(understanding: Any) -> list[dict[str, Any]]:
    """Expose physical-indent clusters in the same corrected space as role logic."""
    lanes: list[dict[str, Any]] = []
    for column in list(getattr(understanding.layout, "columns", []) or []):
        column_index = int(getattr(column, "index", 0) or 0)
        column_lines = list(getattr(column, "lines", []) or [])
        corrected_by_line = normalized_physical_indents(column_lines)

        for lane_index, mode in enumerate(list(getattr(column, "indent_modes", []) or [])):
            mode_lines = list(getattr(mode, "lines", []) or [])
            corrected_values = sorted(
                float(corrected_by_line[id(line)])
                for line in mode_lines
                if id(line) in corrected_by_line
            )
            raw_values = sorted(
                float(getattr(line, "first_x", 0) or 0)
                for line in mode_lines
            )

            center = float(getattr(mode, "center", 0.0) or 0.0)
            if corrected_values:
                low = float(corrected_values[0])
                high = float(corrected_values[-1])
            else:
                tolerance = float(getattr(mode, "tolerance", 0.0) or 0.0)
                low = center - tolerance
                high = center + tolerance

            if raw_values:
                raw_low = float(raw_values[0])
                raw_high = float(raw_values[-1])
            else:
                raw_low = raw_high = center

            lanes.append({
                "column": column_index,
                "lane": int(lane_index),
                "center": center,
                "min": low,
                "max": high,
                "raw_min": raw_low,
                "raw_max": raw_high,
                "support": int(getattr(mode, "support", len(mode_lines)) or len(mode_lines)),
                "role": str(getattr(mode, "role", "") or "unknown"),
            })
    return lanes


def _shared_snapshot_for_app_impl(app: Any) -> Any:
    """Build the ordinary shared Layout snapshot without cache-capture routing."""
    from . import layout_visualization_ui as ui

    if getattr(app, "image", None) is None:
        raise RuntimeError("没有可显示的页面图像")

    key = ui._layout_cache_key(app)
    if (
        getattr(app, "_layout_visualization_snapshot_key", None) == key
        and getattr(app, "_layout_visualization_snapshot", None) is not None
    ):
        return app._layout_visualization_snapshot

    effective = app._current_effective_profile_settings()
    page_index = max(0, int(getattr(app, "current_index", 0)))
    page_sections = list(getattr(app, "page_sections", []) or [])
    analysis = build_analysis_image(app.image, effective)
    try:
        understanding = _understand_page_current(
            analysis,
            effective,
            page_index=page_index,
            page_sections=page_sections,
            layout_only=True,
        )
        if understanding is None:
            raise RuntimeError("Page Understanding 未能生成版面结果")

        geometry = _geometry_from_page_understanding(understanding)
        used = understanding.page_settings
        app._layout_visualization_indent_blocks = _indent_blocks_from_understanding(
            understanding
        )
        app._layout_visualization_indent_lanes = _indent_lanes_from_understanding(
            understanding
        )

        _policy_settings, estimate, _policy_applied = resolve_page_layout_policy(
            analysis,
            effective,
            page_index=page_index,
        )

        raw: dict[str, int] = {}
        if estimate is not None:
            for field, _switch in ORDINARY_AUTO_LAYOUT_FIELDS:
                try:
                    raw[field] = int(getattr(estimate, field))
                except (AttributeError, TypeError, ValueError):
                    pass

        used_values = {
            "columns": int(getattr(used, "columns", len(geometry.column_starts))),
            "start_y": int(getattr(used, "start_y", geometry.top)),
            "manual_x": int(
                getattr(
                    used,
                    "manual_x",
                    geometry.column_starts[0] if geometry.column_starts else 0,
                )
            ),
            "column_width": int(
                getattr(
                    used,
                    "column_width",
                    geometry.column_widths[0] if geometry.column_widths else 0,
                )
            ),
            "gutter": int(getattr(used, "gutter", 0)),
            "character_height": int(getattr(used, "character_height", 0)),
            "row_padding": int(getattr(used, "row_padding", 0)),
            "bottom_y": int(getattr(geometry, "bottom", 0)),
        }

        method = "layout_core"
        if estimate is not None:
            estimate_method = str(getattr(estimate, "method", "layout") or "layout")
            method = f"layout_core:{estimate_method}"

        confidence = None
        if estimate is not None and getattr(estimate, "confidence", None) is not None:
            try:
                confidence = float(getattr(estimate, "confidence"))
            except (TypeError, ValueError):
                confidence = None

        snapshot = ui.LayoutVisualizationSnapshot(
            geometry=geometry,
            method=method,
            confidence=confidence,
            auto_enabled=bool(getattr(effective, "ordinary_auto_layout", False)),
            applied_fields=dict(understanding.applied_layout_fields),
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


def shared_snapshot_for_app(app: Any) -> Any:
    """Return the shared Layout snapshot while seeding the physical-row cache."""
    project = getattr(app, "project", None)
    if project is None:
        return _shared_snapshot_for_app_impl(app)
    try:
        index = max(0, int(getattr(app, "current_index", 0)))
        images = list(getattr(project, "images", []) or [])
    except Exception:
        return _shared_snapshot_for_app_impl(app)
    if not (0 <= index < len(images)):
        return _shared_snapshot_for_app_impl(app)

    # Preserve the historical visualization-runtime contract: cache identity is
    # based on persisted app settings, while the snapshot implementation remains
    # free to derive page-effective settings internally.
    settings = getattr(app, "settings", None)
    if settings is None:
        return _shared_snapshot_for_app_impl(app)
    with capture_layout_rows(
        Path(project.root),
        Path(images[index]),
        index,
        settings,
    ):
        return _shared_snapshot_for_app_impl(app)


def install_shared_layout_visualization_source() -> None:
    """Patch the existing overlay before the v3 summary wrapper imports it."""
    from . import layout_visualization_ui as ui

    ui._snapshot_for_app = shared_snapshot_for_app
