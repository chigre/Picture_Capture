from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace

from PIL import Image

from picture_capture.app import (
    PictureCaptureApp, SettingsDialog, binary_preview_image, effective_main_overlay_font_size,
    ReviewWindow, VerticalWordText, horizontal_ocr_menu_layout, horizontal_overlay_layout,
    transformed_entry_anchor, vertical_marker_contact_gap, vertical_ocr_menu_layout,
    vertical_overlay_layout,
)
from picture_capture.dictionary_profile import effective_project_profile_id, load_dictionary_profile
from picture_capture.models import (
    AppSettings, Entry, ProjectState, project_cover_path, project_page_images,
)
from picture_capture.layout_transform import LayoutTransform
from picture_capture.layout_detection import _analysis_ink_mask
from picture_capture.processing import _left_edge_ink_mask, refine_existing_entries
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
    _repair_multiline_headword_state_machine, parse_headword_text,
    prepare_ocr_band, run_paddle_band,
)
from picture_capture.project_storage import profile_path, settings_path
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
        parameter_display_width=120,
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
    assert 'text="检测 OCR 引擎"' in settings

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
    assert '"特殊页面覆盖"' in crop
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
    assert '"columns": (1, 12, 1)' in settings
    assert "def _show_setting_help(" in settings
    assert 'text="设置说明"' in settings
    assert 'text="ⓘ"' in settings
    assert 'panes = ttk.Panedwindow(host, orient="horizontal")' in settings
    assert 'panes.add(left, weight=3)' in settings
    assert 'panes.add(right, weight=2)' in settings
    assert 'panes.sashpos(0, int(width * 0.60))' in settings
    assert "def _bind_responsive_labels(" in settings
    assert "label.configure(wraplength=wraplength)" in settings
    assert "control.columnconfigure(0, weight=1)" in settings
    assert 'widget.grid(row=0, column=0, sticky="ew")' in settings
    assert "wraplength=180" in settings
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
    assert "ImageTk.PhotoImage(rendered)" in settings

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
    assert '"检测 OCR 引擎"' in guide
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
    assert '"一、版面参数（两种画线共用）"' in text
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
        parameter_display_width=1000,
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
        parameter_display_width=1000,
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
    # Header/footer are physical source-page exclusions, not canonical Y bounds.
    assert effective.start_y == settings.start_y
    assert effective.bottom_y == settings.bottom_y

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
    masked = page_template_analysis_image(
        Image.new("RGB", (1000, 2000), "black"), vertical, 0,
    )
    # Even for vertical writing, page header/footer remain physical top/bottom.
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

    # Multi-page validation is presented one page at a time with the same
    # previous/next navigation language as the page-template preview.
    assert "self._validation_results = list(results)" in text
    assert "def _move_validation_preview" in text
    assert "def _render_validation_result" in text
    assert "width = min(work_w, max(720, int(screen_w * 0.80)))" in text
    assert "SPI_GETWORKAREA" in text
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
    assert "允许的词头结构（决定哪些 parser 通道开放）" in text
    assert "普通左缘短词可以作为词头" in text
    assert "【括号词】可以作为词头" in text
    assert "大字单字可以作为词头" in text
    assert "固定符号开头（○ / ● / ◆ …）可以作为词头" in text
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
