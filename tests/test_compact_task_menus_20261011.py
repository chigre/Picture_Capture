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
    assert "proposed = max(80, min(340, drag[\"width\"] + delta))" in text
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
    state = (ROOT / "ui/quick_state.py").read_text(encoding="utf-8")
    assert '"body_indent": float' in state
    assert "app.quick_pixel_vars[name]" in text
    assert 'app.quick_bool_vars["ordinary_auto_layout"] = master' in text
    assert 'return build_layout_profile_menu(app, parent)' in source(compact_task_menus)


def test_ocr_and_drawing_panels_keep_existing_handlers_in_requested_order():
    text = source(compact_task_menus)
    ocr = text.split("def build_ocr_menu(", 1)[1].split("ACTION_GROUPS =", 1)[0]
    assert '"使用有效缓存": "reuse"' in text
    assert '"重新OCR": "force"' in text
    assert '_coded_select(row, app.ocr_refresh_var, OCR_REFRESH_OPTIONS' in ocr
    assert '"原图": "original"' in text
    assert '"灰度": "grayscale"' in text
    assert '"自动对比度": "auto_contrast"' in text
    assert '"二值化": "binary"' in text
    assert '"paddle_preprocessing"' in ocr
    assert '_coded_select(row, preprocessing_var, OCR_PREPROCESS_OPTIONS' in ocr
    for name in ("ocr_language", "paddle_band_width_ratio", "paddle_left_tolerance",
                 "paddle_use_paddleocr", "paddle_compare_tesseract",
                 "paddle_enable_lens", "paddle_separator_safety_px"):
        assert f'"{name}"' in ocr
    assert 'app.check_ocr_engines' in ocr
    assert 'choose_workspace_section(app, title)' in ocr
    assert 'title = "三之一、OCR画线设置"' in ocr
    expected = [
        '"识别策略"', '"OCR引擎:"', '"PaddleOCR"', '"Tesseract"',
        '"Google Lens"', '"OCR语言"', '"识别带宽%"', '"左缘容差"',
        '"横线与文字安全距离px"', '"OCR图像预处理"',
        '"环境中心"', '"OCR画线设置..."',
    ]
    assert [ocr.index(item) for item in expected] == sorted(
        ocr.index(item) for item in expected
    )
    actions = text.split("ACTION_GROUPS =", 1)[1]
    method_order = (
        "run_normal_draw_action", "ocr_ordinary_lines_text_selected_scope",
        "run_combined_draw_action", "run_ocr_draw_action",
        "clear_entries", "clear_text", "refine_lines_selected_scope",
        "bookmark_modified_line_pages", "open_review", "select_existing_headwords_file",
        "compare_old_new_selected_scope", "fill_existing_headwords",
        "repair_pdic_order_selected_scope", "backup_pdic",
        "restore_from_pdic_backup", "detect_illustrations_selected_scope",
        "toggle_polygon_drawing", "associate_illustrations",
        "cleanup_paddleocr_temp_selected_scope",
    )
    positions = [actions.index('"' + method + '"') for method in method_order]
    assert positions == sorted(positions)
    assert '("插图关联", "associate_illustrations")' in actions
    assert 'app._attach_tooltip(button, "画线/插图校对后再进行本操作！")' in actions
    assert '"编辑插图", "toggle_polygon_drawing"' in actions
    assert actions.index('"编辑插图", "toggle_polygon_drawing"') < actions.index('"插图关联", "associate_illustrations"')
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
    task = source(compact_task_menus)
    assert '("画线行导出", "split_single_lines_selected_scope")' in task
    assert 'if caption == "画线行导出":' in task
    assert '("未画线行导出", "export_unlined_rows_selected_scope")' in task


def test_ocr_visible_labels_do_not_change_runtime_codes():
    import tkinter as tk
    from picture_capture.ui.compact_task_menus import (
        OCR_REFRESH_OPTIONS, OCR_PREPROCESS_OPTIONS, _link_code_selection,
    )

    root = tk.Tcl()
    for options, initial, changed_label, changed_code in (
        (OCR_REFRESH_OPTIONS, "reuse", "重新OCR", "reuse"),
        (OCR_PREPROCESS_OPTIONS, "original", "自动对比度", "binary"),
    ):
        runtime = tk.StringVar(master=root, value=initial)
        visible = tk.StringVar(master=root, value="")
        _link_code_selection(runtime, visible, options)
        assert visible.get() == next(
            label for label, code in options.items() if code == initial
        )
        visible.set(changed_label)
        assert runtime.get() == options[changed_label]
        runtime.set(changed_code)
        assert visible.get() == next(
            label for label, code in options.items() if code == changed_code
        )


def test_ocr_preprocessing_uses_existing_quick_autosave_pipeline():
    ocr = source(compact_task_menus)
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'app.quick_vars["paddle_preprocessing"] = preprocessing_var' in ocr
    assert 'app.quick_field_casts["paddle_preprocessing"] = str' in ocr
    assert 'preprocessing_var.trace_add(' in ocr
    assert 'app._quick_parameter_changed()' in ocr
    assert "for name, var in self.quick_vars.items():" in app
    assert 'self.quick_field_casts[name](var.get())' in app
    assert 'self.settings.paddle_lens_mode = LENS_MODE_VALUES.get(' in app
