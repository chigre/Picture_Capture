"""Regress last-column display bounds, shared auxiliary [X], and palette order.

The page remainder is not the physical dictionary column width. No stored
PDIC/SECTION/auxiliary format or OCR decisions are changed by these tests.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.auxiliary_line_controller import AuxiliaryLineController
from picture_capture.auxiliary_lines import AuxiliaryLine, AuxiliaryLineEdits
from picture_capture.overlay_layout_helpers import (
    effective_overlay_column_width,
)
from picture_capture.ui import overlay_delete_button


def _geometry(widths=(400, 580), starts=(100, 520)):
    class G:
        column_starts = list(starts)
        column_widths = list(widths)
        def source_to_canonical(self, x, y):
            return x, y
        def canonical_to_source(self, x, y):
            return x, y
    return G()


@pytest.mark.parametrize("widths,configured,expected", [
    ((400, 580), 400, (400, 400)),
    ((400, 350), 400, (400, 350)),
    ((390, 410, 700), 400, (390, 410, 400)),
    ((700,), 420, (420,)),
    ((300,), 500, (300,)),
])
def test_last_column_width_is_never_blank_page_remainder(widths, configured, expected):
    geometry = _geometry(widths=widths)
    assert tuple(effective_overlay_column_width(
        geometry, idx, configured,
    ) for idx in range(len(widths))) == expected


class _FakeButton:
    def __init__(self, master, **kwargs):
        self.master = master
        self.options = dict(kwargs)
        self._pc_skip_classic_appearance = False

    def winfo_reqwidth(self):
        return 39

    def winfo_reqheight(self):
        return 23

    def configure(self, **options):
        self.options.update(options)


class _Canvas:
    def __init__(self):
        self.lines = []
        self.windows = []

    def create_line(self, *coords, **options):
        self.lines.append((coords, options))

    def create_window(self, x, y, *, window, **options):
        self.windows.append((x, y, window, options))
        return len(self.windows)

    def create_rectangle(self, *_args, **_kwargs):
        pass

    def create_text(self, *_args, **_kwargs):
        raise AssertionError("Auxiliary [X] must use the shared button, not a canvas glyph")


def test_auxiliary_delete_control_uses_headword_button_style_hover_and_tooltip(monkeypatch):
    monkeypatch.setattr(overlay_delete_button.tk, "Button", _FakeButton)
    monkeypatch.setattr(overlay_delete_button, "resolve_content_font_family", lambda *_: "Arial")
    canvas = _Canvas()
    messages = []
    notes = []
    saves = []
    state = AuxiliaryLineEdits([AuxiliaryLine(520, 100)])
    app = SimpleNamespace(
        image=SimpleNamespace(width=1100, height=700),
        settings=SimpleNamespace(column_width=400, right_ratio=100, ocr_language="chi_sim"),
        view_scale=1.0,
        canvas=canvas,
        overlay_widgets=[],
        _auxiliary_edits=state,
        _auxiliary_drag=None,
        auxiliary_mode_var=SimpleNamespace(get=lambda: False),
        _get_cached_display_geometry=lambda: _geometry(),
        _attach_tooltip=lambda widget, text: notes.append((widget, text)),
        status_var=SimpleNamespace(set=messages.append),
        current_page=Path("page.png"),
        redraw=lambda: None,
    )
    from picture_capture import auxiliary_line_controller as mod
    monkeypatch.setattr(mod, "column_index_for_click", lambda _x, _g, _y: 1)
    monkeypatch.setattr(mod, "write_auxiliary_lines", lambda _p, lines: saves.append(list(lines)))
    ctrl = AuxiliaryLineController(app)
    ctrl.redraw()
    assert len(canvas.lines) == len(canvas.windows) == 1
    assert canvas.lines[0][0][2] == 920.0  # NOT 1100 page edge.
    _x, _y, button, placement = canvas.windows[0]
    assert isinstance(button, _FakeButton)
    assert button in app.overlay_widgets  # app.redraw owns cleanup.
    assert placement["anchor"] == "ne"
    assert button.options["text"] == "[X]"
    assert button.options["cursor"] == "hand2"  # Tk restores parent cursor on leave.
    assert button.options["font"] == ("Arial", 9, "bold")
    assert notes == [(button, "点击删除该辅助线!")]
    assert button._pc_skip_classic_appearance is True

    # Button owns an exact drawing-row deletion; no OCR or PDIC is touched.
    button.options["command"]()
    assert state.lines == []
    assert saves == [[]]
    assert messages[-1].startswith("辅助线已删除")


def test_display_menu_moves_groups_and_removes_denoise_selector():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    source = (root / "ui" / "compact_display_menu.py").read_text("utf-8")
    label = source.index('check(row, "词头标签"')
    illustration = source.index('check(row, "插图形状:线"')
    assert label < illustration
    assert source.index('value(row, "向右比例%", "right_ratio", 4)') < (
        source.index('label(row, "切图预览标签:")')
    ) < source.index('check(row, "显示Layout",')
    assert "去噪强度" not in source
    assert "_DENOISE_LABEL_TO_VALUE" not in source
    assert 'check(row, "粗 ", qb[bold])' in source
    assert source.count("divider()") >= 5


def test_auxiliary_hit_target_matches_visible_last_column_not_page_remainder(monkeypatch):
    """Ink beyond the actual column cannot select a line invisible there."""
    from picture_capture import auxiliary_line_controller as mod
    monkeypatch.setattr(mod, "column_index_for_click", lambda *_args: 1)
    app = SimpleNamespace(
        settings=SimpleNamespace(column_width=400, right_ratio=100, ocr_language="chi_sim"),
        view_scale=1.0,
        _auxiliary_edits=AuxiliaryLineEdits([AuxiliaryLine(520, 100)]),
        _get_cached_display_geometry=lambda: _geometry(),
    )
    ctrl = AuxiliaryLineController(app)
    assert ctrl._nearest(900, 100) == 0
    assert ctrl._nearest(950, 100) is None
    assert ctrl._nearest(1090, 100) is None



@pytest.mark.parametrize("ratio,end", [(100, 920.0), (75, 820.0), (50, 720.0)])
def test_auxiliary_length_matches_entry_marker_ratio_and_hit_bound(
    monkeypatch, ratio, end,
):
    from picture_capture import auxiliary_line_controller as mod
    from picture_capture.overlay_layout_helpers import canonical_headword_marker_span
    monkeypatch.setattr(overlay_delete_button.tk, "Button", _FakeButton)
    monkeypatch.setattr(overlay_delete_button, "resolve_content_font_family", lambda *_: "Arial")
    monkeypatch.setattr(mod, "column_index_for_click", lambda *_args: 1)
    canvas = _Canvas()
    app = SimpleNamespace(
        image=SimpleNamespace(width=1100, height=700),
        settings=SimpleNamespace(column_width=400, right_ratio=ratio, ocr_language="chi_sim"),
        view_scale=1.0, canvas=canvas, overlay_widgets=[],
        _auxiliary_edits=AuxiliaryLineEdits([AuxiliaryLine(520, 100)]),
        _auxiliary_drag=None, auxiliary_mode_var=SimpleNamespace(get=lambda: False),
        _get_cached_display_geometry=lambda: _geometry(),
        _attach_tooltip=lambda *_args: None,
    )
    controller = AuxiliaryLineController(app)
    controller.redraw()
    expected = canonical_headword_marker_span(520, 400, ratio)
    assert expected == (520, int(end))
    assert canvas.lines[0][0][0:3:2] == expected
    assert controller._nearest(end, 100) == 0
    assert controller._nearest(end + 1, 100) is None


def test_entry_delete_button_is_burgundy_but_auxiliary_is_orange_gold(monkeypatch):
    monkeypatch.setattr(overlay_delete_button.tk, "Button", _FakeButton)
    monkeypatch.setattr(
        overlay_delete_button, "resolve_content_font_family", lambda *_: "Arial",
    )
    opts = {"command": lambda: None, "attach_tooltip": lambda *_: None,
            "tooltip": "remove", "ocr_language": "chi_sim"}
    entry = overlay_delete_button.create_overlay_delete_button(
        _Canvas(), kind="entry", **opts,
    )
    auxiliary = overlay_delete_button.create_overlay_delete_button(
        _Canvas(), kind="auxiliary", **opts,
    )
    assert entry.options["font"] == auxiliary.options["font"] == ("Arial", 9, "bold")
    assert entry.options["bg"] == "#9d042f"
    assert entry.options["activebackground"] == "#9d042f"
    assert entry.options["fg"] == "#ffffff"
    assert auxiliary.options["bg"] == "#f5b83d"
    assert auxiliary.options["activebackground"] == "#e9a820"
    assert auxiliary.options["fg"] == "#222222"
    assert entry.options["cursor"] == auxiliary.options["cursor"] == "hand2"


def test_main_and_review_index_are_fixed_auto_font_without_zoom_scaling():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    main = (root / "ui" / "entry_overlay_builder.py").read_text("utf-8")
    review = (root / "ui" / "review_crop_sequence.py").read_text("utf-8")
    x_button = (root / "ui" / "overlay_delete_button.py").read_text("utf-8")
    review_shell = (root / "app.py").read_text("utf-8")
    assert 'fixed_overlay_control_font(\n            self.canvas, self.settings.ocr_language,' in main
    assert 'font=_main_sequence_font(review)' in review
    assert 'return fixed_overlay_control_font(' in review
    assert 'font=fixed_overlay_control_font(' in review_shell
    assert 'AUTO_FONT_FAMILY' in x_button
    assert 'OVERLAY_CONTROL_FONT_SIZE = 9' in x_button
