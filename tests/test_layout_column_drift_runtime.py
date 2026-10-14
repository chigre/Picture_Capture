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
from picture_capture.ordinary_large_head_evidence import (
    detect_ordinary_large_head_entries,
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


def test_static_finalizer_reuses_existing_page_ink_without_reanalysis(monkeypatch):
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

    monkeypatch.setattr(
        base,
        "_analysis_page",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("existing page_ink must avoid _analysis_page")
        ),
    )
    monkeypatch.setattr(
        layout_detection,
        "analysis_ink_mask",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("existing page_ink must avoid analysis_ink_mask")
        ),
    )

    result = finalize_layout_column_drift(
        image,
        SimpleNamespace(),
        layout,
        page_index=3,
        page_ink=ink,
    )

    assert result is layout
    assert lines[0].first_x == -5
    assert lines[1].first_x == -11
    assert layout.reason == "base; unclipped_first_x=C1:2"



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

    entries = detect_ordinary_large_head_entries(
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
    large_head = (
        root / "src/picture_capture/ordinary_large_head_evidence.py"
    ).read_text(encoding="utf-8")
    physical = (root / "src/picture_capture/layout_physical_indent.py").read_text(encoding="utf-8")

    assert "install_ordinary_large_head_runtime" not in core
    assert "install_ordinary_large_head_role_guard" not in core
    assert "from .layout_column_drift import finalize_layout_column_drift" in policy
    layout_at = policy.index("layout = base.DictionaryPageLayout(")
    finalize_at = policy.index("layout = finalize_layout_column_drift(")
    return_at = policy.index("return layout, page_settings, applied", finalize_at)
    assert layout_at < finalize_at < return_at
    assert "page_ink=page_ink" in policy

    for source in (gui, worker, unlined, policy):
        assert "install_layout_column_drift_runtime" not in source
    assert not (root / "src/picture_capture/spawn_layout_runtime.py").exists()
    assert not (root / "src/picture_capture/ordinary_large_head_runtime.py").exists()
    assert "from .layout_column_drift import _analysis_left_for_column" in large_head
    assert "strict_candidate_starts_at_row_front" in large_head
    assert "layout_column_drift_runtime" not in large_head
    assert "count = min(256, count)" in physical


def test_neighbour_tail_bleed_cannot_define_right_body_lane():
    """A repeated tail of LEFT column ink must not create right body indents.

    Structural analogue of 080182: the upper right body is intact, while
    lower LEFT column line endings enter the right-column slant safety window.
    Entire right-column body stays at +3, heads at +52, irrespective of Y.
    No private dictionary text/pixels are part of this fixture.
    """
    from picture_capture.layout_core_understanding import _resolve_directional_body_lanes
    from picture_capture.layout_physical_indent import explicit_physical_layout_ops

    height, width, ref = 1000, 830, 20.0
    ink = np.zeros((height, width), dtype=bool)
    left = base.ColumnDesign(0, 50, 390, 40)
    right = base.ColumnDesign(1, 430, 800, 0)
    y_positions = [12 + index * 38 for index in range(24)]
    genuine_head_rows = {3, 9, 15, 21}
    # Include two lower true headwords: the real failure also hid genuine
    # right-column heads inside the phantom body family.
    polluted_rows = set(range(12, 24))

    for index, y in enumerate(y_positions):
        first = 482 if index in genuine_head_rows else 433
        # Credible, normally printed right-column glyph group.
        ink[y:y + 15, first:first + 27] = True
        if index in polluted_rows:
            # Gutter analysis starts X=395, only 5px past previous.right=390.
            # The LEFT column's protruding line ending is disconnected from
            # genuine right-column glyphs by over 30px of completely blank ink.
            ink[y:y + 15, 380:395] = True  # preceding printed C1 row tail
            ink[y:y + 15, 395:403] = True  # same glyph extends into C2 margin
        right.lines.append(_line(y, y + 18))

    layout = SimpleNamespace(
        columns=[left, right], body_top=0, body_bottom=height,
        ordinary_line_height=ref, indent_type="headword",
    )
    rejected: dict[int, int] = {}
    ops = explicit_physical_layout_ops()
    counts = remeasure_layout_indents_from_ink(
        layout, ink, ops=ops, foreign_tail_rejections=rejected,
    )
    assert counts[1] == 24
    assert rejected == {1: len(polluted_rows)}
    assert [row.first_x for row in right.lines] == [
        52 if i in genuine_head_rows else 3 for i in range(24)
    ]

    _resolve_directional_body_lanes(layout)
    assert right.body_mode is not None
    assert 0 <= right.body_mode.center <= 5
    assert len(right.entry_modes) == 1
    assert right.entry_modes[0].support == len(genuine_head_rows)
    assert sum(line.role == "entry" for line in right.lines) == len(genuine_head_rows)


def test_cross_boundary_continuous_genuine_negative_overhang_is_preserved():
    """Do not discard real protruding text spanning the semantic left edge."""
    from picture_capture.layout_physical_indent import explicit_physical_layout_ops

    ink = np.zeros((100, 680), dtype=bool)
    left = base.ColumnDesign(0, 40, 390, 40)
    right = base.ColumnDesign(1, 430, 660, 0)
    # Starts in the slant-safety band, but continuous ink runs THROUGH
    # column.left. Unlike a neighbor's tail, there is no blank separation.
    ink[12:28, 380:395] = True  # even with nearby prior-column ink
    ink[12:28, 395:457] = True  # continuous through the right semantic edge
    right.lines = [_line(12, 28)]
    layout = SimpleNamespace(
        columns=[left, right], body_top=0,
        ordinary_line_height=20., indent_type="headword",
    )
    rejected: dict[int, int] = {}
    remeasure_layout_indents_from_ink(
        layout, ink, ops=explicit_physical_layout_ops(),
        foreign_tail_rejections=rejected,
    )
    assert -35 <= right.lines[0].first_x <= -25
    assert rejected == {}


def test_genuine_moderately_negative_indent_stays_negative_next_to_other_column():
    """A true nearby outdent is preserved even with a blank inner gutter."""
    from picture_capture.layout_physical_indent import explicit_physical_layout_ops

    ink = np.zeros((100, 680), dtype=bool)
    left = base.ColumnDesign(0, 40, 390, 40)
    right = base.ColumnDesign(1, 430, 660, 0)
    # The real right-column ink starts 15px left of semantic boundary,
    # far from the previous column's right edge.
    ink[10:26, 415:429] = True
    ink[10:26, 435:461] = True
    right.lines = [_line(10, 28)]
    layout = SimpleNamespace(
        columns=[left, right], body_top=0,
        ordinary_line_height=20., indent_type="headword",
    )
    rejected: dict[int, int] = {}
    remeasure_layout_indents_from_ink(
        layout, ink, ops=explicit_physical_layout_ops(),
        foreign_tail_rejections=rejected,
    )
    assert right.lines[0].first_x == -15
    assert rejected == {}


def test_finalizer_diagnostic_counts_foreign_neighbour_tails_without_moving_geometry():
    from picture_capture.layout_physical_indent import explicit_physical_layout_ops

    img = Image.new("L", (680, 100), color=255)
    ink = np.zeros((100, 680), dtype=bool)
    ink[10:27, 380:395] = True
    ink[10:27, 395:403] = True
    ink[10:27, 433:457] = True
    left = base.ColumnDesign(0, 40, 390, 40)
    right = base.ColumnDesign(1, 430, 660, 0)
    right.lines = [_line(10, 27)]
    layout = SimpleNamespace(
        columns=[left, right], body_top=0, body_bottom=100,
        ordinary_line_height=20., indent_type="headword", reason="base",
    )
    finalize_layout_column_drift(
        img, SimpleNamespace(), layout, page_ink=ink,
        ops=explicit_physical_layout_ops(),
    )
    assert "foreign_column_tail_rejected=C2:1" in layout.reason
    assert (left.left, left.right, right.left, right.right) == (40, 390, 430, 660)
    assert right.lines[0].first_x == 3


def test_isolated_outdented_marker_is_not_called_previous_column_text():
    """A genuine detached left-prefix survives without prior-column support."""
    from picture_capture.layout_physical_indent import explicit_physical_layout_ops

    ink = np.zeros((100, 680), dtype=bool)
    left = base.ColumnDesign(0, 40, 390, 40)
    right = base.ColumnDesign(1, 430, 660, 0)
    # Printed C2 marker near the previous column's right edge plus separate
    # indented C2 body, but no pixels whatsoever from C1 to substantiate
    # a claimed foreign origin.
    ink[12:28, 395:403] = True
    ink[12:28, 433:460] = True
    right.lines = [_line(12, 28)]
    layout = SimpleNamespace(
        columns=[left, right], body_top=0,
        ordinary_line_height=20., indent_type="headword",
    )
    rejected = {}
    remeasure_layout_indents_from_ink(
        layout, ink, ops=explicit_physical_layout_ops(),
        foreign_tail_rejections=rejected,
    )
    assert right.lines[0].first_x < 0
    assert rejected == {}


def test_undistorted_right_column_uses_its_inside_ink_not_maximum_probe_radius():
    """A clear 92px potential gutter does not cause 92px applied skew."""
    from picture_capture.layout_physical_indent import explicit_physical_layout_ops

    ink = np.zeros((600, 3220), dtype=bool)
    left = base.ColumnDesign(0, 101, 1591, 94)
    right = base.ColumnDesign(1, 1685, 3175, 0)
    rows = []
    for index in range(6):
        y = 25 + index * 78
        ink[y:y + 49, 1693:1727] = True
        rows.append(_line(y, y + 55))
    right.lines = rows
    layout = SimpleNamespace(
        columns=[left, right], body_top=0, body_bottom=600,
        ordinary_line_height=52.65, indent_type="headword",
        reason="base",
    )
    assert _analysis_left_for_column(layout.columns, 1, 52.65) == 1593
    overhang = {}
    rejected = {}
    counts = remeasure_layout_indents_from_ink(
        layout, ink, ops=explicit_physical_layout_ops(),
        measured_overhangs=overhang,
        foreign_tail_rejections=rejected,
    )
    assert counts == {1: 6}
    assert all(0 <= row.first_x <= 10 for row in right.lines)
    assert overhang == {}
    assert rejected == {}


def test_genuine_outdents_report_actual_ink_distance_not_possible_safety_window():
    """True negative-X ink is retained as a measured 15px outdent."""
    from picture_capture.layout_physical_indent import explicit_physical_layout_ops

    ink = np.zeros((200, 680), dtype=bool)
    first = base.ColumnDesign(0, 40, 390, 40)
    second = base.ColumnDesign(1, 430, 660, 0)
    ink[20:40, 415:429] = True
    ink[20:40, 435:470] = True
    second.lines = [_line(20, 43)]
    layout = SimpleNamespace(
        columns=[first, second], body_top=0, body_bottom=200,
        ordinary_line_height=20., indent_type="headword",
        reason="base",
    )
    actual = {}
    counts = remeasure_layout_indents_from_ink(
        layout, ink, ops=explicit_physical_layout_ops(),
        measured_overhangs=actual,
    )
    assert counts == {1: 1}
    assert second.lines[0].first_x == -15
    assert actual == {1: (1, 15)}
    assert _left_safety(20., 230) > 15


def test_foreign_tail_rejection_has_zero_accepted_gutter_overhang():
    """Reject foreign source without recording it as real skew."""
    from picture_capture.layout_physical_indent import explicit_physical_layout_ops

    ink = np.zeros((150, 680), dtype=bool)
    first = base.ColumnDesign(0, 40, 390, 40)
    second = base.ColumnDesign(1, 430, 660, 0)
    ink[10:27, 380:403] = True
    ink[10:27, 433:465] = True
    second.lines = [_line(10, 27)]
    layout = SimpleNamespace(
        columns=[first, second], body_top=0, body_bottom=150,
        ordinary_line_height=20., indent_type="headword", reason="base",
    )
    actual, rejected = {}, {}
    remeasure_layout_indents_from_ink(
        layout, ink, ops=explicit_physical_layout_ops(),
        measured_overhangs=actual,
        foreign_tail_rejections=rejected,
    )
    assert second.lines[0].first_x == 3
    assert rejected == {1: 1}
    assert actual == {}
