from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.dictionary_page_design import LayoutLine
from picture_capture.layout_column_drift_runtime import (
    _left_safety,
    remeasure_layout_indents_from_ink,
)
from picture_capture.layout_transform import LayoutTransform
from picture_capture.ordinary_large_head_runtime import (
    detect_ordinary_large_head_entries_guarded,
)


def _line(y0: int, y1: int, *, first_x: int = 0) -> LayoutLine:
    return LayoutLine(
        column=0,
        y0=y0,
        y1=y1,
        first_x=first_x,
        anchor_x=None,
        anchor_width=0,
        anchor_height=0,
        gap_before=0,
        patch=np.zeros((0, 0), dtype=bool),
    )


def test_remeasurement_keeps_negative_first_x_instead_of_clipping_to_zero():
    ink = np.zeros((100, 180), dtype=bool)
    # Semantic/Profile column starts at x=50, but this scanned page drifts left.
    # Both rows still contain real leading glyphs and must remain measurable.
    ink[10:25, 45:51] = True
    ink[45:60, 39:45] = True

    lines = [_line(10, 25), _line(45, 60)]
    column = SimpleNamespace(
        index=0,
        left=50,
        right=150,
        lines=lines,
        indent_modes=[],
        body_mode=None,
        entry_modes=[],
    )
    layout = SimpleNamespace(
        body_top=0,
        ordinary_line_height=20.0,
        indent_type="body",
        columns=[column],
    )

    counts = remeasure_layout_indents_from_ink(layout, ink)

    assert counts == {0: 2}
    assert lines[0].first_x == -5
    assert lines[1].first_x == -11
    # Analysis safety must never redefine the semantic/Profile column edge.
    assert column.left == 50
    assert column.right == 150


def test_left_safety_is_large_enough_for_scan_drift_but_bounded():
    assert _left_safety(20.0, 1000) >= 30
    assert _left_safety(40.0, 1000) >= 60
    assert _left_safety(80.0, 1000) <= 96


def test_large_head_left_of_semantic_column_is_still_detected():
    image = Image.new("RGB", (220, 180), "white")
    draw = ImageDraw.Draw(image)
    # Large display glyph begins 12 px left of the semantic column edge. The
    # guarded detector must use the shared safety band without moving the
    # semantic column edge or bypassing row-front authorization.
    draw.rectangle((38, 24, 68, 74), fill="black")

    row = _line(24, 75, first_x=-12)
    column = SimpleNamespace(index=0, left=50, right=170, lines=[row])
    layout = SimpleNamespace(
        transform=LayoutTransform(),
        source_size=image.size,
        body_top=0,
        body_bottom=160,
        ordinary_line_height=20.0,
        columns=[column],
    )
    understanding = SimpleNamespace(layout=layout)
    settings = SimpleNamespace(
        profile_cjk_allow_single_headword=True,
        dictionary_profile_id="cjk-test",
        ocr_language="chi_sim",
        paddle_language="ch",
    )

    entries = detect_ordinary_large_head_entries_guarded(
        image, understanding, settings,
    )

    assert entries
    assert any(entry.ocr_oversized_cjk for entry in entries)
    assert min(entry.y for entry in entries) <= 30
    # Evidence X remains the semantic column edge, not the padded analysis edge.
    assert all(entry.x == 50 for entry in entries)


def test_runtime_installed_before_processing_in_gui_and_worker_composition():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    worker = (root / "src/picture_capture/bootstrap/worker.py").read_text(encoding="utf-8")

    assert gui.index("install_layout_column_drift_runtime()") < gui.index(
        "from .. import processing as processing_module"
    )
    assert worker.index("install_layout_row_recovery_runtime()") < worker.index(
        "install_layout_column_drift_runtime()"
    )
    assert "install_layout_column_drift_runtime()" in worker
