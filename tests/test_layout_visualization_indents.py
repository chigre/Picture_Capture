from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_visualization_shared import _indent_blocks_from_understanding
from picture_capture.layout_visualization_summary import _format_summary


class _Column:
    index = 1
    left = 1302
    body_mode = SimpleNamespace(center=24.0)
    lines = [
        SimpleNamespace(y0=10, y1=42, anchor_x=24.0, role="body"),
        SimpleNamespace(y0=60, y1=94, anchor_x=7.0, role="other_indent"),
    ]


def test_indent_blocks_convert_column_local_coordinates_to_page_coordinates() -> None:
    understanding = SimpleNamespace(
        layout=SimpleNamespace(body_top=134, columns=[_Column()])
    )
    blocks = _indent_blocks_from_understanding(understanding)
    assert len(blocks) == 2

    body = blocks[0]
    assert body["body_x"] == 1326.0
    assert body["anchor_x"] == 1326.0
    assert body["y0"] == 144
    assert body["y1"] == 176

    indented = blocks[1]
    assert indented["x0"] == 1309.0
    assert indented["x1"] == 1326.0
    assert indented["y0"] == 194
    assert indented["y1"] == 228
    assert indented["role"] == "other_indent"


def test_summary_reports_line_indent_role_counts() -> None:
    geometry = SimpleNamespace(
        top=134,
        bottom=900,
        source_size=(2536, 3765),
        column_starts=[33, 1302],
        column_widths=[1204, 1234],
        x_at=lambda index, y: [33, 1302][index],
    )
    snapshot = SimpleNamespace(
        geometry=geometry,
        method="page_understanding:reliable_fusion",
        confidence=0.93,
        auto_enabled=True,
        applied_fields={},
        raw_estimate={},
        used_values={
            "columns": 2,
            "start_y": 134,
            "bottom_y": 900,
            "manual_x": 33,
            "column_width": 1204,
            "gutter": 65,
            "character_height": 51,
            "row_padding": 1,
        },
    )
    app = SimpleNamespace(
        image=SimpleNamespace(size=(2536, 3765)),
        _layout_visualization_indent_blocks=[
            {"role": "body"},
            {"role": "body"},
            {"role": "other_indent"},
        ],
        _current_effective_profile_settings=lambda: SimpleNamespace(
            layout_transform="identity",
            layout_writing_mode="horizontal-tb",
            layout_text_direction="ltr",
        ),
    )
    text = _format_summary(app, snapshot)
    assert "line indents: 3" in text
    assert "body=2" in text
    assert "other_indent=1" in text
