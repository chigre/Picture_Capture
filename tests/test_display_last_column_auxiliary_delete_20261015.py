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
    canvas = _Canvas()
    messages = []
    notes = []
    saves = []
    state = AuxiliaryLineEdits([AuxiliaryLine(520, 100)])
    app = SimpleNamespace(
        image=SimpleNamespace(width=1100, height=700),
        settings=SimpleNamespace(column_width=400),
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
    assert button.options["font"] == overlay_delete_button.DELETE_BUTTON_FONT
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
        settings=SimpleNamespace(column_width=400),
        view_scale=1.0,
        _auxiliary_edits=AuxiliaryLineEdits([AuxiliaryLine(520, 100)]),
        _get_cached_display_geometry=lambda: _geometry(),
    )
    ctrl = AuxiliaryLineController(app)
    assert ctrl._nearest(900, 100) == 0
    assert ctrl._nearest(950, 100) is None
    assert ctrl._nearest(1090, 100) is None

