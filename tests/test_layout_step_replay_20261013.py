"""LAYOUT timeline: production parity, stage immutability, off-mode and UI helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture import layout_core_understanding as core
from picture_capture.layout_step_trace import LayoutStepTrace, diff_rows
from picture_capture.layout_step_replay_ui import (
    _format_stage, _row_at_position, _run_replay, _stage_rows_for_display,
    _preview_at_stage, _stage_entries_for_display,
)
from picture_capture.models import AppSettings


def sample_page():
    image = Image.new("RGB", (280, 200), "white")
    draw = ImageDraw.Draw(image)
    for index in range(7):
        y = 16 + index * 22
        draw.rectangle((19, y, 31, y+11), fill="black")
        draw.rectangle((48, y, 100, y+11), fill="black")
    settings = AppSettings(
        columns=1, manual_x=15, column_width=180,
        start_y=7, character_height=14, ordinary_auto_layout=False,
    )
    return image, settings


def _roles(layout):
    return [
        (i, line.y0, line.y1, line.role)
        for i, column in enumerate(layout.columns) for line in column.lines
    ]


def test_diagnostic_traces_actual_pipeline_and_does_not_pollute_normal_cache():
    image, settings = sample_page()
    core.clear_layout_understanding_cache()
    try:
        ordinary = core.understand_layout_core(image, settings, page_index=0)
        count = len(core._LAYOUT_CACHE)
        trace = LayoutStepTrace()
        replay = core.understand_layout_core(image, settings, page_index=0, trace=trace)
        assert len(core._LAYOUT_CACHE) == count
        assert replay is not ordinary
        assert _roles(replay.layout) == _roles(ordinary.layout)
        keys = [stage["key"] for stage in trace.stages]
        assert keys[:6] == [
            "raw_estimate", "effective_parameters",
            "projection_gap_bridge", "projection_tall_split",
            "physical_rows", "initial_roles",
        ]
        assert keys[-1] == "final"
        assert {"body_lanes", "symbol_evidence", "large_head_evidence", "duplicate_suppression"} <= set(keys)
        assert trace.stages[-1]["rows"]
        assert all("source_box" in row for row in trace.stages[-1]["rows"])
        assert all(not isinstance(value, Image.Image) for stage in trace.stages for value in stage.values())
    finally:
        core.clear_layout_understanding_cache()
        image.close()


def test_full_replay_builds_denoise_stage_but_does_not_edit_original():
    image, settings = sample_page()
    original = image.tobytes()
    trace, previews = _run_replay(image, settings, 0)
    try:
        assert image.tobytes() == original
        assert trace.stages[0]["key"] == "image_preparation"
        assert trace.stages[-1]["key"] == "final_reading_order"
        assert "illustration_mask" in [stage["key"] for stage in trace.stages]
        assert "layout_role_materialization" in [stage["key"] for stage in trace.stages]
        assert previews["image_preparation"].size[0] <= 1400
    finally:
        for preview in previews.values():
            preview.close()
        image.close()


def test_stage_snapshots_freeze_roles_and_report_transitions():
    line = SimpleNamespace(y0=5, y1=14, role="body", first_x=12)
    column = SimpleNamespace(left=7, right=90, lines=[line])
    layout = SimpleNamespace(
        columns=[column], body_top=10, body_bottom=160,
        transform=SimpleNamespace(canonical_to_source_point=lambda x, y, _s: (x, y)),
        source_size=(120, 180),
    )
    trace = LayoutStepTrace()
    trace.add_layout("before", "前", "before", layout)
    line.role = "entry"
    trace.add_layout("after", "后", "after", layout)
    assert trace.stages[0]["rows"][0]["role"] == "body"
    assert trace.stages[1]["rows"][0]["role"] == "entry"
    assert trace.stages[1]["changes"] == [
        {"id": "C1-Y15-24", "kind": "role", "before": "body", "after": "entry"},
    ]
    assert [(v["stage"], v["role"]) for v in trace.history_for_row("C1-Y15-24")] == [
        ("前", "body"), ("后", "entry"),
    ]
    assert _stage_rows_for_display(trace.stages, 1, True)["key"] == "before"
    assert _stage_rows_for_display(trace.stages, 1, False)["key"] == "after"
    row = _row_at_position(trace.stages[1]["rows"], 15, 17)
    assert row["role"] == "entry"
    assert "C1-Y15-24" in _format_stage(trace.stages[1], selected=row)


def test_diff_tracks_removed_and_added_rows():
    old = [{"id": "a", "role": "body"}]
    new = [{"id": "b", "role": "entry"}]
    assert [(x["id"], x["kind"]) for x in diff_rows(old, new)] == [
        ("a", "removed"), ("b", "added"),
    ]


def test_toggle_is_ephemeral_and_trace_is_opt_in():
    controls = Path("src/picture_capture/layout_visualization_ui_v3.py").read_text(encoding="utf-8")
    core_source = Path("src/picture_capture/layout_core_understanding.py").read_text(encoding="utf-8")
    assert 'text="查看 LAYOUT 分析过程"' in controls
    assert "tk.BooleanVar(value=False)" in controls
    assert "show_layout_step_replay(app)" in controls
    assert 'setattr(app.settings, "layout_step_replay"' not in controls
    assert "if trace is not None:" in core_source
    assert "trace.add_layout(\"final\"" in core_source
