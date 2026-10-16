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


def test_semantic_split_partitions_box_without_overlap_or_losing_lines():
    from picture_capture.illustrated_geometry import split_text_group
    from dataclasses import replace
    entry = replace(make_entry(20, 30, 160, 100),
                    lines=("hair", "les cheveux", "das Haar", "头发"))
    top, bottom = split_text_group([entry], entry.id, 2)
    assert top.id == entry.id and bottom.id != entry.id
    assert top.lines == ("hair", "les cheveux")
    assert bottom.lines == ("das Haar", "头发")
    assert top.y + top.h == bottom.y
    assert bottom.y + bottom.h == entry.y + entry.h
    assert top.x == bottom.x == entry.x and top.w == bottom.w == entry.w


def test_copy_paste_keeps_relative_positions_and_remaps_layout_group_id():
    from dataclasses import replace
    first = replace(make_entry(5, 10, 30, 20), group_id="group-a")
    second = replace(make_entry(80, 10, 30, 20), group_id="group-a")
    editor = editor_for_test([first, second])
    editor.selected = {first.id, second.id}
    editor.app.status_var = SimpleNamespace(set=lambda msg: None)
    assert editor.copy_selected() == "break"
    captured = []
    editor._commit = lambda result: captured.append(result) or True
    assert editor.paste_selected() == "break"
    new = captured[0][2:]
    assert len(new) == 2
    assert [v.x for v in new] == [17, 92]
    assert all(v.group_id != "group-a" for v in new)
    assert new[0].group_id == new[1].group_id
    assert {v.id for v in new} == editor.selected
    assert {v.id for v in new}.isdisjoint({first.id, second.id})


def test_illustrated_navigation_autosave_never_touches_legacy_pdic():
    from pathlib import Path
    from picture_capture.app import PictureCaptureApp
    saved = []
    app = SimpleNamespace(
        project=object(), current_page=Path("001.png"), image=object(),
        settings=AppSettings(dictionary_layout_kind="mixed",
                             illustrated_page_overrides={"001.png": "illustrated"}),
        polygon_draw_var=SimpleNamespace(get=lambda: False),
        save_pdic=lambda **_kw: saved.append("pdic"),
    )
    assert PictureCaptureApp._save_current_page_by_mode(app) is None
    assert saved == []
    app.current_page = Path("002.png")
    assert PictureCaptureApp._save_current_page_by_mode(app).name == "002.pdic"
    assert saved == ["pdic"]
