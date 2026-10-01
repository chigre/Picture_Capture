from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_visualization_shared import _indent_blocks_from_understanding
from picture_capture.layout_visualization_summary import _format_summary, _role_style


class _Column:
    index = 1
    left = 1302
    body_mode = SimpleNamespace(center=24.0)
    lines = [
        SimpleNamespace(
            y0=10, y1=42, first_x=0, anchor_x=24.0, role="body"
        ),
        SimpleNamespace(
            y0=60, y1=94, first_x=17, anchor_x=24.0, role="other_indent"
        ),
    ]


def test_indent_blocks_show_column_edge_to_first_real_ink() -> None:
    understanding = SimpleNamespace(
        layout=SimpleNamespace(body_top=134, columns=[_Column()])
    )
    blocks = _indent_blocks_from_understanding(understanding)
    assert len(blocks) == 2

    flush = blocks[0]
    assert flush["x0"] == 1302.0
    assert flush["x1"] == 1302.0
    assert flush["first_x"] == 1302.0
    assert flush["anchor_x"] == 1326.0
    assert flush["body_x"] == 1326.0
    assert flush["indent_px"] == 0.0
    assert flush["y0"] == 144
    assert flush["y1"] == 176

    indented = blocks[1]
    assert indented["x0"] == 1302.0
    assert indented["x1"] == 1319.0
    assert indented["indent_px"] == 17.0
    assert indented["anchor_x"] == 1326.0
    assert indented["y0"] == 194
    assert indented["y1"] == 228
    assert indented["role"] == "other_indent"


def test_line_role_styles_keep_indent_distinct_from_entry_semantics() -> None:
    assert _role_style("entry") == ("#2e7d32", "词条行")
    assert _role_style("headword") == ("#2e7d32", "词条行")
    assert _role_style("body") == ("#1976d2", "正文行")
    assert _role_style("other_indent") == ("#757575", "不确定")
    assert _role_style("unknown") == ("#757575", "不确定")


def test_summary_reports_semantic_role_counts_and_legend() -> None:
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
            {"role": "entry"},
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
    assert "line indents: 4" in text
    assert "词条行=1" in text
    assert "正文行=2" in text
    assert "不确定=1" in text
    assert "绿色=词条行" in text
    assert "蓝色=正文行" in text
    assert "灰色=不确定" in text
