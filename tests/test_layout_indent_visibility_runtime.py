from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from picture_capture.layout_indent_visibility_runtime import (
    _draw_indent_blocks_visible,
    prepared_indent_counts,
)


class _Var:
    def get(self):
        return True


class _Geometry:
    @staticmethod
    def canonical_to_source(x, y):
        return int(x), int(y)


class _Canvas:
    def __init__(self):
        self.rectangles = []
        self.lines = []
        self.raised = []
        self.deleted = []

    def delete(self, tag):
        self.deleted.append(tag)

    def create_rectangle(self, *coords, **options):
        self.rectangles.append((coords, options))
        return len(self.rectangles)

    def create_line(self, *coords, **options):
        self.lines.append((coords, options))
        return len(self.lines)

    def tag_raise(self, tag, *args):
        self.raised.append(tag)


def _block(column, x0, x1, y0, y1):
    return {
        "column": column,
        "x0": x0,
        "x1": x1,
        "y0": y0,
        "y1": y1,
        "role": "body",
    }


def test_prepared_counts_report_each_column_separately():
    blocks = [
        _block(0, 60, 120, 100, 130),
        _block(0, 60, 160, 140, 170),
        _block(1, 1665, 1700, 100, 130),
    ]
    assert prepared_indent_counts(blocks) == {1: 2, 2: 1}


def test_visible_renderer_draws_left_and_right_column_indent_blocks():
    canvas = _Canvas()
    app = SimpleNamespace(
        canvas=canvas,
        view_scale=1.0,
        _layout_visualization_var=_Var(),
        _layout_visualization_indent_blocks=[
            _block(0, 60, 190, 100, 130),
            _block(1, 1665, 1735, 100, 130),
        ],
    )
    snapshot = SimpleNamespace(geometry=_Geometry())

    _draw_indent_blocks_visible(app, snapshot)

    assert len(canvas.rectangles) == 2
    assert len(canvas.lines) == 2
    assert canvas.rectangles[0][0] == (60.0, 100.0, 190.0, 130.0)
    assert canvas.rectangles[1][0] == (1665.0, 100.0, 1735.0, 130.0)
    assert canvas.lines[0][0] == (190.0, 100.0, 190.0, 130.0)
    assert canvas.lines[1][0] == (1735.0, 100.0, 1735.0, 130.0)
    assert app._layout_visualization_indent_drawn_counts == {1: 1, 2: 1}
    assert canvas.raised, "indent blocks must be raised above the scan/base overlay"


def test_gui_composition_installs_indent_visibility_after_lane_summary():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "bootstrap"
        / "gui.py"
    ).read_text(encoding="utf-8")
    lane = source.index("install_physical_lane_summary()")
    visible = source.index("install_layout_indent_visibility()")
    assert lane < visible


def test_visibility_runtime_does_not_lower_indent_below_base_layout():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "layout_indent_visibility_runtime.py"
    ).read_text(encoding="utf-8")
    assert "canvas.tag_raise(indent_tag)" in source
    assert "tag_lower" not in source
