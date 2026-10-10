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
    assert '("当前至指定页", "to_specified")' in app
    assert '("当前至末页", "to_end")' in app
    assert 'text="指定:"' in app
    assert 'page.stem, self._page_section_count_text(index)' in app
    assert 'new_values = (bookmark, page_stem, section, lined, fill_status, illustrations)' in app
    assert 'if mode == "to_specified":' in app
    assert 'len(indices) != 1' in app


def test_fixed_width_icon_cells_and_compact_nav_toggle():
    app, tools = sources()
    assert 'entry.columnconfigure(0, minsize=38)' in tools
    assert 'icon = tk.Canvas(entry, width=30, height=27' in tools
    assert 'text_button = ttk.Button(entry, text=label, width=5' in tools
    assert 'rail, 0, "☰", "模式", lambda: show_sidebar_modes(app)' in tools
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
    assert 'mini_host.grid()' in tools
    assert 'mini_host.grid_remove()' in tools
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
    assert 'min(max(minimum, 1), width - 160)' in tools
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
    assert 'header_font.measure(label) + 6' in app


def test_borderless_index_and_vector_rail_icon_art():
    app, tools = sources()
    assert 'page_panel = ttk.Frame(sidebar, padding=' in app
    assert '"六、页面列表"' not in app[app.index('def _build_ui'):app.index('def _build_ui') + 26000]
    assert '_draw_rail_icon(icon, symbol)' in tools
    assert 'canvas.create_line(' in tools
    assert 'canvas.create_rectangle(' in tools
    assert 'len(TASK_GROUPS) + 2, "▦", "页面"' in tools
    assert 'len(TASK_GROUPS) + 3, "≡", "全部"' not in tools
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


def test_page_headers_and_preferred_sidebar_width():
    app, tools = sources()
    assert '"bookmark": "●"' in app
    assert '"section": "域"' in app
    assert '"lined": "线"' in app
    assert '"illustrations": "图"' in app
    assert 'self.page_list.heading("bookmark", text="●"' in app
    assert 'self.page_list.heading("section", text="域"' in app
    assert 'self.page_list.heading("lined", text="线"' in app
    assert 'self.page_list.heading("illustrations", text="图"' in app
    assert 'min(max(minimum, 1), panes.winfo_width() - 160)' in tools


def test_zoom_toolbar_hover_expands_at_canvas_lower_left():
    app, _ = sources()
    assert 'size_row = ttk.Frame(self.canvas, padding=(5, 4)' in app
    assert 'size_row.place(relx=0, rely=1, x=8, y=-8, anchor="sw")' in app
    assert 'zoom_handle = ttk.Label(size_row, text="≣"' in app
    assert 'self.page_zoom_tools = zoom_tools' in app
    assert 'zoom_tools.pack(side="left", padx=(4, 0))' in app
    assert 'zoom_tools.pack_forget()' in app
    assert 'size_row.after_idle(collapse_zoom_tools)' in app
    assert 'widget.bind("<Enter>", expand_zoom_tools, add="+")' in app
    assert 'widget.bind("<Leave>", schedule_zoom_collapse, add="+")' in app
    assert 'view_zoom_entry.bind("<Return>", self.apply_view_zoom_text)' in app
    assert 'view_zoom_entry.bind("<FocusOut>", self.apply_view_zoom_text)' in app
    assert 'size_row = ttk.Frame(nav_area)' not in app


def test_page_columns_order_and_mandatory_visibility():
    app, _ = sources()
    assert '"bookmark": "●"' in app
    assert '"section": "域"' in app
    assert 'columns = ["bookmark", "page", "lined"]' in app
    assert 'columns.append("illustrations")' in app
    assert 'columns.append("section")' in app
    assert 'columns.append("fill_status")' in app
    assert 'menu.add_checkbutton(label="画线", state="disabled")' in app
    assert 'label="区块", variable=section_var, state="disabled"' in app
    assert '"bookmark": 25' in app
    assert 'borderwidth=1' in app


def test_mini_page_list_below_page_button():
    app, tools = sources()
    assert 'for index, (label, symbol, title) in enumerate(TASK_GROUPS, start=1)' in tools
    assert 'len(TASK_GROUPS) + 2, "▦", "页面"' in tools
    assert 'mini.heading("page", text="页面"' in tools
    assert 'selectmode="browse", height=12' in tools
    assert 'style="PC.CompactPage.Treeview"' in tools
    assert 'def refresh_compact_page_index(app: Any)' in tools
    assert 'source.get_children()' in tools
    assert 'mini.insert("", "end", iid=iid, values=values)' in tools
    assert 'mini.bind("<<TreeviewSelect>>", choose_mini_page)' in tools
    assert 'app.after_idle(lambda: app.page_list.bind(' in tools
    assert 'mini.item(iid, values=new_values)' in app


def test_rail_styles_are_compact_in_both_themes():
    app, tools = sources()
    assert 'style.configure("PC.Rail.TButton", font="TkDefaultFont"' in app
    assert 'style.configure("PC.CompactPage.Treeview", rowheight=26' in app
    assert 'padding=(4, 3), relief="flat", borderwidth=0, font="TkDefaultFont"' in tools


def test_compact_index_has_optional_headers_and_horizontal_scroll():
    app, tools = sources()
    assert 'displaycolumns=("page", "illustrations"), show="headings"' in tools
    assert 'mini_hscroll = ttk.Scrollbar(mini_host, orient="horizontal"' in tools
    assert 'mini.configure(yscrollcommand=mini_scroll.set, xscrollcommand=mini_hscroll.set)' in tools
    assert 'menu.add_checkbutton(label=app.page_index_labels[key]' in tools
    assert 'font=self.compact_page_font' in app
    assert 'round(base_font_size * 0.8)' in app


def test_canvas_right_click_navigation_and_sidebar_presets():
    app, tools = sources()
    assert 'self.canvas.bind("<Shift-Button-3>"' in app
    assert 'def _canvas_shift_right_click(self, event: tk.Event)' in app
    assert 'self.change_page(-1)' in app
    assert '切换到上页（Shift + 鼠标右键）' in app
    assert '切换到下页（鼠标右键）' in app
    assert 'for choice in ("最简", "正常", "最大")' in tools
    assert 'def set_sidebar_mode(app: Any, mode: str)' in tools
    assert 'app.fit_page_height()' in tools
    assert 'app.after(120, app.fit_page_width)' in tools


def test_requested_workspace_updates():
    app, tools = sources()
    assert 'choices.winfo_reqwidth() + 24' in tools
    assert 'value=(key == "illustrations")' in tools
    assert 'width=80 if column == "page" else 26' in tools
    assert 'app.geometry(f"{min(app.winfo_screenwidth(), max(240, required))}x{height}+0+{top}")' in tools
    assert '("普通画线", app.run_normal_draw_action)' in tools
    assert '("OCR画线", app.run_ocr_draw_action)' in tools
    assert '("词条校对", app.open_review)' in tools
    assert '("◧", self.fit_single_column_width, "单栏占满宽度")' in app
    assert 'def fit_single_column_width(self) -> None:' in app


def test_compact_mode_does_not_reuse_full_sidebar_sash_width():
    _, tools = sources()
    assert 'rail, 0, "☰", "模式", lambda: show_sidebar_modes(app)' in tools
    assert 'if tip:' in tools
    assert 'compact_width = app.workspace_tools_rail.winfo_reqwidth() + 10' in tools
    assert 'app.main_paned.sashpos(0, compact_width)' in tools
    assert 'required = int(compact_width + app.image.width * app.view_scale + 32)' in tools
    assert 'app.after_idle(lambda: app.main_paned.sashpos(0, compact_width))' in tools


def test_single_column_fit_includes_two_gutters():
    app, _ = sources()
    assert 'gutter = float(self.settings.gutter)' in app
    assert 'fit_width = column_width + 2 * gutter' in app
    assert 'available / fit_width' in app


def test_compact_review_uses_remaining_screen_and_scrolls_main_canvas():
    app, _ = sources()
    review = (ROOT / "ui" / "controllers" / "review.py").read_text(encoding="utf-8")
    assert 'mini.winfo_manager() == "grid"' in app
    assert 'x = max(0, parent.winfo_rootx() + parent.winfo_width())' in app
    assert 'work_x, work_y, work_w, work_h = _screen_work_area(self)' in app
    assert 'width = max(1, work_right - x)' in app
    assert 'height = max(1, work_bottom - y)' in app
    assert 'def _scroll_review_entry_into_view(self, entry: WordEntry)' in app
    assert '_review_line_box(' in app
    assert 'canvas.xview_moveto(' in app
    assert 'canvas.yview_moveto(' in app
    assert 'app._scroll_review_entry_into_view(entry)' in review


def test_current_review_crop_is_fixed_width_double_height_and_framed():
    app, _ = sources()
    assert 'self.active_crop_frame = tk.Frame(editor_area, bd=2, relief="solid"' in app
    assert 'self.active_crop_frame.place(x=6, y=4, anchor="nw")' in app
    assert 'self._review_display_crops = list(preloaded_crops)' in app
    assert 'def _update_active_crop_preview(self, index: int)' in app
    assert 'self._active_crop_fixed_size = (crop.width, 2 * crop.height)' in app
    assert 'preview = extended.resize(self._active_crop_fixed_size, Image.Resampling.LANCZOS)' in app
    assert 'self._update_active_crop_preview(index)' in app


def test_active_review_row_does_not_repeat_pinned_crop():
    app, _ = sources()
    assert 'if index != 0:' in app
    assert 'self._review_row_pictures.append(picture)' in app
    assert 'if row_index == index:' in app
    assert 'picture.destroy()' in app
    assert 'restored = ttk.Label(self.rows, image=photo' in app


def test_review_preview_is_position_and_size_invariant_on_window_resize():
    app, _ = sources()
    assert 'self.active_crop_host.pack_propagate(False)' in app
    assert 'self.active_crop_frame.place(x=6, y=4, anchor="nw")' in app
    assert 'self._active_crop_fixed_size: tuple[int, int] | None = None' in app
    assert 'if self._active_crop_fixed_size is None:' in app
    assert 'self.active_crop_host.configure(height=self._active_crop_fixed_size[1] + 14)' in app


def test_next_page_button_is_packed_before_expandable_editor_area():
    app, _ = sources()
    left = app.index('self.prev_page_button.pack(side="left", fill="y"')
    right = app.index('self.next_page_button.pack(side="right", fill="y"')
    editor = app.index('editor_area.pack(side="left", fill="both", expand=True)', left)
    assert left < right < editor


def test_active_crop_is_never_materialized_as_inline_image():
    app, _ = sources()
    assert 'picture = None' in app
    assert 'if index != 0:' in app
    assert 'self.thumbnails.append(photo)' in app
    assert 'self._review_row_pictures[row_index] = None' in app
    assert 'self.thumbnails[row_index] = None' in app
