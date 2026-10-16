"""Main canvas illustrated editor: ruler semantics and multi-object safety."""
from types import SimpleNamespace

from picture_capture.models import AppSettings
from picture_capture.illustrated_entries import make_entry
from picture_capture.ui.illustrated_main_canvas import IllustratedCanvasEditor


class DummyCanvas:
    def focus_set(self):
        pass


def editor_for_test(entries=()):
    editor = IllustratedCanvasEditor.__new__(IllustratedCanvasEditor)
    editor.app = SimpleNamespace(
        settings=AppSettings(dictionary_layout_kind="illustrated"),
        canvas=DummyCanvas(),
        image=SimpleNamespace(size=(500, 600)),
        view_scale=1.0,
        redraw=lambda: None,
    )
    editor.entries = list(entries)
    editor.selected = set()
    editor.key_id = None
    editor.last_pointer = (0, 0)
    editor.drag = None
    editor._sync = lambda: True
    editor._ready = lambda: True
    editor._source = lambda event: (event.x, event.y)
    return editor


def event(x, y, state=0):
    return SimpleNamespace(x=x, y=y, state=state)


def test_shift_drag_from_top_ruler_creates_horizontal_guide():
    editor = editor_for_test()
    assert editor.press(event(100, 4, state=0x1)) == "break"
    assert editor.drag[0:2] == ("guide", "horizontal")


def test_shift_drag_from_left_ruler_creates_vertical_guide():
    editor = editor_for_test()
    editor.press(event(4, 100, state=0x1))
    assert editor.drag[0:2] == ("guide", "vertical")


def test_shift_click_toggles_saved_text_group_membership():
    left = make_entry(30, 30, 50, 25)
    right = make_entry(160, 30, 50, 25)
    editor = editor_for_test([left, right])
    editor.selected = {left.id}
    editor.press(event(40, 40, state=0x1))
    assert editor.selected == set()
    editor.press(event(40, 40, state=0x1))
    editor.press(event(170, 40, state=0x1))
    assert editor.selected == {left.id, right.id}
    assert editor.drag is None


def test_nudge_clamps_single_shared_delta_not_each_rectangle():
    left = make_entry(3, 50, 40, 20)
    right = make_entry(120, 50, 40, 20)
    editor = editor_for_test([left, right])
    editor.selected = {left.id, right.id}
    recorded = []
    editor._commit = lambda new: recorded.append(new)
    assert editor.nudge(-1, 0, event(0, 0, state=0x1)) == "break"
    assert len(recorded) == 1
    assert [(e.x, e.y) for e in recorded[0]] == [(0, 50), (117, 50)]
    assert recorded[0][1].x - recorded[0][0].x == 117
