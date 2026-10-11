"""Regression tests for isolated task menus and compact display controls."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.models import AppSettings
from picture_capture.ui import workspace_tools
from picture_capture.ui.compact_display_menu import DISPLAY_MODES
from picture_capture.ui.controllers.canvas import CanvasController

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_tool_icon_opens_only_its_own_panel_not_six_collapsible_titles():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    section = source.split("def choose_workspace_section(", 1)[1].split(
        "def show_workspace_task(", 1
    )[0]
    assert "app.workspace_tools_content.winfo_children()" in section
    assert "child.pack_forget()" in section
    assert 'section.pack(side="top", fill="x")' in section
    assert "candidate is section" not in section
    assert "show_all_sections(app)" not in source.split(
        "def show_workspace_task(", 1
    )[1].split("def size_page_index_to_controls(", 1)[0]
    assert "TOOL_MENU_WIDTH = 280" in source


def test_display_controls_are_in_requested_order_and_share_existing_variables():
    source = (ROOT / "ui" / "compact_display_menu.py").read_text(encoding="utf-8")
    captions = (
        "自动保存", "隐藏线框（插图除外）", "显示标尺", "显示区块",
        "栏左垂线", "词头横线", "插图形状:线",
        "插图标签:线", "词头标签", "显示OCR内容选择器",
        "显示OCR对比底色结果", "显示单行画线候选框",
        "颜色模式", "显示模式", "向右比例%", "显示Layout",
        "去噪强度", "切图预览标签:",
    )
    starts = [source.index('"' + caption + '"') for caption in captions]
    assert starts == sorted(starts)
    assert source.count("divider()") >= 4
    assert "app.quick_vars" in source
    assert "app.quick_bool_vars" in source
    assert "app.quick_color_vars" in source
    assert "app.choose_overlay_color(key, button)" in source
    assert 'value(row, "间隔时间(秒)", "batch_interval", 3)' in source
    assert 'width=chars + 2' in source
    assert 'value(row, "宽", "guide_width", 2)' in source
    assert 'value(row, "宽:", "guide_width", 2)' not in source
    assert 'value(row, "向右比例%", "right_ratio", 4)' in source
    assert 'SWATCH_VERTICAL_PADDING_FRACTION = 0.25' in source
    assert "relheight=1 - 2 * SWATCH_VERTICAL_PADDING_FRACTION" in source
    assert "ocr_crop_preview_checkbox" not in source


def test_ocr_headword_area_is_exclusive_display_mode():
    assert DISPLAY_MODES[-1] == "OCR词头区域预览"
    redraws = []
    app = SimpleNamespace(
        crop_preview_var=Var(False),
        binary_preview_var=Var(False),
        hide_var=Var(False),
        ocr_crop_preview_var=Var(False),
        display_mode_var=Var("OCR词头区域预览"),
        status_var=Var(""),
        redraw=lambda: redraws.append(True),
        photo=None,
        _display_photo_cache_key=None,
    )
    ctrl = CanvasController(app)
    ctrl.apply_display_mode()
    assert app.ocr_crop_preview_var.get() is True
    assert not app.crop_preview_var.get()
    assert not app.hide_var.get()
    assert ctrl.display_mode_from_flags() == "OCR词头区域预览"
    app.display_mode_var.set("切图预览")
    ctrl.apply_display_mode()
    assert app.ocr_crop_preview_var.get() is False
    assert app.crop_preview_var.get() is True
    assert ctrl.display_mode_from_flags() == "切图预览"
    app.display_mode_var.set("仅原图")
    ctrl.apply_display_mode()
    assert app.ocr_crop_preview_var.get() is False
    assert app.crop_preview_var.get() is False
    assert app.hide_var.get() is True
    assert len(redraws) == 3


def test_headword_label_toggle_has_independent_persisted_setting():
    settings = AppSettings()
    assert settings.show_main_entry_labels is True
    draw = (ROOT / "ui/entry_overlay_builder.py").read_text(encoding="utf-8")
    assert '"show_headword_markers"' in draw
    assert 'if not getattr(self.settings, "show_main_entry_labels", True):' in draw
    assert draw.index('"show_headword_markers"') < draw.index(
        'if not getattr(self.settings, "show_main_entry_labels", True):'
    )


def test_all_compact_task_menus_share_regular_row_spacing_and_label_alignment():
    task = (ROOT / "ui" / "compact_task_menus.py").read_text(encoding="utf-8")
    layout = (ROOT / "ui" / "compact_layout_profile_menu.py").read_text(encoding="utf-8")
    assert 'frame.pack(fill="x", padx=(2, 2), pady=(2, 2))' in task
    assert 'result.pack(fill="x", pady=(2, 2))' in layout
    assert 'panel = ttk.Frame(parent, padding=(4, 3, 4, 6))' in layout
    assert 'def _label(row: ttk.Frame, text: str, width: int | None = None)' in task
    assert '_label(row, "OCR语言")' in task
    assert '_label(row, "识别带宽%")' in task
    assert '_label(row, "左缘容差")' in task
    assert '_label(row, "横线与文字安全距离px")' in task
    assert '_label(row, "几何纠正模式", width=12)' in task
    assert 'for pair in margins:' in task
    assert 'app._preprocess_export_settings_changed' in task
    assert 'app._quick_parameter_changed' in task
    assert "ACTION_GROUPS" in task


def test_legacy_postproduction_menu_reflow_has_matching_spacing():
    text = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    reflow = text.split("def _stack_tool_menu_controls(", 1)[1].split(
        "def _draw_rail_icon(", 1
    )[0]
    assert 'padx=(3, 3), pady=(2, 2)' in reflow
    assert 'container.columnconfigure(0, weight=1)' in reflow
    assert 'child.grid(' in reflow and 'child.pack(' in reflow
    # Postproduction stays the one legacy panel and keeps its original actions.
    assert 'sections["五、后期词典制作"]' not in text
    assert 'app._build_quick_settings(content)' in text


def test_display_integer_field_casts_and_loaded_value_formatting():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    opacity = (ROOT / "overlay_opacity.py").read_text(encoding="utf-8")
    fill = (ROOT / "illustration_fill_opacity.py").read_text(encoding="utf-8")
    assert 'self.quick_field_casts["batch_interval"] = int' in app_source
    assert 'self.quick_field_casts["right_ratio"] = float' in app_source
    assert 'self.quick_field_casts[name] = int  # Both width and displayed offset%' in app_source
    assert '"batch_interval", "guide_opacity", "headword_marker_opacity",' in app_source
    assert 'value = round(float(value) * 100)' in app_source
    assert 'value = float(value) / 100.0' in app_source
    assert 'app.quick_field_casts[name] = int' in opacity
    assert 'app.quick_field_casts[name] = int' in fill
    assert 'rendered = str(round(current))' in opacity
    assert 'tk.StringVar(value=str(round(current)))' in fill
