from __future__ import annotations

import json
import queue
import threading
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from ..ui.compat import screen_work_area
from ..ui.appearance import themed_display_image
from .dictionary import (
    dictionary_profile_preset,
    language_effective_settings,
    profile_symbol_inventory_defaults,
    profile_tail_structure_defaults,
    write_project_profile,
)
from ..paddle_headwords import HEADWORD_FILTER_RULES_FILENAME
from ..preprocess.analysis_image import normalize_page_rgb
from ..layout.detection import aggregate_layout_estimates
from .layout_bootstrap import (
    detect_profile_layout_parameters as detect_layout_parameters,
    apply_profile_ink_height_suggestion,
)
from ..models import AppSettings
from ..processing import derive_geometry, detect_entries
from .semantics import (
    PROFILE_SETUP_VERSION,
    READING_LABELS,
    apply_headword_profile,
    apply_headword_tuning,
    apply_reading_choice,
    configured_body_page_indices,
    copy_settings,
    effective_page_settings,
    excluded_source_side,
    excluded_source_side_percent,
    ordered_headword_profiles,
    profile_summary_tags,
    reading_choice_from_settings,
    probable_body_page_indices,
    recommended_headword_structures,
    representative_page_indices,
    suggested_body_page_range,
    page_template_analysis_image,
    page_variant,
)
from ..persistence.project_storage import (
    headword_filter_rules_path,
    ocr_cache_root,
    profile_path as project_profile_path,
    settings_path,
)
from ..visual.marker_templates import (
    parse_visual_marker_samples,
    serialize_visual_marker_samples,
    split_configured_symbols,
)
from ..visual.marker_ui import (
    VisualMarkerCaptureDialog,
    VisualMarkerSamplesDialog,
)
from . import wizard_state_initialization as _wizard_wizard_state_initialization
from . import wizard_tab_builders as _wizard_wizard_tab_builders
from . import wizard_template_preview as _wizard_template_preview
from . import wizard_settings_assembly as _wizard_settings_assembly
from . import wizard_workspace_builder as _wizard_workspace_builder
from . import wizard_validation_diagnostics as _wizard_validation_diagnostics
from . import wizard_validation_execution as _wizard_validation_execution
from . import wizard_validation_controls as _wizard_validation_controls
from . import wizard_validation_visuals as _wizard_validation_visuals
from . import wizard_sample_thumbnails as _wizard_sample_thumbnails
from . import wizard_sample_analysis as _wizard_sample_analysis
from . import wizard_shell_builder as _wizard_shell_builder
from . import wizard_reading_controls as _wizard_reading_controls
from . import wizard_headword_explanations as _wizard_headword_explanations
from . import wizard_persistence as _wizard_persistence
from . import wizard_profile_events as _wizard_profile_events
from . import wizard_visual_markers as _wizard_visual_markers
from . import wizard_bootstrap as _wizard_bootstrap
from . import wizard_template_interactions as _wizard_template_interactions


OCR_LANGUAGE_LABEL_TO_VALUE = {
    "英语 (eng)": "eng",
    "中文简体 (chi_sim)": "chi_sim",
    "中文繁体 (chi_tra)": "chi_tra",
    "日语 (jpn)": "jpn",
    "法语 (fra)": "fra",
    "德语 (deu)": "deu",
    "西班牙语 (spa)": "spa",
    "意大利语 (ita)": "ita",
    "葡萄牙语 (por)": "por",
    "阿拉伯语 (ara)": "ara",
    "荷兰语 (nld)": "nld",
    "波兰语 (pol)": "pol",
    "土耳其语 (tur)": "tur",
    "越南语 (vie)": "vie",
    "捷克语 (ces)": "ces",
    "丹麦语 (dan)": "dan",
    "挪威语 (nor)": "nor",
    "瑞典语 (swe)": "swe",
    "芬兰语 (fin)": "fin",
    "罗马尼亚语 (ron)": "ron",
    "匈牙利语 (hun)": "hun",
    "印度尼西亚语 (ind)": "ind",
    "马来语 (msa)": "msa",
    "克罗地亚语 (hrv)": "hrv",
    "斯洛伐克语 (slk)": "slk",
    "斯洛文尼亚语 (slv)": "slv",
    "加泰罗尼亚语 (cat)": "cat",
    "巴斯克语 (eus)": "eus",
    "加利西亚语 (glg)": "glg",
    "拉丁语 (lat)": "lat",
}

OCR_TO_INDEX_LANGUAGE = {
    "eng": "en", "chi_sim": "zh", "chi_tra": "zh", "jpn": "ja",
    "fra": "fr", "deu": "de", "spa": "es", "ita": "it", "por": "pt",
    "ara": "ar", "nld": "nl", "pol": "pl", "tur": "tr", "vie": "vi",
    "ces": "cs", "dan": "da", "nor": "no", "swe": "sv", "fin": "fi",
    "ron": "ro", "hun": "hu", "ind": "id", "msa": "ms", "hrv": "hr",
    "slk": "sk", "slv": "sl", "cat": "ca", "eus": "eu", "glg": "gl",
    "lat": "la",
}

HEADWORD_HELP_LINES = {
    "latin_regular": (
        "识别对象：词头位于正文栏起始边，通常为明显粗体拉丁词，并常紧跟词性/语法标记。",
        "主要依据：严格栏左缘 + 词性/词后结构优先；若小号斜体词性被 OCR 漏掉或错认，可由明显粗体词形保守补救，普通定义续行仍排除。",
    ),
    "cjk_visual": (
        "识别对象：默认同时识别“大字单字”和“【括号词头】”。两者是两套独立证据：大字靠字号/版式，括号词靠括号结构。",
        "重要：【是括号起始 bracket_open，不是 ○ / ● / ◆ 那种独立入口标记 entry_marker。只有词典真的用独立符号开头时，才勾选“固定符号开头”。",
        "OCR 已能读出【时直接按括号结构解析；视觉样本只用于 OCR 漏掉/错认括号时补救，并建议保持 marker lane 过滤开启。",
    ),
    "numbered_prefix": (
        "识别对象：词头前有稳定数字编号，例如“1. word”“00［词头］”。",
        "主要依据：编号前缀是强词头提示。",
    ),
    "marker_prefixed": (
        "识别对象：词头前有稳定符号，例如 ○、●、◆。",
        "主要依据：符号前缀是强词头提示。",
    ),
    "custom": (
        "识别对象：无法由以上四类稳定描述的特殊版式。",
        "主要依据：沿用当前项目的高级识别参数与自定义规则。",
    ),
}


HEADWORD_EXAMPLE_FILES = {
    "latin_regular": "headword_example_1.png",
    "cjk_visual": "headword_example_2.png",
    "numbered_prefix": "headword_example_3.png",
    "marker_prefixed": "headword_example_4.png",
}


SEPARATOR_LABEL_TO_VALUE = {
    "自动判断": "auto",
    "有中央分隔线": "present",
    "无中央分隔线": "absent",
}
HEADER_LABEL_TO_VALUE = {
    "自动检测页眉": "auto",
    "没有页眉": "none",
    "有页眉，排除固定区域": "present",
}
FOOTER_LABEL_TO_VALUE = {
    "自动检测页尾": "auto",
    "不排除页尾": "none",
    "有页尾，排除固定区域": "present",
}
SIDE_LABEL_TO_VALUE = {
    "无页边占位内容": "none",
    "左侧固定": "left",
    "右侧固定": "right",
    "A/B 页外侧交替": "outer",
    "A/B 页内侧交替": "inner",
}

VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE = {
    "字符符号集 + 视觉样本": "combined",
    "仅字符符号集": "off",
    "视觉样本优先": "template_first",
}
VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE = {
    "按角色合并（推荐）": "role",
    "按具体符号区分": "literal",
}
BRACKET_ROLE_SYMBOLS = frozenset("【〔［[「『〈《")


def _normalize_cjk_visual_symbol_roles(
    entry_text: str,
    bracket_text: str,
    samples: list[dict] | None = None,
) -> tuple[str, str, list[dict]]:
    """Keep bracket openers out of the standalone entry-marker role."""
    entry = list(split_configured_symbols(entry_text))
    bracket = list(split_configured_symbols(bracket_text))
    bracket_set = set(bracket)
    moved = [
        symbol for symbol in entry
        if symbol in BRACKET_ROLE_SYMBOLS or symbol in bracket_set
    ]
    entry = [symbol for symbol in entry if symbol not in moved]
    bracket = list(dict.fromkeys([*bracket, *moved]))
    bracket_set = set(bracket)
    normalized_samples: list[dict] = []
    for sample in samples or []:
        item = dict(sample)
        literal = str(item.get("literal") or "")
        if (
            str(item.get("role") or "") == "entry_marker"
            and literal
            and literal in bracket_set
        ):
            item["role"] = "bracket_open"
        normalized_samples.append(item)
    return " ".join(entry), " ".join(bracket), normalized_samples


def _visual_marker_capture_defaults(
    *,
    marker_prefix_enabled: bool,
    bracket_enabled: bool,
    entry_text: str,
    bracket_text: str,
) -> tuple[str, str]:
    """Choose the semantically correct initial sample role in the capture UI."""
    entry = split_configured_symbols(entry_text)
    bracket = split_configured_symbols(bracket_text)
    if marker_prefix_enabled and entry:
        return "entry_marker", entry[0]
    if bracket_enabled and bracket:
        return "bracket_open", bracket[0]
    if entry:
        return "entry_marker", entry[0]
    if bracket:
        return "bracket_open", bracket[0]
    return ("bracket_open", "") if bracket_enabled else ("entry_marker", "")


def _label_for_value(mapping: dict[str, str], value: str, fallback: str) -> str:
    for label, mapped in mapping.items():
        if mapped == value:
            return label
    return fallback


def _ocr_language_code(value: str) -> str:
    text = str(value or "").strip()
    return OCR_LANGUAGE_LABEL_TO_VALUE.get(text, text or "eng")


def _screen_work_area(widget: tk.Misc) -> tuple[int, int, int, int]:
    return screen_work_area(widget)


class ProjectProfileWizard(tk.Toplevel):
    """User-facing, composable Project Profile workflow.

    The wizard deliberately separates page reading, page template, headword
    structure, and OCR language.  The old detailed Profile page remains the
    expert/override surface; this window is the normal project setup path.
    """

    def __init__(self, parent, *, new_project: bool = False) -> None:
        # Preserve the actual Tk Toplevel superclass initializer on the class.
        super().__init__(parent)
        return _wizard_bootstrap.initialize_wizard(self, parent, new_project=new_project, deps={
            "replace": replace,
            "_screen_work_area": _screen_work_area,
            "ImageTk": ImageTk,
            "ttk": ttk,
            "tk": tk,
            "queue": queue,
            "threading": threading,
            "suggested_body_page_range": suggested_body_page_range,
            "configured_body_page_indices": configured_body_page_indices,
            "probable_body_page_indices": probable_body_page_indices,
            "representative_page_indices": representative_page_indices,
        })

    def _build_vars(self) -> None:
        """Stable ProjectProfileWizard method; dynamic inputs reach the canonical owner."""
        return _wizard_wizard_state_initialization.build_vars(self, deps={
            "tk": tk,
            "reading_choice_from_settings": reading_choice_from_settings,
            "_label_for_value": _label_for_value,
            "SEPARATOR_LABEL_TO_VALUE": SEPARATOR_LABEL_TO_VALUE,
            "HEADER_LABEL_TO_VALUE": HEADER_LABEL_TO_VALUE,
            "FOOTER_LABEL_TO_VALUE": FOOTER_LABEL_TO_VALUE,
            "SIDE_LABEL_TO_VALUE": SIDE_LABEL_TO_VALUE,
            "OCR_LANGUAGE_LABEL_TO_VALUE": OCR_LANGUAGE_LABEL_TO_VALUE,
            "OCR_TO_INDEX_LANGUAGE": OCR_TO_INDEX_LANGUAGE,
            "_ocr_language_code": _ocr_language_code,
            "VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE": VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE,
            "VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE": VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE,
            "parse_visual_marker_samples": parse_visual_marker_samples,
            "profile_symbol_inventory_defaults": profile_symbol_inventory_defaults,
            "profile_tail_structure_defaults": profile_tail_structure_defaults,
            "ordered_headword_profiles": ordered_headword_profiles,
            "recommended_headword_structures": recommended_headword_structures,
        })

    def _build_ui(self) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_shell_builder.build_ui(self, deps={
            "ttk": ttk,
            "tk": tk,
        })

    def _apply_initial_pane_split(self) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_shell_builder.apply_initial_pane_split(self, deps={
            "tk": tk,
        })

    def _apply_left_wraps(self) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_shell_builder.apply_left_wraps(self, deps={
            "ttk": ttk,
            "tk": tk,
        })

    def _build_right_image_workspace(self, parent: ttk.Frame) -> None:
        """Compatibility entrance: forward current Profile Wizard globals."""
        return _wizard_workspace_builder.build_right_image_workspace(self, parent, deps={
            "ttk": ttk,
            "tk": tk,
        })

    def _show_right_image_page(self, index: int) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_shell_builder.show_right_image_page(self, index, deps={
            "tk": tk,
        })

    def _on_wizard_tab_changed(self, _event=None) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_shell_builder.on_wizard_tab_changed(self, _event, deps={
            "tk": tk,
        })

    def _active_tab_canvas(self) -> tk.Canvas | None:
        try:
            index = self.notebook.index(self.notebook.select())
            return self.tab_canvases[index]
        except (tk.TclError, ValueError, IndexError):
            return None

    @staticmethod
    def _is_widget_descendant(widget, ancestor) -> bool:
        current = widget
        while current is not None:
            if current == ancestor:
                return True
            try:
                parent_name = current.winfo_parent()
                current = current._nametowidget(parent_name) if parent_name else None
            except (tk.TclError, KeyError):
                return False
        return False

    def _wizard_mousewheel(self, event) -> str | None:
        if isinstance(event.widget, (tk.Spinbox, ttk.Combobox)):
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        if not delta:
            return None
        if hasattr(self, "right_canvas") and self._is_widget_descendant(
            event.widget, self.right_content
        ):
            self.right_canvas.yview_scroll((-1 if delta > 0 else 1) * 3, "units")
            return "break"
        canvas = self._active_tab_canvas()
        if canvas is None:
            return None
        canvas.yview_scroll((-1 if delta > 0 else 1) * 3, "units")
        return "break"

    def _wizard_linux_wheel(self, event, direction: int) -> str | None:
        if isinstance(event.widget, (tk.Spinbox, ttk.Combobox)):
            return None
        if hasattr(self, "right_canvas") and self._is_widget_descendant(
            event.widget, self.right_content
        ):
            self.right_canvas.yview_scroll(int(direction) * 3, "units")
            return "break"
        canvas = self._active_tab_canvas()
        if canvas is None:
            return None
        canvas.yview_scroll(int(direction) * 3, "units")
        return "break"

    def _build_reading_tab(self, tab: ttk.Frame) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_reading_controls.build_reading_tab(self, tab, deps={
            "ttk": ttk,
            "READING_LABELS": READING_LABELS,
        })

    def _build_language_section(self, parent: ttk.Frame, *, row: int) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_reading_controls.build_language_section(self, parent, row=row, deps={
            "ttk": ttk,
            "tk": tk,
            "OCR_LANGUAGE_LABEL_TO_VALUE": OCR_LANGUAGE_LABEL_TO_VALUE,
        })

    def _body_page_range_changed(self, _event=None) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_reading_controls.body_page_range_changed(self, _event, deps={
            "tk": tk,
            "configured_body_page_indices": configured_body_page_indices,
            "probable_body_page_indices": probable_body_page_indices,
            "representative_page_indices": representative_page_indices,
        })

    def _build_template_tab(self, tab: ttk.Frame) -> None:
        """Stable ProjectProfileWizard method; dynamic inputs reach the canonical owner."""
        return _wizard_wizard_tab_builders.build_template_tab(self, tab, deps={
            "ttk": ttk,
            "tk": tk,
            "SEPARATOR_LABEL_TO_VALUE": SEPARATOR_LABEL_TO_VALUE,
            "HEADER_LABEL_TO_VALUE": HEADER_LABEL_TO_VALUE,
            "FOOTER_LABEL_TO_VALUE": FOOTER_LABEL_TO_VALUE,
            "SIDE_LABEL_TO_VALUE": SIDE_LABEL_TO_VALUE,
        })

    def _selected_column_index(self) -> int:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.selected_column_index(self)

    def _column_offsets_for_count(self, count: int | None = None) -> list[int]:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.column_offsets_for_count(self, count)

    def _refresh_column_adjust_status(self) -> None:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.refresh_column_adjust_status(self)

    def _update_template_column_highlight(self) -> None:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.update_template_column_highlight(self, deps={
            "tk": tk,
        })

    def _nudge_template_column_preview(self, index: int, delta: int) -> None:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.nudge_template_column_preview(self, index, delta, deps={
            "tk": tk,
        })

    def _shift_selected_column(self, delta: int) -> None:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.shift_selected_column(self, delta)

    def _reset_selected_column(self) -> None:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.reset_selected_column(self)

    def _reset_all_column_offsets(self) -> None:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.reset_all_column_offsets(self)

    @staticmethod
    def _preview_path_distance_sq(
        points: list[tuple[float, float]], x: float, y: float,
    ) -> float:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.preview_path_distance_sq(points, x, y)

    def _select_template_column(
        self, event: tk.Event, line_paths: list[list[tuple[float, float]]],
    ) -> None:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.select_template_column(self, event, line_paths)

    def _refresh_template_controls(self) -> None:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.refresh_template_controls(self, deps={
            "tk": tk,
            "HEADER_LABEL_TO_VALUE": HEADER_LABEL_TO_VALUE,
            "FOOTER_LABEL_TO_VALUE": FOOTER_LABEL_TO_VALUE,
            "SIDE_LABEL_TO_VALUE": SIDE_LABEL_TO_VALUE,
        })

    def _move_template_preview(self, delta: int) -> None:
        """Legacy template interaction API; implementation lives in its owner."""
        return _wizard_template_interactions.move_template_preview(self, delta)

    def _refresh_template_preview(self) -> None:
        """Compatibility entrance: forward current Profile Wizard globals."""
        return _wizard_template_preview.refresh_template_preview(self, deps={
            "ttk": ttk,
            "tk": tk,
            "Image": Image,
            "ImageDraw": ImageDraw,
            "ImageTk": ImageTk,
            "normalize_page_rgb": normalize_page_rgb,
            "derive_geometry": derive_geometry,
            "excluded_source_side": excluded_source_side,
            "excluded_source_side_percent": excluded_source_side_percent,
            "effective_page_settings": effective_page_settings,
            "page_template_analysis_image": page_template_analysis_image,
            "page_variant": page_variant,
            "themed_display_image": themed_display_image,
            "HEADER_LABEL_TO_VALUE": HEADER_LABEL_TO_VALUE,
            "FOOTER_LABEL_TO_VALUE": FOOTER_LABEL_TO_VALUE,
        })

    @staticmethod
    def _mode_row(
        parent, row: int, label: str, variable: tk.StringVar, values: tuple[str, ...],
        *, label_style: str | None = None,
    ) -> None:
        kwargs = {"style": label_style} if label_style else {}
        ttk.Label(parent, text=label, **kwargs).grid(
            row=row, column=0, sticky="e", pady=5
        )
        ttk.Combobox(
            parent, textvariable=variable, state="readonly", width=22,
            values=values,
        ).grid(row=row, column=1, sticky="w", pady=5)

    def _build_headword_tab(self, tab: ttk.Frame) -> None:
        """Stable ProjectProfileWizard method; dynamic inputs reach the canonical owner."""
        return _wizard_wizard_tab_builders.build_headword_tab(self, tab, deps={
            "ttk": ttk,
            "tk": tk,
            "VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE": VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE,
            "VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE": VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE,
        })

    def _build_language_tab(self, tab: ttk.Frame) -> None:
        """Compatibility wrapper; language/OCR now lives in step 1."""
        tab.columnconfigure(0, weight=1)
        self._build_language_section(tab, row=0)


    def _build_validation_tab(self, tab: ttk.Frame) -> None:
        """Legacy public call location, forwarding live dependencies to the owner."""
        return _wizard_validation_controls.build_validation_tab(self, tab, deps={
            "ttk": ttk,
            "tk": tk,
        })

    def _profile_label_for_key(self, key: str) -> str:
        for label, value in self.profile_choices:
            if value == key:
                return label
        try:
            wanted = dictionary_profile_preset(key).display_name
        except Exception:
            wanted = ""
        for label, value in self.profile_choices:
            try:
                if dictionary_profile_preset(value).display_name == wanted:
                    return label
            except Exception:
                continue
        return self.profile_choices[0][0] if self.profile_choices else ""

    def _current_profile_key(self) -> str:
        return self.profile_label_to_key.get(self.headword_profile_var.get(), "custom")

    def _mark_validation_stale(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.mark_validation_stale(self)

    def _profile_input_changed(self, *, refresh_preview: bool = True) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.profile_input_changed(self, refresh_preview=refresh_preview)

    def _reading_changed(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.reading_changed(self)

    def _set_structure_defaults_for_profile(self, key: str) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.set_structure_defaults_for_profile(self, key, deps={
            "recommended_headword_structures": recommended_headword_structures,
        })

    def _set_tail_defaults_for_profile(self, key: str) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.set_tail_defaults_for_profile(self, key, deps={
            "profile_tail_structure_defaults": profile_tail_structure_defaults,
        })

    def _set_symbol_defaults_for_profile(self, key: str) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.set_symbol_defaults_for_profile(self, key, deps={
            "profile_symbol_inventory_defaults": profile_symbol_inventory_defaults,
        })

    def _specificity_defaults_for_profile(self, key: str) -> tuple[int, float, float, float]:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.specificity_defaults_for_profile(self, key, deps={
            "replace": replace,
            "_ocr_language_code": _ocr_language_code,
            "apply_headword_profile": apply_headword_profile,
            "language_effective_settings": language_effective_settings,
        })

    def _reset_specificity_for_profile(self, key: str) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.reset_specificity_for_profile(self, key)

    def _headword_changed(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.headword_changed(self, deps={
            "_normalize_cjk_visual_symbol_roles": _normalize_cjk_visual_symbol_roles,
        })

    def _headword_structure_changed(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.headword_structure_changed(self)

    def _headword_specificity_changed(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.headword_specificity_changed(self)

    def _refresh_symbol_template_summary(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_visual_markers.refresh_symbol_template_summary(self, deps={
            "split_configured_symbols": split_configured_symbols,
        })

    def _capture_visual_marker_sample(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_visual_markers.capture_visual_marker_sample(self, deps={
            "messagebox": messagebox,
            "_visual_marker_capture_defaults": _visual_marker_capture_defaults,
            "VisualMarkerCaptureDialog": VisualMarkerCaptureDialog,
        })

    def _visual_marker_sample_saved(self, sample: dict) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_visual_markers.visual_marker_sample_saved(self, sample)

    def _replace_visual_marker_samples(self, samples: list[dict]) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_visual_markers.replace_visual_marker_samples(self, samples, deps={
            "serialize_visual_marker_samples": serialize_visual_marker_samples,
        })

    def _show_visual_marker_samples(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_visual_markers.show_visual_marker_samples(self, deps={
            "messagebox": messagebox,
            "VisualMarkerSamplesDialog": VisualMarkerSamplesDialog,
        })

    def _clear_visual_marker_samples(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_visual_markers.clear_visual_marker_samples(self, deps={
            "messagebox": messagebox,
        })

    def _refresh_headword_structure_summary(self) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_headword_explanations.refresh_headword_structure_summary(self)

    def _refresh_headword_specificity_visibility(self) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_headword_explanations.refresh_headword_specificity_visibility(self)

    def _refresh_headword_tuning_status(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.refresh_headword_tuning_status(self)

    def _custom_name_changed(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.custom_name_changed(self, deps={
            "ordered_headword_profiles": ordered_headword_profiles,
        })

    def _headword_example_asset(self, profile_key: str) -> Path | None:
        filename = HEADWORD_EXAMPLE_FILES.get(profile_key)
        if not filename:
            return None
        candidate = (
            Path(__file__).resolve().parent.parent
            / "data" / "headword_examples" / filename
        )
        return candidate if candidate.exists() else None

    def _headword_example_image(self, profile_key: str) -> Image.Image | None:
        asset = self._headword_example_asset(profile_key)
        if asset is None:
            return None
        try:
            with Image.open(asset) as opened:
                return normalize_page_rgb(opened)
        except Exception:
            return None

    def _refresh_headword_description(self) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_headword_explanations.refresh_headword_description(self, deps={
            "ttk": ttk,
            "dictionary_profile_preset": dictionary_profile_preset,
            "HEADWORD_HELP_LINES": HEADWORD_HELP_LINES,
            "HEADWORD_EXAMPLE_FILES": HEADWORD_EXAMPLE_FILES,
            "Image": Image,
            "ImageTk": ImageTk,
            "themed_display_image": themed_display_image,
        })

    def _ocr_language_changed(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_profile_events.ocr_language_changed(self, deps={
            "_ocr_language_code": _ocr_language_code,
            "OCR_TO_INDEX_LANGUAGE": OCR_TO_INDEX_LANGUAGE,
        })

    def _refresh_language_summary(self) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_reading_controls.refresh_language_summary(self, deps={
            "_ocr_language_code": _ocr_language_code,
            "replace": replace,
            "apply_reading_choice": apply_reading_choice,
            "language_effective_settings": language_effective_settings,
        })

    def _settings_from_ui(self) -> AppSettings:
        """Compatibility entrance: forward current Profile Wizard globals."""
        return _wizard_settings_assembly.settings_from_ui(self, deps={
            "replace": replace,
            "apply_reading_choice": apply_reading_choice,
            "SEPARATOR_LABEL_TO_VALUE": SEPARATOR_LABEL_TO_VALUE,
            "HEADER_LABEL_TO_VALUE": HEADER_LABEL_TO_VALUE,
            "FOOTER_LABEL_TO_VALUE": FOOTER_LABEL_TO_VALUE,
            "SIDE_LABEL_TO_VALUE": SIDE_LABEL_TO_VALUE,
            "_ocr_language_code": _ocr_language_code,
            "split_configured_symbols": split_configured_symbols,
            "_normalize_cjk_visual_symbol_roles": _normalize_cjk_visual_symbol_roles,
            "VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE": VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE,
            "VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE": VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE,
            "serialize_visual_marker_samples": serialize_visual_marker_samples,
            "apply_headword_profile": apply_headword_profile,
            "language_effective_settings": language_effective_settings,
            "apply_headword_tuning": apply_headword_tuning,
            "PROFILE_SETUP_VERSION": PROFILE_SETUP_VERSION,
        })

    def _refresh_summary(self) -> None:
        try:
            settings = self._settings_from_ui()
            self.summary_var.set("  ｜  ".join(profile_summary_tags(settings)))
        except Exception:
            return

    def _sample_groups(self) -> list[ttk.LabelFrame]:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_thumbnails.sample_groups(self, deps={
            "ttk": ttk,
        })

    def _show_sample_loading_state(self) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_thumbnails.show_sample_loading_state(self, deps={
            "ttk": ttk,
        })

    def _start_sample_thumbnail_load(self) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_thumbnails.start_sample_thumbnail_load(self, deps={
            "queue": queue,
            "threading": threading,
            "Image": Image,
            "normalize_page_rgb": normalize_page_rgb,
        })

    def _poll_sample_thumbnail_load(self) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_thumbnails.poll_sample_thumbnail_load(self, deps={
            "queue": queue,
        })

    def _render_sample_thumbnail_slot(
        self, slot: int, index: int, name: str,
        image: Image.Image | None, error: str | None,
    ) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_thumbnails.render_sample_thumbnail_slot(self, slot, index, name, image, error, deps={
            "ttk": ttk,
            "ImageTk": ImageTk,
            "themed_display_image": themed_display_image,
        })

    def _finish_sample_thumbnail_load(self, results) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_thumbnails.finish_sample_thumbnail_load(self, results, deps={
            "ttk": ttk,
        })

    def _start_sample_thumbnail_slot_load(self, slot: int) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_thumbnails.start_sample_thumbnail_slot_load(self, slot, deps={
            "threading": threading,
            "Image": Image,
            "normalize_page_rgb": normalize_page_rgb,
        })

    def _poll_sample_thumbnail_slot_load(self) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_thumbnails.poll_sample_thumbnail_slot_load(self, deps={
            "queue": queue,
        })

    def _choose_sample_page(self, slot: int) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_thumbnails.choose_sample_page(self, slot, deps={
            "tk": tk,
            "ttk": ttk,
            "messagebox": messagebox,
        })

    def _persist_current_profile(
        self, *, finalize: bool = False, apply_runtime: bool = False,
    ) -> AppSettings:
        """Preserve original Wizard call path and live globals."""
        return _wizard_persistence.persist_current_profile(self, finalize=finalize, apply_runtime=apply_runtime, deps={
            "replace": replace,
            "copy_settings": copy_settings,
            "settings_path": settings_path,
            "write_project_profile": write_project_profile,
            "project_profile_path": project_profile_path,
        })

    def _save_profile_progress(
        self, *, finalize: bool = False, apply_runtime: bool = False,
        status: str = "Project Profile 当前内容已保存",
    ) -> bool:
        """Preserve original Wizard call path and live globals."""
        return _wizard_persistence.save_profile_progress(self, finalize=finalize, apply_runtime=apply_runtime, status=status, deps={
            "messagebox": messagebox,
        })

    def _move_step(self, delta: int) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_persistence.move_step(self, delta)

    def analyze_representative_pages(self, auto_apply: bool = False) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_analysis.analyze_representative_pages(self, auto_apply, deps={
            "queue": queue,
            "threading": threading,
            "Image": Image,
            "normalize_page_rgb": normalize_page_rgb,
            "effective_page_settings": effective_page_settings,
            "page_template_analysis_image": page_template_analysis_image,
            "detect_layout_parameters": detect_layout_parameters,
        })

    def _poll_analysis_queue(self) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_analysis.poll_analysis_queue(self, deps={
            "queue": queue,
        })

    def _finish_analysis(self, estimates, errors: list[str]) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_analysis.finish_analysis(self, estimates, errors, deps={
            "aggregate_layout_estimates": aggregate_layout_estimates,
            "apply_profile_ink_height_suggestion": apply_profile_ink_height_suggestion,
        })

    def apply_analysis_suggestion(self) -> None:
        """Retained compatibility method; implementation in representative-page owner."""
        return _wizard_sample_analysis.apply_analysis_suggestion(self, deps={
            "_label_for_value": _label_for_value,
            "SEPARATOR_LABEL_TO_VALUE": SEPARATOR_LABEL_TO_VALUE,
        })

    @staticmethod
    def _validation_coverage_summary(
        cache_path: Path | None, entries, geometry, settings: AppSettings,
    ) -> str:
        """Compatibility entrance: forward current Profile Wizard globals."""
        return _wizard_validation_diagnostics.validation_coverage_summary(cache_path, entries, geometry, settings, deps={
            "json": json,
        })

    def _set_feedback_buttons(self, state: str) -> None:
        if not hasattr(self, "feedback_too_many_button"):
            return
        for button in (
            self.feedback_too_many_button,
            self.feedback_good_button,
            self.feedback_too_few_button,
        ):
            button.configure(state=state)

    def _apply_validation_feedback(self, result: str) -> None:
        """Legacy public call location, forwarding live dependencies to the owner."""
        return _wizard_validation_controls.apply_validation_feedback(self, result)

    def validate_profile(self) -> None:
        """Legacy public call location, forwarding live dependencies to the owner."""
        return _wizard_validation_execution.validate_profile(self, deps={
            "tk": tk,
            "ttk": ttk,
            "Path": Path,
            "Image": Image,
            "normalize_page_rgb": normalize_page_rgb,
            "headword_filter_rules_path": headword_filter_rules_path,
            "HEADWORD_FILTER_RULES_FILENAME": HEADWORD_FILTER_RULES_FILENAME,
            "ocr_cache_root": ocr_cache_root,
            "detect_entries": detect_entries,
            "ProjectProfileWizard": ProjectProfileWizard,
        })

    def _poll_validation_queue(self) -> None:
        if self._validation_queue is None:
            return
        try:
            results = self._validation_queue.get_nowait()
        except queue.Empty:
            if self.winfo_exists() and self._validation_running:
                self.after(100, self._poll_validation_queue)
            return
        self._validation_queue = None
        self._finish_validation(results)

    @staticmethod
    def _marker_preview(
        image: Image.Image, entries, geometry, settings: AppSettings,
        page_index: int, preview_width: int,
    ) -> Image.Image:
        """Legacy public call location, forwarding live dependencies to the owner."""
        return _wizard_validation_visuals.marker_preview(image, entries, geometry, settings, page_index, preview_width, deps={
            "Image": Image,
            "ImageDraw": ImageDraw,
            "excluded_source_side": excluded_source_side,
            "excluded_source_side_percent": excluded_source_side_percent,
        })

    def _set_validation_fit(self, mode: str) -> None:
        self.validation_fit_mode = "width" if mode == "width" else "height"
        if self._validation_results:
            self._render_validation_result()
        try:
            self.right_canvas.yview_moveto(0.0)
        except tk.TclError:
            pass

    def _move_validation_preview(self, delta: int) -> None:
        if not self._validation_results:
            return
        self.validation_preview_slot = (
            int(self.validation_preview_slot) + int(delta)
        ) % len(self._validation_results)
        self._render_validation_result()

    def _render_validation_result(self) -> None:
        """Legacy public call location, forwarding live dependencies to the owner."""
        return _wizard_validation_visuals.render_validation_result(self, deps={
            "ttk": ttk,
            "Image": Image,
            "ImageTk": ImageTk,
            "themed_display_image": themed_display_image,
        })

    def _finish_validation(self, results) -> None:
        """Legacy public call location, forwarding live dependencies to the owner."""
        return _wizard_validation_visuals.finish_validation(self, results)

    def save_and_close(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_persistence.save_and_close(self, deps={
            "messagebox": messagebox,
        })

    def _close_without_save(self) -> None:
        """Preserve original Wizard call path and live globals."""
        return _wizard_persistence.close_without_save(self, deps={
            "messagebox": messagebox,
            "PROFILE_SETUP_VERSION": PROFILE_SETUP_VERSION,
        })
