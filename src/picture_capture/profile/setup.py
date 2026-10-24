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
        super().__init__(parent)
        self.parent = parent
        self.project = parent.project
        if self.project is None:
            self.destroy()
            return
        self.new_project = bool(new_project)
        self.working = replace(parent.settings)
        self.title("建立项目Profile" if self.new_project else "项目Profile")
        self.update_idletasks()
        screen_w = max(800, int(self.winfo_screenwidth()))
        work_x, work_y, work_w, work_h = _screen_work_area(self)
        width = min(work_w, max(720, int(screen_w * 0.80)))
        height = max(1, int(work_h * 0.90))
        x = work_x + max(0, (work_w - width) // 2)
        y = work_y + max(0, (work_h - height) // 2)
        self._wizard_width = width
        self._wizard_height = height
        self._wizard_left_width = max(400, int(width * 0.40) - 36)
        self._wizard_image_width = max(560, int(width * 0.60) - 36)
        self._wizard_content_width = self._wizard_left_width
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(960, width), min(640, height))
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close_without_save)
        self._photos: list[ImageTk.PhotoImage] = []
        self._sample_cells: dict[int, ttk.Frame] = {}
        self._sample_photo_by_slot: dict[int, ImageTk.PhotoImage] = {}
        self._thumbnail_slot_queue: queue.Queue = queue.Queue()
        self._thumbnail_slot_generation: dict[int, int] = {}
        self._thumbnail_slot_pending: set[tuple[int, int]] = set()
        self._validation_photos: list[ImageTk.PhotoImage] = []
        self._template_photos: list[ImageTk.PhotoImage] = []
        self._template_preview_canvas: tk.Canvas | None = None
        self._template_line_items: list[int] = []
        self._template_line_paths: list[list[tuple[float, float]]] = []
        self._template_nudge_vector: tuple[float, float] = (0.0, 0.0)
        self._thumbnail_queue: queue.Queue | None = None
        self._thumbnail_load_generation = 0
        self._validation_results: list[tuple] = []
        self.validation_preview_slot = 0
        self._headword_example_photos: list[ImageTk.PhotoImage] = []
        self._validation_running = False
        self._analysis_running = False
        self._profile_revision = 0
        self._analysis_revision_started = -1
        self._validation_revision_started = -1
        self._analysis_suggestion: dict[str, object] = {}
        self._analysis_auto_apply = False
        self._analysis_queue: queue.Queue | None = None
        self._validation_queue: queue.Queue | None = None
        self._validation_stop_event = threading.Event()
        self._validation_close_requested = False
        self._closing = False
        if not str(getattr(self.working, "dictionary_body_page_range", "") or "").strip():
            self.working.dictionary_body_page_range = suggested_body_page_range(self.project.images)
        configured_body = configured_body_page_indices(
            len(self.project.images),
            getattr(self.working, "dictionary_body_page_range", ""),
        )
        self.sample_candidates = probable_body_page_indices(
            self.project.images,
            configured_body or None,
        )
        self.sample_indices = representative_page_indices(
            self.project.images,
            6,
            configured_body or None,
        )
        self.template_preview_slot = 0

        self._build_vars()
        self._build_ui()
        self._show_sample_loading_state()
        self._refresh_language_summary()
        self._refresh_summary()
        self.after(20, self._start_sample_thumbnail_load)

        # Representative-page analysis starts after the user confirms reading
        # direction and enters step 2. This avoids analyzing a vertical/RTL
        # dictionary with an incorrect default transform.

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
        count = max(1, int(self.columns_var.get()))
        self.selected_column_index = max(
            0, min(count - 1, int(getattr(self, "selected_column_index", 0)))
        )
        return self.selected_column_index

    def _column_offsets_for_count(self, count: int | None = None) -> list[int]:
        count = max(1, int(self.columns_var.get() if count is None else count))
        raw = list(getattr(self.working, "column_start_offsets", []) or [])
        offsets: list[int] = []
        for index in range(count):
            try:
                offsets.append(int(round(float(raw[index]))) if index < len(raw) else 0)
            except (TypeError, ValueError):
                offsets.append(0)
        return offsets

    def _refresh_column_adjust_status(self) -> None:
        if not hasattr(self, "column_adjust_status_var"):
            return
        index = self._selected_column_index()
        offsets = self._column_offsets_for_count()
        column_width = max(1, int(getattr(self.working, "column_width", 1) or 1))
        percent = float(offsets[index]) * 100.0 / column_width
        self.column_adjust_status_var.set(
            f"当前：第 {index + 1} 栏｜人工偏移 {percent:+.2f}% 单栏宽"
        )

    def _update_template_column_highlight(self) -> None:
        canvas = getattr(self, "_template_preview_canvas", None)
        if canvas is None:
            return
        selected = self._selected_column_index()
        for index, item in enumerate(getattr(self, "_template_line_items", [])):
            if item < 0:
                continue
            try:
                canvas.itemconfigure(
                    item,
                    fill="#ee7c00" if index == selected else "#1e78d2",
                    width=4 if index == selected else 2,
                )
            except tk.TclError:
                return

    def _nudge_template_column_preview(self, index: int, delta: int) -> None:
        """Move only the cached overlay line; do not reload/re-render the page image."""
        if not delta:
            return
        canvas = getattr(self, "_template_preview_canvas", None)
        items = getattr(self, "_template_line_items", [])
        paths = getattr(self, "_template_line_paths", [])
        if canvas is None or index >= len(items) or index >= len(paths) or items[index] < 0:
            return
        dx = float(self._template_nudge_vector[0]) * int(delta)
        dy = float(self._template_nudge_vector[1]) * int(delta)
        try:
            canvas.move(items[index], dx, dy)
        except tk.TclError:
            return
        paths[index] = [(x + dx, y + dy) for x, y in paths[index]]

    def _shift_selected_column(self, delta: int) -> None:
        index = self._selected_column_index()
        offsets = self._column_offsets_for_count()
        old_value = offsets[index]
        column_width = max(1, int(getattr(self.working, "column_width", 1) or 1))
        step_px = max(1, int(round(column_width * 0.001)))
        max_offset = max(step_px, int(round(column_width * 0.25)))
        offsets[index] = max(
            -max_offset,
            min(max_offset, old_value + (step_px if int(delta) > 0 else -step_px)),
        )
        actual_delta = offsets[index] - old_value
        if not actual_delta:
            return
        self.working.column_start_offsets = offsets
        self._refresh_column_adjust_status()
        self._nudge_template_column_preview(index, actual_delta)
        self._profile_input_changed(refresh_preview=False)

    def _reset_selected_column(self) -> None:
        index = self._selected_column_index()
        offsets = self._column_offsets_for_count()
        old_value = offsets[index]
        if old_value == 0:
            return
        offsets[index] = 0
        self.working.column_start_offsets = offsets
        self._refresh_column_adjust_status()
        self._nudge_template_column_preview(index, -old_value)
        self._profile_input_changed(refresh_preview=False)

    def _reset_all_column_offsets(self) -> None:
        offsets = self._column_offsets_for_count()
        if not any(offsets):
            return
        for index, value in enumerate(offsets):
            if value:
                self._nudge_template_column_preview(index, -value)
        self.working.column_start_offsets = [0] * len(offsets)
        self._refresh_column_adjust_status()
        self._profile_input_changed(refresh_preview=False)

    @staticmethod
    def _preview_path_distance_sq(
        points: list[tuple[float, float]], x: float, y: float,
    ) -> float:
        if not points:
            return float("inf")
        if len(points) == 1:
            dx, dy = x - points[0][0], y - points[0][1]
            return dx * dx + dy * dy
        best = float("inf")
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            dx, dy = x1 - x0, y1 - y0
            denom = dx * dx + dy * dy
            if denom <= 0:
                px, py = x0, y0
            else:
                t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / denom))
                px, py = x0 + t * dx, y0 + t * dy
            ex, ey = x - px, y - py
            best = min(best, ex * ex + ey * ey)
        return best

    def _select_template_column(
        self, event: tk.Event, line_paths: list[list[tuple[float, float]]],
    ) -> None:
        if not line_paths:
            return
        distances = [
            self._preview_path_distance_sq(points, float(event.x), float(event.y))
            for points in line_paths
        ]
        index = min(range(len(distances)), key=distances.__getitem__)
        if distances[index] > 18.0 * 18.0:
            return
        self.selected_column_index = index
        self._refresh_column_adjust_status()
        self._update_template_column_highlight()


    def _refresh_template_controls(self) -> None:
        """Enable only page-template controls that currently have meaning."""
        if not hasattr(self, "header_percent_spin"):
            return
        header_present = HEADER_LABEL_TO_VALUE.get(self.header_mode_var.get()) == "present"
        footer_present = FOOTER_LABEL_TO_VALUE.get(self.footer_mode_var.get()) == "present"
        side_value = SIDE_LABEL_TO_VALUE.get(self.side_mode_var.get(), "none")
        fixed_side = side_value in {"left", "right"}
        alternating = side_value in {"outer", "inner"}
        self.columns_spin.configure(state="normal")
        self.header_percent_spin.configure(state="normal" if header_present else "disabled")
        self.footer_percent_spin.configure(state="normal" if footer_present else "disabled")
        self.side_percent_spin.configure(state="normal" if fixed_side else "disabled")
        self.side_percent_a_spin.configure(state="normal" if alternating else "disabled")
        self.side_percent_b_spin.configure(state="normal" if alternating else "disabled")
        self.first_variant_combo.configure(state="readonly" if alternating else "disabled")
        if hasattr(self, "template_preview_frame") and hasattr(self, "notebook"):
            try:
                preview_visible = self.notebook.index(self.notebook.select()) == 1
            except (tk.TclError, ValueError):
                preview_visible = False
            if preview_visible:
                self.after_idle(self._refresh_template_preview)

    def _move_template_preview(self, delta: int) -> None:
        if not self.sample_indices:
            return
        self.template_preview_slot = (
            int(self.template_preview_slot) + int(delta)
        ) % len(self.sample_indices)
        self._refresh_template_preview()

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
        """A saved validation result is meaningful only for the exact current settings."""
        if getattr(self.working, "profile_last_validated_pages", None):
            self.working.profile_last_validated_pages = []
        if hasattr(self, "validation_status_var") and not self._validation_running:
            self.validation_status_var.set("设置已修改，需要重新测试")
        if hasattr(self, "feedback_too_many_button"):
            for button in (
                self.feedback_too_many_button,
                self.feedback_good_button,
                self.feedback_too_few_button,
            ):
                button.configure(state="disabled")

    def _profile_input_changed(self, *, refresh_preview: bool = True) -> None:
        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_summary()
        self._refresh_column_adjust_status()
        if refresh_preview and hasattr(self, "template_preview_frame"):
            self.after_idle(self._refresh_template_preview)

    def _reading_changed(self) -> None:
        self._profile_revision += 1
        self._mark_validation_stale()
        if hasattr(self, "analysis_suggestion_var") and self._analysis_suggestion:
            self._analysis_suggestion = {}
            self.analysis_suggestion_var.set("阅读方向已改变，请重新分析代表页。")
            self.apply_analysis_button.configure(state="disabled")
        self._refresh_language_summary()
        self._refresh_summary()

    def _set_structure_defaults_for_profile(self, key: str) -> None:
        defaults = recommended_headword_structures(key)
        self.ordinary_left_edge_var.set(defaults["ordinary_left_edge"])
        self.cjk_allow_bracketed_var.set(defaults["cjk_bracketed"])
        self.cjk_allow_single_var.set(defaults["cjk_single_visual"])
        self.marker_prefix_var.set(defaults["marker_prefix"])
        self.numbered_prefix_var.set(defaults["numbered_prefix"])

    def _set_tail_defaults_for_profile(self, key: str) -> None:
        defaults = profile_tail_structure_defaults(key)
        self.tail_allow_pos_var.set(bool(defaults["allow_pos"]))
        self.tail_allow_inflection_var.set(bool(defaults["allow_inflection"]))
        self.tail_allow_variant_var.set(bool(defaults["allow_variant"]))
        self.tail_allow_pronunciation_var.set(bool(defaults["allow_pronunciation"]))
        self.tail_allow_descriptor_var.set(bool(defaults["allow_descriptor"]))
        self.tail_require_selected_var.set(bool(defaults["require_selected"]))
        self.tail_allow_visual_rescue_var.set(bool(defaults["allow_visual_rescue"]))

    def _set_symbol_defaults_for_profile(self, key: str) -> None:
        defaults = profile_symbol_inventory_defaults(key)
        self.symbol_inventory_enabled_var.set(bool(defaults["enabled"]))
        self.entry_marker_symbols_var.set(" ".join(defaults["entry_markers"]))
        self.bracket_open_symbols_var.set(" ".join(defaults["bracket_openers"]))
        self.symbol_visual_rescue_var.set(bool(defaults["visual_rescue"]))
        self.symbol_lane_required_var.set(bool(defaults["lane_required"]))
        self.symbol_lane_tolerance_var.set(int(defaults["lane_tolerance_percent"]))

    def _specificity_defaults_for_profile(self, key: str) -> tuple[int, float, float, float]:
        temp = replace(self.working)
        temp.ocr_language = _ocr_language_code(self.ocr_language_var.get())
        apply_headword_profile(temp, key)
        for name, value in language_effective_settings(
            temp.ocr_language, temp.layout_writing_mode
        ).items():
            if hasattr(temp, name):
                setattr(temp, name, value)
        column_width = max(1, int(getattr(temp, "column_width", 700) or 700))
        left_percent = (
            float(getattr(temp, "paddle_left_tolerance", 34) or 34)
            * 100.0 / column_width
        )
        return (
            left_percent,
            float(getattr(temp, "paddle_height_ratio", 1.08)),
            float(getattr(temp, "paddle_boldness_ratio", 1.12)),
            float(getattr(temp, "paddle_min_candidate_score", 1.0)),
        )

    def _reset_specificity_for_profile(self, key: str) -> None:
        left, height, bold, score = self._specificity_defaults_for_profile(key)
        self.headword_left_tolerance_var.set(left)
        self.headword_height_ratio_var.set(round(height, 2))
        self.headword_boldness_ratio_var.set(round(bold, 2))
        self.headword_min_score_var.set(round(score, 2))

    def _headword_changed(self) -> None:
        # Selecting a structure preset seeds human-readable parser checkboxes;
        # users may then customize them without opening advanced parameters.
        self.headword_tuning_level_var.set(0)
        key = self._current_profile_key()
        self._set_structure_defaults_for_profile(key)
        self._set_tail_defaults_for_profile(key)
        self._set_symbol_defaults_for_profile(key)
        if key == "cjk_visual":
            (
                normalized_entry,
                normalized_bracket,
                normalized_samples,
            ) = _normalize_cjk_visual_symbol_roles(
                self.entry_marker_symbols_var.get(),
                self.bracket_open_symbols_var.get(),
                list(getattr(self, "visual_marker_samples", []) or []),
            )
            self.entry_marker_symbols_var.set(normalized_entry)
            self.bracket_open_symbols_var.set(normalized_bracket)
            self.visual_marker_samples = normalized_samples
            self._refresh_symbol_template_summary()
        self._reset_specificity_for_profile(key)
        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_headword_description()
        self._refresh_summary()

    def _headword_structure_changed(self) -> None:
        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_headword_structure_summary()
        self._refresh_headword_specificity_visibility()
        self._refresh_summary()

    def _headword_specificity_changed(self) -> None:
        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_headword_tuning_status()
        self._refresh_symbol_template_summary()
        self._refresh_summary()

    def _refresh_symbol_template_summary(self) -> None:
        if not hasattr(self, "effective_entry_markers_var"):
            return
        entry = split_configured_symbols(self.entry_marker_symbols_var.get())
        bracket = split_configured_symbols(self.bracket_open_symbols_var.get())
        self.effective_entry_markers_var.set(
            "有效入口标记：" + (" ".join(entry) if entry else "无")
        )
        self.effective_bracket_markers_var.set(
            "有效括号起始：" + (" ".join(bracket) if bracket else "无")
        )
        samples = list(getattr(self, "visual_marker_samples", []) or [])
        entry_count = sum(
            1 for sample in samples
            if str(sample.get("role") or "") == "entry_marker"
        )
        bracket_count = sum(
            1 for sample in samples
            if str(sample.get("role") or "") == "bracket_open"
        )
        self.visual_marker_sample_count_var.set(
            f"入口标记样本：{entry_count} ｜ 括号起始样本：{bracket_count}"
        )

    def _capture_visual_marker_sample(self) -> None:
        if not self.project.images:
            messagebox.showinfo(
                "无法采样", "项目中没有可用页面。", parent=self,
            )
            return
        initial_index = 0
        if self._validation_results:
            try:
                initial_index = int(
                    self._validation_results[
                        self.validation_preview_slot % len(self._validation_results)
                    ][0]
                )
            except (TypeError, ValueError, IndexError):
                initial_index = 0
        elif self.sample_indices:
            initial_index = int(self.sample_indices[0])
        initial_role, initial_literal = _visual_marker_capture_defaults(
            marker_prefix_enabled=bool(self.marker_prefix_var.get()),
            bracket_enabled=bool(self.cjk_allow_bracketed_var.get()),
            entry_text=self.entry_marker_symbols_var.get(),
            bracket_text=self.bracket_open_symbols_var.get(),
        )
        VisualMarkerCaptureDialog(
            self,
            self.project.images,
            initial_index=initial_index,
            initial_role=initial_role,
            initial_literal=initial_literal,
            on_saved=self._visual_marker_sample_saved,
        )

    def _visual_marker_sample_saved(self, sample: dict) -> None:
        samples = [
            dict(item) for item in getattr(self, "visual_marker_samples", []) or []
        ]
        sample_id = str(sample.get("id") or "")
        if sample_id:
            samples = [
                item for item in samples
                if str(item.get("id") or "") != sample_id
            ]
        samples.append(dict(sample))
        self._replace_visual_marker_samples(samples)

    def _replace_visual_marker_samples(self, samples: list[dict]) -> None:
        self.visual_marker_samples = [dict(sample) for sample in samples]
        self.working.profile_symbol_template_version = 1
        self.working.profile_symbol_templates_json = (
            serialize_visual_marker_samples(self.visual_marker_samples)
        )
        self._refresh_symbol_template_summary()
        self._headword_specificity_changed()

    def _show_visual_marker_samples(self) -> None:
        if not getattr(self, "visual_marker_samples", None):
            messagebox.showinfo(
                "本词典视觉标记样本",
                "尚未保存视觉标记样本。请先点击【从页面采样…】。",
                parent=self,
            )
            return
        VisualMarkerSamplesDialog(
            self,
            [dict(sample) for sample in self.visual_marker_samples],
            on_changed=self._replace_visual_marker_samples,
        )

    def _clear_visual_marker_samples(self) -> None:
        if not getattr(self, "visual_marker_samples", None):
            return
        if not messagebox.askyesno(
            "清空视觉标记样本",
            "确定清空当前项目保存的全部视觉标记样本吗？\n"
            "原始扫描页不会被修改。",
            parent=self,
        ):
            return
        self._replace_visual_marker_samples([])

    def _refresh_headword_structure_summary(self) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_headword_explanations.refresh_headword_structure_summary(self)

    def _refresh_headword_specificity_visibility(self) -> None:
        """Historical Wizard method; delegate to canonical UI owner."""
        return _wizard_headword_explanations.refresh_headword_specificity_visibility(self)

    def _refresh_headword_tuning_status(self) -> None:
        if not hasattr(self, "headword_tuning_status_var"):
            return
        level = max(-2, min(2, int(self.headword_tuning_level_var.get())))
        labels = {
            -2: "当前自动调节：明显放宽（-2）",
            -1: "当前自动调节：轻度放宽（-1）",
            0: "当前自动调节：标准（0）",
            1: "当前自动调节：轻度收紧（+1）",
            2: "当前自动调节：明显收紧（+2）",
        }
        self.headword_tuning_status_var.set(labels[level])

    def _custom_name_changed(self) -> None:
        # Renaming the custom structure is presentation metadata; recognition
        # settings are unchanged, so a completed Profile test remains valid.
        current = self._current_profile_key()
        self.profile_choices = ordered_headword_profiles(self.custom_name_var.get())
        self.profile_label_to_key = dict(self.profile_choices)
        self.headword_combo.configure(values=tuple(label for label, _key in self.profile_choices))
        self.headword_profile_var.set(self._profile_label_for_key(current))
        self._refresh_headword_description()
        self._refresh_summary()

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
        language = _ocr_language_code(self.ocr_language_var.get())
        auto_index = OCR_TO_INDEX_LANGUAGE.get(language)
        if auto_index:
            self.index_language_var.set(auto_index)
        self._refresh_language_summary()
        self._refresh_summary()

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
        """Write current Wizard fields so navigation/closing cannot lose work."""
        settings = self._settings_from_ui()
        if not finalize:
            # A partial Wizard save is a recoverable draft, not proof that a
            # new-project Profile has completed the full setup workflow.
            settings.profile_setup_version = int(
                getattr(self.working, "profile_setup_version", 0) or 0
            )
        settings.profile_last_validated_pages = list(
            getattr(self.working, "profile_last_validated_pages", []) or []
        )
        copy_settings(self.parent.settings, settings)
        self.parent.settings.to_json(settings_path(self.project.root))
        write_project_profile(
            project_profile_path(self.project.root),
            self.parent.settings,
            self.parent.settings.dictionary_profile_id,
            force=True,
        )
        self.working = replace(settings)
        self.parent.sync_quick_settings()
        if apply_runtime:
            self.parent.redraw()
        return settings

    def _save_profile_progress(
        self, *, finalize: bool = False, apply_runtime: bool = False,
        status: str = "Project Profile 当前内容已保存",
    ) -> bool:
        try:
            self._persist_current_profile(
                finalize=finalize, apply_runtime=apply_runtime,
            )
            self.parent.status_var.set(status)
            return True
        except Exception as exc:
            messagebox.showerror(
                "Project Profile 保存失败", str(exc), parent=self,
            )
            return False

    def _move_step(self, delta: int) -> None:
        # 上一步 / 下一步 are explicit save points.
        if not self._save_profile_progress():
            return
        current = self.notebook.index(self.notebook.select())
        target = max(0, min(len(self.tabs) - 1, current + int(delta)))
        self.notebook.select(self.tabs[target])
        if (current == 0 and target == 1 and self.working.dictionary_layout_kind != "illustrated"
                and not self._analysis_suggestion and not self._analysis_running):
            self.analyze_representative_pages(auto_apply=True)

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
        # The confirmation button saves immediately, even if the user chooses
        # to go back to validation instead of closing the Wizard.
        if not self._save_profile_progress(
            finalize=False,
            status="Project Profile 当前内容已保存",
        ):
            return
        try:
            if not self.working.profile_last_validated_pages:
                if not messagebox.askyesno(
                    "Profile 尚未完整验证",
                    "当前设置尚未通过全部代表页测试，或测试后又修改了设置。\n\n"
                    "建议先到【4 测试与确认】运行“测试当前 Profile”。"
                    "是否仍然保存并使用当前设置？",
                    parent=self,
                ):
                    self.notebook.select(self.tabs[3])
                    return
            if not self._save_profile_progress(
                finalize=True,
                apply_runtime=True,
                status="Project Profile 已保存并应用",
            ):
                return
            self._closing = True
            if self._validation_running:
                self._validation_close_requested = True
                self._validation_stop_event.set()
                self.validation_status_var.set("正在安全结束当前测试页，完成后关闭…")
                return
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Project Profile 保存失败", str(exc), parent=self)

    def _close_without_save(self) -> None:
        # 关闭也先保存当前页；因此误关窗口不会丢掉尚未切页的输入。
        if not self._save_profile_progress(
            finalize=False,
            apply_runtime=True,
            status="Project Profile 当前内容已保存",
        ):
            return
        if self.new_project and int(
            getattr(self.parent.settings, "profile_setup_version", 0) or 0
        ) < PROFILE_SETUP_VERSION:
            if not messagebox.askyesno(
                "尚未完成 Project Profile",
                "当前内容已经保存。项目 Profile 尚未完整确认，确定先关闭吗？"
                "以后可从【项目Profile】继续。",
                parent=self,
            ):
                return
        self._closing = True
        if self._validation_running:
            self._validation_close_requested = True
            self._validation_stop_event.set()
            self.validation_status_var.set("正在安全结束当前测试页，完成后关闭…")
            return
        self.destroy()
