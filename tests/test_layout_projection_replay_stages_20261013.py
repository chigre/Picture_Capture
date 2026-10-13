"""The 2 pre-physical stages are produced by the live Page Design projector.

These tests compare diagnostic/on-off output, stage order, original source
coordinates, and actual short-gap/valley changes. They do not simulate rows
from the final rectangles and do not require a running Tk display.
"""
from __future__ import annotations

from PIL import Image, ImageDraw
import numpy as np

from picture_capture.layout_physical_indent import (
    _raw_projection_runs, projection_line_runs,
)
from picture_capture.layout_step_trace import LayoutStepTrace
from picture_capture.layout_step_replay_ui import (
    _projection_candidates_for_display, _format_stage, _candidate_at_source,
)
from picture_capture.layout_core_understanding import (
    understand_layout_core, clear_layout_understanding_cache,
)
from picture_capture.models import AppSettings
from picture_capture.profile_indent_ui import apply_indent_type_label


def _ink_with_gap():
    ink = np.zeros((115, 35), dtype=bool)
    ink[5:20, :8] = True
    ink[22:40, :8] = True    # exactly 2 blank scan-lines between
    ink[66:74, :8] = True
    return ink


def test_live_gap_trace_and_default_produce_identical_runs():
    ink = _ink_with_gap()
    raw_debug = {}
    with_debug = projection_line_runs(ink, 60, debug=raw_debug)
    ordinary = projection_line_runs(ink, 60)
    assert with_debug == ordinary
    assert raw_debug["original_runs"] == [(5, 20), (22, 40), (66, 74)]
    assert raw_debug["bridged_gaps"] == [(20, 22)]
    assert raw_debug["connected_runs"] == [(5, 40), (66, 74)]
    assert raw_debug["max_gap_px"] == 2
    assert raw_debug["final_runs"] == ordinary
    assert raw_debug["threshold"] == 2.0


def test_live_tall_band_records_actual_valley_splits_without_modifying_result():
    ink = np.zeros((105, 30), dtype=bool)
    ink[5:65, :9] = True
    ink[23, :] = False
    ink[23, :2] = True       # sparse shoulders retain active row projection
    ink[24, :] = False       # 1px blank valley, joined by the same projector
    ink[25, :] = False
    ink[25, :2] = True       # 3-row mean now passes the actual valley gate
    diag = {}
    observed = projection_line_runs(ink, 20, debug=diag)
    reference = projection_line_runs(ink, 20)
    assert observed == reference
    assert diag["bridged_gaps"] == [(24, 25)]
    assert diag["valley_splits"]
    assert any(23 <= x["at_y"] <= 25 for x in diag["valley_splits"])
    assert diag["final_runs"] == observed


def _page():
    page = Image.new("RGB", (420, 340), "white")
    draw = ImageDraw.Draw(page)
    for n in range(11):
        y = 19 + n * 26
        draw.rectangle((25, y, 40, y + 15), fill="black")
        draw.rectangle((52, y, 162, y + 15), fill="black")
    return page


def _roles(understanding):
    return [
        (column.index, line.y0, line.y1, line.role, float(line.first_x))
        for column in understanding.layout.columns for line in column.lines
    ]


def test_composed_layout_captures_final_real_pass_before_physical_rows():
    page = _page()
    settings = AppSettings(
        columns=1, manual_x=20, column_width=250,
        start_y=8, character_height=17, ordinary_auto_layout=False,
    )
    apply_indent_type_label(settings, "无明显缩进")
    clear_layout_understanding_cache()
    try:
        ordinary = understand_layout_core(page, settings, page_index=0)
        trace = LayoutStepTrace()
        traced = understand_layout_core(
            page, settings, page_index=0, trace=trace,
        )
        assert _roles(ordinary) == _roles(traced)
        keys = [stage["key"] for stage in trace.stages]
        i = keys.index("projection_gap_bridge")
        assert keys[i + 1] == "projection_tall_split"
        assert keys[i + 2] == "physical_rows"
        assert keys.index("effective_parameters") < i
        assert keys[i + 3] == "symbol_evidence"  # no-indent shortcut
        first = trace.stages[i]
        second = trace.stages[i + 1]
        assert first["details"]["projection_pass_count"] == 3
        assert second["details"]["shown_pass"].startswith("最后一轮")
        assert first["details"]["columns"][0]["sample_strip_width"] > 0
        assert first["details"]["columns"][0]["output_rows"] > 0
        assert sum(c["status"] == "retained_row" for c in second["candidates"]) == (
            first["details"]["columns"][0]["output_rows"]
        )
        assert len(trace.stages[i + 2]["rows"]) > 0
        assert any(c["status"] == "raw_band" for c in first["candidates"])
        assert all(
            0 <= coord <= (page.width if k % 2 == 0 else page.height)
            for c in first["candidates"]
            for k, coord in enumerate(c["source_box"])
        )
        original = _projection_candidates_for_display(first, True)
        bridged = _projection_candidates_for_display(first, False)
        assert original and bridged
        assert {x["status"] for x in original} == {"raw_band"}
        assert {x["status"] for x in bridged} <= {
            "connected_band", "bridged_gap",
        }
        assert {x["status"] for x in
                _projection_candidates_for_display(second, True)} == {
            "connected_band",
        }
        assert "采样宽" in _format_stage(first)
        assert "\n" in _format_stage(first)
    finally:
        clear_layout_understanding_cache()
        page.close()


def test_empty_projection_preserves_normal_run_output_and_no_fake_changes():
    empty = np.zeros((90, 40), dtype=bool)
    debug = {}
    assert projection_line_runs(empty, 22, debug=debug) == []
    assert projection_line_runs(empty, 22) == []
    assert debug["original_runs"] == []
    assert debug["bridged_gaps"] == []
    assert debug["final_runs"] == []


def test_split_stage_before_after_only_shows_real_computational_state():
    fake = {
        "key": "projection_tall_split",
        "candidates": [
            {"status": "connected_band"}, {"status": "retained_row"},
            {"status": "split_valley"}, {"status": "fallback_slot"},
            {"status": "ignored_short"},
        ],
    }
    assert [x["status"] for x in _projection_candidates_for_display(fake, True)] == [
        "connected_band",
    ]
    assert [x["status"] for x in _projection_candidates_for_display(fake, False)] == [
        "retained_row", "split_valley", "fallback_slot", "ignored_short",
    ]



def test_narrow_real_bridge_marker_wins_click_over_its_parent_band():
    parent = {
        "status": "connected_band", "source_box": [10, 5, 70, 70],
    }
    gap = {
        "status": "bridged_gap", "source_box": [10, 25, 70, 26],
    }
    assert _candidate_at_source([parent, gap], 30, 25)["status"] == "bridged_gap"
    assert _candidate_at_source([parent, gap], 30, 28)["status"] == "bridged_gap"
    assert _candidate_at_source([parent, gap], 30, 50)["status"] == "connected_band"



def test_runtime_diagnostics_exposes_loaded_paths_and_complete_stage_list():
    from types import SimpleNamespace
    from picture_capture.layout_step_replay_ui import LayoutStepReplayWindow

    shown = []
    trace = LayoutStepTrace()
    for key, title in [
        ("raw_estimate", "自动版面候选"),
        ("projection_gap_bridge", "墨迹投影与短间隙连接"),
        ("projection_tall_split", "过高墨迹带拆分与逻辑行恢复"),
        ("physical_rows", "物理行检测"),
    ]:
        trace.add_note(key, title, "真实阶段")
    fake = SimpleNamespace(
        _trace=trace,
        _show_text=lambda value: shown.append(value),
    )
    LayoutStepReplayWindow.show_runtime_diagnostics(fake)
    assert len(shown) == 1
    displayed = shown[0]
    assert "实际加载的模块路径" in displayed
    assert "layout_step_replay_ui.py" in displayed
    assert "layout_composition.py" in displayed
    assert "projection_gap_bridge=已记录" in displayed
    assert "projection_tall_split=已记录" in displayed
    assert "04  物理行检测" in displayed


def test_runtime_diagnostics_reports_anomalous_missing_projection_stages():
    from types import SimpleNamespace
    from picture_capture.layout_step_replay_ui import LayoutStepReplayWindow

    shown = []
    trace = LayoutStepTrace()
    trace.add_note("physical_rows", "物理行检测", "缺少投影记录")
    fake = SimpleNamespace(
        _trace=trace,
        _show_text=lambda value: shown.append(value),
    )
    LayoutStepReplayWindow.show_runtime_diagnostics(fake)
    assert "异常：存在物理行阶段但缺少投影阶段" in shown[0]
    assert "projection_gap_bridge=缺失" in shown[0]
