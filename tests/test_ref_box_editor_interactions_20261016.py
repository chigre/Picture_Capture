"""REF interaction regression: edges, controls, and Tk window event routing.

No display server needed: the controller talks to fake Canvas/child widgets.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.ref_box_geometry import hit_test, transform_box
from picture_capture.ref_boxes import RefBox, read_ref_boxes
from picture_capture.ui.ref_box_controller import RefBoxController


BOX = RefBox(4, 20, 30, 80, 50, 2, "参见 see also")


@pytest.mark.parametrize(("point", "expected"), [
    ((20, 55), "left"),
    ((100, 55), "right"),
    ((60, 30), "top"),
    ((60, 80), "bottom"),
    ((20, 30), "top-left"),
    ((100, 30), "top-right"),
    ((20, 80), "bottom-left"),
    ((100, 80), "bottom-right"),
    ((60, 55), "move"),
    ((135, 105), "create"),
])
def test_all_edges_and_corners_have_click_targets(point, expected):
    box, action = hit_test([BOX], *point, scale=1.0, selected_id=BOX.id)
    assert action == expected
    assert box == (None if expected == "create" else BOX)


@pytest.mark.parametrize(("action", "delta", "expected"), [
    ("left", (15, 0), (35, 30, 65, 50)),
    ("right", (-12, 0), (20, 30, 68, 50)),
    ("top", (0, 10), (20, 40, 80, 40)),
    ("bottom", (0, -10), (20, 30, 80, 40)),
    ("top-left", (12, 8), (32, 38, 68, 42)),
    ("top-right", (-10, 6), (20, 36, 70, 44)),
    ("bottom-left", (9, -8), (29, 30, 71, 42)),
    ("bottom-right", (14, 12), (20, 30, 94, 62)),
    ("move", (8, 11), (28, 41, 80, 50)),
])
def test_drag_geometry_preserves_identity_text_and_link(action, delta, expected):
    result = transform_box(
        BOX, action, start=(60, 55),
        current=(60 + delta[0], 55 + delta[1]),
        image_size=(200, 180),
    )
    assert (result.x, result.y, result.w, result.h) == expected
    assert (result.id, result.entry_index, result.text) == (
        BOX.id, BOX.entry_index, BOX.text,
    )


def test_resize_clamps_to_minimum_and_page_bounds():
    left = transform_box(
        BOX, "left", start=(20, 55), current=(180, 55),
        image_size=(200, 180),
    )
    assert (left.x, left.w) == (98, 2)
    top = transform_box(
        BOX, "top", start=(60, 30), current=(60, 200),
        image_size=(200, 180),
    )
    assert (top.y, top.h) == (78, 2)
    right = transform_box(
        BOX, "right", start=(100, 55), current=(400, 55),
        image_size=(200, 180),
    )
    assert (right.x, right.w) == (20, 180)
    moved = transform_box(
        BOX, "move", start=(40, 50), current=(-300, -300),
        image_size=(200, 180),
    )
    assert (moved.x, moved.y) == (0, 0)


def test_zoomed_hit_targets_remain_screen_accessible():
    for scale in (0.2, 0.5, 1.0, 2.5):
        assert hit_test(
            [BOX], BOX.x, BOX.y + BOX.h / 2,
            scale=scale, selected_id=BOX.id,
        )[1] == "left"
        assert hit_test(
            [BOX], BOX.x + BOX.w / 2, BOX.y + BOX.h,
            scale=scale, selected_id=BOX.id,
        )[1] == "bottom"


class FakeCanvas:
    def __init__(self):
        self.actions = []
        self.bindings = {}
    def focus_set(self):
        self.actions.append("focus")
    def delete(self, tag):
        self.actions.append(("delete", (tag,), {}))
    def create_rectangle(self, *coords, **kwargs):
        self.actions.append(("rectangle", coords, kwargs))
        return 5
    def create_text(self, *coords, **kwargs):
        self.actions.append(("text", coords, kwargs))
        return 6
    def create_image(self, *coords, **kwargs):
        self.actions.append(("image", coords, kwargs))
        return 7
    def canvasx(self, x):
        return x
    def canvasy(self, y):
        return y
    def winfo_rootx(self):
        return 100
    def winfo_rooty(self):
        return 200


class FakeWidget:
    def __init__(self, children=()):
        self.bindings = {}
        self.children = list(children)
    def bind(self, name, callback):
        self.bindings[name] = callback
    def winfo_children(self):
        return self.children


class FakeApp:
    def __init__(self, page: Path, *, scale=1.0):
        self.current_page = page
        self.image = Image.new("RGB", (200, 180), "white")
        self.image.save(page)
        self.view_scale = scale
        self.canvas = FakeCanvas()
        self.settings = AppSettings()
        self.status_var = SimpleNamespace(set=lambda _text: None)
        self.overlay_widgets = []
        self.errors = []
        self.redraw_count = 0
    def show_error(self, name, error):
        self.errors.append((name, str(error)))
    def redraw(self):
        self.redraw_count += 1


def editor_with_box(tmp_path):
    app = FakeApp(tmp_path / "page.png")
    editor = RefBoxController(app)
    editor.load_page(app.current_page)
    assert editor._commit([BOX])
    editor.editing = True
    return app, editor


@pytest.mark.parametrize(("press", "drag", "expected"), [
    ((20, 55), (30, 55), (30, 30, 70, 50)),
    ((100, 55), (90, 55), (20, 30, 70, 50)),
    ((60, 30), (60, 39), (20, 39, 80, 41)),
    ((60, 80), (60, 90), (20, 30, 80, 60)),
    ((60, 50), (68, 54), (28, 34, 80, 50)),
])
def test_main_editor_drag_saves_rbox_and_supports_undo(tmp_path, press, drag, expected):
    app, editor = editor_with_box(tmp_path)
    editor.press(*press)
    editor.drag(*drag)
    editor.release(*drag)
    saved = read_ref_boxes(app.current_page)[0]
    assert (saved.x, saved.y, saved.w, saved.h) == expected
    editor.undo()
    assert read_ref_boxes(app.current_page) == [BOX]
    assert not app.errors


def test_click_select_does_not_recreate_pdic_text_widgets(tmp_path):
    app, editor = editor_with_box(tmp_path)
    painted = []
    editor.render = lambda: painted.append("render")
    old_redraws = app.redraw_count
    editor.press(60, 55)
    editor.release(60, 55)
    assert editor.selected_id == BOX.id
    assert app.redraw_count == old_redraws
    assert painted == ["render"]
    assert read_ref_boxes(app.current_page) == [BOX]


def test_edit_and_delete_chips_are_active_and_persist(tmp_path):
    app, editor = editor_with_box(tmp_path)
    editor.selected_id = BOX.id
    called = []
    editor.edit_properties = lambda *a: called.append("edit")
    actions = {name: (x0, y0, x1, y1)
               for name, x0, y0, x1, y1 in editor._action_buttons()}
    assert set(actions) == {"edit", "delete"}
    x0, y0, x1, y1 = actions["edit"]
    px, py = (x0+x1)//2, (y0+y1)//2
    editor.press(px, py)
    editor.release(px, py)
    assert called == ["edit"]
    assert read_ref_boxes(app.current_page) == [BOX]
    x0, y0, x1, y1 = actions["delete"]
    px, py = (x0+x1)//2, (y0+y1)//2
    editor.press(px, py)
    editor.release(px, py)
    assert read_ref_boxes(app.current_page) == []
    editor.undo()
    assert read_ref_boxes(app.current_page) == [BOX]


def test_tk_child_widgets_forward_pointer_events_to_ref_editor(tmp_path):
    app, editor = editor_with_box(tmp_path)
    entry = FakeWidget()
    frame = FakeWidget(children=[entry])
    app.overlay_widgets = [frame]
    editor.bind_overlay_widgets()
    assert all(event in entry.bindings for event in (
        "<Button-1>", "<B1-Motion>", "<ButtonRelease-1>",
        "<Double-Button-1>", "<Button-3>", "<Button-2>",
    ))
    # Synthetic widget mouse positions (x_root/y_root) must respect canvas
    # scrolling and zoom even when widget-local coordinates are unrelated.
    event = SimpleNamespace(x_root=160, y_root=255)
    assert entry.bindings["<Button-1>"](event) == "break"
    assert editor.selected_id == BOX.id
    other = SimpleNamespace(x_root=170, y_root=265)
    entry.bindings["<B1-Motion>"](other)
    entry.bindings["<ButtonRelease-1>"](other)
    saved = read_ref_boxes(app.current_page)[0]
    assert (saved.x, saved.y) == (30, 40)


def test_context_text_and_delete_remain_independent_of_pdic(tmp_path):
    app, editor = editor_with_box(tmp_path)
    before = read_ref_boxes(app.current_page)
    editor.selected_id = BOX.id
    proposed = [RefBox(
        before[0].id, before[0].x, before[0].y,
        before[0].w, before[0].h, before[0].entry_index,
        "另见\toppose\nword",
    )]
    assert editor._commit(proposed)
    assert read_ref_boxes(app.current_page) == proposed
    editor.delete_selected()
    assert read_ref_boxes(app.current_page) == []
    editor.undo()
    assert read_ref_boxes(app.current_page) == proposed


def test_ref_delete_only_via_cross_not_keyboard_or_context_menu():
    from pathlib import Path
    import picture_capture.app as app_module
    import picture_capture.ui.ref_box_controller as ref_ui

    app_code = Path(app_module.__file__).read_text(encoding="utf-8")
    controller_code = Path(ref_ui.__file__).read_text(encoding="utf-8")
    assert 'lambda e: self.ref_box_controller.delete_selected(e)' not in app_code
    assert 'label="删除选中 REF"' not in controller_code
    assert 'if action == "delete":' in controller_code
    assert 'self.delete_selected()' in controller_code


@pytest.mark.parametrize(("follow_zoom", "zoom", "expected"), [
    (True, 1.0, 16),
    (True, 0.5, 8),
    (True, 2.0, 32),
    (False, 0.5, 16),
    (False, 2.0, 16),
])
def test_ref_body_font_uses_same_main_entry_zoom_contract(
    tmp_path, monkeypatch, follow_zoom, zoom, expected,
):
    import picture_capture.ui_compat as fonts
    from picture_capture.overlay_layout_helpers import effective_main_overlay_font_size

    app, ctl = editor_with_box(tmp_path)
    app.image = Image.new("RGB", (1400, 1800), "white")
    app.view_scale = zoom
    app.settings = AppSettings(
        ref_box_show=True, ref_box_fill_opacity=0.0,
        ref_box_filled_opacity=0.0,
        ref_text_label_background_opacity=0.0,
        ref_box_font_size=16, ref_box_font_bold=True,
        main_entry_follow_zoom=follow_zoom, main_entry_font_size=24,
    )
    ctl.editing = False
    monkeypatch.setattr(fonts, "resolve_content_font_family", lambda *_args: "Arial")
    ctl.render()
    body = next(row[2] for row in app.canvas.actions
                if row[0] == "text" and row[2].get("text") == BOX.text)
    assert body["font"] == ("Arial", expected, "bold")
    assert expected == effective_main_overlay_font_size(
        app.image.width, zoom, app.settings, base_font_size=16,
    )
    # REF remains independent from the main headword's configured base size.
    assert app.settings.main_entry_font_size == 24


def test_ref_fill_palette_switches_when_text_is_added_or_removed(tmp_path):
    from picture_capture.ui.ref_box_controller import ref_box_background

    app, editor = editor_with_box(tmp_path)
    settings = app.settings
    assert ref_box_background("", settings) == ("#ffe0b2", 0.0)
    assert ref_box_background("  \t\n", settings) == ("#ffe0b2", 0.0)
    assert ref_box_background("参见", settings) == ("#c8e6c9", 0.0)
    assert ref_box_background("see also", settings) == ("#c8e6c9", 0.0)
    settings.ref_box_show_text = False
    assert ref_box_background("参见", settings) == ("#c8e6c9", 0.0)
    settings.ref_box_fill_color = "#ffccaa"
    settings.ref_box_fill_opacity = 30.0
    settings.ref_box_filled_color = "#bbdd99"
    settings.ref_box_filled_opacity = 75.0
    assert ref_box_background("", settings) == ("#ffccaa", 30.0)
    assert ref_box_background("参见", settings) == ("#bbdd99", 75.0)


def test_canvas_render_hides_only_ref_text_not_green_background_or_saved_content(
    tmp_path, monkeypatch,
):
    import picture_capture.ui.ref_box_controller as ref_ui
    import picture_capture.ui_compat as fonts

    app, editor = editor_with_box(tmp_path)
    editor._commit([
        BOX,
        RefBox(5, 100, 90, 35, 20, None, ""),
        RefBox(6, 130, 125, 35, 20, None, "  \t"),
    ])
    editor.editing = False
    displayed_images = []

    def take_rgba(image):
        displayed_images.append(image.getpixel((0, 0)))
        return object()

    monkeypatch.setattr(ref_ui.ImageTk, "PhotoImage", take_rgba)
    monkeypatch.setattr(fonts, "resolve_content_font_family", lambda *_: "Arial")

    editor.render()
    assert displayed_images == [(220, 238, 252, 242)]  # label only; image ROI transparent
    assert [kwargs["text"] for kind, _args, kwargs in app.canvas.actions
            if kind == "text"] == [BOX.text]

    displayed_images.clear()
    app.canvas.actions.clear()
    app.settings.ref_box_show_text = False
    editor.render()
    assert displayed_images == []  # hidden label; the source-image boxes stay outlined
    assert not [kwargs for kind, _args, kwargs in app.canvas.actions if kind == "text"]
    assert read_ref_boxes(app.current_page)[0].text == BOX.text

    # Editing text reclassifies the color immediately, including while
    # the "show text" option is disabled.
    editor._commit([
        RefBox(BOX.id, BOX.x, BOX.y, BOX.w, BOX.h,
               BOX.entry_index, ""),
        RefBox(5, 100, 90, 35, 20, None, "leave"),
        RefBox(6, 130, 125, 35, 20, None, "  \t"),
    ])
    displayed_images.clear()
    editor.render()
    assert displayed_images == []  # labels hidden; status still stored in REF text
    assert read_ref_boxes(app.current_page)[1].text == "leave"


def test_ref_show_text_false_keeps_edit_mode_overlay_usable(tmp_path, monkeypatch):
    import picture_capture.ui.ref_box_controller as ref_ui
    import picture_capture.ui_compat as fonts

    app, editor = editor_with_box(tmp_path)
    app.settings.ref_box_show_text = False
    app.settings.ref_box_show = False
    monkeypatch.setattr(ref_ui.ImageTk, "PhotoImage", lambda _im: object())
    monkeypatch.setattr(fonts, "resolve_content_font_family", lambda *_: "Arial")
    editor.editing = True
    editor.selected_id = BOX.id
    editor.render()

    # show-box=False is overridden during editing, while hidden body text
    # must not hide REF handles or the pencil/cross action buttons.
    assert any(kind == "rectangle" for kind, _args, _kwargs in app.canvas.actions)
    texts = [kwargs["text"] for kind, _args, kwargs in app.canvas.actions
             if kind == "text"]
    assert BOX.text not in texts
    assert "✎" in texts and "×" in texts


def test_ref_palette_and_text_visibility_persist_after_reopen(tmp_path):
    from picture_capture.models import AppSettings
    from picture_capture.ui.settings.schema import (
        CHECK_HELP, SETTING_HELP, FIELDS, REF_BOX_STYLE_FIELDS,
        REF_BOX_CHECKS,
    )
    from picture_capture.ui.settings.lifecycle import validate_ref_box_controls

    settings = AppSettings(
        ref_box_show_text=False,
        ref_box_fill_color="#ffc48a",
        ref_box_fill_opacity=42.0,
        ref_box_filled_color="#b6e2af",
        ref_box_filled_opacity=65.0,
    )
    path = tmp_path / "settings.json"
    settings.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.ref_box_show_text is False
    assert (reopened.ref_box_fill_color, reopened.ref_box_fill_opacity) == ("#ffc48a", 42.0)
    assert (reopened.ref_box_filled_color, reopened.ref_box_filled_opacity) == ("#b6e2af", 65.0)

    ref_field_names = {name for _label, name, _cast in FIELDS}
    for name in ("ref_box_fill_color", "ref_box_fill_opacity",
                 "ref_box_filled_color", "ref_box_filled_opacity"):
        assert name in REF_BOX_STYLE_FIELDS
        assert name in ref_field_names
        assert name in SETTING_HELP and len(SETTING_HELP[name]) > 40
    from picture_capture.ui.settings.schema import REF_TEXT_LABEL_CHECKS
    assert ("显示 REF 文本标签", "ref_box_show_text") in REF_TEXT_LABEL_CHECKS
    assert len(CHECK_HELP["ref_box_show_text"]) > 40

    from types import SimpleNamespace
    values = {
        name: SimpleNamespace(get=lambda val=value: val)
        for name, value in (
            ("ref_box_fill_color", "#ffc48a"),
            ("ref_box_fill_opacity", "42"),
            ("ref_box_filled_color", "#b6e2af"),
            ("ref_box_filled_opacity", "65"),
        )
    }
    validate_ref_box_controls(values)


def test_ref_text_label_can_show_without_original_frame_and_select_for_edit(
    tmp_path, monkeypatch,
):
    import picture_capture.ui.ref_box_controller as ref_ui
    import picture_capture.ui_compat as fonts

    app, editor = editor_with_box(tmp_path)
    app.settings.ref_box_show = False
    app.settings.ref_box_show_text = True
    monkeypatch.setattr(ref_ui.ImageTk, "PhotoImage", lambda _image: object())
    monkeypatch.setattr(fonts, "resolve_content_font_family", lambda *_: "Arial")
    editor.editing = False
    editor.render()
    assert BOX.id in editor._label_rects
    assert not [kwargs for kind, _, kwargs in app.canvas.actions
                if kind == "rectangle" and "ref-box-border" in kwargs.get("tags", ())]
    assert [kwargs["text"] for kind, _, kwargs in app.canvas.actions
            if kind == "text"] == [BOX.text]

    # Label has its own hit target; selecting does not create/move the REF box.
    editor.editing = True
    editor.selected_id = None
    editor.render()
    x0, y0, x1, y1 = editor._label_rects[BOX.id]
    assert editor.press((x0+x1)//2, (y0+y1)//2) == "break"
    assert editor.selected_id == BOX.id
    assert editor.pointer_action == "label"
    editor.release((x0+x1)//2, (y0+y1)//2)
    assert read_ref_boxes(app.current_page)[0] == BOX
