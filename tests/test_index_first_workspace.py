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
    assert '("至指定", "to_specified")' in app
    assert '("至末页", "to_end")' in app
    assert 'text="指定:"' not in app
    assert 'page.stem, self._page_section_count_text(index)' in app
    assert 'new_values = (bookmark, page_stem, section, lined, fill_status, illustrations)' in app
    assert 'if mode == "to_specified":' in app
    assert 'len(indices) != 1' in app


def test_fixed_width_icon_cells_and_compact_nav_toggle():
    app, tools = sources()
    assert 'entry.columnconfigure(0, minsize=36)' in tools
    assert 'icon = tk.Canvas(entry, width=30, height=27' in tools
    assert 'text_button = tk.Button(' in tools
    assert 'font="TkDefaultFont", anchor="center", justify="center"' in tools
    assert 'relief="flat", bd=0, highlightthickness=0, padx=0, pady=0' in tools
    assert 'rail, 0, "☰", "工具菜单"' not in tools
    assert 'app.workspace_rail_labels.append(text_button)' in tools
    assert 'label.grid_remove()' in tools
    assert 'label.grid()' in tools
    assert 'return rail_width + RAIL_DIVIDER_WIDTH' in tools
    assert 'panes.forget(host)' not in tools
    assert 'sidebar_toggle.place(' not in app
    assert 'app.bind("<Control-Shift-b>"' not in tools
    assert 'def toggle_page_index(' not in tools
    assert 'def toggle_sidebar(' not in tools


def test_page_index_visibility_is_mode_only_and_tools_unchanged():
    app, tools = sources()
    assert 'app.page_panel.grid_remove()' in tools
    assert 'app.page_panel.grid()' in tools
    assert 'app.sidebar_canvas.pack_forget()' in tools
    assert 'simple_slot = ttk.Frame(' in tools
    assert '_set_simple_page_visible(app, compact)' in tools
    assert 'initialize_quick_state(app)' in tools
    assert 'popup.place(x=left, y=top, width=width, height=height)' in tools
    assert 'popup.place_forget()' in tools
    assert 'tk.Toplevel(' not in tools
    assert 'grab_set(' not in tools


def test_project_commands_move_into_shared_top_row():
    _, tools = sources()
    for label, method in (
        ("项目", "open_recent_project"),
        ("Profile", "open_project_profile"),
        ("设置", "open_settings"),
        ("帮助", "show_help_dialog"),
    ):
        assert f'("{label}",' in tools
        assert f'app.{method}' in tools
    assert 'app.project_footer_buttons.append(button)' in tools
    assert 'project_group.pack(side="left", padx=(2, 0))' in tools
    assert 'app.project_action_bar = project_group' in tools
    assert 'rail_action(footer, index, symbol, label' not in tools


def test_tt_buttons_never_receive_unsupported_anchor_widget_parameter():
    _, tools = sources()
    assert 'anchor="w", command=' not in tools
    assert 'anchor="w", style=' not in tools
    assert 'relief="flat"' in tools
    assert 'borderwidth=0, font="TkDefaultFont"' in tools


def test_index_width_and_treeview_columns_fit_available_space():
    app, tools = sources()
    assert 'self.page_range_controls_row = range_row' in app
    assert 'min(preferred_sidebar_width(app), width - 160)' in tools
    assert 'font.nametofont("TkHeadingFont")' in app
    assert 'orient="horizontal", command=self._page_list_hscroll' in app
    horizontal_handler = app[
        app.index('    def _page_list_hscroll('):
        app.index('    def _page_list_yscroll(', app.index('    def _page_list_hscroll('))
    ]
    assert 'self.page_list.xview(*args)' in horizontal_handler
    assert 'self._schedule_page_cell_overlay_refresh()' in horizontal_handler
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
    assert 'workspace_page_index_button' not in tools
    assert 'def toggle_page_index(' not in tools
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
    assert 'min(preferred_sidebar_width(app), width - 160)' in tools


def test_inline_zoom_is_visible_in_normal_and_compact_without_old_launcher():
    app, tools = sources()
    assert 'self.page_size_row = size_row' in app
    assert 'self.page_zoom_tools = zoom_tools' in app
    assert 'zoom_handle = ttk.Label(size_row, text="≣"' not in app
    assert '("普", "O", "校")[index]' in tools
    assert 'toggle_image_toolbar(app)' not in tools
    assert '("➖", lambda: app.zoom(0.87)' in tools
    assert '("➕", lambda: app.zoom(1.15)' in tools
    assert '("⇔", app.fit_page_width' in tools
    assert '("⇳", app.fit_page_height' in tools
    assert '("◧", app.fit_single_column_width' in tools
    assert 'style.configure("PC.WorkspaceZoom.TEntry", font=small' in tools
    assert 'view_zoom_entry.bind("<Return>", self.apply_view_zoom_text)' in app



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


def test_mini_page_list_below_task_icons():
    app, tools = sources()
    assert 'for index, (label, symbol, title) in enumerate(TASK_GROUPS)' in tools
    assert 'workspace_page_index_button' not in tools
    assert 'row=len(TASK_GROUPS) + 2, column=0, sticky="nsew"' in tools
    assert 'mini.heading(column, text=app.page_index_labels[column]' in tools
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
    assert 'style.configure("PC.CompactPage.Treeview", rowheight=22' in app
    assert 'padding=(0, 0), relief="flat"' in tools
    assert 'style.configure("PC.QuickRail.TButton", font="TkDefaultFont"' in app


def test_compact_index_has_optional_headers_and_horizontal_scroll():
    app, tools = sources()
    assert 'displaycolumns=("page", "lined", "illustrations")' in tools
    assert 'mini_hscroll = ttk.Scrollbar(mini_host, orient="horizontal"' in tools
    assert 'mini.configure(yscrollcommand=mini_scroll.set, xscrollcommand=mini_hscroll.set)' in tools
    assert 'menu.add_checkbutton(label=app.page_index_labels[key]' in tools
    assert 'font=self.compact_page_font' in app
    assert 'self.compact_page_font = default_page_font.copy()' in app
    assert "round(base_size * 0.9)" in app


def test_canvas_right_click_navigation_and_sidebar_presets():
    app, tools = sources()
    assert 'self.canvas.bind("<Shift-Button-3>"' in app
    assert 'def _canvas_shift_right_click(self, event: tk.Event)' in app
    assert 'self.change_page(-1)' in app
    assert '切换到上页（Shift + 鼠标右键）' in app
    assert '切换到下页（鼠标右键）' in app
    assert 'for caption in ("极简", "紧凑", "正常", "最大")' in tools
    assert 'def set_sidebar_mode(app: Any, mode: str)' in tools
    assert 'app.fit_page_height()' in tools
    assert 'app.after(120, app.fit_page_width)' in tools


def test_requested_workspace_updates():
    app, tools = sources()
    assert 'DEFAULT_PAGE_LIST_WIDTH = 260' in tools
    assert 'value=(key in {"lined", "illustrations"})' in tools
    assert 'size_compact_page_columns(app)' in tools
    assert 'max(required_header_width(app), required)' in tools
    assert 'enforce_header_min_width(app)' in tools
    assert '("普通画线", app.run_normal_draw_action)' in tools
    assert '("OCR画线", app.run_ocr_draw_action)' in tools
    assert '("词条校对", app.open_review)' in tools
    assert '("◧", self.fit_single_column_width, "单栏占满宽度")' in app
    assert 'def fit_single_column_width(self) -> None:' in app


def test_compact_mode_does_not_reuse_full_sidebar_sash_width():
    _, tools = sources()
    assert 'rail, 0, "☰", "工具菜单"' not in tools
    assert 'if tip:' in tools
    assert 'compact_width = preferred_sidebar_width(' in tools
    assert 'compact=(mode == "紧凑")' in tools
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
    assert 'getattr(parent, "workspace_mode", "") in {"极简", "紧凑"}' in app
    assert 'if compact_workspace:' in app
    assert 'x = max(0, parent.winfo_rootx() + parent.winfo_width())' in app
    assert 'work_x, work_y, work_w, safe_client_height = _preset_work_geometry(parent)' in app
    assert 'width = max(1, work_right - x)' in app
    assert 'height = max(1, safe_client_height)' in app
    assert 'def _scroll_review_entry_into_view(self, entry: WordEntry)' in app
    assert '_review_line_box(' in app
    assert 'canvas.xview_moveto(' in app
    assert 'canvas.yview_moveto(' in app
    assert 'app._scroll_review_entry_into_view(entry)' in review


def test_current_review_crop_is_fixed_width_double_height_and_framed():
    app, _ = sources()
    assert 'self.active_crop_frame = tk.Frame(self.active_crop_host, bd=2, relief="solid"' in app
    assert 'self.active_crop_frame.place(x=6, y=4, anchor="nw")' in app
    assert 'self._review_display_crops = list(preloaded_crops)' in app
    assert 'def _update_active_crop_preview(self, index: int)' in app
    assert 'crop.width, max(1, round(multiplier * crop.height))' in app
    assert 'extended_review_crop_box(' in app
    assert 'center_y - half_height' not in app
    assert 'preview = extended.resize(self._active_crop_fixed_size, Image.Resampling.LANCZOS)' in app
    assert 'self._update_active_crop_preview(index)' in app


def test_current_review_entry_keeps_ordinary_row_and_pinned_crop():
    app, _ = sources()
    assert 'photo = self._ordinary_review_photo(index)' in app
    assert 'self._review_row_pictures.append(picture)' in app
    assert 'self._update_active_crop_preview(index)' in app
    active = app[app.index('    def set_active(self, index: int)'):]
    active = active[:active.index('    def _scroll_editor_into_view')]
    assert 'picture.destroy()' not in active
    assert 'picture.grid_remove()' not in active


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




def test_compact_review_anchors_to_work_area_top():
    app, _ = sources()
    assert 'y = work_y  # Align compact proofreading to the usable desktop top.' in app
    assert 'height = max(1, safe_client_height)' in app


def test_inline_review_slice_uses_text_based_height_without_classification():
    app, _ = sources()
    assert '_focused_review_is_single_character(displayed_text)' in app
    assert 'classified_entry_crop_height(' not in app
    assert 'entry, geometry, image, review_settings, next_entry,' in app
    assert 'editor_text=editor_texts[index]' in app
    assert 'ordinary_height_only=True' not in app
    assert 'themed_display_image(crop, self.parent.appearance_mode)' in app
    assert 'self._update_active_crop_preview(index)' in app


def test_workspace_mode_is_restored_from_last_session():
    app, tools = sources()
    session = (ROOT / "ui" / "controllers" / "session.py").read_text(encoding="utf-8")
    assert '"workspace_mode": getattr(app, "workspace_mode", "最大")' in session
    assert 'stored_mode = self._last_session.get("workspace_mode", "最大")' in app
    assert 'self._restore_workspace_mode_pending = True' in app
    assert 'self._restore_workspace_layout()' in app
    assert 'set_sidebar_mode(self, self.workspace_mode)' in app
    assert 'app.workspace_mode = mode' in tools
    assert 'app._restore_workspace_layout()' in session


def test_pinned_preview_and_every_inline_crop_coexist():
    app, _ = sources()
    start = app.index('    def render_rows(self, preloaded_crops:')
    end = app.index('    def _ordinary_review_photo(', start)
    render = app[start:end]
    assert 'photo = self._ordinary_review_photo(index)' in render
    # Every inline crop is still resident; its child label now shares one
    # disposable row with the lower-aligned main-style sequence badge.
    assert 'picture, sequence_label, crop_row = create_review_crop_with_index(' in render
    assert 'self, self.rows, photo=photo, index=index, total=len(ordered)' in render
    assert 'self._review_row_pictures.append(picture)' in render
    assert 'if index != 0:' not in render
    active = app[app.index('    def set_active(self, index: int)'):]
    active = active[:active.index('    def _scroll_editor_into_view')]
    assert 'self._update_active_crop_preview(index)' in active
    assert 'picture.destroy()' not in active
    assert 'picture.grid_remove()' not in active


def test_each_tool_menu_is_280px_and_vertically_scrollable():
    _, tools = sources()
    assert "TOOL_MENU_WIDTH = 280" in tools
    assert "width = min(TOOL_MENU_WIDTH, max(1, root_width - 12))" in tools
    assert "canvas.itemconfigure(item, width=max(1, event.width))" in tools
    assert "horizontal = ttk.Scrollbar(scroller" not in tools
    assert "initialize_quick_state(app)" in tools
    assert "sections: dict[str, ttk.Frame] = {}" in tools
    assert 'app.bind_all("<MouseWheel>", scroll_menu_wheel, add="+")' in tools
    assert "popup.place(x=left, y=top, width=width, height=height)" in tools


def test_legacy_builder_and_reflow_are_gone_from_compact_menus():
    _, tools = sources()
    assert "_stack_tool_menu_controls" not in tools
    assert "def retire_superseded_quick_panels(" not in tools
    assert "app._build_quick_settings(" not in tools
    assert 'sections["五、后期词典制作"] = build_postproduction_menu(app, content)' in tools


def test_extreme_mode_icons_and_abbreviated_run_actions():
    _, tools = sources()
    assert '("极简", "紧凑", "正常", "最大")' in tools
    assert 'if mode in {"最简", "简单"}:' in tools
    assert '"极简" if' not in tools  # Mode checks use concrete preset values.
    for value in ("版面参数", "显示参数", "OCR参数", "画线…", "后期制作",
                  "项目", "Profile", "设置", "帮助"):
        assert f'"{value}"' in tools
    assert '("上", -1), ("下", 1)' in tools
    assert 'app.workspace_extreme_page_navigation = extreme_nav' in tools
    assert 'command=lambda direction=delta: app.change_page(direction)' in tools
    assert '("普", "O", "校")' in tools


def test_extreme_zoom_is_vertical_and_compact_is_three_rows(monkeypatch):
    from types import SimpleNamespace

    class Widget:
        def __init__(self):
            self.visible = True
            self.values = {}
            self.position = None
            self.columns = []

        def grid(self, **values):
            self.visible = True
            self.position = values

        def grid_remove(self):
            self.visible = False

        def grid_configure(self, **values):
            self.position = values

        def configure(self, **values):
            self.values.update(values)

        def columnconfigure(self, column, **options):
            self.columns.append((column, options))

        def winfo_manager(self):
            return "" if not self.visible else "grid"

    labels = [Widget() for _ in range(9)]
    rows = [Widget() for _ in range(9)]
    nav = Widget()
    quick = [Widget() for _ in range(3)]
    zoom = [Widget() for _ in range(6)]
    host = Widget()
    monkeypatch.setattr(workspace_tools, "_apply_compact_sidebar_font",
                        lambda _app, _compact: None)
    app = SimpleNamespace(
        workspace_rail_labels=labels,
        workspace_rail_rows=rows,
        workspace_rail_width=120,
        workspace_tools_rail=Widget(),
        workspace_extreme_page_navigation=nav,
        workspace_quick_action_buttons=quick,
        workspace_quick_zoom_controls=zoom,
        workspace_quick_actions_host=host,
        workspace_sidebar_visible=True,
        page_size_row=None,
    )
    workspace_tools._apply_preset_rail_controls(app, "极简")
    assert nav.visible
    assert not any(label.visible for label in labels)
    assert all(row.values["width"] == 36 for row in rows)
    assert [w.values["text"] for w in quick] == ["普", "O", "校"]
    assert [w.position["row"] for w in zoom] == [0, 1, 2, 3, 4, 5]
    assert [w.position["column"] for w in zoom] == [0] * 6
    assert [w.position["row"] for w in quick[:3]] == [6, 7, 8]
    assert len(quick) == 3

    workspace_tools._apply_preset_rail_controls(app, "紧凑")
    assert not nav.visible
    assert all(label.visible for label in labels)
    assert all(row.values["width"] == 120 for row in rows)
    assert [w.position["row"] for w in zoom] == [0, 0, 0, 1, 1, 1]
    assert [w.position["column"] for w in zoom] == [0, 1, 2, 0, 1, 2]
    assert [w.position["row"] for w in quick[:3]] == [2, 2, 2]
    assert [w.position["column"] for w in quick[:3]] == [0, 1, 2]
    assert len(quick) == 3

    workspace_tools._apply_preset_rail_controls(app, "正常")
    assert all(w.visible for w in zoom)
    assert all(w.visible for w in quick)
    assert [w.position["row"] for w in zoom] == [0, 0, 0, 1, 1, 1]
    assert [w.position["column"] for w in zoom] == [0, 1, 2, 0, 1, 2]
    assert [w.position["row"] for w in quick] == [2, 2, 2]
    assert [w.position["column"] for w in quick] == [0, 1, 2]


def test_extreme_simple_normal_modes_have_independent_page_list_visibility(monkeypatch):
    from types import SimpleNamespace

    class Panel:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def winfo_manager(self):
            return self.manager

        def pack_forget(self):
            self.manager = ""
            self.calls.append("pack_forget")

        def pack(self, **_kwargs):
            self.manager = "pack"
            self.calls.append("pack")

        def grid_remove(self):
            self.manager = ""
            self.calls.append("grid_remove")

        def grid(self):
            self.manager = "grid"
            self.calls.append("grid")

    class Panes:
        def sashpos(self, *_args):
            return 175

    canvas = Panel("pack")
    scroller = Panel("pack")
    mini = Panel("")
    full_panel = Panel("grid")
    app = SimpleNamespace(
        sidebar_canvas=canvas,
        sidebar_scrollbar=scroller,
        workspace_mini_page_slot=mini,
        workspace_tools_rail=Panel("pack"),
        page_panel=full_panel,
        main_paned=Panes(),
    )
    refreshes = []
    monkeypatch.setattr(workspace_tools, "refresh_compact_page_index",
                        lambda _app: refreshes.append(True))
    workspace_tools._apply_preset_page_index(app, "极简")
    assert canvas.manager == "" and mini.manager == "" and full_panel.manager == ""
    workspace_tools._apply_preset_page_index(app, "紧凑")
    assert mini.manager == "grid" and canvas.manager == ""
    assert len(refreshes) == 1
    workspace_tools._apply_preset_page_index(app, "正常")
    assert mini.manager == "" and canvas.manager == "pack" and full_panel.manager == "grid"


def test_review_pinned_crop_2_5x_and_compact_font_captions():
    app, _ = sources()
    start = app.index("    def _update_active_crop_preview(self, index: int)")
    end = app.index("    def _ordinary_review_photo(", start)
    pinned = app[start:end]
    assert "extended_review_crop_box(" in pinned
    assert "round(multiplier * crop.height)" in pinned
    assert "center_y - half_height" not in pinned
    assert 'editor_text=self.vars[index].get()' in pinned

    start = app.index("        font_row = ttk.Frame(review_info, style=")
    end = app.index("        digit_box = self._review_collapsible_section(", start)
    review_font_controls = app[start:end]
    assert 'text="字号："' not in review_font_controls
    assert 'text="粗体"' not in review_font_controls
    assert 'text="斜体"' not in review_font_controls
    assert 'text="粗"' in review_font_controls
    assert 'text="斜"' in review_font_controls


def test_saved_legacy_simple_mode_migrates_to_new_name():
    app, _ = sources()
    assert '"紧凑" if stored_mode in {"最简", "简单"} else stored_mode' in app
    assert 'stored_mode in {"极简", "紧凑", "正常", "最大"}' in app
