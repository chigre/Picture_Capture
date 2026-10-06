from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture import dictionary_page_design as base
from picture_capture import layout_detection
from picture_capture.dictionary_page_design import LayoutLine
from picture_capture.layout_column_drift import (
    _analysis_left_for_column,
    _left_safety,
    finalize_layout_column_drift,
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
    assert column.left == 50
    assert column.right == 150


def test_left_safety_is_large_enough_for_scan_drift_but_bounded():
    assert _left_safety(20.0, 1000) >= 30
    assert _left_safety(40.0, 1000) >= 60
    assert _left_safety(80.0, 1000) <= 96


def test_later_column_analysis_never_crosses_previous_text_column():
    columns = [
        SimpleNamespace(left=50, right=150),
        SimpleNamespace(left=170, right=270),
    ]
    analysis_left = _analysis_left_for_column(columns, 1, 40.0)
    assert 151 <= analysis_left < 170
    assert columns[1].left == 170


def test_static_finalizer_replays_analysis_and_preserves_reason_provenance(monkeypatch):
    image = Image.new("RGB", (180, 100), "white")
    ink = np.zeros((100, 180), dtype=bool)
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
        reason="base",
    )
    settings = SimpleNamespace()
    calls: list[int] = []

    def fake_analysis_page(source_image, page_settings, page_index):
        calls.append(int(page_index))
        return source_image.copy(), source_image.copy(), None, page_settings

    monkeypatch.setattr(base, "_analysis_page", fake_analysis_page)
    monkeypatch.setattr(
        layout_detection,
        "analysis_ink_mask",
        lambda _gray, _settings: ink,
    )

    result = finalize_layout_column_drift(
        image,
        settings,
        layout,
        page_index=3,
    )

    assert result is layout
    assert calls == [3]
    assert lines[0].first_x == -5
    assert lines[1].first_x == -11
    assert layout.reason == "base; unclipped_first_x=C1:2"
    assert column.left == 50
    assert column.right == 150


def test_large_head_left_of_semantic_column_is_still_detected():
    image = Image.new("RGB", (220, 180), "white")
    draw = ImageDraw.Draw(image)
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
    assert all(entry.x == 50 for entry in entries)


def test_column_drift_is_static_and_shared_helper_ownership_is_explicit():
    root = Path(__file__).resolve().parents[1]
    core = (root / "src/picture_capture/bootstrap/core.py").read_text(encoding="utf-8")
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    worker = (root / "src/picture_capture/bootstrap/worker.py").read_text(encoding="utf-8")
    policy = (root / "src/picture_capture/dictionary_page_layout_policy.py").read_text(encoding="utf-8")
    unlined = (root / "src/picture_capture/unlined_physical_rows_resolver.py").read_text(encoding="utf-8")
    spawn = (root / "src/picture_capture/spawn_layout_runtime.py").read_text(encoding="utf-8")
    large_head = (root / "src/picture_capture/ordinary_large_head_runtime.py").read_text(encoding="utf-8")
    physical = (root / "src/picture_capture/layout_physical_indent.py").read_text(encoding="utf-8")

    assert core.index("install_ordinary_large_head_role_guard()") < core.index(
        "from .. import processing as processing_module"
    )
    assert "from .layout_column_drift import finalize_layout_column_drift" in policy
    layout_at = policy.index("layout = base.DictionaryPageLayout(")
    finalize_at = policy.index("layout = finalize_layout_column_drift(")
    return_at = policy.index("return layout, page_settings, applied", finalize_at)
    assert layout_at < finalize_at < return_at

    for source in (gui, worker, unlined, spawn, policy):
        assert "install_layout_column_drift_runtime" not in source
    assert "from .layout_column_drift import _analysis_left_for_column" in large_head
    assert "layout_column_drift_runtime" not in large_head
    assert "count = min(256, count)" in physical
