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
        for key in ("physical_rows", "initial_roles"):
            stage = stages[key]
            assert stage["provisional_no_indent"] is True
            assert stage["details"]["profile_indent_mode"] == "无明显缩进"
            assert {r["role"] for r in stage["rows"]} <= {"unclassified"}
            assert {m["role"] for m in stage["lanes"]} <= {"unclassified"}
            assert all("raw_provisional_role" in row for row in stage["rows"])
            assert "不允许以行首 X 差异推断词条" in _format_stage(stage)
        assert stages["indent_semantics"]["details"]["indent_type"] == "none"
        assert all(row["role"] == "body"
                   for row in stages["indent_semantics"]["rows"])
        assert all(mode["role"] == "body"
                   for mode in stages["indent_semantics"]["lanes"])
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
    trace.add_layout("indent_semantics", "缩进语义判定", "生效", layout)
    assert trace.stages[1]["rows"][0]["role"] == "body"
    assert trace.stages[1]["changes"][0]["before"] == "unclassified"
    assert trace.stages[1]["changes"][0]["after"] == "body"
