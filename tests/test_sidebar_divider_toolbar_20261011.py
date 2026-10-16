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


def test_icon_rail_and_page_list_use_120_plus_260_width():
    app = SimpleNamespace(workspace_rail_width=120, workspace_page_list_width=260)
    assert workspace_tools.RAIL_DIVIDER_WIDTH == 6
    assert workspace_tools.DEFAULT_RAIL_WIDTH == 120
    assert workspace_tools.DEFAULT_PAGE_LIST_WIDTH == 260
    assert workspace_tools.preferred_sidebar_width(app) == 386
    app.workspace_rail_width = 140
    assert workspace_tools.preferred_sidebar_width(app) == 406
    assert workspace_tools.preferred_sidebar_width(app, extreme=True) == 42
    assert workspace_tools.preferred_sidebar_width(app, compact=True) == 146


def test_compact_page_list_is_below_task_icons_in_same_rail():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'simple_slot = ttk.Frame(rail, style="PC.Sidebar.TFrame")' in source
    assert 'row=len(TASK_GROUPS) + 2, column=0, sticky="nsew"' in source
    assert 'workspace_page_index_button' not in source
    assert 'def toggle_page_index(' not in source
    assert 'def toggle_sidebar(' not in source
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
        main_paned=SimpleNamespace(sashpos=lambda *_args: 175),
    )
    workspace_tools._apply_preset_page_index(app, "紧凑")
    assert canvas.manager == "" and slot.manager == "grid"
    assert page.manager == ""
    workspace_tools._apply_preset_page_index(app, "正常")
    assert canvas.manager == "pack" and slot.manager == ""
    assert page.manager == "grid"
    workspace_tools._apply_preset_page_index(app, "极简")
    assert canvas.manager == "" and slot.manager == ""


def test_compact_font_is_limited_to_page_range_and_zoom_percent_field():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    start = source.index("def _apply_compact_sidebar_font(app: Any, compact: bool)")
    end = source.index("def install_compact_zoom_controls(", start)
    scope = source[start:end]
    assert "slot = app.workspace_mini_page_slot" in scope
    assert "visit(slot)" in scope
    assert "app.workspace_rail_labels" not in scope
    assert "app.workspace_quick_action_buttons" not in scope
    assert 'widget.configure(style="PC.CompactPage.Treeview")' in scope
    assert '"PC.Workspace80.Treeview"' not in scope
    app_source = (Path(__file__).resolve().parents[1] / "src" /
                  "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert 'self.compact_page_font.configure(size=compact_size)' in app_source
    assert 'round(base_size * 0.9)' in app_source
    assert 'max(1, viewport - 2), app.compact_page_font.measure' in source
    assert '"PC.Workspace80.TButton", "PC.SimplePage.TButton"' in scope

    zoom_start = source.index("def install_compact_zoom_controls(")
    zoom_end = source.index("def _apply_preset_rail_controls(", zoom_start)
    zoom = source[zoom_start:zoom_end]
    assert 'style="PC.WorkspaceZoom.TEntry"' in zoom
    assert 'style="PC.QuickRail.TButton"' in zoom
    assert "font=_compact_font(app)" not in zoom
    style_start = source.index("def _style_compact_sidebar(")
    style_end = source.index("def _apply_compact_sidebar_font(", style_start)
    assert 'style.configure("PC.WorkspaceZoom.TEntry", font=small' in source[style_start:style_end]


def test_zoom_toolbar_is_inline_in_every_mode_without_old_launcher():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    app_source = (Path(__file__).resolve().parents[1] / "src" /
                  "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert '("普", "O", "校")[index]' in source
    assert 'app.workspace_quick_action_buttons, ("普", "O", "校")' in source
    assert '"≣")[index]' not in source
    assert 'toggle_image_toolbar(app)' not in source
    assert 'row=index if extreme else index // 3' in source
    assert 'row=6 + index if extreme else 2' in source
    assert 'column=0 if extreme else index' in source
    assert 'zoom_handle = ttk.Label(' not in app_source
    assert '("➖", lambda: app.zoom(0.87)' in source
    assert '("➕", lambda: app.zoom(1.15)' in source
    assert '("⇔", app.fit_page_width' in source
    assert '("⇳", app.fit_page_height' in source
    assert '("◧", app.fit_single_column_width' in source


def test_compact_layout_has_page_list_under_page_icon_and_no_outer_scroll():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    app_source = (Path(__file__).resolve().parents[1] / "src" /
                  "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert 'simple_slot = ttk.Frame(rail, style="PC.Sidebar.TFrame")' in source
    assert 'row=len(TASK_GROUPS) + 2, column=0, sticky="nsew"' in source
    assert 'slot.grid()' in source and 'slot.grid_remove()' in source
    assert 'self.sidebar_scrollbar.pack(side="right", fill="y")' not in app_source
    assert 'app.sidebar_scrollbar.pack(side="right", fill="y")' not in source
    assert 'self.page_scroll.grid(row=0, column=1, sticky="ns")' in app_source
