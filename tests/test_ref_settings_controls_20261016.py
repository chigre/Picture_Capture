"""REF action location and shared Settings Center color-swatch regressions."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk

import pytest
from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.ref_boxes import RefBox, read_ref_boxes
from picture_capture.ref_box_geometry import ref_action_buttons, REF_ACTION_POSITIONS
from picture_capture.ui.settings.color_picker import (
    contrast_foreground, normalized_hex, make_color_widget,
    validate_color_controls,
)
from picture_capture.ui.settings import schema
from picture_capture.ui.ref_box_controller import RefBoxController

from types import SimpleNamespace


class _TestCanvas:
    def focus_set(self):
        return None
    def delete(self, _tag):
        return None


class FakeApp:
    def __init__(self, page: Path):
        self.current_page = page
        self.image = Image.new("RGB", (200, 160), "white")
        self.image.save(page)
        self.canvas = _TestCanvas()
        self.view_scale = 1.0
        self.settings = AppSettings()
        self.status_var = SimpleNamespace(set=lambda *_args: None)
        self.errors = []
    def redraw(self):
        return None
    def show_error(self, name, error):
        self.errors.append((name, str(error)))


@pytest.mark.parametrize("position", REF_ACTION_POSITIONS)
@pytest.mark.parametrize("box", [
    RefBox(1, 90, 60, 60, 25, 0),
    RefBox(1, 2, 1, 30, 20, 0),
    RefBox(1, 156, 130, 42, 28, 0),
])
def test_buttons_stay_on_image_and_do_not_overlap(position, box):
    result = ref_action_buttons(box, (200, 160), 1.0, position)
    assert [b[0] for b in result] == ["edit", "delete"]
    for _, x0, y0, x1, y1 in result:
        assert 0 <= x0 < x1 <= 200
        assert 0 <= y0 < y1 <= 160
    a, b = result
    assert (a[3] <= b[1] or b[3] <= a[1]
            or a[4] <= b[2] or b[4] <= a[2])


def test_right_side_placement_is_to_right_with_room_and_falls_left_on_edge():
    box = RefBox(1, 20, 30, 60, 20, None)
    edit = ref_action_buttons(box, (200, 150), 1, "right_side")[0]
    assert edit[1] > box.x + box.w
    edge = RefBox(1, 170, 30, 29, 20, None)
    edit = ref_action_buttons(edge, (200, 150), 1, "right_side")[0]
    assert edit[3] <= edge.x
    assert ref_action_buttons(box, (200, 150), 1, "unknown") == (
        ref_action_buttons(box, (200, 150), 1, "above_right")
    )


def test_no_hidden_delete_targets_when_cross_is_selected_only(tmp_path):
    page = tmp_path / "page.png"
    app = FakeApp(page)
    editor = RefBoxController(app)
    editor.load_page(page)
    a, b = (RefBox(1, 10, 20, 30, 16, None, "one"),
            RefBox(2, 85, 90, 30, 16, None, "two"))
    assert editor._commit([a, b])
    editor.editing = True
    editor.selected_id = a.id
    app.settings.ref_box_delete_always_visible = False
    assert {item[0] for item in editor._visible_action_buttons()} == {a.id}
    app.settings.ref_box_delete_always_visible = True
    visible = editor._visible_action_buttons()
    assert {(item[0], item[1]) for item in visible} == {
        (a.id, "edit"), (a.id, "delete"), (b.id, "delete"),
    }
    app.settings.ref_box_action_position = "right_side"
    target = next(item for item in editor._visible_action_buttons()
                  if item[:2] == (b.id, "delete"))
    _, _, x0, y0, x1, y1 = target
    x, y = (x0+x1)//2, (y0+y1)//2
    editor.press(x, y)
    assert editor.selected_id == b.id
    editor.release(x, y)
    assert read_ref_boxes(page) == [a]
    editor.undo()
    assert read_ref_boxes(page) == [a, b]
    editor.editing = False
    assert editor._visible_action_buttons() == []


def test_action_settings_persist_and_are_registered(tmp_path):
    s = AppSettings(
        ref_box_action_position="right_side",
        ref_box_delete_always_visible=True,
    )
    path = tmp_path / "settings.json"
    s.to_json(path)
    loaded = AppSettings.from_json(path)
    assert loaded.ref_box_action_position == "right_side"
    assert loaded.ref_box_delete_always_visible is True
    assert "ref_box_action_position" in dict(
        (name, type_) for _label, name, type_ in schema.FIELDS
    )
    assert set(schema.SETTING_CHOICES["ref_box_action_position"].values()) == set(
        REF_ACTION_POSITIONS
    )
    assert ("编辑模式中所有 REF 一直显示 ×",
            "ref_box_delete_always_visible") in schema.REF_BOX_CHECKS
    assert "ref_box_action_position" in schema.SETTING_HELP
    assert "ref_box_delete_always_visible" in schema.CHECK_HELP


@pytest.mark.parametrize(("hex_color", "normalized"), [
    ("#FFFFFF", "#ffffff"), ("#00aAbB", "#00aabb"),
    ("#123456", "#123456"), ("bad", None), ("#FFF", None),
    ("#12345g", None), ("", None),
])
def test_hex_color_presentation(hex_color, normalized):
    assert normalized_hex(hex_color) == normalized


def test_swatch_button_foreground_contrast():
    assert contrast_foreground("#000000") == "#ffffff"
    assert contrast_foreground("#ffffff") == "#161616"
    assert contrast_foreground("#C8E6C9") == "#161616"
    assert contrast_foreground("invalid") == "#202020"


def test_universal_picker_covers_all_settings_color_fields():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    picker = (root / "ui" / "settings" / "color_picker.py").read_text(encoding="utf-8")
    illustration = (root / "ui" / "settings" / "illustration.py").read_text(encoding="utf-8")
    ref = (root / "ui" / "settings" / "ref_box.py").read_text(encoding="utf-8")
    names = {name for _label, name, _type in schema.FIELDS}
    colors = {name for name in names if name.endswith("_color")}
    assert {
        "illustration_outline_color", "illustration_fill_color",
        "illustration_label_border_color", "illustration_label_fill_color",
        "ref_box_fill_color", "ref_box_filled_color", "ref_box_text_color",
    }.issubset(colors)
    assert 'if name.endswith("_color")' in app
    assert "make_color_widget(parent, var)" in app
    assert 'bg=chosen' in picker and 'text="选色…"' in picker
    assert "value.trace_add(" in picker
    assert "colorchooser.askcolor(" in picker
    assert "for name in COLOR_FIELDS" not in illustration
    assert "colorchooser.askcolor(" not in ref  # no feature-local picker


def test_native_tk_swatch_updates_when_manual_hex_changes():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No display server for native Tk widget test")
    root.withdraw()
    try:
        var = tk.StringVar(master=root, value="#ffe0b2")
        widget = make_color_widget(root, var)
        buttons = [c for c in widget.winfo_children()
                   if isinstance(c, tk.Button)]
        assert len(buttons) == 1
        button = buttons[0]
        assert button.cget("bg").lower() == "#ffe0b2"
        var.set("#3a5678")
        assert button.cget("bg").lower() == "#3a5678"
        var.set("not a color")
        assert button.cget("text") == "颜色无效"
        assert button.cget("bg").lower() == "#e5e7eb"
    finally:
        root.destroy()


@pytest.mark.parametrize(("color", "valid"), [
    ("#ffe0b2", True), ("#c8E6C9", True), ("#123abc", True),
    ("#FFF", False), ("red", False), ("#12345G", False),
    ("#123456 ", False), ("", False),
])
def test_generic_color_validation_blocks_invalid_autosave(color, valid):
    from types import SimpleNamespace
    values = {
        "illustration_outline_color": SimpleNamespace(get=lambda: color),
        "ref_box_text_color": SimpleNamespace(get=lambda: "#15395b"),
    }
    if valid:
        validate_color_controls(values)
    else:
        with pytest.raises(ValueError):
            validate_color_controls(values)


def test_color_validation_is_before_settings_mutation():
    src = (Path(__file__).resolve().parents[1] /
           "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    settings_start = src.index("class SettingsDialog")
    save_start = src.index("    def save(self, *, close: bool", settings_start)
    target = src[save_start:save_start + 2600]
    assert target.index("_settings_color_ui.validate_color_controls(self.vars)") < (
        target.index("for name, var in self.vars.items():")
    )
