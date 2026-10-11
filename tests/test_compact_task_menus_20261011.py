"""Regression guard for compact task menus, draggable rail and scrollbars.

No GUI display server is required; these protect the explicit widget hierarchy
and re-used command/variable identities when the large legacy UI is refactored.
"""
from pathlib import Path

from picture_capture.ui import compact_task_menus, workspace_tools

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def source(module):
    return Path(module.__file__).read_text(encoding="utf-8")


def test_draggable_140px_icon_column_and_vertical_divider():
    text = source(workspace_tools)
    assert "app.workspace_rail_width = DEFAULT_RAIL_WIDTH" in text
    assert 'style="PC.Sidebar.TFrame", width=DEFAULT_RAIL_WIDTH' in text
    assert "rail.pack_propagate(False)" in text
    assert 'cursor="sb_h_double_arrow"' in text
    assert 'ttk.Separator(divider, orient="vertical")' in text
    assert 'divider.bind("<ButtonPress-1>", start_drag)' in text
    assert 'divider.bind("<B1-Motion>", update_drag)' in text
    assert "max(80, min(340, proposed))" in text
    assert 'entry.configure(width=36 if extreme else app.workspace_rail_width)' in text
    assert 'drag["sash"] + proposed - drag["width"]' in text


def test_scrollbar_is_allocated_only_for_overflow():
    text = source(workspace_tools)
    assert 'needs_scroll = content.winfo_reqheight() > max(1, canvas.winfo_height())' in text
    assert 'if needs_scroll and scrollbar.winfo_manager() != "pack":' in text
    assert 'elif not needs_scroll and scrollbar.winfo_manager() == "pack":' in text
    assert "scrollbar.pack_forget()" in text
    assert "app.workspace_tools_scrollbar_refresh = refresh_scrollbar" in text
    assert "app.workspace_tools_scrollbar_refresh()" in text


def test_preprocess_panel_preserves_all_settings_and_action_connections():
    text = source(compact_task_menus)
    assert 'app.preprocess_mode_button = _button(_row(panel), "进入预处理模式"' in text
    assert 'app.preprocess_auto_deskew_var' in text
    assert 'app.preprocess_safety_var' in text
    assert 'app.preprocess_geometry_var' in text
    assert '"手动四角", app.edit_preprocess_corners' in text
    assert '"重置四角", app.reset_preprocess_corners' in text
    assert '"分析诊断", app.analyze_preprocess_selected' in text
    assert '"诊断信息", app.show_preprocess_diagnostics' in text
    assert '"上一需检", lambda: app.jump_preprocess_review(-1)' in text
    assert '"下一需检", lambda: app.jump_preprocess_review(1)' in text
    for field in (
        "preprocess_export_canvas_var", "preprocess_export_canvas_mode_var",
        "preprocess_export_canvas_width_var", "preprocess_export_canvas_height_var",
        "preprocess_export_margin_top_var", "preprocess_export_margin_bottom_var",
        "preprocess_export_margin_left_var", "preprocess_export_margin_right_var",
        "preprocess_export_align_x_var", "preprocess_export_align_y_var",
    ):
        assert f"app.{field}" in text
    assert 'app.export_preprocess_previews' in text
    assert 'app.export_preprocess_images' in text
    assert 'app.promote_preprocessed_working_images' in text


def test_layout_percent_and_pixel_fields_use_shared_traces():
    from picture_capture.ui import compact_layout_profile_menu

    text = source(compact_layout_profile_menu)
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    for name in ("columns", "start_y", "manual_x", "column_width", "gutter",
                 "character_height", "row_padding", "body_indent", "horizontal_tolerance"):
        assert f'"{name}"' in text
    assert 'add_field(normal, field_row, 0, caption, name, float)' in app
    assert "app.quick_pixel_vars[name]" in text
    assert 'app.quick_bool_vars["ordinary_auto_layout"] = master' in text
    assert 'return build_layout_profile_menu(app, parent)' in source(compact_task_menus)


def test_ocr_and_drawing_panels_keep_existing_handlers_in_requested_order():
    text = source(compact_task_menus)
    ocr = text.split("def build_ocr_menu(", 1)[1].split("ACTION_GROUPS =", 1)[0]
    assert '"使用有效缓存（推荐）"' in ocr
    assert '"重新OCR（模型/图像改变时）"' in ocr
    for name in ("ocr_language", "paddle_band_width_ratio", "paddle_left_tolerance",
                 "paddle_use_paddleocr", "paddle_compare_tesseract",
                 "paddle_enable_lens", "paddle_separator_safety_px"):
        assert f'"{name}"' in ocr
    assert 'app.check_ocr_engines' in ocr
    assert 'initial_tab="ocr"' in ocr
    actions = text.split("ACTION_GROUPS =", 1)[1]
    method_order = (
        "run_normal_draw_action", "ocr_ordinary_lines_text_selected_scope",
        "run_combined_draw_action", "run_ocr_draw_action",
        "clear_entries", "clear_text", "refine_lines_selected_scope",
        "save_current_page", "open_review", "select_existing_headwords_file",
        "compare_old_new_selected_scope", "fill_existing_headwords",
        "repair_pdic_order_selected_scope", "backup_pdic",
        "restore_from_pdic_backup", "detect_illustrations_selected_scope",
        "toggle_polygon_drawing", "cleanup_paddleocr_temp_selected_scope",
    )
    positions = [actions.index('"' + method + '"') for method in method_order]
    assert positions == sorted(positions)
    assert '"辅助线模式"' in actions
    assert 'app._auxiliary_controller.undo' in actions


def test_all_four_task_panels_are_only_visible_owners_and_locked_in_preprocess():
    tools = source(workspace_tools)
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    for title, builder in (
        ("图片预处理(前置)", "build_preprocess_menu"),
        ("一、版面参数", "build_layout_menu"),
        ("三、共享 OCR 通道 / OCR画线", "build_ocr_menu"),
        ("四、画线 / OCR / 插图 / 校对", "build_drawing_menu"),
    ):
        assert f'sections["{title}"] = {builder}(app, content)' in tools
    assert 'compact_sections.get(compact_titles.get(key, ""))' in app
    assert 'self.preprocess_mode_button.configure(' in app
    assert 'self.polygon_draw_button.configure(' in app


def test_postproduction_menu_is_renamed_but_export_callback_unchanged():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '("画线行导出", self.split_single_lines_selected_scope)' in app
    assert 'if text == "画线行导出":' in app
    assert '("未画线行导出", self.export_unlined_rows_selected_scope)' in app
