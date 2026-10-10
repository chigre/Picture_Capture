"""Regression guards for minimalist icon navigation and the page index."""
from pathlib import Path
from picture_capture.ui import workspace_tools

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def sources():
    return ((ROOT / "app.py").read_text(encoding="utf-8"),
            Path(workspace_tools.__file__).read_text(encoding="utf-8"))


def test_index_page_controls_and_extension_free_display():
    app, tools = sources()
    assert "install_workspace_tools(self, sidebar, sidebar_host)" in app
    assert 'page_panel.grid(row=0, column=0, rowspan=2' in app
    assert '("当前页至指定页", "to_specified")' in app
    assert '("当前页至末页", "to_end")' in app
    assert 'text="指定范围："' in app
    assert 'page.stem, self._page_section_count_text(index)' in app
    assert 'new_values = (bookmark, page_stem, section, lined, fill_status, illustrations)' in app
    assert 'if mode == "to_specified":' in app
    assert 'len(indices) != 1' in app


def test_fixed_width_icon_cells_and_compact_nav_toggle():
    app, tools = sources()
    assert 'entry.columnconfigure(0, minsize=38)' in tools
    assert 'icon = tk.Canvas(entry, width=30, height=27' in tools
    assert 'text_button = ttk.Button(entry, text=label, width=5' in tools
    assert 'rail, 0, "☰", "侧栏", lambda: toggle_sidebar(app)' in tools
    assert 'app.workspace_rail_labels.append(text_button)' in tools
    assert 'button.grid_remove()' in tools
    assert 'button.grid()' in tools
    assert 'app.main_paned.sashpos(0, app.workspace_tools_rail.winfo_reqwidth() + 8)' in tools
    assert 'panes.forget(host)' not in tools
    assert 'sidebar_toggle.place(' not in app
    assert 'app.bind("<Control-Shift-b>"' in tools


def test_page_index_still_collapsible_and_tools_unchanged():
    app, tools = sources()
    assert 'panel.grid_remove()' in tools
    assert 'panel.grid()' in tools
    assert 'canvas.pack_forget()' in tools
    assert 'app._build_quick_settings(content)' in tools
    assert 'popup.place(x=left, y=top, width=width, height=height)' in tools
    assert 'popup.place_forget()' in tools
    assert 'tk.Toplevel(' not in tools
    assert 'grab_set(' not in tools


def test_footer_commands_remain_on_icon_rail():
    _, tools = sources()
    for label, method in (
        ("项目", "open_recent_project"),
        ("档案", "open_project_profile"),
        ("设置", "open_settings"),
        ("帮助", "show_help_dialog"),
    ):
        assert f'("{label}",' in tools
        assert f'app.{method}' in tools
    assert 'app.project_footer_buttons.append(button)' in tools


def test_tt_buttons_never_receive_unsupported_anchor_widget_parameter():
    _, tools = sources()
    assert 'anchor="w", command=' not in tools
    assert 'anchor="w", style=' not in tools
    assert 'relief="flat", borderwidth=0' in tools


def test_index_width_and_treeview_columns_fit_available_space():
    app, tools = sources()
    assert 'self.page_range_controls_row = range_row' in app
    assert 'choices.winfo_reqwidth() + 38' in tools
    assert 'font.nametofont("TkHeadingFont")' in app
    assert 'orient="horizontal", command=self.page_list.xview' in app
    assert 'body_font.measure(name) for name in page_names' in app
    assert '"page": max(52, page_width)' in app
    assert 'self.page_list.column(column, width=width, anchor="center", stretch=False)' in app
    assert '("上页", lambda: self.change_page(-1)' in app
    assert '("下页", lambda: self.change_page(1)' in app


def test_page_name_column_does_not_absorb_all_spare_sidebar_width():
    app, _ = sources()
    assert 'weights = {' not in app[app.index('    def _fit_page_list_columns'):app.index('    def _hide_page_list_section_heading_hint')]
    assert 'page.stem for page in getattr(self.project, "images", ())' in app
    assert 'header_font.measure(label) + 10' in app


def test_borderless_index_and_vector_rail_icon_art():
    app, tools = sources()
    assert 'page_panel = ttk.Frame(sidebar, padding=' in app
    assert '"六、页面列表"' not in app[app.index('def _build_ui'):app.index('def _build_ui') + 26000]
    assert '_draw_rail_icon(icon, symbol)' in tools
    assert 'canvas.create_line(' in tools
    assert 'canvas.create_rectangle(' in tools
    assert 'len(TASK_GROUPS) + 3, "≡", "全部"' in tools
    for column in ('bookmark', 'page', 'section', 'lined', 'fill_status', 'illustrations'):
        assert f'self.page_list.column("{column}",' in app


def test_main_window_has_no_minimum_width_constraint():
    app, _ = sources()
    assert 'fit_window_to_work_area(self, 1440, 900, min_width=1, min_height=680)' in app
    assert 'fit_window_to_work_area(self, 1440, 900, min_width=1080' not in app


def test_canvas_background_is_theme_specific_and_reapplied_on_switch():
    app, _ = sources()
    assert '"canvas": "#e9edf2"' in app
    assert '"canvas": base["canvas"]' in app
    assert 'self._main_ui_colors["canvas"] if name == "canvas" else palette[color_key]' in app


def test_batch_progress_is_inline_with_status_bar_and_hidden_when_idle():
    app, _ = sources()
    assert 'self.batch_bar = ttk.Frame(status_bar, padding=(4, 1)' in app
    assert 'self.batch_bar.pack(side="right", fill="x")' in app
    assert 'self.batch_bar.pack_forget()' in app
    assert 'self.batch_pause_button = ttk.Button(' in app
    assert 'self.batch_stop_button = ttk.Button(' in app
    assert 'maximum=100.0, length=160' in app
