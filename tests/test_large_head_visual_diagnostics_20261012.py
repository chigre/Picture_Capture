"""Non-mutating, production-detector-backed visualization regression tests."""
from __future__ import annotations

from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.layout_transform import LayoutTransform
from picture_capture.models import AppSettings
from picture_capture.ordinary_large_head_evidence import (
    detect_ordinary_large_head_entries,
)
from picture_capture import large_head_visualization_ui as ui
from picture_capture import layout_visualization_ui_v3 as v3


class _Flag:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _fixture():
    image = Image.new("RGB", (460, 700), "white")
    pen = ImageDraw.Draw(image)
    for y in (100, 250, 400):
        pen.rectangle((25, y, 86, y+75), fill="black")

    lines = [
        SimpleNamespace(
            y0=y, y1=y+29, first_x=5, anchor_x=5, role="body",
        )
        for y in (100, 250, 400)
    ]
    lines.extend(
        SimpleNamespace(y0=y, y1=y+29, first_x=38,
                        anchor_x=38, role="body")
        for y in (30, 55, 195, 220, 345, 370, 510, 535, 560)
    )
    column = SimpleNamespace(index=0, left=20, right=210, lines=lines)
    layout = SimpleNamespace(
        columns=[column], ordinary_line_height=30.0,
        body_top=0, body_bottom=700,
        source_size=image.size, transform=LayoutTransform("identity"),
    )
    settings = AppSettings(
        ocr_language="chi_sim",
        profile_cjk_allow_single_headword=True,
    )
    return image, SimpleNamespace(layout=layout), settings


def test_candidate_trace_has_exact_same_detector_output_and_does_not_change_roles():
    image, understanding, settings = _fixture()
    original_roles = [line.role for line in understanding.layout.columns[0].lines]
    baseline = detect_ordinary_large_head_entries(
        image, understanding, settings,
    )
    trace = []
    with_trace = detect_ordinary_large_head_entries(
        image, understanding, settings, diagnostics=trace,
    )
    def signature(entries):
        return [(e.x, e.y, e.issue_type, e.ocr_visual_run_height,
                 e.ocr_source) for e in entries]

    assert signature(baseline) == signature(with_trace)
    assert original_roles == [
        line.role for line in understanding.layout.columns[0].lines
    ]
    assert trace
    assert any(row["status"] == "accepted" for row in trace)
    assert all(
        len(row["source_box"]) == 4
        and row["reference_height"] > 0
        and isinstance(row["detector_output"], bool)
        for row in trace
    )


def test_debug_disabled_for_non_cjk_yields_no_evidence():
    image, understanding, settings = _fixture()
    settings.ocr_language = "eng"
    settings.paddle_language = "en"
    settings.dictionary_profile_id = "latin"
    report = []
    assert detect_ordinary_large_head_entries(
        image, understanding, settings, diagnostics=report,
    ) == []
    assert report == []


class _Canvas:
    def __init__(self):
        self.calls = []
        self.bindings = []

    def delete(self, *args):
        self.calls.append(("delete", args))

    def create_rectangle(self, *args, **kwargs):
        self.calls.append(("rect", args, kwargs))
        return 11

    def create_text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))
        return 12

    def create_line(self, *args, **kwargs):
        self.calls.append(("line", args, kwargs))
        return 13

    def tag_bind(self, *args):
        self.bindings.append(args)


def test_overlay_is_independent_and_does_not_change_data(monkeypatch):
    candidate = {
        "column": 0, "source_box": (25, 100, 93, 176),
        "reference_height": 30.0, "height_ratio": 2.5,
        "status": "accepted", "detector_output": True,
        "layout_role": "entry", "layout_source": "large_head",
        "nearby_final_lines": [{
            "x": 20, "y": 100, "source": "ordinary_layout_role",
        }],
    }
    calls = []
    monkeypatch.setattr(
        ui, "get_large_head_debug_snapshot",
        lambda _app: {
            "candidates": [candidate], "summary": {"accepted": 1},
            "enabled": True,
        },
    )
    canvas = _Canvas()
    app = SimpleNamespace(
        image=Image.new("RGB", (200, 300), "white"),
        canvas=canvas, view_scale=1,
        _large_head_visualization_var=_Flag(False),
    )

    ui.draw_large_head_debug_overlay(app)
    assert canvas.calls == [("delete", (ui._TAG,))]
    assert canvas.bindings == []
    assert calls == []

    app._large_head_visualization_var.set(True)
    ui.draw_large_head_debug_overlay(app)
    assert any(c[0] == "rect" for c in canvas.calls)
    assert any(c[0] == "line" for c in canvas.calls)
    assert len(canvas.bindings) == 1
    assert candidate["status"] == "accepted"
    assert (candidate["source_box"]) == (25, 100, 93, 176)


def test_large_overlay_can_display_with_layout_off_and_preserves_hide_state(monkeypatch):
    seen = []
    app = SimpleNamespace(
        _layout_visualization_var=_Flag(False),
        _large_head_visualization_var=_Flag(True),
        hide_var=_Flag(True),
    )
    monkeypatch.setattr(
        ui, "draw_large_head_debug_overlay",
        lambda app: seen.append(("large", app.hide_var.get())),
    )
    v3.draw_layout_visualization_if_enabled(app)
    assert seen == [("large", False)]
    assert app.hide_var.get() is True


def test_session_only_switch_never_becomes_an_appsettings_field(monkeypatch):
    """Regression for AttributeError: no 'show_large_head_diagnostics'."""
    import tkinter as tk
    from tkinter import ttk
    import picture_capture.layout_visualization_ui_v3 as layout_controls

    class Widget:
        def __init__(self, parent, **kwargs):
            self.parent = parent
            self.options = kwargs
            self.command = kwargs.get("command")

        def grid(self, **kwargs):
            self.grid_options = kwargs

    monkeypatch.setattr(tk, "BooleanVar", lambda value=False: _Flag(value))
    monkeypatch.setattr(ttk, "Checkbutton", Widget)
    monkeypatch.setattr(ttk, "Button", Widget)
    monkeypatch.setattr(layout_controls, "_next_grid_row", lambda section: 4)
    events = []
    settings = AppSettings()
    app = SimpleNamespace(
        settings=settings, quick_bool_vars={"show_rulers": _Flag(True)},
        redraw=lambda: events.append("redraw"),
        _attach_tooltip=lambda *a, **k: None,
    )
    ui.add_large_head_debug_controls(app, object())
    assert set(app.quick_bool_vars) == {"show_rulers"}
    assert not hasattr(settings, "show_large_head_diagnostics")
    assert app._large_head_debug_toggle_widget.options["text"] == "显示大字头检测"
    app._large_head_visualization_var.set(True)
    app._large_head_debug_toggle_widget.command()
    assert events == ["redraw"]
    assert app._large_head_debug_snapshot_key is None


def test_real_compact_display_panel_contains_same_session_toggle():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "picture_capture" / "ui"
        / "compact_display_menu.py"
    ).read_text(encoding="utf-8")
    helper = (
        root / "src" / "picture_capture"
        / "large_head_visualization_ui.py"
    ).read_text(encoding="utf-8")
    assert 'check(row, "显示大字头检测", large_var, toggle_large_heads)' in source
    assert 'row, text="导出诊断 JSON", command=export_large_heads' in source
    assert "app._large_head_visualization_var" in source
    assert "app.quick_bool_vars[\"show_large_head_diagnostics\"]" not in helper
    assert "export_large_head_debug_json(app)" in source
