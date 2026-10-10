"""Minimal icon navigation and overlay palette regression guards."""
from pathlib import Path
from picture_capture.ui import workspace_tools


def test_index_and_fixed_project_actions_survive_layout_change():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    assert "install_workspace_tools(self, sidebar, sidebar_host)" in app
    assert 'sidebar.columnconfigure(0, weight=1)' in app
    assert 'page_panel.grid(row=0, column=0, rowspan=2' in app
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'rail.pack(side="left", fill="y", before=app.sidebar_canvas' in source
    assert 'app.project_action_bar = footer' in source
    for action in ("项目", "档案", "设置", "帮助"):
        assert f'("{action}",' in source


def test_icon_rail_popover_does_not_change_main_pane():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'rail.pack(side="left", fill="y"' in source
    assert 'popup = ttk.Frame(app,' in source
    assert 'popup.place(x=left, y=top, width=width, height=height)' in source
    assert "popup.place_forget()" in source
    assert "app._build_quick_settings(content)" in source
    assert "panes.add(" not in source
    assert "tk.Toplevel(" not in source
    assert "grab_set(" not in source


def test_minimal_task_buttons_and_pin_behavior():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert "for index, (label, symbol, title) in enumerate(TASK_GROUPS, start=1):" in source
    assert "app._attach_tooltip(button, label)" in source
    assert "title == app.workspace_tools_active" in source
    assert "app.workspace_tools_pinned" in source
    assert 'app.bind_all("<Button-1>", dismiss_outside, add="+")' in source
    assert 'popup.bind("<Escape>"' in source
    assert 'app.bind("<Control-Shift-t>"' in source
    assert 'orient="horizontal", command=canvas.xview' in source


def test_page_index_is_visible_by_default_and_toggled_from_icon_rail():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'page_panel.grid(row=0, column=0, rowspan=2' in app
    assert 'command=lambda: toggle_page_index(app)' in source
    assert 'panel.grid_remove()' in source
    assert 'panel.grid()' in source
    assert 'enumerate(TASK_GROUPS, start=1)' in source
    assert '("上页", lambda: self.change_page(-1)' in app
    assert '("下页", lambda: self.change_page(1)' in app
    assert 'text="上一页"' not in app
    assert 'text="下一页"' not in app


def test_four_project_icons_remain_fixed_below_tool_icons():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'rail.rowconfigure(footer_row - 1, weight=1)' in source
    assert 'footer.grid(row=footer_row, column=0, sticky="sew"' in source
    assert 'app.project_footer_buttons.append(button)' in source
    assert 'app._attach_tooltip(button, f"{label}：{tip}")' in source
    assert 'command=command' in source


def test_page_index_controls_have_four_distinct_rows_and_range_modes():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    source = (root / "app.py").read_text(encoding="utf-8")
    assert '("当前页至指定页", "to_specified")' in source
    assert '("当前页至末页", "to_end")' in source
    assert 'value="specified"' in source
    assert 'spec_row.pack(fill="x"' in source
    assert 'size_row.pack(fill="x"' in source
    assert 'nav_row.pack(fill="x")' in source
    assert '("⇔", self.fit_page_width, "占满宽度")' in source
    assert '("⇕", self.fit_page_height, "占满高度")' in source
    assert 'if mode == "to_specified":' in source
    assert 'len(indices) != 1' in source


def test_index_collapse_releases_actual_pane_width_and_labels_are_visible():
    src = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'canvas.pack_forget()' in src
    assert 'scrollbar.pack_forget()' in src
    assert 'panes.sashpos(0, rail.winfo_reqwidth() + 10)' in src
    assert 'panes.sashpos(0, min(int(desired)' in src
    assert 'text=f"{symbol} {label}"' in src
    assert 'text="▦ 页面"' in src


def test_visible_heading_width_adapts_to_header_text():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    src = (root / "app.py").read_text(encoding="utf-8")
    assert 'font.nametofont("TkHeadingFont")' in src
    assert 'self._page_list_heading_labels.get(column, column)' in src


def test_index_uses_range_control_width_and_table_can_scroll():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    src = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'self.page_range_controls_row = range_row' in app
    assert 'choices.winfo_reqwidth() + 38' in src
    assert 'app.after_idle(lambda: size_page_index_to_controls(app))' in src
    assert 'orient="horizontal", command=self.page_list.xview' in app
    assert 'if available <= base_total:' in app
    assert 'widths = minimum[:]' in app


def test_page_index_omits_filename_extension_and_rail_is_left_aligned():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app_source = (root / "app.py").read_text(encoding="utf-8")
    ui_source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'page.stem, self._page_section_count_text(index)' in app_source
    assert 'page.name, self._page_section_count_text(index)' not in app_source
    assert 'ttk.Style(app).configure("PC.Rail.TButton", anchor="w")' in ui_source
    assert 'text="▦ 页面", width=8, style="PC.Rail.TButton"' in ui_source
    assert 'text=f"{symbol} {label}", width=8, style="PC.Rail.TButton"' in ui_source
    assert 'text="☰ 全部", width=8, style="PC.Rail.TButton"' in ui_source
    assert 'width=8, anchor="w"' not in ui_source


def test_rail_buttons_do_not_pass_invalid_anchor_widget_option():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'anchor="w", style="PC.Rail.TButton"' not in source
    assert 'anchor="w", command=command' not in source


def test_page_names_stay_extension_free_on_metadata_updates():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    source = (root / "app.py").read_text(encoding="utf-8")
    assert 'page.stem, self._page_section_count_text(index)' in source
    assert 'new_values = (bookmark, page_stem, section, lined, fill_status, illustrations)' in source
    assert 'text="指定范围：" ' not in source
    assert 'text="指定范围："' in source


def test_flat_sidebar_navigation_and_full_sidebar_toggle():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    source = (root / "app.py").read_text(encoding="utf-8")
    rail = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'relief="flat", borderwidth=0' in rail
    assert 'padding=(10, 9)' in rail
    assert 'panes.forget(host)' in rail
    assert 'panes.insert(0, host, weight=0)' in rail
    assert 'app.bind("<Control-Shift-b>"' in rail
    assert 'command=lambda: toggle_sidebar(self)' in source
    assert '"显示/隐藏侧边栏（Ctrl+Shift+B）"' in source
