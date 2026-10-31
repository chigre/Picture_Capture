"""Physical owner of shared Layout geometry and ordinary settings freeze.

Historical processing functions inject current constructors and settings copier
at call time, retaining monkeypatch and source/canonical coordinate contracts.
"""
from __future__ import annotations
from typing import Any
from .page_understanding import PageUnderstanding
from ..models import AppSettings


def geometry_from_page_understanding(understanding: PageUnderstanding, *, column_path_type: Any, geometry_type: Any) -> Any:
    layout = understanding.layout
    starts = [int(column.left) for column in layout.columns]
    widths = [max(1, int(column.right) - int(column.left)) for column in layout.columns]
    paths = [
        column_path_type([
            (int(layout.body_top), int(column.left)),
            (int(layout.body_bottom), int(column.left)),
        ])
        for column in layout.columns
    ]
    return geometry_type(
        column_starts=starts,
        column_widths=widths,
        top=int(layout.body_top),
        bottom=int(layout.body_bottom),
        column_paths=paths,
        transform=layout.transform,
        source_size=layout.source_size,
    )


def ordinary_settings_for_shared_geometry(
    effective: AppSettings,
    geometry: Any,
    *,
    method: str,
    replace_settings: Any,
) -> AppSettings:
    """Freeze ordinary/VB to the already-resolved shared page geometry."""
    frozen = replace_settings(effective)
    frozen.detection_method = str(method or "left_edge")
    frozen.ordinary_auto_layout = False
    frozen.manual_columns = False
    frozen.follow_column_deformation = False

    starts = [int(value) for value in list(getattr(geometry, "column_starts", []) or [])]
    widths = [int(value) for value in list(getattr(geometry, "column_widths", []) or [])]
    frozen.columns = max(1, len(starts) or int(getattr(frozen, "columns", 1) or 1))
    frozen.start_y = int(getattr(geometry, "top", getattr(frozen, "start_y", 0)))

    if starts:
        frozen.manual_x = starts[0]
    if widths:
        frozen.column_width = max(1, widths[0])

    if len(starts) >= 2 and widths:
        frozen.gutter = max(0, starts[1] - (starts[0] + widths[0]))

    if starts:
        base_width = max(1, int(getattr(frozen, "column_width", widths[0] if widths else 1)))
        base_gutter = max(0, int(getattr(frozen, "gutter", 0) or 0))
        pitch = base_width + base_gutter
        frozen.column_start_offsets = [
            int(start - (starts[0] + index * pitch))
            for index, start in enumerate(starts)
        ]

    return frozen
