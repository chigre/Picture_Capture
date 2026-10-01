from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_visualization_ui import (
    LayoutVisualizationSnapshot,
    _source_polyline,
    _summary_lines,
)


class _Geometry:
    def canonical_to_source(self, x: int, y: int) -> tuple[int, int]:
        return x + 10, y + 20


def test_source_polyline_converts_canonical_points_to_source_xy() -> None:
    geometry = _Geometry()
    # ColumnPath stores points as (y, x); Canvas consumes flattened (x, y).
    assert _source_polyline(geometry, [(5, 7), (15, 9)]) == [17.0, 25.0, 19.0, 35.0]


def test_summary_distinguishes_raw_estimate_from_applied_fields() -> None:
    snapshot = LayoutVisualizationSnapshot(
        geometry=SimpleNamespace(),
        method="reliable_fusion+paddle+projection",
        confidence=0.87,
        auto_enabled=True,
        applied_fields={"start_y": 120, "manual_x": 42},
        raw_estimate={
            "start_y": 120,
            "manual_x": 42,
            "column_width": 310,
            "gutter": 24,
        },
        used_values={
            "columns": 2,
            "start_y": 120,
            "bottom_y": 2010,
            "manual_x": 42,
            "column_width": 300,
            "gutter": 20,
            "character_height": 28,
            "row_padding": 3,
        },
    )

    text = "\n".join(_summary_lines(snapshot))

    assert "Layout AUTO" in text
    assert "confidence: 0.87" in text
    assert "auto applied: start_y, manual_x" in text
    assert "raw only: column_width, gutter" in text
    # The displayed effective values remain the ones actually consumed rather
    # than silently replacing disabled fields with the raw detector estimate.
    assert "column_width: 300" in text
    assert "gutter: 20" in text


def test_summary_without_auto_layout_is_explicitly_current_geometry() -> None:
    snapshot = LayoutVisualizationSnapshot(
        geometry=SimpleNamespace(),
        method="project/profile geometry",
        confidence=None,
        auto_enabled=False,
        applied_fields={},
        raw_estimate={},
        used_values={
            "columns": 3,
            "start_y": 90,
            "bottom_y": 1900,
            "manual_x": 30,
            "column_width": 250,
            "gutter": 18,
            "character_height": 26,
            "row_padding": 2,
        },
    )

    text = "\n".join(_summary_lines(snapshot))

    assert "Layout CURRENT" in text
    assert "method: project/profile geometry" in text
    assert "confidence: —" in text
    assert "auto applied:" not in text
    assert "raw only:" not in text
