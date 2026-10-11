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
    assert workspace_tools.preferred_sidebar_width(app, compact=True) == 166


def test_compact_page_list_is_directly_below_page_icon_in_same_rail():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'simple_slot = ttk.Frame(rail, style="PC.Sidebar.TFrame")' in source
    assert 'row=len(TASK_GROUPS) + 4, column=0, sticky="nsew"' in source
    assert 'row=len(TASK_GROUPS) + 2, "▦", "页面"' in source
    assert 'mini_host = ttk.Frame(simple_slot, style="PC.Sidebar.TFrame")' in source
    assert "simple_slot.pack(side=" not in source
    assert "drag[\"sash\"] + proposed - drag[\"width\"]" in source
    assert 'drag["origin"] = int(event.x_root)' in source
    assert "old_width = app.workspace_rail_width" not in source
    assert 'app.geometry(' not in source.split(
        '    def update_drag(event: tk.Event)', 1
    )[1].split('    divider.bind(', 1)[0]


def test_compact_slot_only_uses_grid_below_page_icon():
    slot = FakeWidget()
    app = SimpleNamespace(workspace_mini_page_slot=slot)
    workspace_tools._set_simple_page_visible(app, True)
    assert slot.manager == "grid"
    assert slot.calls == [("grid", {})]
    workspace_tools._set_simple_page_visible(app, True)
    assert len(slot.calls) == 1
    workspace_tools._set_simple_page_visible(app, False)
    assert slot.manager == ""
    assert slot.calls[-1][0] == "grid_remove"


def test_compact_to_normal_restores_separate_full_page_column(monkeypatch):
    monkeypatch.setattr(workspace_tools, "refresh_compact_page_index", lambda app: None)
    canvas = FakeWidget("pack")
    scrollbar = FakeWidget("pack")
    page = FakeWidget("grid")
    slot = FakeWidget()
    app = SimpleNamespace(
        sidebar_canvas=canvas, sidebar_scrollbar=scrollbar,
        page_panel=page, workspace_mini_page_slot=slot,
        workspace_tools_rail=FakeWidget("pack"),
    )
    workspace_tools._apply_preset_page_index(app, "紧凑")
    assert canvas.manager == "" and slot.manager == "grid"
    assert page.manager == ""
    workspace_tools._apply_preset_page_index(app, "正常")
    assert canvas.manager == "pack" and slot.manager == ""
    assert page.manager == "grid"
    workspace_tools._apply_preset_page_index(app, "极简")
    assert canvas.manager == "" and slot.manager == ""


def test_compact_font_is_limited_to_page_controls_not_rail_or_zoom():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    start = source.index("def _apply_compact_sidebar_font(app: Any, compact: bool)")
    end = source.index("def install_compact_zoom_controls(", start)
    scope = source[start:end]
    assert "slot = app.workspace_mini_page_slot" in scope
    assert "visit(slot)" in scope
    assert "app.workspace_rail_labels" not in scope
    assert "app.workspace_quick_action_buttons" not in scope
    assert '"PC.Workspace80.Treeview" if compact' in scope
    assert '"PC.Workspace80.TButton", "PC.SimplePage.TButton"' in scope

    zoom_start = source.index("def install_compact_zoom_controls(")
    zoom_end = source.index("def _apply_preset_rail_controls(", zoom_start)
    zoom = source[zoom_start:zoom_end]
    assert 'style="PC.WorkspaceZoom.TEntry"' in zoom
    assert 'style="PC.QuickRail.TButton"' in zoom
    assert "font=_compact_font(app)" not in zoom
    style_start = source.index("def _style_compact_sidebar(")
    style_end = source.index("def _apply_compact_sidebar_font(", style_start)
    assert 'style.configure("PC.WorkspaceZoom.TEntry", font="TkDefaultFont"' in source[style_start:style_end]


def test_picture_toolbar_uses_fourth_compact_button_and_click_toggle():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    app_source = (Path(__file__).resolve().parents[1] / "src" /
                  "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert '("图片工具栏", lambda: toggle_image_toolbar(app))' in source
    assert '("普", "O", "校", "≣")[index]' in source
    assert 'app.workspace_quick_action_buttons, ("普", "O", "校", "≣")' in source
    assert 'row=(6 + index if extreme else 2 if compact else 0)' in source
    assert 'column=(0 if extreme else index)' in source
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
