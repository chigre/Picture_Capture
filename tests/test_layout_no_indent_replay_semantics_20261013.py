"""No-indent means no *semantic* entry assignment from X clustering.

Physical leading-X clusters remain observable. Page Design's legacy raw
headword/body polarity must not be mislabeled as applied Profile semantics.
"""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.layout_core_understanding import (
    clear_layout_understanding_cache, understand_layout_core,
)
from picture_capture.layout_step_trace import LayoutStepTrace
from picture_capture.layout_step_replay_ui import _format_stage
from picture_capture.models import AppSettings
from picture_capture.profile_indent_ui import apply_indent_type_label, indent_type_label


def _page():
    page = Image.new("RGB", (320, 260), "white")
    draw = ImageDraw.Draw(page)
    for i in range(9):
        y = 20 + 22 * i
        draw.rectangle((26, y, 42, y+10), fill="black")
        draw.rectangle((55, y, 165, y+10), fill="black")
    return page


def test_actual_no_indent_snapshot_is_unclassified_until_profile_semantics():
    image = _page()
    settings = AppSettings(
        columns=1, manual_x=22, column_width=220,
        start_y=6, character_height=14, ordinary_auto_layout=False,
    )
    apply_indent_type_label(settings, "无明显缩进")
    assert indent_type_label(settings) == "无明显缩进"
    trace = LayoutStepTrace()
    clear_layout_understanding_cache()
    try:
        result = understand_layout_core(image, settings, page_index=0, trace=trace)
        stages = {item["key"]: item for item in trace.stages}
        keys = [item["key"] for item in trace.stages]
        # Skip semantic interpretation entirely in replay for explicit no-indent.
        assert keys[keys.index("physical_rows") + 1] == "symbol_evidence"
        assert not {
            "initial_roles", "indent_semantics", "body_lanes",
            "visual_consistency", "indent_recovery",
        } & set(keys)
        stage = stages["physical_rows"]
        assert stage["provisional_no_indent"] is True
        assert stage["details"]["profile_indent_mode"] == "无明显缩进"
        assert stage["details"]["skipped_semantic_stages"] == [
            "基础行角色", "缩进语义判定", "正文缩进族调整",
            "视觉一致性复核", "缺失缩进恢复",
        ]
        assert stage["details"]["next_visible_stage"] == "符号证据融合"
        assert {r["role"] for r in stage["rows"]} <= {"unclassified"}
        assert {m["role"] for m in stage["lanes"]} <= {"unclassified"}
        assert all("raw_provisional_role" in row for row in stage["rows"])
        assert "不允许以行首 X 差异推断词条" in _format_stage(stage)
        visible = stages["symbol_evidence"]
        # The only visible transitions are genuine symbol promotions.
        assert not any(
            item["kind"] == "role"
            and item["before"] == "unclassified"
            and item["after"] == "body"
            for item in visible["changes"]
        )
        assert all(
            item["kind"] != "role" or item["after"] != "body"
            for item in visible["changes"]
        )
        assert result.layout.indent_type == "none"
    finally:
        clear_layout_understanding_cache()
        image.close()


def test_legacy_raw_entry_label_is_recorded_but_not_presented_as_valid_entry():
    line = SimpleNamespace(y0=10, y1=20, role="entry", first_x=471)
    mode = SimpleNamespace(center=471., tolerance=1., support=1,
                           role="entry", lines=[line])
    layout = SimpleNamespace(
        body_top=0, body_bottom=150, source_size=(600, 180),
        transform=SimpleNamespace(
            canonical_to_source_point=lambda x, y, _size: (x, y),
        ),
        columns=[SimpleNamespace(left=0, right=550, lines=[line],
                                 indent_modes=[mode])],
    )
    trace = LayoutStepTrace()
    trace.add_layout(
        "physical_rows", "物理行检测", "仅反映几何观察", layout,
        provisional_no_indent=True,
    )
    stage = trace.stages[0]
    assert stage["rows"][0]["role"] == "unclassified"
    assert stage["rows"][0]["raw_provisional_role"] == "entry"
    assert stage["lanes"][0]["role"] == "unclassified"
    assert stage["lanes"][0]["raw_provisional_role"] == "entry"
    explanation = _format_stage(stage)
    assert "中心 471.0px" in explanation
    assert "单行离群位置：1 组" in explanation
    assert "语义 未分类" in explanation
    assert "行角色：entry" not in explanation
    line.role = "body"
    mode.role = "body"
    trace.adopt_unshown_role_baseline(layout)
    trace.add_layout("symbol_evidence", "符号证据融合", "生效", layout)
    assert len(trace.stages) == 2
    assert trace.stages[1]["rows"][0]["role"] == "body"
    assert trace.stages[1]["changes"] == []  # neutralization is NOT visual inference
    history = trace.history_for_row("C1-Y10-20")
    assert [item["role"] for item in history] == ["unclassified", "body"]
    assert "内部中性角色初始化" in history[1]["stage"]
    assert not any(item["stage"] == "符号证据融合" for item in history)


def test_indented_profiles_still_retain_true_semantic_stages():
    image = _page()
    settings = AppSettings(
        columns=1, manual_x=22, column_width=220,
        start_y=6, character_height=14, ordinary_auto_layout=False,
    )
    apply_indent_type_label(settings, "词头缩进")
    trace = LayoutStepTrace()
    clear_layout_understanding_cache()
    try:
        understand_layout_core(image, settings, page_index=0, trace=trace)
        keys = [stage["key"] for stage in trace.stages]
        assert keys.index("physical_rows") < keys.index("initial_roles")
        assert keys.index("initial_roles") < keys.index("indent_semantics")
        assert keys.index("indent_semantics") < keys.index("body_lanes")
        assert keys.index("body_lanes") < keys.index("visual_consistency")
    finally:
        clear_layout_understanding_cache()
        image.close()


def test_no_indent_skips_actual_no_op_consumers(monkeypatch):
    from picture_capture import (
        layout_column_indent_recovery, layout_role_visual_consistency,
    )
    def forbidden(*args, **kwargs):
        raise AssertionError("no-indent must not call body-indent-only consumers")

    monkeypatch.setattr(
        layout_role_visual_consistency, "suppress_contradictory_cjk_body_lane_entries",
        forbidden,
    )
    monkeypatch.setattr(
        layout_column_indent_recovery, "restore_proven_column_indents", forbidden,
    )
    image = _page()
    settings = AppSettings(
        columns=1, manual_x=22, column_width=220,
        start_y=6, character_height=14, ordinary_auto_layout=False,
    )
    apply_indent_type_label(settings, "无明显缩进")
    clear_layout_understanding_cache()
    try:
        normal = understand_layout_core(image, settings, page_index=0)
        trace = LayoutStepTrace()
        traced = understand_layout_core(image, settings, page_index=0, trace=trace)
        assert normal.layout.indent_type == traced.layout.indent_type == "none"
        def roles(result):
            return [(int(line.y0), int(line.y1), line.role)
                    for column in result.layout.columns for line in column.lines]
        assert roles(normal) == roles(traced)
    finally:
        clear_layout_understanding_cache()
        image.close()
