"""Regression checks for renamed compact mode and directly accessible zoom."""
from pathlib import Path

from picture_capture.ui import workspace_tools

MODULE = Path(workspace_tools.__file__)
APP = MODULE.parents[1] / "app.py"


def test_modes_and_saved_session_migrate_to_compact():
    tools = MODULE.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    assert 'for caption in ("极简", "紧凑", "正常")' in tools
    assert 'if mode in {"最简", "简单"}:' in tools
    assert 'mode = "紧凑"' in tools
    assert '"紧凑" if stored_mode in {"最简", "简单"} else stored_mode' in app
    assert 'getattr(parent, "workspace_mode", "") in {"极简", "紧凑"}' in app


def test_compact_index_precedes_rail_at_same_independent_width():
    source = MODULE.read_text(encoding="utf-8")
    assert 'simple_slot = ttk.Frame(rail, style="PC.Sidebar.TFrame")' in source
    assert 'app.workspace_rail_width = DEFAULT_RAIL_WIDTH' in source
    assert 'app.workspace_page_list_width = DEFAULT_PAGE_LIST_WIDTH' in source
    assert 'compact = mode == "紧凑"' in source
    assert "int(app.workspace_rail_width) + RAIL_DIVIDER_WIDTH" in source


def test_compact_font_uses_eighty_percent_only_within_sidebar():
    source = MODULE.read_text(encoding="utf-8")
    assert 'round(original * 0.8)' in source
    assert 'style.configure("PC.Workspace80.Treeview", font=small, rowheight=19)' in source
    assert 'style.configure("PC.Workspace80.Treeview.Heading", font=small' in source
    assert 'widget.configure(font=_compact_font(app) if compact else "TkDefaultFont")' in source
    assert '_apply_compact_sidebar_font(app, mode == "紧凑")' in source
    assert 'app.after_idle(finish_compact_page_controls)' in source
    assert 'getattr(app, "workspace_mode", "") == "紧凑"' in source
    assert 'style=app.workspace_compact_font' not in source


def test_extreme_and_compact_zoom_actions_are_single_shared_value():
    source = MODULE.read_text(encoding="utf-8")
    assert 'app.after_idle(lambda: install_compact_zoom_controls(app))' in source
    for symbol, call in (
        ("➖", "app.zoom(0.87)"),
        ("➕", "app.zoom(1.15)"),
        ("⇔", "app.fit_page_width"),
        ("⇳", "app.fit_page_height"),
        ("◧", "app.fit_single_column_width"),
    ):
        assert f'("{symbol}",' in source
        assert call in source
    assert 'host, textvariable=app.view_zoom_var, width=4' in source
    assert 'widget.configure(font=_compact_font(app) if compact else "TkDefaultFont")' in source
    assert 'widget.bind("<Return>", app.apply_view_zoom_text)' in source
    assert 'widget.bind("<FocusOut>", app.apply_view_zoom_text)' in source
    assert "row=index if extreme else index // 3" in source
    assert "column=0 if extreme else index % 3" in source
    assert 'row=6 + index if extreme else 2' in source
    assert 'row=index if extreme else index // 3' in source
    assert 'canvas_zoom.place_forget()' in source
