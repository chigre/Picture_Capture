"""Regression tests for the two-column rail, drag math and zoom launcher."""
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import workspace_tools


class FakeWidget:
    def __init__(self, manager=""):
        self.manager = manager
        self.calls = []

    def winfo_manager(self):
        return self.manager

    def pack(self, **kwargs):
        self.manager = "pack"
        self.calls.append(("pack", kwargs))

    def pack_forget(self):
        self.manager = ""
        self.calls.append(("pack_forget", {}))

    def grid(self, **kwargs):
        self.manager = "grid"
        self.calls.append(("grid", kwargs))

    def grid_remove(self):
        self.manager = ""
        self.calls.append(("grid_remove", {}))

    def place(self, **kwargs):
        self.manager = "place"
        self.calls.append(("place", kwargs))

    def place_forget(self):
        self.manager = ""
        self.calls.append(("place_forget", {}))

    def lift(self):
        self.calls.append(("lift", {}))


def test_icon_rail_and_both_page_lists_have_same_initial_446px_footprint():
    app = SimpleNamespace(workspace_rail_width=140, workspace_page_list_width=300)
    assert workspace_tools.RAIL_DIVIDER_WIDTH == 6
    assert workspace_tools.DEFAULT_RAIL_WIDTH == 140
    assert workspace_tools.DEFAULT_PAGE_LIST_WIDTH == 300
    assert workspace_tools.preferred_sidebar_width(app) == 446
    app.workspace_rail_width = 160
    assert workspace_tools.preferred_sidebar_width(app) == 466
    assert workspace_tools.preferred_sidebar_width(app, extreme=True) == 42


def test_simple_page_list_is_a_separate_packed_column_not_a_child_of_rail():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'simple_slot = ttk.Frame(' in source
    assert 'sidebar_host, style="PC.Sidebar.TFrame"' in source
    assert 'mini_host = ttk.Frame(simple_slot, style="PC.Sidebar.TFrame")' in source
    assert "mini_host = ttk.Frame(rail" not in source
    assert "drag[\"sash\"] + proposed - drag[\"width\"]" in source
    assert 'drag["origin"] = int(event.x_root)' in source
    assert "old_width = app.workspace_rail_width" not in source
    assert 'app.geometry(' not in source.split(
        '    def update_drag(event: tk.Event)', 1
    )[1].split('    divider.bind(', 1)[0]


def test_simple_slot_can_pack_after_full_canvas_has_been_unmapped():
    slot = FakeWidget()
    app = SimpleNamespace(workspace_mini_page_slot=slot)
    workspace_tools._set_simple_page_visible(app, True)
    assert slot.manager == "pack"
    assert slot.calls == [("pack", {"side": "left", "fill": "both", "expand": True})]
    workspace_tools._set_simple_page_visible(app, True)
    assert len(slot.calls) == 1
    workspace_tools._set_simple_page_visible(app, False)
    assert slot.manager == ""
    assert slot.calls[-1][0] == "pack_forget"


def test_simple_to_normal_mode_reuses_exact_same_page_column(monkeypatch):
    monkeypatch.setattr(workspace_tools, "refresh_compact_page_index", lambda app: None)
    canvas = FakeWidget("pack")
    scrollbar = FakeWidget("pack")
    page = FakeWidget("grid")
    slot = FakeWidget()
    app = SimpleNamespace(
        sidebar_canvas=canvas, sidebar_scrollbar=scrollbar,
        page_panel=page, workspace_mini_page_slot=slot,
    )
    workspace_tools._apply_preset_page_index(app, "简单")
    assert canvas.manager == "" and slot.manager == "pack"
    assert page.manager == ""
    workspace_tools._apply_preset_page_index(app, "正常")
    assert canvas.manager == "pack" and slot.manager == ""
    assert page.manager == "grid"
    workspace_tools._apply_preset_page_index(app, "极简")
    assert canvas.manager == "" and slot.manager == ""


def test_picture_toolbar_uses_fourth_compact_button_and_click_toggle():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    app_source = (Path(__file__).resolve().parents[1] / "src" /
                  "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert '("图片工具栏", lambda: toggle_image_toolbar(app))' in source
    assert '("普", "O", "校", "≣")[index]' in source
    assert 'app.workspace_quick_action_buttons, ("普", "O", "校", "≣")' in source
    assert 'row=index if extreme else 0' in source
    assert 'column=0 if extreme else index' in source
    assert 'zoom_handle = ttk.Label(' not in app_source

    bar = FakeWidget()
    app = SimpleNamespace(page_size_row=bar)
    workspace_tools.toggle_image_toolbar(app)
    assert bar.manager == "place"
    assert bar.calls[0] == (
        "place", {"relx": 0, "rely": 1, "x": 8, "y": -8, "anchor": "sw"},
    )
    workspace_tools.toggle_image_toolbar(app)
    assert bar.manager == ""
    assert bar.calls[-1][0] == "place_forget"
