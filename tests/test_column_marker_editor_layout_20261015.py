"""Regression: full-column marker span, editable slot, independent [X] visibility.

A source-native two-column page, mock Tk widget lifecycle and configured Y ROI
are used; no private scans/PDIC fixtures and no claims about actual OCR accuracy.
"""
from __future__ import annotations

from types import SimpleNamespace
import inspect

import pytest
from PIL import Image

from picture_capture.layout_transform import LayoutTransform
from picture_capture.models import AppSettings, Entry
from picture_capture.overlay_layout_helpers import (
    canonical_headword_marker_span, effective_overlay_column_width,
    horizontal_entry_editor_slot,
)
from picture_capture.paddle_headwords_core import _separator_analysis_x_bounds
from picture_capture.processing import derive_nominal_geometry, line_box
from picture_capture.ui import entry_overlay_builder as builder


def _settings(**kwargs):
    return AppSettings(
        columns=2, manual_x=100, column_width=400, gutter=20, start_y=0,
        follow_column_deformation=False, layout_writing_mode="horizontal-tb",
        main_entry_x_ratio=0.66, **kwargs,
    )


@pytest.mark.parametrize("ratio,first_end,last_end", [
    (100, 500, 920),
    (75, 400, 820),
    (50, 300, 720),
])
def test_display_marker_ratio_stops_at_actual_column_end_not_page_remainder(
    ratio, first_end, last_end,
):
    settings = _settings(right_ratio=ratio)
    geometry = derive_nominal_geometry(1100, 800, settings)
    image = Image.new("RGB", (1100, 800), "white")
    assert geometry.column_widths == [400, 580]
    for idx, (start, expected_end) in enumerate(((100, first_end), (520, last_end))):
        visible_width = effective_overlay_column_width(
            geometry, idx, settings.column_width,
        )
        assert canonical_headword_marker_span(
            start, visible_width, settings.right_ratio,
        ) == (start, expected_end)
        entry = Entry("", start, 100)
        # Existing crop policy still uses the page remainder for the last
        # column; do not change stored crop/export behavior in a display fix.
        if idx == 0:
            assert line_box(entry, geometry, image, settings)[2] == expected_end
        else:
            assert line_box(entry, geometry, image, settings)[2] >= expected_end


@pytest.mark.parametrize("kind", ["identity", "mirror_x", "rotate_ccw90", "rotate_cw90"])
def test_column_marker_span_round_trips_source_transform(kind):
    transform = LayoutTransform(kind)
    source_size = (1100, 800)
    canonical_size = transform.canonical_size(source_size)
    start = 100
    width = min(400, canonical_size[0] - start)
    p0, p1 = canonical_headword_marker_span(start, width, 100)
    a, b = transform.canonical_marker_to_source((p0, 120), (p1, 120), source_size)
    assert transform.source_segment_to_canonical(a, b, source_size) == (
        (p0, 120), (p1, 120),
    )


@pytest.mark.parametrize("rtl", [False, True])
def test_editor_reserves_actual_delete_width_before_column_end(rtl):
    editor_x, end_x, delete_width = (364, 500, 39) if not rtl else (736, 600, 39)
    width, delete_x, anchor = horizontal_entry_editor_slot(
        editor_x, end_x, delete_width, rtl=rtl,
    )
    assert width == 97
    assert delete_x == float(end_x)
    # The visible [X] occupies its measured 39px from the editor's span.
    assert anchor == ("ne" if rtl else "nw")
    full_width, _x, _anchor = horizontal_entry_editor_slot(
        editor_x, end_x, 0, rtl=rtl,
    )
    assert full_width == width + delete_width


def test_refinement_roi_is_independent_of_visual_marker_ratio_and_respects_margin():
    settings = _settings(
        right_ratio=100,
        paddle_separator_roi_width_ratio=100,
        paddle_separator_column_margin=8,
    )
    assert _separator_analysis_x_bounds(400, settings) == (8, 392)
    settings.right_ratio = 50
    assert _separator_analysis_x_bounds(400, settings) == (8, 392)
    # 100% Y ROI means full *usable* column after deliberate 8px margins.
    # This is independent from drawing 100% of the visual marker.


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Widget:
    def __init__(self, parent, **options):
        self.parent, self.options, self.bindings = parent, options, {}

    def insert(self, *_args):
        pass

    def configure(self, **options):
        self.options.update(options)

    def bind(self, key, func):
        self.bindings[key] = func

    def winfo_reqwidth(self):
        return 39 if isinstance(self, _Button) else 145 if isinstance(self, _Entry) else 30

    def winfo_reqheight(self):
        return 23


class _Entry(_Widget):
    pass


class _Button(_Widget):
    pass


class _Label(_Widget):
    pass


class _Checkbutton(_Widget):
    pass


class _OCRMenu(_Widget):
    pass


class _Canvas:
    def __init__(self):
        self.windows = []

    def create_window(self, x, y, *, window, **options):
        self.windows.append((x, y, window, options))
        return len(self.windows)


def _render(monkeypatch, *, show_markers=True, show_labels=True, index=0, ratio=100,
            candidate=False, show_candidate=True, show_ocr=False):
    monkeypatch.setattr(builder.tk, "Entry", _Entry)
    monkeypatch.setattr(builder.tk, "Button", _Button)
    monkeypatch.setattr(builder.tk, "Label", _Label)
    monkeypatch.setattr(builder.tk, "Checkbutton", _Checkbutton)
    monkeypatch.setattr(builder, "resolve_content_font_family", lambda *_args: "Arial")
    from picture_capture.ui import overlay_delete_button
    monkeypatch.setattr(builder, "fixed_overlay_control_font", lambda *_: ("Arial", 9, "bold"))
    monkeypatch.setattr(overlay_delete_button, "fixed_overlay_control_font", lambda *_: ("Arial", 9, "bold"))
    lines = []
    monkeypatch.setattr(
        builder, "create_alpha_canvas_line",
        lambda _app, coords, **_options: lines.append(coords) or 99,
    )
    settings = _settings(right_ratio=ratio, show_main_entry_labels=show_labels)
    image = Image.new("RGB", (1100, 800), "white")
    geometry = derive_nominal_geometry(*image.size, settings)
    entries = [Entry("甲", 100, 100), Entry("乙", 520, 150)]
    app = SimpleNamespace(
        image=image, hide_var=_Var(False), quick_bool_vars={
            "show_headword_markers": _Var(show_markers),
            "paddle_show_candidate_checkboxes": _Var(show_candidate),
        }, settings=settings, view_scale=1.0, canvas=_Canvas(),
        overlay_widgets=[], entry_editor_bindings=[],
        _entry_visuals={}, entries=entries, crop_preview_var=_Var(False),
        _style_entry_editor=lambda *_args: None,
        _candidate_for_entry=lambda _entry: {"candidate_id": "one"} if candidate else None,
        _main_ocr_review_option_enabled=lambda _key: show_ocr,
        _create_main_ocr_menu=lambda *_args: _OCRMenu(None),
        _entry_keypress_batch_guard=lambda _event: None,
        _claim_page_for_manual_edit=lambda: True,
        _entry_sequence_text=lambda idx, total: f"{idx + 1}/{total}",
        _attach_tooltip=lambda *_args: None,
        update_entry=lambda *_args: None, focus_next=lambda *_args: None,
        focus_previous=lambda *_args: None, delete_entry=lambda *_args: None,
        _move_entry_via_dialog=lambda *_args: None,
    )
    builder.draw_entry_overlay(
        app, entries[index], index, geometry, image.size, 1.0,
        processing_readonly=False,
    )
    return app, lines, entries[index], geometry


@pytest.mark.parametrize("index", [0, 1])
def test_real_overlay_builder_100_percent_and_editor_delete_slot(monkeypatch, index):
    app, lines, entry, geometry = _render(monkeypatch, index=index)
    left = geometry.column_starts[index]
    right = left + effective_overlay_column_width(
        geometry, index, app.settings.column_width,
    )
    assert len(lines) == 1
    assert (lines[0][0], lines[0][2]) == (left, right)
    windows = app.canvas.windows
    editor_x, _y, editor, options = next(
        w for w in windows if isinstance(w[2], _Entry)
    )
    _bx, _by, _button, button_options = next(
        w for w in windows if isinstance(w[2], _Button)
    )
    assert options["width"] == max(1, round(right - editor_x) - _button.winfo_reqwidth())
    assert (_bx, button_options["anchor"]) == (float(right), "ne")
    assert app._entry_visuals[id(entry)]["delete_widget"] is _button


@pytest.mark.parametrize("show_markers,show_labels,expected", [
    (True, True, (_Entry, _Label, _Button)),
    (True, False, (_Button,)),
    (False, True, (_Entry, _Label)),
    (False, False, ()),
])
def test_delete_button_follows_marker_not_headword_label(
    monkeypatch, show_markers, show_labels, expected,
):
    app, lines, entry, _geometry = _render(
        monkeypatch, show_markers=show_markers, show_labels=show_labels,
    )
    classes = tuple(type(window[2]) for window in app.canvas.windows)
    assert set(classes) == set(expected)
    assert bool(lines) is show_markers
    assert ("delete_widget" in app._entry_visuals[id(entry)]) is show_markers


@pytest.mark.parametrize("index,ratio", [(0, 50), (1, 50), (0, 75), (1, 75), (0, 100), (1, 100)])
def test_entry_x_right_edge_equals_marker_right_at_any_ratio(monkeypatch, index, ratio):
    app, lines, entry, geometry = _render(monkeypatch, index=index, ratio=ratio)
    assert len(lines) == 1
    line_right = max(lines[0][0], lines[0][2])
    bx, by, button, placement = next(
        item for item in app.canvas.windows if isinstance(item[2], _Button)
    )
    assert bx == float(line_right)
    assert placement["anchor"] == "ne"


@pytest.mark.parametrize("candidate,show_candidate", [
    (True, True), (True, False), (False, True), (False, False),
])
def test_saved_entry_never_claims_to_be_ocr_line_candidate(
    monkeypatch, candidate, show_candidate,
):
    app, lines, _entry, _geometry = _render(
        monkeypatch, index=0, ratio=50, candidate=candidate,
        show_candidate=show_candidate, show_ocr=True,
    )
    assert not any(isinstance(w[2], _Checkbutton) for w in app.canvas.windows)
    menu = next(w for w in app.canvas.windows if isinstance(w[2], _OCRMenu))
    assert menu[0] == max(lines[0][0], lines[0][2])
    assert menu[3]["anchor"] == "nw"


@pytest.mark.parametrize("ratio", [50, 75, 100])
def test_selector_starts_at_marker_end_without_false_candidate(monkeypatch, ratio):
    app, lines, _entry, _geometry = _render(
        monkeypatch, ratio=ratio, show_ocr=True, candidate=True,
    )
    menu = next(v for v in app.canvas.windows if isinstance(v[2], _OCRMenu))
    assert menu[0] == max(lines[0][0], lines[0][2])
    assert menu[3]["anchor"] == "nw"


def test_native_delete_key_edits_characters_not_entire_headword(monkeypatch):
    app, _lines, _entry, _geometry = _render(monkeypatch)
    editor = next(
        item[2] for item in app.canvas.windows if isinstance(item[2], _Entry)
    )
    # No widget-specific binding consumes Delete. Native Tk Entry class
    # bindings remain responsible for deleting the selected character(s).
    assert "<Delete>" not in editor.bindings
    assert "<FocusOut>" in editor.bindings
    assert "<KeyPress>" in editor.bindings
    assert "<Return>" in editor.bindings
