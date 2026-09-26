from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.app import (
    PictureCaptureApp, SettingsDialog, binary_preview_image, effective_main_overlay_font_size,
    ReviewWindow, VerticalWordText, entry_index_label_layout,
    horizontal_ocr_menu_layout, horizontal_overlay_layout,
    transformed_entry_anchor, vertical_marker_contact_gap, vertical_ocr_menu_layout,
    vertical_overlay_layout,
)
from picture_capture.dictionary_profile import (
    apply_project_profile_components, effective_project_profile_id,
    load_dictionary_profile, profile_tail_structure_defaults, write_project_profile,
)
from picture_capture.models import (
    AppSettings, Entry, ProjectState, project_cover_path, project_page_images,
)
from picture_capture.layout_transform import LayoutTransform
from picture_capture.layout_detection import _analysis_ink_mask
from picture_capture.processing import (
    _left_edge_ink_mask, apply_column_start_offsets, derive_geometry,
    derive_nominal_geometry, refine_existing_entries,
)
from picture_capture.profile_semantics import (
    apply_headword_profile, apply_headword_tuning, apply_reading_choice, configured_body_page_indices,
    effective_page_settings,
    entry_allowed_by_page_template, excluded_source_side, excluded_source_side_percent,
    ordered_headword_profiles,
    page_template_analysis_image, probable_body_page_indices, READING_LABELS,
    reading_choice_from_settings, representative_page_indices, sample_page_indices,
    suggested_body_page_range,
)
from picture_capture.paddle_headwords import (
    OCRLine, OCRRecord, _cache_signature, _compile_patterns,
    _detect_visual_entry_markers, _headword_script_compatibility,
    _ordinary_strong_edge_visual_rescue, _ordinary_visual_rescue_thresholds,
    _repair_multiline_headword_state_machine,
    _selected_tail_structure_evidence, filter_headword_records, HeadwordParse,
    parse_headword_filter_rules, parse_headword_text, prepare_ocr_band,
    run_paddle_band,
)
from picture_capture.visual_marker_templates import (
    build_visual_marker_sample, match_visual_marker_template,
    parse_visual_marker_samples, serialize_visual_marker_samples,
    split_configured_symbols,
)
from picture_capture.project_storage import profile_path, qt_root, settings_path
from picture_capture.picdic import PicDicBuildCancelled, build_picdic_package
from picture_capture.training_export import TrainingExportCancelled, make_training_zip
from picture_capture.recent_projects import (
    load_recent_projects, recent_project_details, remove_recent_project, touch_recent_project,
)


def _project(root: Path, **settings) -> None:
    root.mkdir()
    Image.new("RGB", (8, 8), "white").save(root / "page10.jpg")
    Image.new("RGB", (8, 8), "white").save(root / "page2.jpg")
    Image.new("RGB", (8, 8), "white").save(root / "page1.jpg")
    state = ProjectState.open(root)
    for key, value in settings.items():
        setattr(state.settings, key, value)
    state.settings.to_json(settings_path(root))


def test_projects_restore_independent_settings_and_natural_order(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    _project(a, columns=1, main_entry_font_size=18, ocr_language="eng", paddle_band_width_ratio=60)
    _project(b, columns=3, main_entry_font_size=32, ocr_language="jpn", paddle_band_width_ratio=75)
    for root, expected in ((a, (1, 18, "eng", 60)), (b, (3, 32, "jpn", 75))) * 2:
        state = ProjectState.open(root)
        assert [page.name for page in state.images] == ["page1.jpg", "page2.jpg", "page10.jpg"]
        assert (state.settings.columns, state.settings.main_entry_font_size,
                state.settings.ocr_language, state.settings.paddle_band_width_ratio) == expected


def test_settings_json_beats_profile_sidecar(tmp_path):
    root = tmp_path / "project"
    _project(root, dictionary_profile_id="latin_pos_classic")
    profile_path(root).write_text('{"format":"dictionary-profile-v2","preset":"cjk_bracket_display"}', encoding="utf-8")
    assert ProjectState.open(root).settings.dictionary_profile_id == "latin_pos_classic"


def test_recent_removal_only_changes_registry(tmp_path):
    project, registry = tmp_path / "scan", tmp_path / "recent.json"
    project.mkdir(); (project / "user.jpg").write_bytes(b"user")
    touch_recent_project(project, registry)
    remove_recent_project(project, registry)
    assert load_recent_projects(registry) == []
    assert (project / "user.jpg").read_bytes() == b"user"


def test_recent_project_keeps_per_project_last_page(tmp_path):
    project, registry = tmp_path / "scan", tmp_path / "recent.json"
    project.mkdir()
    touch_recent_project(
        project, registry, last_page="page10.jpg", last_page_index=9,
    )
    # Re-touching a project without a page update must not erase its resume point.
    touch_recent_project(project, registry)
    row = load_recent_projects(registry)[0]
    assert row["last_page"] == "page10.jpg"
    assert row["last_page_index"] == 9


def test_project_cover_is_preferred_but_never_counted_as_a_page(tmp_path):
    project = tmp_path / "scan"
    _project(project)
    legacy_cover = project / "_project_cover.jpg"
    Image.new("RGB", (60, 90), "red").save(legacy_cover)
    cover = project / "_cover.jpg"
    Image.new("RGB", (60, 90), "blue").save(cover)

    assert project_cover_path(project) == cover
    assert [path.name for path in project_page_images(project)] == [
        "page1.jpg", "page2.jpg", "page10.jpg",
    ]
    state = ProjectState.open(project)
    assert [path.name for path in state.images] == [
        "page1.jpg", "page2.jpg", "page10.jpg",
    ]

    detail = recent_project_details({"name": "scan", "path": str(project)})
    assert detail["image_count"] == 3
    assert detail["cover_source"] == "cover"
    assert detail["cover_path"] == str(cover)
    assert detail["preview_path"] == str(cover)


def test_recent_project_details_expose_requested_columns(tmp_path):
    project = tmp_path / "scan"
    _project(project, dictionary_full_name="完整词典", dictionary_abbreviation="缩写")
    detail = recent_project_details({
        "name": "scan",
        "path": str(project),
        "opened_at": "old",
        "last_page": "page2.png",
        "last_page_index": 1,
    })
    assert detail["full_name"] == "完整词典"
    assert detail["abbreviation"] == "缩写"
    assert detail["image_count"] == 3
    assert detail["path"] == str(project)
    assert detail["last_edited"] != "old"
    missing = recent_project_details({
        "name": "missing",
        "path": str(tmp_path / "missing"),
        "opened_at": "2026-09-23T08:11:05.111954+00:00",
    })
    assert "T" not in str(missing["last_edited"])
    assert len(str(missing["last_edited"])) == 16
    assert detail["last_page"] == "page2.png"
    assert detail["last_page_index"] == 1
    assert detail["position_text"] == "第 2 / 3 页"


def test_recent_projects_dialog_uses_modern_card_information_hierarchy():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    start = source.index("    def open_recent_project(self) -> None:")
    end = source.index("\n    @staticmethod", start)
    text = source[start:end]

    assert 'dialog.title("已有项目")' in text
    assert 'text="最近项目"' in text
    assert 'text="搜索项目"' in text
    assert 'text="清理失效项"' in text
    assert 'text="打开"' in text
    assert 'text="⋯"' in text
    assert '"可用" if exists else "路径失效"' in text
    assert "张图片" in text
    assert "上次停留：" in text
    assert "最近活动：" in text
    assert "复制项目路径" in text
    assert "从最近项目移除（不删除文件）" in text
    assert "_cover.jpg" in text
    assert "_project_cover.*" in text
    assert "该文件不会计入正文图片" in text
    assert 'cover_source == "cover"' in text
    assert 'cover_source == "first_page"' in text
    assert "ImageTk.PhotoImage" in text
    assert "width=76" in text and "height=96" in text
    assert "int(screen_w * 0.58)" in text
    assert 'tools.grid(row=1, column=0' in text
    assert 'list_host.grid(row=3, column=0' in text
    assert "显示列" not in text
    assert "词典完整名称" not in text
    assert "从列表删除" not in text


def test_refine_existing_entries_never_changes_count_or_exceeds_safe_delta(monkeypatch):
    import picture_capture.paddle_headwords as paddle_headwords

    def far_refiner(_gray, coarse_y, _line_height, _settings, **_kwargs):
        return coarse_y + 999, {"reason": "test"}

    monkeypatch.setattr(paddle_headwords, "refine_separator_y", far_refiner)
    image = Image.new("RGB", (120, 160), "white")
    settings = AppSettings(
        columns=1,
        manual_columns=True,
        manual_x=10,
        column_width=100,
        gutter=0,
        start_y=0,
        bottom_y=160,
        character_height=10,
        paddle_separator_search_ratio=0.30,
        paddle_refine_separator_y=True,
    )
    entries = [Entry("alpha", 10, 30), Entry("beta", 10, 70)]
    refined, stats = refine_existing_entries(image, entries, settings)

    assert len(refined) == len(entries) == stats["total"]
    assert [entry.word for entry in refined] == ["alpha", "beta"]
    assert stats["max_delta"] == 3
    assert all(abs(new.y - old.y) <= stats["max_delta"] for old, new in zip(entries, refined))


def test_custom_profile_name_persists_and_numbered_choices_keep_custom_last(tmp_path):
    path = tmp_path / "settings.json"
    AppSettings(dictionary_custom_profile_name="古汉语单字结构").to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.dictionary_custom_profile_name == "古汉语单字结构"

    fake = SimpleNamespace(
        custom_profile_name_var=SimpleNamespace(get=lambda: "古汉语单字结构"),
    )
    labels = SettingsDialog._build_profile_choice_labels(fake)
    keys = list(labels.values())
    visible = list(labels.keys())
    assert keys[-1] == "custom"
    assert visible[-1].endswith("古汉语单字结构（自定义）")
    assert all(label.startswith(f"{index}. ") for index, label in enumerate(visible, start=1))


def test_secondary_windows_share_modern_shell_without_changing_review_window():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")

    settings_start = source.index("class SettingsDialog")
    settings_end = source.index("class ReviewWindow", settings_start)
    settings = source[settings_start:settings_end]
    assert '_build_modern_dialog_heading(' in settings
    assert '"设置中心"' in settings
    assert 'text="校验当前设置"' in settings
    assert 'command=self._close_validated' in settings
    assert 'text="保存并关闭"' not in settings
    assert 'text="环境中心"' in settings

    review_start = source.index("class ReviewWindow")
    review_end = source.index("class OCRConflictReviewDialog", review_start)
    review = source[review_start:review_end]
    assert '_build_modern_dialog_heading(' not in review

    conflict_start = source.index("class OCRConflictReviewDialog")
    conflict_end = source.index("class CropSettingsDialog", conflict_start)
    conflict = source[conflict_start:conflict_end]
    assert '"OCR 词头冲突复核"' in conflict
    assert 'text="所选候选"' in conflict
    assert 'text="关闭"' in conflict

    crop_start = source.index("class CropSettingsDialog")
    crop_end = source.index("class OldNewComparisonWindow", crop_start)
    crop = source[crop_start:crop_end]
    assert '"通用切图规则"' in crop
    assert '"特殊页面范围"' in crop
    assert '主界面【六、页面列表】的 Section 列双击设置' in crop
    assert '"特殊页面覆盖"' not in crop
    assert 'text="保存并关闭"' in crop

    compare_start = source.index("class OldNewComparisonWindow")
    compare_end = source.index("class PictureCaptureApp", compare_start)
    compare = source[compare_start:compare_end]
    assert '"新旧比较"' in compare
    assert 'text="比较来源"' in compare
    assert 'text="比较摘要"' in compare
    assert 'text="保存当前 PDIC 快照…"' in compare
    assert 'text="导出差异报告…"' in compare


def test_settings_center_uses_context_help_units_and_user_facing_modes():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("class SettingsDialog")
    end = text.index("class ReviewWindow", start)
    settings = text[start:end]

    assert '"bottom_y", int' in settings
    assert '"bottom_y": "正文结束 Y"' in settings
    assert '"columns": "正文栏数"' in settings
    assert '"manual_x": "第一栏左缘 X"' in settings
    assert '"paddle_band_width_ratio": "%"' in settings
    assert '"paddle_left_tolerance": "原图px"' in settings
    assert '"paddle_separator_safety_px": "原图px"' in settings
    assert '"columns": (1, 12, 1)' in settings
    assert "def _show_setting_help(" in settings
    assert 'text="设置说明"' in settings
    assert "程序取第 1 个捕获组作为原始词头" in settings
    assert "实际 POS 正则由 Profile 的 pos_labels 动态生成" in settings
    assert "可作为新词条起始证据" in settings
    assert "命中只增加一项结构证据，不会无条件把该行接受为词头" in settings
    assert 'text="ⓘ"' in settings
    assert 'panes = ttk.Panedwindow(host, orient="horizontal")' in settings
    assert 'panes.add(left, weight=3)' in settings
    assert 'panes.add(right, weight=2)' in settings
    assert 'panes.sashpos(0, int(width * 0.60))' in settings
    assert "def _bind_responsive_labels(" in settings
    assert "label.configure(wraplength=wraplength)" in settings
    assert "control.columnconfigure(0, weight=1)" in settings
    assert 'widget.grid(row=0, column=0, sticky="ew")' in settings
    assert "wraplength=0 if single_line_labels else 180" in settings
    assert 'justify="left"' in settings
    assert 'style="PC.Settings.TNotebook"' in settings
    assert '"PC.Settings.TNotebook.Tab"' in settings
    assert 'padding=(13, 7)' in settings
    assert "self.transient(parent); self.grab_set()" not in settings
    assert "def select_tab(self, key: str | None)" in settings

    assert 'text="OCR画线（推荐）"' in settings
    assert 'text="普通画线（备用）"' in settings
    assert 'value=DETECTION_LABELS["left_edge"]' in settings
    assert 'value=DETECTION_LABELS["paddleocr"]' in settings

    assert 'text="校验当前设置"' in settings
    assert 'self.bind("<Escape>", lambda _event: self._close_validated())' in settings
    assert "✓ 已自动保存" in settings
    assert "⚠ 当前输入暂未保存" in settings

    # Every Settings Center field/check must have a real help entry; avoid
    # silently falling back to the generic "专家参数" text as the UI grows.
    from picture_capture.app import SettingsDialog
    field_names = {name for _label, name, _cast in SettingsDialog.FIELDS}
    assert field_names <= set(SettingsDialog.SETTING_HELP)
    visible_checks = (
        SettingsDialog.NORMAL_CHECKS
        + SettingsDialog.OCR_COMMON_CHECKS
        + SettingsDialog.OCR_ADVANCED_CHECKS
        + SettingsDialog.DISPLAY_STYLE_CHECKS
        + SettingsDialog.DISPLAY_CHECKS
    )
    check_names = {name for _label, name in visible_checks} | {"paddle_enable_lens"}
    assert check_names <= set(SettingsDialog.CHECK_HELP)
    for key in field_names:
        assert len(SettingsDialog.SETTING_HELP[key]) >= 40, key
    for key in check_names:
        assert len(SettingsDialog.CHECK_HELP[key]) >= 40, key
    for key in (
        "detection_method", "paddle_lens_mode", "ocr_engine",
        "headword_sort_mode", "headword_custom_order", "headword_custom_fold_accents",
    ):
        assert len(SettingsDialog.SETTING_HELP[key]) >= 60, key
    assert 'self._show_setting_help("paddle_lens_mode")' in settings
    assert 'self._show_setting_help("ocr_engine")' in settings
    assert 'self._show_setting_help("headword_sort_mode")' in settings


def test_settings_center_is_reused_without_blocking_main_workspace():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    start = source.index("    def open_settings(self, initial_tab:")
    end = source.index("\n    def open_project_profile(", start)
    open_settings = source[start:end]

    assert 'self.__dict__.get("_settings_dialog")' in open_settings
    assert "existing.select_tab(initial_tab)" in open_settings
    assert "existing.deiconify()" in open_settings
    assert "dialog = SettingsDialog(self, initial_tab=initial_tab)" in open_settings
    assert "self._settings_dialog = dialog" in open_settings


def test_common_layout_settings_show_packaged_context_diagrams():
    root = Path(__file__).resolve().parents[1]
    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("class SettingsDialog")
    end = app_text.index("class ReviewWindow", start)
    settings = app_text[start:end]

    assert '"columns": "layout_col_number.png"' in settings
    for field in (
        "start_y", "bottom_y", "manual_x", "column_width",
        "gutter", "character_height", "row_padding",
    ):
        assert f'"{field}": "layout_settings.png"' in settings
    assert "help_images=True" in settings
    assert "show_layout_image: bool = False" in settings
    assert '/ "data"' in settings
    assert '/ "layout_example"' in settings
    assert "Image.Resampling.LANCZOS" in settings
    assert "ImageTk.PhotoImage(themed_display_image(rendered, self.parent.appearance_mode))" in settings

    layout_dir = root / "src" / "picture_capture" / "data" / "layout_example"
    assert (layout_dir / "layout_col_number.png").is_file()
    assert (layout_dir / "layout_settings.png").is_file()

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"data/layout_example/*.png"' in pyproject


def test_project_toolbar_and_profile_scroll_layout_are_wired():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")

    project_bar_start = text.index("        project_row = ttk.Frame(self.project_action_bar")
    project_bar_end = text.index("        self.canvas = tk.Canvas(", project_bar_start)
    project_bar = text[project_bar_start:project_bar_end]
    assert project_bar.index('("已有项目", self.open_recent_project, "project")') < project_bar.index('("导出训练标记包", self.export_training_package, None)')
    assert project_bar.index('("项目Profile", self.open_project_profile, "config")') < project_bar.index('("设置中心", self.open_settings, "config")')
    assert project_bar.index('("设置中心", self.open_settings, "config")') < project_bar.index('("保存参数", self.save_main_parameters, None)')
    assert project_bar.index('("保存参数", self.save_main_parameters, None)') < project_bar.index('("使用指南", self.show_help_dialog, None)')
    assert '("项目Profile", self.open_project_profile, "config")' in project_bar
    assert 'uniform="project-footer-columns"' in project_bar
    assert 'project_row.columnconfigure(col, weight=1, uniform="project-footer-columns")' in project_bar
    assert 'parameter_row.columnconfigure(col, weight=1, uniform="project-footer-columns")' in project_bar
    assert 'self._footer_action_button(' in project_bar

    actions_start = text.index('        actions = self._section_frame(parent, "四、画线与校对"')
    actions_end = text.index("        postproduction = self._section_frame(", actions_start)
    actions = text[actions_start:actions_end]
    assert '("设置中心", self.open_settings)' not in actions
    assert '("导出训练标记包", self.export_training_package)' not in actions

    profile_start = text.index("    def _build_profile_tab(")
    profile_end = text.index("    def _build_profile_choice_labels(", profile_start)
    profile = text[profile_start:profile_end]
    assert "self.profile_canvas = profile_canvas" in profile
    assert "profile_scrollbar" in profile
    assert 'text="自定义结构名称："' in profile
    assert "ProjectProfileWizard(self, new_project=new_project)" in text


def test_bottom_important_actions_follow_scheme_a_groups():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _footer_action_button(")
    end = text.index("    def _section_frame(", start)
    helper = text[start:end]
    assert '"project": (colors["success"], colors["success_hover"], "#ffffff")' in helper
    assert '"config": (colors["success"], colors["success_hover"], "#ffffff")' in helper
    assert 'border = colors["button_border"]' in helper
    assert '"profile":' not in helper
    assert '"settings":' not in helper
    assert '"save":' not in helper
    assert '"help":' not in helper
    assert 'highlightbackground=border' in helper
    assert 'highlightthickness=1' in helper

    project_bar_start = text.index("        project_row = ttk.Frame(self.project_action_bar")
    project_bar_end = text.index("        self.canvas = tk.Canvas(", project_bar_start)
    project_bar = text[project_bar_start:project_bar_end]
    assert '("新建项目", self.open_project, "project")' in project_bar
    assert '("已有项目", self.open_recent_project, "project")' in project_bar
    assert '("导出训练标记包", self.export_training_package, None)' in project_bar
    assert '("项目Profile", self.open_project_profile, "config")' in project_bar
    assert '("设置中心", self.open_settings, "config")' in project_bar
    assert '("保存参数", self.save_main_parameters, None)' in project_bar
    assert '("使用指南", self.show_help_dialog, None)' in project_bar


def test_usage_guide_is_modern_task_oriented_and_centered():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")

    guide_start = text.index("class UsageGuideWindow(tk.Toplevel):")
    guide_end = text.index("class SettingsDialog(tk.Toplevel):", guide_start)
    guide = text[guide_start:guide_end]

    assert '"快速开始"' in guide
    assert 'self.title("Picture Capture · 使用指南")' in guide
    assert "work_x, work_y, work_w, work_h = _screen_work_area(self)" in guide
    assert "x = work_x + max(0, (work_w - width) // 2)" in guide
    assert "y = work_y + max(0, (work_h - height) // 2)" in guide
    assert 'self.geometry(f"{width}x{height}+{x}+{y}")' in guide
    assert '"画线与 OCR"' in guide
    assert '"校对与词表"' in guide
    assert '"插图与切图"' in guide
    assert '"后期制作"' in guide
    assert '"导航与排错"' in guide
    assert 'self.search_var = tk.StringVar()' in guide
    assert '"推荐原则"' in guide
    assert '"项目Profile"' in guide
    assert '"检测版面参数"' in guide
    assert '"环境中心"' in guide
    assert '"设置中心"' in guide
    assert "OCR画线是默认推荐模式" in guide
    assert "普通画线降为备用" in guide
    assert "默认先用 OCR画线验证代表页" in guide
    assert "wraplength=158" in guide
    assert 'self.bind("<Escape>", lambda _event: self.destroy())' in guide

    show_start = text.index("    def show_help_dialog(self) -> None:")
    show_end = text.index("    @staticmethod\n    def _distribution_version", show_start)
    show = text[show_start:show_end]
    assert "UsageGuideWindow(self)" in show
    assert "_usage_guide_window" in show
    assert "messagebox.showinfo" not in show
    assert "show_help_popup" not in text
    assert "OCR_USAGE_HELP" not in text
    assert "打开使用指南：推荐流程、各功能用途、快捷操作与常见排错。" in text


def test_main_workspace_modern_styles_are_scoped_and_dense():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")

    styles_start = text.index("    def _configure_main_workspace_styles(")
    styles_end = text.index("    def _sidebar_action_button(", styles_start)
    styles = text[styles_start:styles_end]
    assert "theme_use(" not in styles
    assert '"PC.Section.TLabelframe"' in styles
    assert '"PC.Treeview"' in styles
    assert '"PC.Footer.TFrame"' in styles

    ui_start = text.index("    def _build_ui(self) -> None:")
    ui_end = text.index("    def _pointer_over_sidebar(", ui_start)
    ui = text[ui_start:ui_end]
    assert 'style="PC.Treeview"' in ui
    assert 'style="PC.Footer.TFrame"' in ui
    assert '"一、版面参数（规范全分辨率坐标；横排 U/X、V/Y 与原图一致）"' in text
    assert '"二、OCR画线（推荐默认）"' in text
    assert 'text="普通画线设置（备用）…"' in text
    assert 'ttk.Separator(size_row, orient="vertical")' in ui
    assert 'relief="sunken"' not in ui
    assert 'relief="ridge"' not in ui

    actions_start = text.index('        actions = self._section_frame(parent, "四、画线与校对"')
    actions_end = text.index("        postproduction = self._section_frame(", actions_start)
    actions = text[actions_start:actions_end]
    assert 'self._sidebar_action_button(row, text, command, role=role)' in actions
    assert '"primary" if text == "运行OCR画线（推荐）"' in actions
    assert '("运行OCR画线（推荐）", self.run_ocr_draw_action)' in actions
    assert '("运行普通画线（备用）", self.run_normal_draw_action)' in actions
    assert actions.index('("运行普通画线（备用）", self.run_normal_draw_action)') < actions.index('("运行OCR画线（推荐）", self.run_ocr_draw_action)')
    assert '("填充词条", self.fill_existing_headwords)' in actions
    assert '("修复排序", self.repair_pdic_order_selected_scope)' in actions
    assert '("恢复PDIC", self.restore_from_pdic_backup)' in actions
    assert '"success" if text == "保存当前页"' in actions
    assert '"primary" if text == "词条校对"' in actions
    assert '"danger_soft"' not in actions
    assert '"refine_soft"' not in actions
    assert '"compare_soft"' not in actions
    assert '("新旧比较", self.compare_old_new_selected_scope), ("词条校对", self.open_review)' in actions
    assert '"text": "#000000"' in styles
    assert '"primary": "#4F7CAC"' in styles
    assert '"primary_hover": "#416A94"' in styles
    assert '"success": "#69A875"' in styles
    assert '"success_hover": "#588F64"' in styles
    assert '"review_soft"' not in styles
    assert '"button_border": "#d3d8df"' in styles

    button_start = text.index("    def _sidebar_action_button(")
    button_end = text.index("    def _section_frame(", button_start)
    button = text[button_start:button_end]
    assert 'if role == "neutral":' in button
    assert 'return ttk.Button(' in button
    assert 'style="PC.Compact.TButton"' in button
    assert 'border = colors["button_border"]' in button
    assert 'relief="flat"' in button
    assert "bd=0" in button
    assert "highlightthickness=1" in button
    assert "highlightbackground=border" in button
    assert "highlightcolor=border" in button
    assert '"PC.EditActive.TButton"' in styles


def test_binary_preview_and_font_scaling_are_display_only():
    source = Image.new("RGB", (2, 1)); source.putdata([(20, 20, 20), (240, 200, 160)])
    before = source.tobytes()
    preview = binary_preview_image(source)
    assert source.tobytes() == before and source.mode == "RGB"
    assert all(color in {(0, 0, 0), (255, 255, 255)} for _count, color in preview.getcolors())
    settings = AppSettings(main_entry_font_size=32, main_entry_follow_zoom=True)
    assert effective_main_overlay_font_size(1400, 1, settings) == 32
    assert effective_main_overlay_font_size(2800, .5, settings) == 32
    assert effective_main_overlay_font_size(4200, 1 / 3, settings) == 32


def test_vertical_overlay_anchor_uses_canonical_offset():
    # x_ratio is applied in canonical space before the rotated widget is placed.
    editor = transformed_entry_anchor(
        LayoutTransform("rotate_ccw90"), 100, 200, 600, .5, (1400, 2200), .5,
    )
    assert editor == (599.5, 200)
    assert VerticalWordText._entry_index(0) == "1.0"
    assert VerticalWordText._entry_index("end") == "end-1c"


def test_vertical_editor_border_touches_marker_stroke():
    # A 2 px marker paints 1 px to either side of its centreline, so the
    # editor edge should be exactly 1 px away from the centreline.
    assert vertical_marker_contact_gap(2) == 1
    assert vertical_marker_contact_gap(3) == 2
    assert vertical_marker_contact_gap(4) == 2

    rl_box, *_ = vertical_overlay_layout(
        600, 200, editor_width=28, editor_height=180,
        writing_mode="vertical-rl", gap=vertical_marker_contact_gap(2),
    )
    lr_box, *_ = vertical_overlay_layout(
        600, 200, editor_width=28, editor_height=180,
        writing_mode="vertical-lr", gap=vertical_marker_contact_gap(2),
    )
    assert rl_box[2] == 599
    assert lr_box[0] == 601


def test_vertical_entry_boxes_have_fixed_length_and_mirror_marker_side():
    # Real vertical Text widgets use the same fixed requested size for every word.
    rl_box, rl_popup, rl_anchor, rl_index, rl_index_anchor = vertical_overlay_layout(
        600, 200, editor_width=28, editor_height=180, writing_mode="vertical-rl", gap=4,
    )
    lr_box, lr_popup, lr_anchor, lr_index, lr_index_anchor = vertical_overlay_layout(
        600, 200, editor_width=28, editor_height=180, writing_mode="vertical-lr", gap=4,
    )

    assert rl_box == (568, 200, 596, 380)
    assert lr_box == (604, 200, 632, 380)
    assert rl_box[2] < 600 < lr_box[0]
    assert (rl_box[3] - rl_box[1]) == (lr_box[3] - lr_box[1]) == 180
    assert (rl_box[2] - rl_box[0]) == (lr_box[2] - lr_box[0]) == 28
    assert rl_popup == (596.0, 200.0) and rl_anchor == "ne"
    assert lr_popup == (604.0, 200.0) and lr_anchor == "nw"
    assert rl_index == (565.0, 200.0) and rl_index_anchor == "ne"
    assert lr_index == (635.0, 200.0) and lr_index_anchor == "nw"


def test_vertical_ocr_menu_follows_vertical_writing_side():
    assert vertical_ocr_menu_layout((568, 200, 596, 380), 80, "vertical-rl", 1000) == (
        565.0, 200.0, "ne",
    )
    assert vertical_ocr_menu_layout((604, 200, 632, 380), 80, "vertical-lr", 1000) == (
        635.0, 200.0, "nw",
    )


def test_vertical_proxy_reuses_editor_membership_and_confidence_style():
    fake = SimpleNamespace(
        _project_words={"known"}, settings=AppSettings(main_entry_default_color="#ffffff"),
        _main_ocr_review_option_enabled=lambda _name: True,
        _confidence_bg=lambda confidence: "#c8e6c9" if confidence == .97 else "#ffcdd2",
    )
    known = PictureCaptureApp._entry_overlay_style(fake, Entry("known", 0, 0, confidence=.97))
    missing = PictureCaptureApp._entry_overlay_style(fake, Entry("missing", 0, 0, confidence=.5))
    assert known == ("#c8e6c9", "#b0b0b0", 1)
    assert missing == ("#ffcdd2", "#d32f2f", 2)


def test_entry_sequence_label_sits_before_editor_in_reading_direction():
    assert entry_index_label_layout(
        500, 150, 180, 24, horizontal=True, rtl=False,
    ) == (500.0, 150.0, "ne")
    assert entry_index_label_layout(
        500, 150, 180, 24, horizontal=True, rtl=True,
    ) == (500.0, 150.0, "nw")
    assert entry_index_label_layout(
        0, 0, 28, 180, horizontal=False, vertical_box=(568, 200, 596, 380),
    ) == (582.0, 200.0, "s")


def test_horizontal_ltr_rtl_are_mirror_equivalent():
    args = dict(canonical_x=100, canonical_y=300, column_width=600,
                source_size=(1400, 2200), view_scale=.5)
    ltr_low = horizontal_overlay_layout(LayoutTransform("identity"), x_ratio=.2, rtl=False, **args)
    ltr_high = horizontal_overlay_layout(LayoutTransform("identity"), x_ratio=.8, rtl=False, **args)
    rtl_low = horizontal_overlay_layout(LayoutTransform("mirror_x"), x_ratio=.2, rtl=True, **args)
    rtl_high = horizontal_overlay_layout(LayoutTransform("mirror_x"), x_ratio=.8, rtl=True, **args)
    assert ltr_low[0][1] == ltr_high[0][1] == rtl_low[0][1] == rtl_high[0][1] == 150
    assert ltr_high[0][0] > ltr_low[0][0]
    assert rtl_high[0][0] < rtl_low[0][0]
    assert ltr_low[1] == "nw" and rtl_low[1] == "ne"
    assert ltr_low[2][1] == rtl_low[2][1] == 150
    assert ltr_low[3] == "nw" and rtl_low[3] == "ne"
    assert horizontal_ocr_menu_layout(500, 150, 180, rtl=False) == (683, 150, "nw")
    assert horizontal_ocr_menu_layout(500, 150, 180, rtl=True) == (317, 150, "ne")


def test_horizontal_ui_uses_shared_layout_and_keeps_arabic_semantics():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("        horizontal = self.settings.layout_writing_mode == \"horizontal-tb\"")
    end = text.index("        vertical_box: tuple[int, int, int, int] | None = None", start)
    rtl_branch = text[start:end]
    assert "horizontal_overlay_layout(" in rtl_branch
    assert "line_box(" not in rtl_branch
    assert "if rtl:" in rtl_branch
    assert 'editor.configure(justify="right")' in rtl_branch


def test_review_edits_remain_bound_to_entries_after_main_line_insert():
    first, second = Entry("first", 10, 20), Entry("second", 10, 40)
    inserted = Entry("", 10, 30)
    fake = SimpleNamespace(
        row_entries=[first, second], vars=[SimpleNamespace(get=lambda: "FIRST"), SimpleNamespace(get=lambda: "SECOND")],
        parent=SimpleNamespace(entries=[first, inserted, second]),
        _capture_simplified_edits=lambda _stem: None, _rendered_page_stem="page",
    )
    fake._bound_row_entries = lambda: fake.row_entries
    ReviewWindow._commit_edits(fake)
    assert (first.word, inserted.word, second.word) == ("FIRST", "", "SECOND")


def test_latin_pronunciation_pos_and_cjk_rejection():
    profile = load_dictionary_profile(preset="latin_pos_classic", language="eng")
    settings = AppSettings(ocr_language="eng")
    for text in ("ab·a·cus ['æbəkəs] n. frame", "a·ban·don /ə'bændən/ v.t. leave"):
        parsed = parse_headword_text(text, settings, profile=profile)
        assert parsed is not None and parsed.has_pos
    assert parse_headword_text("中文正文", settings, profile=profile) is None


def test_script_neutral_default_is_narrowed_only_for_latin_profiles():
    assert r"[^\W\d_]" in AppSettings().paddle_headword_regex
    arabic = load_dictionary_profile(preset="arabic_rtl_bilingual_2col", language="ara")
    parsed_arabic = parse_headword_text("كتاب", AppSettings(ocr_language="ara"), profile=arabic)
    assert parsed_arabic is not None and parsed_arabic.normalized == "كتاب"
    japanese = load_dictionary_profile(preset="jpn_numbered_headword_2col", language="jpn")
    parsed_kana = parse_headword_text("10. かな", AppSettings(ocr_language="jpn"), profile=japanese)
    assert parsed_kana is not None and parsed_kana.normalized == "かな"


def test_settings_profile_is_authoritative_for_ui_and_ocr_resolution(tmp_path):
    root = tmp_path / "project"
    _project(root, dictionary_profile_id="latin_pos_classic", ocr_language="eng")
    sidecar = profile_path(root)
    sidecar.write_text(
        '{"format":"dictionary-profile-v2","preset":"cjk_bracket_display","language":"chi_sim"}',
        encoding="utf-8",
    )
    settings = ProjectState.open(root).settings
    # SettingsDialog and OCR both call this resolver; loading with its result
    # must ignore the disagreeing sidecar preset.
    selected = effective_project_profile_id(settings, sidecar)
    assert selected == "latin_pos_classic"
    ocr_profile = load_dictionary_profile(sidecar, preset=selected, language=settings.ocr_language)
    assert ocr_profile.key == "latin_pos_classic"
    assert parse_headword_text("中文正文", settings, profile=ocr_profile) is None


def test_cjk_pinyin_regex_handles_stars_and_apostrophes_without_ambiguity():
    profile = load_dictionary_profile(preset="cjk_large_head_pinyin_2col", language="chi_sim")
    settings = AppSettings(ocr_language="chi_sim")
    for text, expected in (("案* ān", "案"), ("暗* àn", "暗"), ("谙 ān", "谙"), ("西 xī'ān", "西")):
        assert parse_headword_text(text, settings, profile=profile).normalized == expected


def test_multiline_pronunciation_keeps_first_line_geometry():
    settings = AppSettings(ocr_language="eng")
    profile = load_dictionary_profile(preset="latin_pos_classic", language="eng")
    patterns = _compile_patterns(settings, profile)
    first = OCRLine("a·ban·don [ə'bændən;", .9, (3, 10, 180, 30), [])
    second = OCRLine("ə'bændən] v.t. leave", .9, (8, 31, 210, 50), [])
    repaired = _repair_multiline_headword_state_machine([first, second], settings, 20, patterns)
    assert repaired[0].box == first.box
    parsed = parse_headword_text(repaired[0].text, settings, patterns, profile)
    assert parsed is not None and parsed.has_pos


def test_cjk_features_gate_parsers_and_pinyin_is_structural():
    settings = AppSettings(ocr_language="chi_sim")
    pinyin = load_dictionary_profile(preset="cjk_large_head_pinyin_2col", language="chi_sim")
    parsed = parse_headword_text("案* ān", settings, profile=pinyin)
    assert parsed is not None and parsed.normalized == "案"
    disabled = replace(load_dictionary_profile(preset="cjk_bracket_display", language="chi_sim"), headword_features=())
    assert parse_headword_text("【案件】", settings, profile=disabled) is None
    enabled = load_dictionary_profile(preset="cjk_bracket_large_head_2col", language="chi_sim")
    assert parse_headword_text("【案件】", settings, profile=enabled).normalized == "案件"


def test_ocr_resize_coordinates_round_trip():
    class Result:
        json = {"res": {"rec_texts": ["word"], "rec_scores": [.9], "rec_boxes": [[100, 200, 300, 400]]}}
    class Engine:
        def predict(self, image, **kwargs):
            assert image.shape[:2] == (1400, 700)
            return [Result()]
    band = Image.new("RGB", (1400, 2800), "white")
    prepared, scale = prepare_ocr_band(band, max_long_side=1400)
    assert prepared.size == (700, 1400) and scale == .5
    records = run_paddle_band(band, AppSettings(paddle_max_input_side=1400), Engine())
    assert records == [OCRRecord("word", .9, (200, 400, 600, 800))]



def test_raw_ocr_cache_signature_tracks_pixels_and_inference_settings():
    class PathStub:
        points = [(10, 20), (10, 200)]

    geometry = SimpleNamespace(
        transform=SimpleNamespace(kind="identity"),
        column_paths=[PathStub()],
        top=20,
        bottom=200,
    )
    image = Image.new("RGB", (64, 64), "white")
    base = AppSettings(
        paddle_preprocessing="original",
        paddle_max_input_side=2800,
        paddle_use_textline_orientation=False,
    )
    sig = _cache_signature(image, geometry, base)
    assert _cache_signature(image, geometry, replace(base, paddle_preprocessing="binary")) != sig
    assert _cache_signature(image, geometry, replace(base, paddle_max_input_side=1400)) != sig
    assert _cache_signature(image, geometry, replace(base, paddle_use_textline_orientation=True)) != sig
    moved_body = SimpleNamespace(
        transform=geometry.transform,
        column_paths=geometry.column_paths,
        top=30,
        bottom=200,
    )
    assert _cache_signature(image, moved_body, base) != sig

    changed = image.copy()
    changed.putpixel((32, 32), (0, 0, 0))
    assert _cache_signature(changed, geometry, base) != sig

    # Candidate/parser-only settings deliberately do not invalidate raw OCR.
    assert _cache_signature(image, geometry, replace(base, paddle_min_candidate_score=9.0)) == sig
    assert _cache_signature(image, geometry, replace(base, paddle_headword_regex=r"^foo")) == sig


def test_project_profile_samples_front_middle_back_and_keeps_pairs():
    assert sample_page_indices(24, 6) == [0, 1, 11, 12, 22, 23]
    assert sample_page_indices(24, 4) == [0, 1, 12, 23]
    assert sample_page_indices(4, 6) == [0, 1, 2, 3]



def test_project_profile_configured_body_range_has_priority():
    images = [Path(f"{number:04d}.png") for number in range(1, 101)]
    allowed = configured_body_page_indices(len(images), "10-80")
    assert allowed[0] == 9
    assert allowed[-1] == 79
    samples = representative_page_indices(images, 6, allowed)
    assert len(samples) == 6
    assert min(samples) >= 9
    assert max(samples) <= 79

    assert configured_body_page_indices(len(images), "10至80") == allowed
    assert configured_body_page_indices(len(images), "10-800") == []



def test_project_profile_suggests_zero_padded_body_range():
    images = [
        Path("0000_cover.png"),
        Path("0001_title.png"),
        Path("0002.png"),
        Path("0003.png"),
        Path("0004.png"),
        Path("appendix_0005.png"),
    ]
    assert suggested_body_page_range(images) == "0003-0005"


def test_project_profile_representatives_avoid_obvious_front_and_back_matter():
    images = [Path("0000_cover.png")]
    images += [Path(f"{number:04d}_body.png") for number in range(1, 31)]
    images += [Path("appendix_01.png"), Path("附录_02.png")]
    candidates = probable_body_page_indices(images)
    assert 0 not in candidates
    assert len(images) - 1 not in candidates
    assert len(images) - 2 not in candidates

    samples = representative_page_indices(images, 6)
    assert len(samples) == 6
    assert all(index in candidates for index in samples)
    assert samples == sorted(samples)
    # Sampling stays inside the body rather than pinning to its absolute edges.
    assert samples[0] > candidates[0]
    assert samples[-1] < candidates[-1]


def test_project_profile_reading_labels_match_wizard_wording():
    assert READING_LABELS == {
        "horizontal-ltr": "横排：左→右",
        "horizontal-rtl": "横排：右→左",
        "vertical-rl": "纵排：右→左",
        "vertical-lr": "纵排：左→右",
    }


def test_project_profile_reading_dimension_is_independent():
    settings = AppSettings(
        layout_writing_mode="horizontal-tb",
        layout_text_direction="ltr",
        layout_transform="identity",
        ocr_language="ara",
    )
    apply_reading_choice(settings, "horizontal-rtl")
    assert reading_choice_from_settings(settings) == "horizontal-rtl"
    assert settings.layout_transform == "mirror_x"

    apply_reading_choice(settings, "vertical-rl")
    assert settings.layout_writing_mode == "vertical-rl"
    assert settings.layout_transform == "rotate_ccw90"


def test_headword_profile_does_not_override_confirmed_layout_or_language():
    settings = AppSettings(
        layout_writing_mode="vertical-rl",
        layout_text_direction="rtl",
        layout_transform="rotate_ccw90",
        layout_columns_policy="fixed",
        columns=3,
        layout_column_separator_mode="absent",
        ocr_language="jpn",
    )
    apply_headword_profile(settings, "latin_regular")
    assert settings.dictionary_profile_id == "latin_regular"
    assert settings.layout_writing_mode == "vertical-rl"
    assert settings.layout_text_direction == "rtl"
    assert settings.layout_transform == "rotate_ccw90"
    assert settings.columns == 3
    assert settings.layout_column_separator_mode == "absent"
    assert settings.ocr_language == "jpn"


def test_numbered_headword_profile_choices_keep_fixed_order_and_custom_last():
    choices = ordered_headword_profiles("古汉语单字结构")
    labels = [label for label, _key in choices]
    keys = [key for _label, key in choices]
    assert keys == [
        "latin_regular",
        "cjk_visual",
        "numbered_prefix",
        "marker_prefixed",
        "custom",
    ]
    assert labels == [
        "1. 常规边缘词头",
        "2. 视觉词头（大字/括号词头）",
        "3. 编号前缀词头",
        "4. 符号前缀词头",
        "5. 古汉语单字结构（自定义）",
    ]


def test_page_template_masks_side_content_before_geometry_without_mutating_source():
    image = Image.new("RGB", (100, 60), "white")
    for x in range(0, 12):
        for y in range(0, 60):
            image.putpixel((x, y), (0, 0, 0))
    settings = AppSettings(
        profile_side_content_mode="left",
        profile_side_percent=12,
    )
    masked = page_template_analysis_image(image, settings, 0)
    assert image.getpixel((5, 20)) == (0, 0, 0)
    assert masked.getpixel((5, 20)) == (255, 255, 255)
    assert masked.size == image.size


def test_page_template_alternating_ab_side_widths_are_independent():
    image = Image.new("RGB", (100, 60), "black")
    settings = AppSettings(
        profile_side_content_mode="outer",
        profile_page_pair_mode="alternate",
        profile_first_page_variant="A",
        profile_side_percent=8,
        profile_side_percent_a=6,
        profile_side_percent_b=14,
    )
    assert excluded_source_side(settings, 0) == "left"
    assert excluded_source_side(settings, 1) == "right"
    assert excluded_source_side_percent(settings, 0) == 6
    assert excluded_source_side_percent(settings, 1) == 14

    masked_a = page_template_analysis_image(image, settings, 0)
    masked_b = page_template_analysis_image(image, settings, 1)
    assert masked_a.getpixel((5, 30)) == (255, 255, 255)
    assert masked_a.getpixel((8, 30)) == (0, 0, 0)
    assert masked_b.getpixel((90, 30)) == (255, 255, 255)
    assert masked_b.getpixel((84, 30)) == (0, 0, 0)
    assert not entry_allowed_by_page_template(5, 30, image.size, settings, 0)
    assert entry_allowed_by_page_template(7, 30, image.size, settings, 0)
    assert not entry_allowed_by_page_template(90, 30, image.size, settings, 1)
    assert entry_allowed_by_page_template(84, 30, image.size, settings, 1)


def test_page_template_auto_footer_uses_learned_body_bottom():
    settings = AppSettings(
        bottom_y=1800,
        profile_footer_mode="auto",
    )
    effective = effective_page_settings(settings, (1000, 2000), 0)
    assert effective.crop_to_bottom_y is True
    assert effective.bottom_y == 1800

    empty = replace(settings, bottom_y=0)
    effective_empty = effective_page_settings(empty, (1000, 2000), 0)
    assert effective_empty.crop_to_bottom_y is False


def test_page_template_applies_header_footer_and_ab_side_exclusion():
    settings = AppSettings(
        profile_header_mode="present",
        profile_header_percent=10,
        profile_footer_mode="present",
        profile_footer_percent=5,
        profile_side_content_mode="outer",
        profile_side_percent=8,
        profile_page_pair_mode="alternate",
        profile_first_page_variant="A",
    )
    effective = effective_page_settings(settings, (1000, 2000), 0)
    # For horizontal pages, the confirmed physical header/footer are also the
    # body/OCR geometry bounds. The blue column path must therefore begin/end
    # exactly at the yellow exclusion boundaries.
    assert effective.start_y == 200
    assert effective.bottom_y == 1900
    assert effective.crop_to_bottom_y is True

    source = Image.new("RGB", (1000, 2000), "white")
    masked_horizontal = page_template_analysis_image(source, effective, 0)
    geometry = derive_geometry(masked_horizontal, effective)
    assert geometry.top == 200
    assert geometry.bottom == 1900
    assert all(path.points[0][0] == 200 for path in geometry.column_paths)
    assert all(path.points[-1][0] == 1900 for path in geometry.column_paths)

    assert excluded_source_side(settings, 0) == "left"
    assert excluded_source_side(settings, 1) == "right"
    assert not entry_allowed_by_page_template(500, 100, (1000, 2000), settings, 0)
    assert not entry_allowed_by_page_template(500, 1950, (1000, 2000), settings, 0)
    assert not entry_allowed_by_page_template(50, 500, (1000, 2000), settings, 0)
    assert entry_allowed_by_page_template(950, 500, (1000, 2000), settings, 0)
    assert not entry_allowed_by_page_template(950, 500, (1000, 2000), settings, 1)

    vertical = replace(
        settings,
        layout_writing_mode="vertical-rl",
        layout_text_direction="rtl",
        layout_transform="rotate_ccw90",
    )
    vertical_effective = effective_page_settings(vertical, (1000, 2000), 0)
    # For vertical writing, physical top/bottom are not the canonical reading
    # axis, so keep the learned start_y/bottom_y and apply only source masks.
    assert vertical_effective.start_y == vertical.start_y
    assert vertical_effective.bottom_y == vertical.bottom_y
    masked = page_template_analysis_image(
        Image.new("RGB", (1000, 2000), "black"), vertical_effective, 0,
    )
    assert masked.getpixel((500, 50)) == (255, 255, 255)
    assert masked.getpixel((500, 1950)) == (255, 255, 255)


def test_project_profile_feedback_tuning_is_profile_aware():
    cjk = AppSettings(ocr_language="chi_tra")
    apply_headword_profile(cjk, "cjk_visual")
    base_cjk = (
        cjk.paddle_left_tolerance,
        cjk.paddle_height_ratio,
        cjk.paddle_boldness_ratio,
    )
    apply_headword_tuning(cjk, "cjk_visual", 1)
    assert cjk.paddle_left_tolerance < base_cjk[0]
    assert cjk.paddle_height_ratio > base_cjk[1]
    assert cjk.paddle_boldness_ratio > base_cjk[2]

    marker = AppSettings(ocr_language="chi_sim")
    apply_headword_profile(marker, "marker_prefixed")
    base_score = marker.paddle_min_candidate_score
    base_left = marker.paddle_left_tolerance
    apply_headword_tuning(marker, "marker_prefixed", 1)
    assert marker.paddle_left_tolerance < base_left
    assert marker.paddle_min_candidate_score == base_score


def test_project_profile_headword_examples_are_packaged():
    from PIL import Image

    root = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "data" / "headword_examples"
    )
    expected = [
        "headword_example_1.png",
        "headword_example_2.png",
        "headword_example_3.png",
        "headword_example_4.png",
    ]
    for name in expected:
        path = root / name
        assert path.exists()
        with Image.open(path) as image:
            assert image.width > 0 and image.height > 0

    assert not (root / "classic_headword_examples.jpg").exists()
    assert not (root / "recommended_current").exists()
    assert not (root / "manifest.csv").exists()
    assert not (root / "manifest.json").exists()

    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert "data/headword_examples/*.png" in pyproject
    assert "data/headword_examples/recommended_current/" not in pyproject
    assert "data/profile_previews/" not in pyproject
    assert "data/headword_examples/extended/" not in pyproject

    dictionary_source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "dictionary_profile.py"
    ).read_text(encoding="utf-8")
    app_source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    assert "profile_preview_path" not in dictionary_source
    assert "profile_preview_dir" not in dictionary_source
    assert "profile_preview_path" not in app_source
    assert "preview_profile_examples" not in app_source


def test_project_profile_wizard_uses_analysis_as_a_setup_aid_then_stable_columns():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "profile_setup.py"
    text = source.read_text(encoding="utf-8")
    assert "代表页会自动分析并建议栏数；确认后作为本项目的稳定栏数使用。" in text
    assert 's.layout_columns_policy = "fixed"' in text
    assert "设置已修改，需要重新测试" in text

    assert '"1 词典信息与阅读方式"' in text
    assert '"2 页面模板"' in text
    assert '"3 词头结构"' in text
    assert '"4 测试与确认"' in text
    assert '"4 语言与 OCR"' not in text
    assert "self._build_language_section(tab, row=4)" in text
    assert 'text="词典项目详情"' in text
    assert 'text="词典全称："' in text
    assert 'text="词典简称(字母)："'.strip() in text
    assert 'text="ISBN："' in text
    assert 'text="正文页码："' in text
    assert 'row=0, column=0' in text
    assert 'row=0, column=2' in text
    assert 'row=1, column=0' in text
    assert 'row=1, column=2' in text
    assert "suggested_body_page_range(self.project.images)" in text
    assert "s.dictionary_full_name = self.dictionary_full_name_var.get().strip()" in text
    assert "s.dictionary_body_page_range = self.dictionary_body_page_range_var.get().strip()" in text
    assert "def _body_page_range_changed" in text

    assert "每一张都可在右侧手动更换" in text
    assert 'text="更换…"' in text
    assert '"页面模板即时预览"' in text
    assert 'text="◀ 上一张"' in text and 'text="下一张 ▶"' in text
    assert '"词头类型样例"' in text
    assert "self._build_right_image_workspace(right_panel)" in text
    assert 'ttk.Panedwindow(outer, orient="horizontal")' in text
    assert "self.profile_paned.add(left_panel, weight=40)" in text
    assert "self.profile_paned.add(right_panel, weight=60)" in text
    assert "def _apply_initial_pane_split" in text
    assert "round(pane_width * 0.40)" in text
    assert "self.after_idle(self._apply_initial_pane_split)" in text
    assert "self.profile_paned.sashpos" in text
    assert "def _apply_left_wraps" in text
    assert 'left_panel.bind(' in text
    assert 'child.configure(wraplength=wrap, justify="left")' in text
    assert "ProfileYellow.TLabelframe" not in text
    assert "fill=(255, 215, 0, 105)" in text
    marker_start = text.index("    def _marker_preview(")
    marker_end = text.index("    def _set_validation_fit(", marker_start)
    assert "fill=(255, 215, 0, 105)" in text[marker_start:marker_end]
    assert 'text="A 页排除宽度%"' in text
    assert 'text="B 页排除宽度%"' in text
    assert "s.profile_side_percent_a" in text
    assert "s.profile_side_percent_b" in text
    assert 'text="◀ 上一页"' in text
    assert 'text="适合高度"' in text
    assert 'text="适合宽度"' in text
    assert 'text="下一页 ▶"' in text
    assert "默认适合高度；适合宽度时图片横向占满" not in text
    assert 'self.validation_fit_mode = "height"' in text
    assert "def _set_validation_fit" in text
    assert "索引语言（2 位）" in text
    assert "indices = list(self.sample_indices)" in text
    assert 'uniform="sample"' in text
    assert 'uniform="sample_row"' in text
    assert "thumb_w = max(180, (available_w - 54) // 3)" in text
    assert "thumb_h = max(220, (available_h - 150) // 2 - 42)" in text

    # The window skeleton is built first; representative image decoding begins
    # later on a worker thread instead of blocking the button click.
    assert "self._show_sample_loading_state()" in text
    assert "self.after(20, self._start_sample_thumbnail_load)" in text
    assert "threading.Thread(target=worker, daemon=True).start()" in text
    assert "elif index == 2:" in text and "self._refresh_headword_description" in text

    # Replacing one representative page is a slot-local operation. It must not
    # rebuild/re-decode all six thumbnails or refresh a hidden template preview.
    assert "def _start_sample_thumbnail_slot_load" in text
    assert "def _render_sample_thumbnail_slot" in text
    choose_start = text.index("    def _choose_sample_page(")
    choose_end = text.index("    def _persist_current_profile(", choose_start)
    choose_text = text[choose_start:choose_end]
    assert "self._start_sample_thumbnail_slot_load(slot)" in choose_text
    assert "self._start_sample_thumbnail_load()" not in choose_text
    assert "preview_uses_slot = self.template_preview_slot == slot" in choose_text
    assert "self.notebook.index(self.notebook.select()) == 1" in choose_text

    # Multi-page validation is presented one page at a time with the same
    # previous/next navigation language as the page-template preview.
    assert "self._validation_results = list(results)" in text
    assert "def _move_validation_preview" in text
    assert "def _render_validation_result" in text
    assert "width = min(work_w, max(720, int(screen_w * 0.80)))" in text
    assert "return screen_work_area(widget)" in text
    ui_compat = (Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "ui_compat.py").read_text(encoding="utf-8")
    assert "SystemParametersInfoW" in ui_compat
    assert "height = max(1, int(work_h * 0.90))" in text
    assert "x = work_x + max(0, (work_w - width) // 2)" in text
    assert "y = work_y + max(0, (work_h - height) // 2)" in text
    assert "self._wizard_left_width = max(400, int(width * 0.40) - 36)" in text
    assert "self._wizard_image_width = max(560, int(width * 0.60) - 36)" in text
    assert "target_width = max(320, int(preview_width))" in text
    assert "source.resize(" in text
    assert "right_width = int(getattr(self, \"right_canvas\", self).winfo_width())" in text
    assert "HEADWORD_EXAMPLE_FILES" in text
    assert '"headword_example_1.png"' in text
    assert '"headword_example_2.png"' in text
    assert '"headword_example_3.png"' in text
    assert '"headword_example_4.png"' in text
    assert "HEADWORD_EXAMPLE_ATLAS_CROPS" not in text
    assert '"classic_headword_examples.jpg"' not in text
    assert "recommended_current" not in text
    assert 'root / "extended"' not in text
    assert "fill=(255, 0, 0, 255), width=1" in text
    assert "完整词头结构（词头前 + 词头本体 + 词头后）" in text
    assert "普通左缘短词可以作为词头" in text
    assert "【括号词】可以作为词头" in text
    assert "大字单字可以作为词头" in text
    assert "分析大字右侧留白（仅辅助“大字单字”判断）" in text
    assert "大字右侧检测宽度：" in text
    assert "profile_cjk_right_context_width_percent" in text
    assert "固定符号开头（○ / ● / ◆ …）可以作为词头" in text
    assert "本词典固定词头符号集" in text
    assert "启用本词典专用符号集" in text
    assert "入口标记：" in text
    assert "括号起始：" in text
    assert "OCR 漏掉/错认符号时允许视觉形状补救" in text
    assert "使用同栏 marker lane 过滤正文中的相似符号" in text
    assert "本词典视觉标记样本" in text
    assert "字符符号集 + 视觉样本" in text
    assert "视觉样本优先" in text
    assert "按角色合并（推荐）" in text
    assert "最低匹配分数：" in text
    assert "从页面采样…" in text
    assert "查看/删除样本" in text
    assert "有效入口标记：" in text
    assert "profile_symbol_template_version" in text
    assert "profile_symbol_templates_json" in text
    assert "profile_symbol_inventory_version" in text
    assert "profile_entry_marker_symbols" in text
    assert "profile_bracket_open_symbols" in text
    assert "profile_symbol_lane_tolerance_percent" in text
    assert "编号开头（1. / 2. / …）可以作为词头" in text
    assert "词头专属性（当前结构的视觉证据）" in text
    assert 'text="栏左缘容差："' in text
    assert "允许词头起点偏离栏左边界的最大距离；越小越严格" in text
    assert 'text="文字大小倍率 ≥"' in text
    assert 'text="粗体倍率 ≥"' in text
    assert 'text="候选强度 ≥"' in text
    assert "CJK 单字 / 括号词附加条件" in text
    assert "右侧显示与当前词头结构匹配的经典局部裁切样例。" not in text
    assert "必须靠近栏左缘" in text
    assert "释义正文中也经常出现【括号词】" in text
    assert "只有视觉明显突出时才把单字/括号词当词头" in text
    assert 'text="偏多"' in text and 'text="合适"' in text and 'text="偏少"' in text
    assert "def _apply_validation_feedback" in text
    assert "def _headword_structure_changed" in text
    assert "recommended_headword_structures" in text
    assert "s.profile_parser_controls_version = 1" in text
    assert "s.profile_allow_ordinary_left_edge" in text
    assert "s.profile_allow_numbered_prefix" in text
    assert "s.profile_allow_marker_prefix" in text
    assert "s.paddle_left_tolerance = max(" in text
    assert "s.paddle_height_ratio = max(" in text
    assert "s.paddle_boldness_ratio = max(" in text
    assert "s.paddle_min_candidate_score = max(" in text
    assert "def _persist_current_profile" in text
    assert "def _save_profile_progress" in text
    assert "if not self._save_profile_progress():" in text
    assert 'text="关闭"' in text
    assert "当前内容已经保存。项目 Profile 尚未完整确认" in text
    assert "settings.profile_setup_version = int(" in text
    assert 'header_mode == "auto" and geometry.top > 0' in text
    assert 'elif header_mode == "present"' in text
    validate_start = text.index("    def validate_profile(")
    validate_end = text.index("    def _poll_validation_queue(", validate_start)
    validate_text = text[validate_start:validate_end]
    assert 'settings.detection_method = "paddleocr"' in validate_text
    assert "settings.paddle_use_paddleocr = True" in validate_text
    assert "force_paddle_refresh=True" in validate_text
    assert "正在强制重新识别并测试代表页" in text
    assert "def _validation_coverage_summary" in text
    assert "self.validation_diagnostic_var" in text
    assert "下半页候选" in text
    assert "左缘最大漂移" in text
    assert "原始OCR完整但词头在中途停止" in text


def _parsed_headword_for_script_test(value: str) -> HeadwordParse:
    return HeadwordParse(
        raw=value,
        normalized=value,
        has_pos=False,
        pos_text="",
        has_inflection=False,
        inflection_text="",
        has_descriptor=False,
        descriptor_text="",
        match_end=max(1, len(value)),
    )


def test_headword_script_guard_rejects_cjk_for_non_cjk_ocr_but_keeps_japanese_kanji():
    han = _parsed_headword_for_script_test("波")
    kana = _parsed_headword_for_script_test("あい")
    latin = _parsed_headword_for_script_test("abbassare")

    ita = AppSettings(
        ocr_language="ita",
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=True,
    )
    assert _headword_script_compatibility(ita, han) == (False, "han")
    assert _headword_script_compatibility(ita, kana) == (False, "kana")
    assert _headword_script_compatibility(ita, latin) == (True, "other")

    jpn = AppSettings(
        ocr_language="jpn",
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=True,
    )
    assert _headword_script_compatibility(jpn, han) == (True, "han")
    assert _headword_script_compatibility(jpn, kana) == (True, "kana")

    chi = AppSettings(
        ocr_language="chi_sim",
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=True,
    )
    assert _headword_script_compatibility(chi, han) == (True, "han")
    assert _headword_script_compatibility(chi, kana) == (False, "kana")


def test_headword_script_guard_is_a_hard_candidate_gate():
    settings = AppSettings(
        ocr_language="ita",
        profile_parser_controls_version=1,
        profile_allow_ordinary_left_edge=True,
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=True,
        paddle_auto_header_rule=False,
        paddle_left_tolerance=40,
        paddle_band_left_margin=12,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(preset="latin_regular", language="ita")
    records = [
        OCRRecord(text="波 s.m. definizione", confidence=0.99, box=(2, 20, 95, 38))
    ]
    entries, diagnostics = filter_headword_records(
        records,
        Image.new("RGB", (160, 100), "white"),
        0,
        0,
        settings,
        user_rules=parse_headword_filter_rules("accept_lemma_exact: 波"),
        profile=profile,
    )
    assert entries == []
    rows = [row for row in diagnostics if "meta" not in row]
    assert rows
    assert rows[0]["normalized_headword"] == "波"
    assert rows[0]["reject_reason"] == "incompatible_headword_script"
    assert rows[0]["features"]["headword_leading_script"] == "han"
    assert rows[0]["features"]["headword_script_compatible"] is False


def test_headword_script_guard_can_be_disabled_for_special_bilingual_projects():
    han = _parsed_headword_for_script_test("波")
    settings = AppSettings(
        ocr_language="ita",
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=False,
    )
    assert _headword_script_compatibility(settings, han) == (True, "")


def test_headword_profiles_seed_explicit_tail_structure_defaults():
    latin = profile_tail_structure_defaults("latin_regular")
    assert latin == {
        "allow_pos": True,
        "allow_inflection": True,
        "allow_variant": True,
        "allow_pronunciation": False,
        "allow_descriptor": True,
        "require_selected": True,
        "allow_visual_rescue": True,
    }
    numbered = profile_tail_structure_defaults("numbered_prefix")
    assert numbered["require_selected"] is False
    assert numbered["allow_visual_rescue"] is False
    cjk = profile_tail_structure_defaults("cjk_visual")
    assert not any(
        cjk[name]
        for name in (
            "allow_pos", "allow_inflection", "allow_variant",
            "allow_pronunciation", "allow_descriptor",
            "require_selected", "allow_visual_rescue",
        )
    )


def test_selected_tail_structure_evidence_obeys_project_checkboxes():
    settings = AppSettings(
        ocr_language="ita",
        profile_tail_structure_version=1,
        profile_tail_allow_pos=False,
        profile_tail_allow_inflection=False,
        profile_tail_allow_variant=True,
        profile_tail_allow_pronunciation=False,
        profile_tail_allow_descriptor=False,
    )
    profile = load_dictionary_profile(preset="latin_regular", language="ita")
    patterns = _compile_patterns(settings, profile)
    parsed = parse_headword_text(
        "abbandonata, da agg. forma femminile",
        settings, patterns, profile,
    )
    assert parsed is not None
    assert parsed.has_pos
    assert parsed.variants
    evidence, features = _selected_tail_structure_evidence(settings, parsed)
    assert evidence == ("variant",)
    assert features["available_pos"] is True
    assert features["selected_pos"] is False
    assert features["selected_variant"] is True


def test_complete_headword_structure_round_trips_in_v3_sidecar(tmp_path):
    path = tmp_path / "dictionary_profile.json"
    settings = AppSettings(
        dictionary_profile_id="latin_regular",
        ocr_language="ita",
        profile_parser_controls_version=1,
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=True,
        profile_allow_ordinary_left_edge=True,
        profile_allow_numbered_prefix=False,
        profile_allow_marker_prefix=True,
        profile_cjk_allow_single_headword=False,
        profile_cjk_allow_bracketed_headword=False,
        profile_tail_structure_version=1,
        profile_tail_allow_pos=True,
        profile_tail_allow_inflection=False,
        profile_tail_allow_variant=True,
        profile_tail_allow_pronunciation=True,
        profile_tail_allow_descriptor=False,
        profile_tail_require_selected=True,
        profile_tail_allow_visual_rescue=True,
        profile_symbol_inventory_version=1,
        profile_symbol_inventory_enabled=True,
        profile_entry_marker_symbols="◆ ◇",
        profile_bracket_open_symbols="",
        profile_symbol_visual_rescue_enabled=True,
        profile_symbol_lane_required=True,
        profile_symbol_lane_tolerance_percent=45,
    )
    write_project_profile(path, settings, "latin_regular", force=True)
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))
    assert payload["headword_structure"]["tail"]["allow_pronunciation"] is True
    assert payload["headword_structure"]["script_guard_enabled"] is True
    assert payload["headword_structure"]["starts"]["marker_prefix"] is True
    assert payload["headword_structure"]["symbol_inventory"]["entry_markers"] == "◆ ◇"

    restored = AppSettings()
    apply_project_profile_components(path, restored)
    assert restored.profile_headword_script_guard_version == 1
    assert restored.profile_headword_script_guard_enabled is True
    assert restored.profile_tail_structure_version == 1
    assert restored.profile_tail_allow_pos is True
    assert restored.profile_tail_allow_inflection is False
    assert restored.profile_tail_allow_variant is True
    assert restored.profile_tail_allow_pronunciation is True
    assert restored.profile_tail_allow_descriptor is False
    assert restored.profile_tail_require_selected is True
    assert restored.profile_tail_allow_visual_rescue is True
    assert restored.profile_allow_marker_prefix is True
    assert restored.profile_entry_marker_symbols == "◆ ◇"


def test_profile_setup_exposes_complete_headword_structure_controls():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "profile_setup.py"
    )
    text = source.read_text(encoding="utf-8")
    assert "完整词头结构（词头前 + 词头本体 + 词头后）" in text
    assert "按 OCR 语言排除不兼容的词头首字符（推荐）" in text
    assert "日语允许汉字/假名，中文允许汉字" in text
    assert "profile_headword_script_guard_version = 1" in text
    assert "词头后结构（哪些内容可以作为新词条证据）" in text
    assert "词性 POS（s.m. / v.tr. / agg. / adj. …）" in text
    assert "词形 / 屈折变化" in text
    assert "变体 / 性数变化" in text
    assert "发音 / 音标" in text
    assert "描述型结构" in text
    assert "普通左缘词至少需要命中一种上面勾选的词后结构" in text
    assert "允许“严格左缘 + 粗体”视觉补救" in text
    assert "不再另设隐藏的粗体/行高门槛" in text
    assert "profile_tail_structure_version = 1" in text


def test_latin_regular_italian_pos_labels_tolerate_ocr_dot_spacing():
    settings = AppSettings(
        ocr_language="ita",
        profile_parser_controls_version=1,
        profile_allow_ordinary_left_edge=True,
    )
    profile = load_dictionary_profile(preset="latin_regular", language="ita")
    patterns = _compile_patterns(settings, profile)
    examples = (
        "abbassare v. tr. abbassare qualcosa",
        "abbarbagliare vtr. la mente",
        "abbandono s. m. stato di abbandono",
        "abbattere v. intr. forma rara",
    )
    for text in examples:
        parsed = parse_headword_text(text, settings, patterns, profile)
        assert parsed is not None, text
        assert parsed.has_pos, text


def test_latin_regular_profile_enables_conservative_strong_edge_visual_rescue():
    settings = AppSettings(ocr_language="ita")
    apply_headword_profile(settings, "latin_regular")
    assert settings.paddle_require_pos_or_symbol is True
    assert settings.paddle_allow_strong_edge_visual_rescue is True
    assert settings.paddle_strong_edge_visual_boldness_ratio == 1.22
    assert settings.paddle_strong_edge_visual_height_ratio == 0.90


def test_explicit_tail_visual_rescue_uses_visible_profile_thresholds_only():
    settings = AppSettings(
        ocr_language="ita",
        profile_tail_structure_version=1,
        profile_tail_allow_visual_rescue=True,
        paddle_boldness_ratio=1.00,
        paddle_rec_score_threshold=0.20,
        # Deliberately impossible legacy thresholds: explicit Profile mode must
        # ignore them instead of silently overriding the visible UI.
        paddle_strong_edge_visual_boldness_ratio=2.80,
        paddle_strong_edge_visual_height_ratio=2.20,
        paddle_strong_edge_visual_min_confidence=0.99,
    )
    profile = load_dictionary_profile(preset="latin_regular", language="ita")
    patterns = _compile_patterns(settings, profile)
    parsed = parse_headword_text(
        "addomesticare vti. addomesticare qualcosa",
        settings,
        patterns,
        profile,
    )
    assert parsed is not None
    assert not parsed.has_pos

    thresholds = _ordinary_visual_rescue_thresholds(settings)
    assert thresholds["source"] == "visible_profile_specificity"
    assert thresholds["boldness"] == 1.00
    assert thresholds["height"] == 0.0
    assert thresholds["confidence"] == 0.20

    assert _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.04,
        height_ratio=0.78,
        confidence=0.85,
        looks_like_continuation=False,
        marker_noise=False,
    )

    # Raising the visible UI boldness threshold must immediately tighten the
    # same rescue path; no second hidden threshold participates.
    settings.paddle_boldness_ratio = 1.10
    assert not _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.04,
        height_ratio=1.10,
        confidence=0.85,
        looks_like_continuation=False,
        marker_noise=False,
    )
    assert _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.12,
        height_ratio=0.78,
        confidence=0.85,
        looks_like_continuation=False,
        marker_noise=False,
    )


def test_strong_edge_visual_rescue_recovers_pos_ocr_failure_but_not_body_text():
    settings = AppSettings(
        ocr_language="ita",
        paddle_allow_strong_edge_visual_rescue=True,
        paddle_strong_edge_visual_boldness_ratio=1.22,
        paddle_strong_edge_visual_height_ratio=0.90,
        paddle_strong_edge_visual_min_confidence=0.55,
        paddle_boldness_ratio=1.12,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(preset="latin_regular", language="ita")
    patterns = _compile_patterns(settings, profile)
    parsed = parse_headword_text(
        "abbarbagliamento sim. 眩眼，迷乱",
        settings,
        patterns,
        profile,
    )
    assert parsed is not None
    assert not parsed.has_pos

    assert _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.34,
        height_ratio=0.96,
        confidence=0.91,
        looks_like_continuation=False,
        marker_noise=False,
    )
    assert not _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.08,
        height_ratio=0.96,
        confidence=0.91,
        looks_like_continuation=False,
        marker_noise=False,
    )
    assert not _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.34,
        height_ratio=0.96,
        confidence=0.91,
        looks_like_continuation=True,
        marker_noise=False,
    )
    assert not _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=False,
        below_header=True,
        boldness_ratio=1.34,
        height_ratio=0.96,
        confidence=0.91,
        looks_like_continuation=False,
        marker_noise=False,
    )


def test_visual_marker_symbol_inventory_accepts_contiguous_input():
    expected = ("●", "○", "◉", "◯")
    assert split_configured_symbols("●○◉◯") == expected
    assert split_configured_symbols("● ○ ◉ ◯") == expected
    assert split_configured_symbols("●,○,◉,◯") == expected
    assert split_configured_symbols("●，○，◉，◯") == expected
    assert split_configured_symbols("ABC") == ("ABC",)


def test_visual_marker_templates_round_trip_with_project_settings(tmp_path):
    image = Image.new("L", (36, 36), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((7, 7, 28, 28), outline=0, width=4)
    sample = build_visual_marker_sample(
        image,
        role="entry_marker",
        literal="○",
        sample_id="entry:test",
        source_page="0023.png",
        source_box=(10, 20, 46, 56),
    )
    settings = AppSettings(
        profile_symbol_template_version=1,
        profile_symbol_template_mode="combined",
        profile_symbol_template_group_mode="role",
        profile_symbol_template_threshold=0.68,
        profile_symbol_templates_json=serialize_visual_marker_samples([sample]),
    )
    path = tmp_path / "settings.json"
    settings.to_json(path)
    reopened = AppSettings.from_json(path)
    samples = parse_visual_marker_samples(reopened.profile_symbol_templates_json)
    assert reopened.profile_symbol_template_version == 1
    assert reopened.profile_symbol_template_mode == "combined"
    assert len(samples) == 1
    assert samples[0]["literal"] == "○"
    assert samples[0]["source_page"] == "0023.png"
    assert samples[0]["source_box"] == [10, 20, 46, 56]


def test_dictionary_visual_template_matches_scan_variation():
    reference = Image.new("L", (40, 40), 255)
    draw = ImageDraw.Draw(reference)
    draw.ellipse((8, 8, 31, 31), outline=0, width=4)
    sample = build_visual_marker_sample(
        reference, role="entry_marker", literal="○", sample_id="ring"
    )

    candidate = Image.new("L", (42, 42), 255)
    draw = ImageDraw.Draw(candidate)
    draw.ellipse((8, 9, 33, 34), outline=0, width=5)
    candidate_mask = np.asarray(candidate, dtype=np.uint8) < 128
    match = match_visual_marker_template(candidate_mask, [sample])
    assert match is not None
    assert float(match["score"]) >= 0.55
    assert match["sample"]["id"] == "ring"


def test_visual_marker_detector_can_use_dictionary_template_without_generic_family():
    reference = Image.new("L", (24, 24), 255)
    draw = ImageDraw.Draw(reference)
    draw.ellipse((4, 4, 19, 19), outline=0, width=3)
    sample = build_visual_marker_sample(
        reference, role="entry_marker", literal="○", sample_id="ring"
    )

    page = Image.new("L", (90, 120), 255)
    draw = ImageDraw.Draw(page)
    draw.ellipse((6, 46, 21, 61), outline=0, width=3)
    markers = _detect_visual_entry_markers(
        np.asarray(page, dtype=np.uint8),
        18.0,
        24,
        lower_bound=0,
        inventory={
            "enabled": True,
            "entry_markers": ("○",),
            "bracket_openers": (),
            "visual_rescue": True,
            "lane_required": False,
            "lane_tolerance_percent": 50,
            "visual_families": (),
            "visual_templates": [sample],
            "visual_template_mode": "template_first",
            "visual_template_threshold": 0.50,
        },
    )
    assert markers
    assert markers[0]["family"] == "dictionary_template"
    assert markers[0]["role"] == "entry_marker"
    assert markers[0]["symbol"] == "○"
    assert float(markers[0]["template_score"]) >= 0.50


def test_visual_marker_capture_uses_source_pixel_zoom_controls():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "visual_marker_ui.py"
    )
    text = source.read_text(encoding="utf-8")
    assert "self.zoom_percent = 100" in text
    assert 'text="图片缩放（默认 100% 原始像素）："' in text
    assert 'text="100%", command=lambda: self._set_zoom(100)' in text
    assert 'text="适合窗口", command=self._fit_window' in text
    assert '"<Control-MouseWheel>"' in text
    assert "self.canvas.canvasx(event.x)" in text
    assert "self.canvas.canvasy(event.y)" in text
    assert 'orient="horizontal", command=self.canvas.xview' in text
    assert 'orient="vertical", command=self.canvas.yview' in text
    assert "self.selection_source = source_box" in text
    assert "当前缩放 {self.zoom_percent}%" in text


def test_project_profile_column_left_nudges_persist_and_drive_geometry(tmp_path):
    settings = AppSettings(
        columns=2,
        manual_x=40,
        column_width=300,
        gutter=40,
        column_start_offsets=[0, 12],
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(800, 1000, settings)
    assert geometry.column_starts == [40, 392]

    # Version-3 values are literal image pixels. A wider image must not silently
    # double the user's X positions or per-column corrections.
    larger = derive_nominal_geometry(1600, 2000, settings)
    assert larger.column_starts == [40, 392]

    path = tmp_path / "settings.json"
    settings.to_json(path)
    saved = path.read_text(encoding="utf-8")
    reopened = AppSettings.from_json(path)
    assert reopened.column_start_offsets == [0, 12]
    # Corrupt/extreme nudges are clipped before columns can cross.
    guarded = apply_column_start_offsets(
        [40, 380], [250, -250], gutter=40, max_x=799,
    )
    assert guarded[0] < guarded[1]
    assert guarded[1] - guarded[0] >= 50


def test_source_pixel_settings_never_scale_against_page_width():
    settings = AppSettings(
        paddle_left_tolerance=34,
        paddle_separator_safety_px=2,
    )
    assert settings.paddle_left_tolerance == 34
    assert settings.paddle_separator_safety_px == 2
    geometry_1400 = derive_nominal_geometry(1400, 1800, settings)
    geometry_4200 = derive_nominal_geometry(4200, 5400, settings)
    assert geometry_1400.column_starts[0] == geometry_4200.column_starts[0]
    assert geometry_1400.top == geometry_4200.top

def test_project_profile_exposes_clickable_column_left_line_nudging():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "profile_setup.py"
    text = source.read_text(encoding="utf-8")
    assert 'text="栏左线微调"' in text
    assert "点击右侧预览中的栏左线选择；选中线显示为橙色" in text
    assert "每次移动 1 个原图 px" in text
    assert 'text="← 左移"' in text
    assert 'text="右移 →"' in text
    assert 'text="重置当前"' in text
    assert 'text="重置全部"' in text
    assert "def _shift_selected_column" in text
    assert "self.working.column_start_offsets = offsets" in text
    assert "s.column_start_offsets = self._column_offsets_for_count(s.columns)" in text
    assert 'canvas.bind(\n                "<Button-1>"' in text
    assert 'fill="#ee7c00" if column_index == selected_column else "#1e78d2"' in text
    assert "self.working.column_start_offsets = [0] * max(1, int(self.columns_var.get()))" in text
    assert "def _nudge_template_column_preview" in text
    assert "canvas.move(items[index], dx, dy)" in text
    assert "self._profile_input_changed(refresh_preview=False)" in text
    select_start = text.index("    def _select_template_column(")
    select_end = text.index("\n\n    def _refresh_template_controls", select_start)
    assert "_refresh_template_preview" not in text[select_start:select_end]
    assert "self._update_template_column_highlight()" in text[select_start:select_end]
    assert "canvas.create_image(0, 0, image=photo, anchor=\"nw\")" in text


def test_project_profile_validation_masks_remain_translucent():
    from picture_capture.processing import ColumnPath, Geometry
    from picture_capture.profile_setup import ProjectProfileWizard

    image = Image.new("RGB", (100, 100), "white")
    geometry = Geometry(
        column_starts=[10], column_widths=[80], top=20, bottom=100,
        column_paths=[ColumnPath([(20, 10), (100, 10)])],
    )
    settings = AppSettings(
        profile_header_mode="present", profile_header_percent=20.0,
        profile_footer_mode="none", profile_side_content_mode="none",
    )
    preview = ProjectProfileWizard._marker_preview(
        image, [], geometry, settings, 0, 100,
    )
    pixel = preview.getpixel((50, 10))
    assert pixel != (255, 215, 0)
    assert pixel != (255, 255, 255)
    assert pixel[0] == 255 and 215 < pixel[1] < 255 and 0 < pixel[2] < 255



def test_project_profile_wizard_is_the_normal_entry_path():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert "ProjectProfileWizard(self, new_project=new_project)" in text
    assert "launch_profile_setup=not existing_project" in text

    profile_source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "profile_setup.py"
    ).read_text(encoding="utf-8")
    wizard_start = profile_source.index("class ProjectProfileWizard(tk.Toplevel):")
    wizard_end = profile_source.index("    def _build_vars(self) -> None:", wizard_start)
    wizard_init = profile_source[wizard_start:wizard_end]
    assert "x = work_x + max(0, (work_w - width) // 2)" in wizard_init
    assert "y = work_y + max(0, (work_h - height) // 2)" in wizard_init
    assert '(common_tab, "常用")' in text
    assert '(ocr_tab, "OCR画线（推荐）")' in text
    assert '(normal_tab, "普通画线（备用）")' in text
    assert text.index('(ocr_tab, "OCR画线（推荐）")') < text.index('(normal_tab, "普通画线（备用）")')
    assert '(advanced_tab, "高级")' in text
    assert '"profile": advanced_tab' in text
    start = text.index("    def open_project_profile(")
    end = text.index("    def open_project_details(", start)
    assert 'self.open_settings(initial_tab="profile")' not in text[start:end]


def test_main_ocr_drawing_defaults_to_cache_reuse_and_paddle_only():
    app_source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    app_text = app_source.read_text(encoding="utf-8")
    assert 'self.ocr_refresh_var = tk.StringVar(value="reuse")' in app_text
    assert "使用有效缓存（推荐）" in app_text
    assert "重新OCR（模型/图像改变时）" in app_text
    assert "默认只启用 PaddleOCR；Tesseract 与 Google Lens 按需手动开启" in app_text
    assert 'LENS_MODE_LABELS["off"]' in app_text

    settings = AppSettings()
    assert settings.paddle_use_paddleocr is True
    assert settings.paddle_compare_tesseract is False
    assert settings.paddle_enable_lens is False
    assert settings.paddle_lens_mode == "off"

def test_ordinary_drawing_uses_shared_threshold_policy():
    import numpy as np

    gray = np.array([
        [30, 90, 150, 230],
        [40, 100, 160, 240],
        [50, 110, 170, 250],
        [60, 120, 180, 245],
    ], dtype=np.uint8)
    fixed = _left_edge_ink_mask(
        gray, AppSettings(analysis_threshold_mode="fixed", darkness_threshold=300)
    )
    assert fixed.dtype == bool and fixed.shape == gray.shape
    assert fixed[0, 0] and fixed[0, 1]
    assert not fixed[1, 1] and not fixed[0, 2]

    auto = _left_edge_ink_mask(gray, AppSettings(analysis_threshold_mode="auto"))
    adaptive = _left_edge_ink_mask(gray, AppSettings(analysis_threshold_mode="adaptive"))
    assert auto.dtype == bool and adaptive.dtype == bool
    processing_source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "processing.py"
    ).read_text(encoding="utf-8")
    start = processing_source.index("def _detect_entries_left_edge(")
    end = processing_source.index("\ndef detect_entries(", start)
    assert "dark = _left_edge_ink_mask(gray, settings)" in processing_source[start:end]
    assert "density_floor" in processing_source[start:end]


def test_analysis_threshold_modes_are_effective():
    import numpy as np

    gray = np.array([
        [40, 80, 140, 220],
        [50, 90, 150, 230],
        [60, 100, 160, 240],
        [70, 110, 170, 250],
    ], dtype=np.uint8)
    fixed = _analysis_ink_mask(gray, AppSettings(analysis_threshold_mode="fixed", darkness_threshold=300))
    # RGB-sum threshold 300 corresponds to grayscale threshold 100.
    assert fixed[0, 0] and fixed[1, 1]
    assert not fixed[2, 1] and not fixed[0, 2]

    auto = _analysis_ink_mask(gray, AppSettings(analysis_threshold_mode="auto"))
    otsu = _analysis_ink_mask(gray, AppSettings(analysis_threshold_mode="otsu"))
    assert np.array_equal(auto, otsu)
    adaptive = _analysis_ink_mask(gray, AppSettings(analysis_threshold_mode="adaptive"))
    assert adaptive.shape == gray.shape and adaptive.dtype == bool


def test_sidecar_only_v3_project_restores_components(tmp_path):
    root = tmp_path / "sidecar"
    root.mkdir()
    Image.new("RGB", (8, 8), "white").save(root / "1.jpg")
    # First opening creates the managed storage; remove settings to emulate a
    # sidecar-only migration project.
    ProjectState.open(root)
    settings_path(root).unlink(missing_ok=True)
    profile_path(root).write_text(
        '{"format":"picture-capture-dictionary-profile-v3","preset":"cjk_bracket_display",'
        '"layout":{"writing_mode":"vertical-rl","text_direction":"rtl","columns":3,'
        '"columns_policy":"fixed","column_separator":"absent","analysis_threshold_mode":"fixed"},'
        '"ocr":{"semantic_language":"jpn","paddle_language":"japan",'
        '"tesseract_language":"jpn","use_textline_orientation":true}}',
        encoding="utf-8",
    )
    restored = ProjectState.open(root).settings
    assert restored.layout_writing_mode == "vertical-rl"
    assert restored.layout_text_direction == "rtl"
    assert restored.layout_transform == "rotate_ccw90"
    assert restored.columns == 3
    assert restored.layout_columns_policy == "fixed"
    assert restored.layout_column_separator_mode == "absent"
    assert restored.analysis_threshold_mode == "fixed"
    assert restored.ocr_language == "jpn"
    assert restored.tesseract_language == "jpn"
    assert restored.paddle_use_textline_orientation is True


def test_numbered_profile_accepts_three_and_four_digit_prefixes():
    profile = load_dictionary_profile(preset="numbered_prefix", language="eng")
    settings = AppSettings(ocr_language="eng")
    for text, expected in (
        ("100. anniversary", "anniversary"),
        ("1234. word", "word"),
        ("100 word", "word"),
    ):
        parsed = parse_headword_text(text, settings, profile=profile)
        assert parsed is not None and parsed.normalized == expected


def test_vertical_main_editor_is_a_real_text_widget_not_a_canvas_proxy():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _draw_entry_overlay(")
    end = text.index("    def _remove_entry_overlay(", start)
    block = text[start:end]

    assert "VerticalWordText(" in block
    assert 'cursor="xterm"' in block
    assert "window=editor" in block
    assert "width=vertical_box[2] - vertical_box[0]" in block
    assert "height=vertical_box[3] - vertical_box[1]" in block
    assert "vertical_ocr_menu_layout(" in block
    assert "vertical_overlay_layout(" in block

    # The old non-editable proxy/popup architecture must not return.
    assert "proxy_box_item" not in block
    assert "label_item" not in block
    assert "open_vertical_editor" not in block
    assert "_suppress_next_canvas_left_click" not in text
    assert 'if rtl:\n            editor.configure(justify="right")' in block


def test_round1_blocking_ui_paths_use_background_workers():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")

    assert "def _start_ui_worker(" in text
    assert "self._ui_worker_queue.put(event)" in text
    assert "def _poll_ui_worker_queue(" in text

    settings_start = text.index("class SettingsDialog")
    settings_check = text.index("    def check_ocr_engines(self) -> None:", settings_start)
    settings_check_end = text.index("\n\ndef _review_window_dimensions", settings_check)
    settings_block = text[settings_check:settings_check_end]
    assert "self.parent.show_environment_center()" in settings_block

    app_start = text.index("class PictureCaptureApp")
    main_check = text.index("    def check_ocr_engines(self) -> None:", app_start)
    main_check_end = text.index("\n    def detect_layout_current", main_check)
    assert "self.show_environment_center()" in text[main_check:main_check_end]

    environment_center = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "environment_center.py"
    ).read_text(encoding="utf-8")
    refresh_start = environment_center.index("    def refresh(self) -> None:")
    refresh_end = environment_center.index("\n    def _open_ocr_settings", refresh_start)
    refresh = environment_center[refresh_start:refresh_end]
    assert "def worker():" in refresh
    assert 'self.app._start_ui_worker(f"environment-center-' in refresh

    page_request = text.index("    def _request_page_load(", app_start)
    page_load = text.index("    def load_page(", page_request)
    page_block = text[page_request:page_load]
    assert "with Image.open(page) as opened:" in page_block
    assert 'self._start_ui_worker("page-load"' in page_block
    select_start = text.index("    def on_page_select(", app_start)
    assert "self._request_page_load(index)" in text[select_start:page_request]

    project_start = text.index("    def _load_project(", app_start)
    project_end = text.index("\n    def on_page_select", project_start)
    project_block = text[project_start:project_end]
    worker_pos = project_block.index("        def worker():")
    done_pos = project_block.index("        def done(result)")
    assert worker_pos < project_block.index("migrate_legacy_project(", worker_pos) < done_pos
    assert worker_pos < project_block.index("ProjectState.open(root)", worker_pos) < done_pos
    assert worker_pos < project_block.index("with Image.open(page) as opened:", worker_pos) < done_pos
    assert "self._start_ui_worker(" in project_block
    assert '"project-load", worker, done, failed, wait_on_close=True' in project_block

    recent_start = text.index("    def open_recent_project(", app_start)
    recent_end = text.index("\n    @staticmethod\n    def _attach_tooltip", recent_start)
    recent_block = text[recent_start:recent_end]
    rebuild_start = recent_block.index("        def rebuild(")
    refresh_start = recent_block.index("        def refresh_recent_data(")
    rebuild_block = recent_block[rebuild_start:refresh_start]
    assert "recent_project_details(" not in rebuild_block
    assert "Image.open(" not in rebuild_block
    assert "recent_project_details(row)" in recent_block[refresh_start:]
    assert "with Image.open(preview_path) as opened:" in recent_block[refresh_start:]

    picdic_start = text.index("    def build_picdic(", app_start)
    picdic_end = text.index("\n    def _order_key", picdic_start)
    picdic_block = text[picdic_start:picdic_end]
    assert "self._start_batch_task(" in picdic_block
    assert "should_stop=self._batch_stop_event.is_set" in picdic_block


def test_round1_picdic_cancel_is_atomic(tmp_path):
    root = tmp_path / "dictionary"
    pww = qt_root(root) / "PWW"
    pww.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(pww / "0001_0001.png")
    (pww / "0001.PWWords").write_text(
        "0001|1|alpha|0001_0001.png\n", encoding="utf-8"
    )

    try:
        build_picdic_package(root, should_stop=lambda: True)
    except PicDicBuildCancelled:
        pass
    else:
        raise AssertionError("expected cooperative PicDic cancellation")

    out = qt_root(root) / "PicDic"
    assert not list(out.glob("*.tmp")) if out.exists() else True
    assert not list(out.glob("*.dsl")) if out.exists() else True
    assert not list(out.glob("*.zip")) if out.exists() else True



def test_round2_heavy_finalizers_and_review_crops_stay_off_tk():
    root = Path(__file__).resolve().parents[1]
    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile_text = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")

    app_start = app_text.index("class PictureCaptureApp")
    training_start = app_text.index("    def export_training_package(", app_start)
    training_end = app_text.index("\n    def show_help_dialog", training_start)
    training = app_text[training_start:training_end]
    assert 'items: list[object] = ["__prepare__"]' in training
    assert "context_files[:] = copy_project_context(project.root, staging)" in training
    assert "make_training_zip(" in training
    assert "should_stop=self._batch_stop_event.is_set" in training
    assert "shutil.rmtree(staging, ignore_errors=True)" in training
    done_start = training.index("        def done(")
    done = training[done_start:]
    assert "shutil.rmtree(staging, ignore_errors=True)" not in done
    assert 'self._start_ui_worker(' in done

    layout_start = app_text.index("    def detect_layout_consistency_selected(", app_start)
    layout_end = app_text.index("\n    @staticmethod\n    def _normalize_suffix", layout_start)
    layout = app_text[layout_start:layout_end]
    done_start = layout.index("        def done(")
    layout_done = layout[done_start:]
    assert "def finalize_report():" in layout_done
    assert 'self._start_ui_worker(' in layout_done
    finalized_start = layout_done.index("        def finalized(")
    ui_finalized = layout_done[finalized_start:]
    assert 'target.open("w"' not in ui_finalized
    assert "statistics.fmean(" not in ui_finalized

    review_start = app_text.index("class ReviewWindow")
    review_end = app_text.index("class OCRConflictReviewDialog", review_start)
    review = app_text[review_start:review_end]
    request_start = review.index("    def _request_render_rows(")
    render_start = review.index("    def render_rows(", request_start)
    render_end = review.index("\n    def _candidate_for_entry", render_start)
    request = review[request_start:render_start]
    render = review[render_start:render_end]
    assert "with Image.open(page) as opened:" in request
    assert "Image.Resampling.LANCZOS" in request
    assert "self.parent._start_ui_worker(" in request
    assert "Image.Resampling.LANCZOS" not in render
    assert "_review_line_box(" not in render
    assert "ImageTk.PhotoImage(themed_display_image(crop, self.parent.appearance_mode))" in render
    assert "self.render_rows()" not in review

    preview_start = profile_text.index("    def _refresh_template_preview(")
    preview_end = profile_text.index("\n    @staticmethod\n    def _mode_row", preview_start)
    preview = profile_text[preview_start:preview_end]
    assert "with Image.open(path) as opened:" in preview
    assert "derive_geometry(" in preview
    assert "self.parent._start_ui_worker(" in preview
    worker_start = preview.index("        def worker():")
    done_start = preview.index("        def done(", worker_start)
    worker = preview[worker_start:done_start]
    assert "ImageTk.PhotoImage" not in worker
    assert "themed_display_image(" in preview[done_start:]
    assert 'preview, getattr(self.parent, "appearance_mode", "light")' in preview[done_start:]


def test_round2_training_zip_cancel_is_atomic(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "dataset_manifest.json").write_text("{}", encoding="utf-8")
    (staging / "large.bin").write_bytes(b"x" * 1024)
    target = tmp_path / "training.zip"

    try:
        make_training_zip(staging, target, should_stop=lambda: True)
    except TrainingExportCancelled:
        pass
    else:
        raise AssertionError("expected cooperative training ZIP cancellation")

    assert not target.exists()
    assert not target.with_name(f".{target.name}.tmp").exists()



def test_round3_long_tail_ui_paths_are_backgrounded_and_snapshotted():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    app_start = text.index("class PictureCaptureApp")

    reload_start = text.index("    def _request_wordslist_reload(", app_start)
    reload_end = text.index("\n    def open_recent_project", reload_start)
    reload_block = text[reload_start:reload_end]
    assert "read_noncomment_lines(path)" in reload_block
    assert 'self._start_ui_worker("wordslist-reload"' in reload_block

    settings_start = text.index("class SettingsDialog")
    settings_end = text.index("class ReviewWindow", settings_start)
    settings = text[settings_start:settings_end]
    assert "self.parent._request_wordslist_reload(persist=False, redraw=False)" in settings

    review_start = text.index("class ReviewWindow")
    review_end = text.index("class OCRConflictReviewDialog", review_start)
    review = text[review_start:review_end]
    assert "self.parent._request_wordslist_reload(" in review
    assert "reload_wordslist_reference(Path(chosen)" not in review

    order_start = text.index("    def check_headword_order(", app_start)
    order_end = text.index("\n    def _show_text_report", order_start)
    order = text[order_start:order_end]
    all_pages_branch = order[order.index("        if all_pages:"):]
    assert 'self._start_batch_task(' in all_pages_branch
    assert '"所有词头顺序核对"' in all_pages_branch
    assert 'self._start_ui_worker(' in all_pages_branch
    assert '"headword-order-finalize"' in all_pages_branch
    worker_start = all_pages_branch.index("            def worker(")
    worker_done = all_pages_branch.index("            def done(", worker_start)
    worker = all_pages_branch[worker_start:worker_done]
    assert "read_pdic(pdic_path(page))" in worker
    assert "self.settings" not in worker
    finalize_start = all_pages_branch.index("                def finalize():")
    finalized_start = all_pages_branch.index("                def finalized(", finalize_start)
    finalize = all_pages_branch[finalize_start:finalized_start]
    assert "sorted(sequence" in finalize

    for name, next_name in (
        ("auto_detect_current", "paddle_detect_current"),
        ("ocr_current", "export_text"),
        ("split_lines_current", "split_whole_current"),
        ("split_whole_current", "_crop_settings_defaults"),
        ("import_legacy_words", "_default_old_new_compare_source"),
    ):
        start = text.index(f"    def {name}(", app_start)
        end = text.index(f"\n    def {next_name}(", start)
        block = text[start:end]
        assert "self._start_batch_task(" in block

    fill_start = text.index("    def fill_existing_headwords(", app_start)
    fill_end = text.index("\n    def import_legacy_words", fill_start)
    fill = text[fill_start:fill_end]
    ensure_start = fill.index("        def ensure_mapping()")
    worker_start = fill.index("        def worker(", ensure_start)
    ensure = fill[ensure_start:worker_start]
    assert "self._word_fill_source_mapping =" not in ensure
    assert "settings_snapshot = replace(self.settings)" in fill
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in fill
    done_start = fill.index("        def done(", worker_start)
    assert "self._word_fill_source_mapping = mapping" in fill[done_start:]

    prefetch_start = review.index("    def _schedule_adjacent_preload(")
    prefetch_end = review.index("\n    def change_page(", prefetch_start)
    prefetch = review[prefetch_start:prefetch_end]
    worker_start = prefetch.index("            def worker(")
    worker = prefetch[worker_start:]
    assert "local_anchor_index=anchor_index" in worker
    assert "self.parent.current_index" not in worker
    assert "self.parent._ppp_read_path" not in worker


def test_round3_wordslist_stream_reader_supports_legacy_encodings(tmp_path):
    from picture_capture.models import read_noncomment_lines

    samples = {
        "utf8.txt": ("alpha\n'comment\nβeta\n", "utf-8"),
        "utf16.txt": ("繁體\n詞條\n", "utf-16"),
        "gb.txt": ("简体\n词条\n", "gb18030"),
        "big5.txt": ("繁體\n詞條\n", "big5"),
    }
    for name, (content, encoding) in samples.items():
        path = tmp_path / name
        path.write_bytes(content.encode(encoding))
        expected = [
            line for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("'")
        ]
        assert read_noncomment_lines(path) == expected


def test_round3_wordslist_reader_does_not_materialize_full_text_source():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "models.py"
    ).read_text(encoding="utf-8")
    start = source.index("def read_noncomment_lines(")
    block = source[start:]
    assert "iter_text_lines_detected" in block
    assert "read_text_detected" not in block
    assert ".splitlines()" not in block



def test_concurrency_atomic_text_replace_failure_preserves_previous_file(tmp_path, monkeypatch):
    import pytest
    import picture_capture.formats as formats

    target = tmp_path / "page.pdic"
    target.write_text("old-complete\n", encoding="utf-8")
    original_replace = formats.os.replace

    def fail_publish(src, dst):
        if Path(dst) == target:
            raise OSError("injected replace failure")
        return original_replace(src, dst)

    monkeypatch.setattr(formats.os, "replace", fail_publish)
    with pytest.raises(OSError, match="injected replace failure"):
        formats.write_text_atomic(target, "new-complete\n")

    assert target.read_text(encoding="utf-8") == "old-complete\n"
    assert not list(tmp_path.glob(".page.pdic.*.tmp"))


def test_concurrency_picdic_pair_rolls_back_when_second_publish_fails(tmp_path, monkeypatch):
    import pytest
    import picture_capture.picdic as picdic

    root = tmp_path / "dictionary"
    pww = qt_root(root) / "PWW"
    pww.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(pww / "0001_0001.png")
    (pww / "0001.PWWords").write_text(
        "0001|1|alpha|0001_0001.png\n", encoding="utf-8"
    )

    out = qt_root(root) / "PicDic"
    out.mkdir(parents=True)
    dsl = out / "PicDic_dictionary.dsl"
    archive = out / "PicDic_dictionary.dsl.files.zip"
    dsl.write_text("old-dsl", encoding="utf-8")
    archive.write_bytes(b"old-zip")

    original_replace = picdic.os.replace

    def fail_second_publish(src, dst):
        src_path = Path(src)
        dst_path = Path(dst)
        if dst_path == archive and src_path.suffix == ".tmp":
            raise OSError("injected zip publish failure")
        return original_replace(src, dst)

    monkeypatch.setattr(picdic.os, "replace", fail_second_publish)
    with pytest.raises(OSError, match="injected zip publish failure"):
        picdic.build_picdic_package(root)

    assert dsl.read_text(encoding="utf-8") == "old-dsl"
    assert archive.read_bytes() == b"old-zip"
    assert not list(out.glob("*.tmp"))
    assert not list(out.glob("*.bak"))


def test_concurrency_review_tracks_critical_workers_and_stale_results():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")

    worker_start = app.index("    def _ui_worker_key_active(")
    worker_end = app.index("\n    def _configure_main_workspace_styles", worker_start)
    workers = app[worker_start:worker_end]
    assert "_ui_worker_active" in workers
    assert "_ui_worker_close_wait" in workers
    assert "generation == self._ui_worker_generations.get(key)" in workers
    assert "not self._ui_close_requested" in workers
    assert "self._ui_worker_active.discard(token)" in workers
    assert "self._ui_worker_close_wait.discard(token)" in workers
    assert "if self._ui_close_requested and not self._ui_worker_close_wait:" in workers

    close_start = app.index("    def on_close(")
    close_end = app.index("\n    def _build_ui", close_start)
    close = app[close_start:close_end]
    assert "if self._ui_worker_close_wait:" in close
    assert "self.withdraw()" in close
    assert "正在完成后台文件操作" in close

    project_start = app.index("    def _load_project(")
    project_end = app.index("\n    def on_page_select", project_start)
    project = app[project_start:project_end]
    assert 'self._ui_worker_key_active("project-load")' in project
    assert 'self._ui_worker_key_active("profile-validation")' in project
    assert 'wait_on_close=True' in project

    sequential = app[app.index("    def _start_batch_task("):app.index("    def _start_parallel_batch_task(")]
    parallel = app[app.index("    def _start_parallel_batch_task("):app.index("    def _poll_batch_queue(")]
    for block in (sequential, parallel):
        assert 'self._ui_worker_key_active("project-load")' in block
        assert 'self._ui_worker_key_active("profile-validation")' in block
        assert "self._ui_close_requested" in block

    validate_start = profile.index("    def validate_profile(")
    validate_end = profile.index("\n    def _poll_validation_queue", validate_start)
    validate = profile[validate_start:validate_end]
    assert 'self.parent._start_ui_worker(' in validate
    assert '"profile-validation"' in validate
    assert "wait_on_close=True" in validate
    assert "stop_event.is_set()" in validate
    assert "self.project.images[index]" not in validate[validate.index("        def worker():"):]

    close_profile = profile[profile.index("    def _close_without_save("):]
    assert "self._validation_close_requested = True" in close_profile
    assert "self._validation_stop_event.set()" in close_profile
    assert "正在安全结束当前测试页" in close_profile


def test_concurrency_review_atomic_ocr_cache_and_timeouts_are_enforced():
    root = Path(__file__).resolve().parents[1]
    paddle = (root / "src" / "picture_capture" / "paddle_headwords.py").read_text(encoding="utf-8")
    processing = (root / "src" / "picture_capture" / "processing.py").read_text(encoding="utf-8")

    assert "_QUALITY_SUMMARY_LOCK = threading.Lock()" in paddle
    assert "with _QUALITY_SUMMARY_LOCK:" in paddle
    assert "_atomic_write_json(cache_path, payload)" in paddle
    for suffix in (
        "_ocr_diagnostics.txt", "_ocr_comparison.txt", "_issues.tsv",
        "_ocr_engines.tsv", "_fusion.tsv",
    ):
        assert suffix in paddle
    assert "timeout=120" in paddle
    assert "except subprocess.TimeoutExpired" in paddle
    assert "timeout=120" in processing
    assert "except subprocess.TimeoutExpired" in processing


def test_concurrency_review_workers_use_snapshots_not_live_app_state():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")

    check_start = app.index("    def check_ocr_engines(self) -> None:", app.index("class PictureCaptureApp"))
    check_end = app.index("\n    def detect_layout_current", check_start)
    check = app[check_start:check_end]
    assert "self.show_environment_center()" in check

    environment_center = (root / "src" / "picture_capture" / "environment_center.py").read_text(encoding="utf-8")
    refresh_start = environment_center.index("    def refresh(self) -> None:")
    refresh_end = environment_center.index("\n    def _open_ocr_settings", refresh_start)
    refresh = environment_center[refresh_start:refresh_end]
    worker = refresh[refresh.index("        def worker():"):refresh.index("        def done(", refresh.index("        def worker():"))]
    assert "tesseract_status(executable, language)" in worker
    assert "opencc_runtime_status(retry=True)" in worker

    split_start = app.index("    def batch_split_whole(")
    split_end = app.index("\n    def repair_pdic_order_selected_scope", split_start)
    split = app[split_start:split_end]
    worker = split[split.index("        def worker("):split.index("        def done(", split.index("        def worker("))]
    assert "self._ppp_read_path" not in worker
    assert "ppp_read_path_for_image(page)" in worker

    restore_start = app.index("    def restore_from_pdic_backup(")
    restore_end = app.index("\n    def restore_from_merged_pdic", restore_start)
    restore = app[restore_start:restore_end]
    assert "settings_snapshot = replace(self.settings)" in restore
    worker = restore[restore.index("        def worker("):restore.index("        def done(", restore.index("        def worker("))]
    assert "self.settings" not in worker
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in worker

    preview_start = profile.index("    def _refresh_template_preview(")
    preview_end = profile.index("\n    @staticmethod\n    def _mode_row", preview_start)
    preview = profile[preview_start:preview_end]
    worker = preview[preview.index("        def worker():"):preview.index("        def done(", preview.index("        def worker():"))]
    assert "len(self.sample_indices)" not in worker
    assert "sample_count" in worker

    analysis_start = profile.index("    def analyze_representative_pages(")
    analysis_end = profile.index("\n    def _poll_analysis_queue", analysis_start)
    analysis = profile[analysis_start:analysis_end]
    worker = analysis[analysis.index("        def worker()"):analysis.index("        threading.Thread", analysis.index("        def worker()"))]
    assert "self.project" not in worker
    assert "self._analysis_queue" not in worker
    assert "result_queue.put" in worker



def test_concurrency_audit_p0_p1_guards_are_present():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")
    training = (root / "src" / "picture_capture" / "training_export.py").read_text(encoding="utf-8")

    poll_start = app.index("    def _poll_ui_worker_queue(")
    poll_end = app.index("\n    def _configure_main_workspace_styles", poll_start)
    assert "_ui_worker_active" in app[poll_start:poll_end]

    load_start = app.index("    def _load_project(")
    load_end = app.index("\n    def on_page_select", load_start)
    load = app[load_start:load_end]
    assert "root == Path(self.project.root).expanduser().resolve()" in load
    assert load.index("root == Path(self.project.root).expanduser().resolve()") < load.index("def worker():")

    profile_open_start = app.index("    def open_project_profile(")
    profile_open_end = app.index("\n    def open_project_details", profile_open_start)
    assert "if self._batch_active:" in app[profile_open_start:profile_open_end]

    validate_start = profile.index("    def validate_profile(")
    validate_end = profile.index("\n    def _poll_validation_queue", validate_start)
    assert "if self.parent._batch_active:" in profile[validate_start:validate_end]

    export_start = app.index("    def export_training_package(")
    export_end = app.index("\n    def show_help_dialog", export_start)
    export = app[export_start:export_end]
    assert 'startswith("training-cleanup-")' in export
    assert '%Y%m%d_%H%M%S_%f' in export
    assert "uuid.uuid4().hex" in training


def test_project_profile_legacy_workers_drop_results_while_closing():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")
    assert "self._closing = False" in text
    for name in (
        "_start_sample_thumbnail_load",
        "_poll_sample_thumbnail_load",
        "_start_sample_thumbnail_slot_load",
        "_poll_sample_thumbnail_slot_load",
        "analyze_representative_pages",
        "_poll_analysis_queue",
        "validate_profile",
    ):
        start = text.index(f"    def {name}(")
        next_def = text.find("\n    def ", start + 8)
        block = text[start: next_def if next_def >= 0 else len(text)]
        assert "_closing" in block



def test_crop_file_transaction_rolls_back_complete_previous_set(tmp_path, monkeypatch):
    from picture_capture.processing import _publish_file_transaction

    first = tmp_path / "page_SW_000.png"
    second = tmp_path / "page.PSWords"
    stale = tmp_path / "page_SW_999.png"
    first.write_text("old-image", encoding="utf-8")
    second.write_text("old-manifest", encoding="utf-8")
    stale.write_text("old-stale", encoding="utf-8")
    first_tmp = tmp_path / ".first.tmp"
    second_tmp = tmp_path / ".second.tmp"
    first_tmp.write_text("new-image", encoding="utf-8")
    second_tmp.write_text("new-manifest", encoding="utf-8")

    import os
    real_replace = os.replace

    def fail_second_publish(src, dst):
        if Path(src) == second_tmp:
            raise OSError("injected manifest publish failure")
        return real_replace(src, dst)

    monkeypatch.setattr("picture_capture.processing.os.replace", fail_second_publish)
    try:
        _publish_file_transaction(
            [(first_tmp, first), (second_tmp, second)],
            stale_paths=[stale],
        )
    except OSError:
        pass
    else:
        raise AssertionError("expected injected publish failure")

    assert first.read_text(encoding="utf-8") == "old-image"
    assert second.read_text(encoding="utf-8") == "old-manifest"
    assert stale.read_text(encoding="utf-8") == "old-stale"
    assert not list(tmp_path.glob(".*.bak"))
    assert not first_tmp.exists()
    assert not second_tmp.exists()


def test_crop_exports_stage_pngs_manifest_and_crop_plan_before_publish():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "picture_capture" / "processing.py").read_text(encoding="utf-8")

    assert "def _publish_file_transaction(" in text
    assert "def _stage_page_crop_plan(" in text
    assert "uuid.uuid4().hex" in text

    single_start = text.index("def split_single_lines(")
    single_end = text.index("\ndef _special_bounds", single_start)
    single = text[single_start:single_end]
    assert "_stage_crop(" in single
    assert "_stage_text_file(" in single
    assert "_publish_file_transaction(" in single

    whole_start = text.index("def split_whole_entries(")
    whole_end = text.index("\ndef append_crop_log", whole_start)
    whole = text[whole_start:whole_end]
    assert "_stage_page_crop_plan(" in whole
    assert "_publish_file_transaction(" in whole
    assert '.PWWords"' in whole

    ill_start = text.index("def split_illustrations(")
    ill_end = text.index("\ndef append_illustration_crop_log", ill_start)
    illustrations = text[ill_start:ill_end]
    assert "_stage_page_crop_plan(" in illustrations
    assert "_publish_file_transaction(" in illustrations
    assert '.PPPictures"' in illustrations



def test_crop_transaction_preserves_backup_when_rollback_itself_fails(tmp_path, monkeypatch):
    from picture_capture.processing import _publish_file_transaction

    first = tmp_path / "page_SW_000.png"
    second = tmp_path / "page.PSWords"
    first.write_text("old-image", encoding="utf-8")
    second.write_text("old-manifest", encoding="utf-8")
    first_tmp = tmp_path / ".first.tmp"
    second_tmp = tmp_path / ".second.tmp"
    first_tmp.write_text("new-image", encoding="utf-8")
    second_tmp.write_text("new-manifest", encoding="utf-8")

    import os
    real_replace = os.replace
    restore_attempted = False

    def fail_publish_and_one_restore(src, dst):
        nonlocal restore_attempted
        src_path = Path(src)
        dst_path = Path(dst)
        if src_path == second_tmp:
            raise OSError("injected publish failure")
        if src_path.name.startswith(f".{first.name}.") and src_path.suffix == ".bak":
            restore_attempted = True
            raise OSError("injected rollback failure")
        return real_replace(src, dst)

    monkeypatch.setattr(
        "picture_capture.processing.os.replace", fail_publish_and_one_restore,
    )
    try:
        _publish_file_transaction([(first_tmp, first), (second_tmp, second)])
    except RuntimeError as exc:
        assert "已保留隐藏 .bak 恢复副本" in str(exc)
    else:
        raise AssertionError("expected rollback RuntimeError")

    assert restore_attempted
    backups = list(tmp_path.glob(".*.bak"))
    assert backups
    assert any(path.read_text(encoding="utf-8") == "old-image" for path in backups)


def test_headword_order_finalizer_blocks_new_batches_until_snapshot_report_finishes():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    sequential_start = text.index("    def _start_batch_task(")
    parallel_start = text.index("    def _start_parallel_batch_task(", sequential_start)
    sequential = text[sequential_start:parallel_start]
    parallel_end = text.index("\n    def _poll_batch_queue", parallel_start)
    parallel = text[parallel_start:parallel_end]
    expected = 'self._ui_worker_key_active("headword-order-finalize")'
    assert expected in sequential
    assert expected in parallel
