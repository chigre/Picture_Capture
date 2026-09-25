from __future__ import annotations

import json
import queue
import sys
import threading
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from .dictionary_profile import (
    dictionary_profile_preset,
    language_effective_settings,
    write_project_profile,
)
from .paddle_headwords import HEADWORD_FILTER_RULES_FILENAME
from .image_utils import normalize_page_rgb
from .layout_detection import aggregate_layout_estimates, detect_layout_parameters
from .models import AppSettings
from .processing import derive_geometry, detect_entries
from .profile_semantics import (
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
from .project_storage import (
    headword_filter_rules_path,
    ocr_cache_root,
    profile_path as project_profile_path,
    settings_path,
)


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
        "识别对象：词头位于正文栏起始边，依靠边缘位置及视觉/结构线索识别。",
        "主要依据：栏边位置是主证据，字号、粗体及词头后的结构线索作为辅助。",
    ),
    "cjk_visual": (
        "识别对象：大字单字、【】/〔〕/［］括号词等视觉上明显突出的词头。",
        "主要依据：字号/粗体、括号结构与词条起始位置。",
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
def _label_for_value(mapping: dict[str, str], value: str, fallback: str) -> str:
    for label, mapped in mapping.items():
        if mapped == value:
            return label
    return fallback


def _ocr_language_code(value: str) -> str:
    text = str(value or "").strip()
    return OCR_LANGUAGE_LABEL_TO_VALUE.get(text, text or "eng")


def _screen_work_area(widget: tk.Misc) -> tuple[int, int, int, int]:
    """Return usable desktop x/y/width/height, excluding the Windows taskbar."""
    screen_w = max(800, int(widget.winfo_screenwidth()))
    screen_h = max(600, int(widget.winfo_screenheight()))
    if sys.platform.startswith("win"):
        try:
            import ctypes

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT()
            # SPI_GETWORKAREA excludes the taskbar and other app bars.
            if ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(rect), 0
            ):
                width = max(1, int(rect.right - rect.left))
                height = max(1, int(rect.bottom - rect.top))
                return int(rect.left), int(rect.top), width, height
        except Exception:
            pass
    return 0, 0, screen_w, screen_h


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
        self.title("建立项目 Profile" if self.new_project else "项目 Profile")
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
        # Let Tk paint the complete Wizard frame before any representative
        # image files are opened. Thumbnail decoding then happens off the UI
        # thread so clicking Project Profile never feels like a frozen window.
        self.after(20, self._start_sample_thumbnail_load)

        # Representative-page analysis starts after the user confirms reading
        # direction and enters step 2. This avoids analyzing a vertical/RTL
        # dictionary with an incorrect default transform.

    def _build_vars(self) -> None:
        s = self.working
        self.dictionary_full_name_var = tk.StringVar(value=str(s.dictionary_full_name or ""))
        self.dictionary_abbreviation_var = tk.StringVar(value=str(s.dictionary_abbreviation or ""))
        self.dictionary_isbn_var = tk.StringVar(value=str(s.dictionary_isbn or ""))
        self.dictionary_body_page_range_var = tk.StringVar(value=str(s.dictionary_body_page_range or ""))
        self.reading_var = tk.StringVar(value=reading_choice_from_settings(s))
        self.columns_var = tk.IntVar(value=max(1, int(s.columns)))
        self.separator_var = tk.StringVar(value=_label_for_value(
            SEPARATOR_LABEL_TO_VALUE, str(s.layout_column_separator_mode or "auto"), "自动判断",
        ))
        self.header_mode_var = tk.StringVar(value=_label_for_value(
            HEADER_LABEL_TO_VALUE,
            str(getattr(s, "profile_header_mode", "auto") or "auto"),
            "自动检测页眉",
        ))
        footer_value = str(getattr(s, "profile_footer_mode", "auto") or "auto")
        self.footer_mode_var = tk.StringVar(value=_label_for_value(
            FOOTER_LABEL_TO_VALUE, footer_value, "自动检测页尾",
        ))
        self.side_mode_var = tk.StringVar(value=_label_for_value(
            SIDE_LABEL_TO_VALUE,
            str(getattr(s, "profile_side_content_mode", "none") or "none"),
            "无页边占位内容",
        ))
        self.first_variant_var = tk.StringVar(value=str(getattr(s, "profile_first_page_variant", "A") or "A"))
        self.header_percent_var = tk.DoubleVar(value=float(getattr(s, "profile_header_percent", 6.0)))
        self.footer_percent_var = tk.DoubleVar(value=float(getattr(s, "profile_footer_percent", 5.0)))
        self.side_percent_var = tk.DoubleVar(value=float(getattr(s, "profile_side_percent", 8.0)))
        self.side_percent_a_var = tk.DoubleVar(value=float(
            getattr(s, "profile_side_percent_a", getattr(s, "profile_side_percent", 8.0))
        ))
        self.side_percent_b_var = tk.DoubleVar(value=float(
            getattr(s, "profile_side_percent_b", getattr(s, "profile_side_percent", 8.0))
        ))
        self.ocr_language_var = tk.StringVar(value=_label_for_value(
            OCR_LANGUAGE_LABEL_TO_VALUE, str(s.ocr_language or "eng"), str(s.ocr_language or "eng"),
        ))
        initial_index = str(s.dictionary_index_language or "").strip()
        if not initial_index:
            initial_index = OCR_TO_INDEX_LANGUAGE.get(_ocr_language_code(self.ocr_language_var.get()), "")
        self.index_language_var = tk.StringVar(value=initial_index)
        self.content_language_var = tk.StringVar(value=str(s.dictionary_content_language or ""))
        self.custom_name_var = tk.StringVar(value=str(getattr(s, "dictionary_custom_profile_name", "") or ""))
        self.headword_tuning_level_var = tk.IntVar(
            value=max(-2, min(2, int(getattr(s, "profile_headword_tuning_level", 0) or 0)))
        )
        self.headword_left_tolerance_var = tk.IntVar(
            value=max(4, int(getattr(s, "paddle_left_tolerance", 34) or 34))
        )
        self.headword_height_ratio_var = tk.DoubleVar(
            value=max(0.5, float(getattr(s, "paddle_height_ratio", 1.08) or 1.08))
        )
        self.headword_boldness_ratio_var = tk.DoubleVar(
            value=max(0.5, float(getattr(s, "paddle_boldness_ratio", 1.12) or 1.12))
        )
        self.headword_min_score_var = tk.DoubleVar(
            value=max(0.0, float(getattr(s, "paddle_min_candidate_score", 1.0) or 1.0))
        )

        self.profile_choices = ordered_headword_profiles(self.custom_name_var.get())
        self.profile_label_to_key = dict(self.profile_choices)
        self.headword_profile_var = tk.StringVar(value=self._profile_label_for_key(s.dictionary_profile_id))
        structure_defaults = recommended_headword_structures(s.dictionary_profile_id)
        parser_controls_saved = int(
            getattr(s, "profile_parser_controls_version", 0) or 0
        ) >= 1
        self.ordinary_left_edge_var = tk.BooleanVar(value=(
            bool(getattr(s, "profile_allow_ordinary_left_edge", True))
            if parser_controls_saved else structure_defaults["ordinary_left_edge"]
        ))
        self.numbered_prefix_var = tk.BooleanVar(value=(
            bool(getattr(s, "profile_allow_numbered_prefix", False))
            if parser_controls_saved else structure_defaults["numbered_prefix"]
        ))
        self.marker_prefix_var = tk.BooleanVar(value=(
            bool(getattr(s, "profile_allow_marker_prefix", False))
            if parser_controls_saved else structure_defaults["marker_prefix"]
        ))
        self.cjk_allow_single_var = tk.BooleanVar(value=(
            bool(getattr(s, "profile_cjk_allow_single_headword", True))
            if parser_controls_saved else structure_defaults["cjk_single_visual"]
        ))
        self.cjk_allow_bracketed_var = tk.BooleanVar(value=(
            bool(getattr(s, "profile_cjk_allow_bracketed_headword", True))
            if parser_controls_saved else structure_defaults["cjk_bracketed"]
        ))
        self.cjk_require_left_edge_var = tk.BooleanVar(
            value=bool(getattr(s, "profile_cjk_require_left_edge", True))
        )
        self.cjk_brackets_in_body_var = tk.BooleanVar(
            value=bool(getattr(s, "profile_cjk_brackets_in_body", False))
        )
        self.cjk_require_visual_var = tk.BooleanVar(
            value=bool(getattr(s, "profile_cjk_require_visual_evidence", False))
        )

        detection_vars = (
            self.reading_var, self.columns_var, self.separator_var,
            self.header_mode_var, self.footer_mode_var, self.side_mode_var,
            self.first_variant_var, self.header_percent_var,
            self.footer_percent_var, self.side_percent_var,
            self.side_percent_a_var, self.side_percent_b_var,
            self.ocr_language_var,
        )
        for var in detection_vars:
            var.trace_add("write", lambda *_args: self.after_idle(self._profile_input_changed))
        # Project metadata changes the summary only; it does not invalidate a
        # successful recognition test.
        for var in (
            self.dictionary_full_name_var, self.dictionary_abbreviation_var,
            self.dictionary_isbn_var, self.index_language_var, self.content_language_var,
        ):
            var.trace_add("write", lambda *_args: self.after_idle(self._refresh_summary))

        for var in (
            self.headword_left_tolerance_var,
            self.headword_height_ratio_var,
            self.headword_boldness_ratio_var,
            self.headword_min_score_var,
        ):
            var.trace_add(
                "write", lambda *_args: self.after_idle(self._headword_specificity_changed)
            )

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        self.profile_paned = ttk.Panedwindow(outer, orient="horizontal")
        self.profile_paned.grid(row=0, column=0, sticky="nsew")

        left_panel = ttk.Frame(self.profile_paned, padding=(2, 2, 8, 2))
        right_panel = ttk.Frame(self.profile_paned, padding=(8, 2, 2, 2))
        self.left_panel = left_panel
        left_panel.rowconfigure(3, weight=1)
        left_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)
        right_panel.columnconfigure(0, weight=1)
        self.profile_paned.add(left_panel, weight=40)
        self.profile_paned.add(right_panel, weight=60)
        self._initial_pane_split_done = False
        left_panel.bind(
            "<Configure>",
            lambda _event: self.after_idle(self._apply_left_wraps),
            add="+",
        )

        title = "依次确认词典信息与 OCR、阅读方式、页面模板、词头结构，再用多页测试确认。"
        ttk.Label(left_panel, text=title, font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            left_panel,
            text="左侧只放设置；右侧始终显示当前步骤的图片。中间分隔条可以拖动。",
            foreground="#666666", wraplength=self._wizard_left_width,
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))

        self.notebook = ttk.Notebook(left_panel)
        self.notebook.grid(row=3, column=0, sticky="nsew")
        self.tabs: list[ttk.Frame] = []
        self.tab_contents: list[ttk.Frame] = []
        self.tab_canvases: list[tk.Canvas] = []
        for label in (
            "1 词典信息与阅读方式",
            "2 页面模板",
            "3 词头结构",
            "4 测试与确认",
        ):
            host = ttk.Frame(self.notebook)
            host.rowconfigure(0, weight=1)
            host.columnconfigure(0, weight=1)
            canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0)
            scrollbar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.grid(row=0, column=0, sticky="nsew")
            scrollbar.grid(row=0, column=1, sticky="ns")
            content = ttk.Frame(canvas, padding=10)
            window = canvas.create_window((0, 0), window=content, anchor="nw")
            content.bind(
                "<Configure>",
                lambda _event, cv=canvas: cv.configure(scrollregion=cv.bbox("all")),
            )
            canvas.bind(
                "<Configure>",
                lambda event, cv=canvas, item=window: cv.itemconfigure(item, width=event.width),
            )
            self.notebook.add(host, text=label)
            self.tabs.append(host)
            self.tab_contents.append(content)
            self.tab_canvases.append(canvas)

        self._build_right_image_workspace(right_panel)
        self._build_reading_tab(self.tab_contents[0])
        self._build_template_tab(self.tab_contents[1])
        self._build_headword_tab(self.tab_contents[2])
        self._build_validation_tab(self.tab_contents[3])
        self.notebook.bind("<<NotebookTabChanged>>", self._on_wizard_tab_changed, add="+")
        self.bind("<MouseWheel>", self._wizard_mousewheel, add="+")
        self.bind("<Button-4>", lambda event: self._wizard_linux_wheel(event, -1), add="+")
        self.bind("<Button-5>", lambda event: self._wizard_linux_wheel(event, 1), add="+")

        summary_box = ttk.LabelFrame(left_panel, text="当前 Project Profile", padding=(8, 5))
        summary_box.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.summary_var = tk.StringVar(value="")
        ttk.Label(
            summary_box, textvariable=self.summary_var,
            wraplength=self._wizard_left_width,
        ).pack(anchor="w")

        footer = ttk.Frame(left_panel)
        footer.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(footer, text="上一步", command=lambda: self._move_step(-1)).pack(side="left")
        ttk.Button(footer, text="下一步", command=lambda: self._move_step(1)).pack(side="left", padx=(6, 0))
        ttk.Button(footer, text="关闭", command=self._close_without_save).pack(side="right")
        ttk.Button(footer, text="确认并使用", command=self.save_and_close).pack(side="right", padx=(0, 8))

        self._show_right_image_page(0)
        self.after_idle(self._apply_initial_pane_split)
        self.after_idle(self._apply_left_wraps)

    def _apply_initial_pane_split(self) -> None:
        """Place the startup sash at exactly 40% of the realized pane width."""
        if getattr(self, "_initial_pane_split_done", False):
            return
        try:
            self.update_idletasks()
            pane_width = int(self.profile_paned.winfo_width())
        except tk.TclError:
            return
        if pane_width <= 200:
            self.after(20, self._apply_initial_pane_split)
            return
        self.profile_paned.sashpos(0, round(pane_width * 0.40))
        self._initial_pane_split_done = True
        self.after_idle(self._apply_left_wraps)

    def _apply_left_wraps(self) -> None:
        """Keep all explanatory text in the left pane readable after resizing."""
        root = getattr(self, "left_panel", None)
        if root is None or not root.winfo_exists():
            return

        def visit(widget) -> None:
            for child in widget.winfo_children():
                if isinstance(child, (ttk.Label, tk.Label)):
                    try:
                        parent_width = int(child.master.winfo_width())
                    except (tk.TclError, AttributeError):
                        parent_width = 0
                    wrap = max(
                        90,
                        (parent_width - 18)
                        if parent_width > 120
                        else (self._wizard_left_width - 24),
                    )
                    try:
                        child.configure(wraplength=wrap, justify="left")
                    except tk.TclError:
                        pass
                visit(child)

        visit(root)

    def _build_right_image_workspace(self, parent: ttk.Frame) -> None:
        """Persistent image-only workspace shared by all Wizard steps."""
        host = ttk.LabelFrame(parent, text="图片预览", padding=6)
        host.grid(row=0, column=0, sticky="nsew")
        host.rowconfigure(1, weight=1)
        host.columnconfigure(0, weight=1)

        self.right_heading_var = tk.StringVar(value="代表页（前部 / 中部 / 后部）")
        ttk.Label(
            host, textvariable=self.right_heading_var,
            font=("TkDefaultFont", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.right_canvas = canvas

        content = ttk.Frame(canvas, padding=(2, 2, 6, 6))
        self.right_content = content
        self._right_window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.columnconfigure(0, weight=1)
        content.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(self._right_window, width=e.width),
        )
        self.right_image_pages: list[ttk.Frame] = []
        for _ in range(4):
            page = ttk.Frame(content)
            page.grid(row=0, column=0, sticky="nsew")
            page.columnconfigure(0, weight=1)
            self.right_image_pages.append(page)

        # Step 1: six editable representative pages.
        sample_page = self.right_image_pages[0]
        sample_page.rowconfigure(0, weight=1)
        self.sample_frame = ttk.Frame(sample_page)
        self.sample_frame.grid(row=0, column=0, sticky="nsew")
        self.sample_frame.rowconfigure(0, weight=1)
        for column in range(3):
            self.sample_frame.columnconfigure(column, weight=1, uniform="sample")

        # Step 2: one live page-template preview at a time.
        template_page = self.right_image_pages[1]
        template_nav = ttk.Frame(template_page)
        template_nav.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(
            template_nav, text="◀ 上一张",
            command=lambda: self._move_template_preview(-1),
        ).pack(side="left")
        ttk.Button(
            template_nav, text="下一张 ▶",
            command=lambda: self._move_template_preview(1),
        ).pack(side="right")
        self.template_preview_caption_var = tk.StringVar(value="")
        ttk.Label(
            template_nav, textvariable=self.template_preview_caption_var,
        ).pack(side="left", expand=True)
        self.template_preview_frame = ttk.Frame(template_page)
        self.template_preview_frame.grid(row=1, column=0, sticky="nsew")
        self.template_preview_frame.columnconfigure(0, weight=1)

        # Step 3: one fixed example image for each built-in headword type.
        examples_page = self.right_image_pages[2]
        self.headword_examples_frame = ttk.Frame(examples_page)
        self.headword_examples_frame.grid(row=0, column=0, sticky="ew")
        self.headword_examples_frame.columnconfigure(0, weight=1)
        self.headword_examples_frame.columnconfigure(1, weight=1)

        # Step 4: one full-width validation page at a time.
        validation_page = self.right_image_pages[3]
        nav = ttk.Frame(validation_page)
        nav.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.validation_prev_button = ttk.Button(
            nav, text="◀ 上一页",
            command=lambda: self._move_validation_preview(-1), state="disabled",
        )
        self.validation_prev_button.pack(side="left")
        self.validation_fit_mode = "height"
        ttk.Button(
            nav, text="适合高度",
            command=lambda: self._set_validation_fit("height"),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            nav, text="适合宽度",
            command=lambda: self._set_validation_fit("width"),
        ).pack(side="left", padx=(6, 0))
        self.validation_caption_var = tk.StringVar(value="")
        ttk.Label(nav, textvariable=self.validation_caption_var).pack(
            side="left", expand=True
        )
        self.validation_next_button = ttk.Button(
            nav, text="下一页 ▶",
            command=lambda: self._move_validation_preview(1), state="disabled",
        )
        self.validation_next_button.pack(side="right")
        self.validation_frame = ttk.Frame(validation_page)
        self.validation_frame.grid(row=1, column=0, sticky="ew")
        self.validation_frame.columnconfigure(0, weight=1)

    def _show_right_image_page(self, index: int) -> None:
        if not getattr(self, "right_image_pages", None):
            return
        index = max(0, min(len(self.right_image_pages) - 1, int(index)))
        for slot, page in enumerate(self.right_image_pages):
            if slot == index:
                page.grid()
                page.tkraise()
            else:
                page.grid_remove()
        headings = (
            "代表页（前部 / 中部 / 后部）",
            "页面模板即时预览",
            "词头类型样例",
            "多页测试结果",
        )
        self.right_heading_var.set(headings[index])
        try:
            self.right_canvas.yview_moveto(0.0)
        except tk.TclError:
            pass


    def _on_wizard_tab_changed(self, _event=None) -> None:
        """Switch the persistent right image pane with the selected step."""
        try:
            index = self.notebook.index(self.notebook.select())
        except (tk.TclError, ValueError):
            return
        self._show_right_image_page(index)
        if index == 1:
            self.after_idle(self._refresh_template_preview)
        elif index == 2:
            self.after_idle(self._refresh_headword_description)
        elif index == 3 and self._validation_results:
            self.after_idle(self._render_validation_result)

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
        tab.columnconfigure(0, weight=1)

        info = ttk.LabelFrame(tab, text="词典项目详情", padding=(8, 7))
        info.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        info.columnconfigure(1, weight=1)
        info.columnconfigure(3, weight=1)

        ttk.Label(info, text="词典全称：").grid(
            row=0, column=0, sticky="e", padx=(0, 4), pady=3
        )
        ttk.Entry(
            info, textvariable=self.dictionary_full_name_var, width=24,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=3)
        ttk.Label(info, text="词典简称(字母)：").grid(
            row=0, column=2, sticky="e", padx=(0, 4), pady=3
        )
        ttk.Entry(
            info, textvariable=self.dictionary_abbreviation_var, width=16,
        ).grid(row=0, column=3, sticky="ew", pady=3)

        ttk.Label(info, text="ISBN：").grid(
            row=1, column=0, sticky="e", padx=(0, 4), pady=3
        )
        ttk.Entry(
            info, textvariable=self.dictionary_isbn_var, width=24,
        ).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=3)
        ttk.Label(info, text="正文页码：").grid(
            row=1, column=2, sticky="e", padx=(0, 4), pady=3
        )
        self.body_page_range_entry = ttk.Entry(
            info, textvariable=self.dictionary_body_page_range_var, width=16,
        )
        self.body_page_range_entry.grid(
            row=1, column=3, sticky="ew", pady=3
        )
        self.body_page_range_entry.bind("<FocusOut>", self._body_page_range_changed)
        self.body_page_range_entry.bind("<Return>", self._body_page_range_changed)

        ttk.Label(
            tab, text="阅读方式：页面怎么读？",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=1, column=0, sticky="w")
        ttk.Label(
            tab,
            text="这里只确认实际页面的阅读方向；镜像或旋转由软件自动处理。",
            foreground="#666666", wraplength=self._wizard_left_width,
        ).grid(row=2, column=0, sticky="w", pady=(2, 6))

        choices = ttk.Frame(tab)
        choices.grid(row=3, column=0, sticky="w")
        for column, key in enumerate(
            ("horizontal-ltr", "horizontal-rtl", "vertical-rl", "vertical-lr")
        ):
            ttk.Radiobutton(
                choices, text=READING_LABELS[key],
                variable=self.reading_var, value=key,
                command=self._reading_changed,
            ).grid(row=0, column=column, sticky="w", padx=(0, 10), pady=3)

        self._build_language_section(tab, row=4)

        ttk.Label(
            tab,
            text="右侧代表页优先使用正文页码范围；未填写或无效时再从疑似正文的前部 / 中部 / 后部抽取。每一张都可在右侧手动更换。",
            foreground="#666666", wraplength=self._wizard_left_width,
        ).grid(row=5, column=0, sticky="w", pady=(10, 0))

    def _build_language_section(self, parent: ttk.Frame, *, row: int) -> None:
        box = ttk.LabelFrame(parent, text="语言与 OCR", padding=8)
        box.grid(row=row, column=0, sticky="ew", pady=(12, 0))
        box.columnconfigure(1, weight=1)

        ttk.Label(
            box,
            text="常用语言置前；选择 OCR 语言时自动建议 2 位索引语言，但仍可手动覆盖。",
            foreground="#666666", wraplength=self._wizard_left_width,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 7))

        ttk.Label(box, text="OCR 语言：").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=4)
        combo = ttk.Combobox(
            box, textvariable=self.ocr_language_var,
            values=tuple(OCR_LANGUAGE_LABEL_TO_VALUE.keys()),
            state="normal", width=28,
        )
        combo.grid(row=1, column=1, sticky="ew", pady=4)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._ocr_language_changed())
        combo.bind("<FocusOut>", lambda _e: self._ocr_language_changed())
        self.ocr_language_var.trace_add(
            "write", lambda *_args: self.after_idle(self._refresh_language_summary)
        )

        ttk.Label(box, text="索引语言（2 位）：").grid(
            row=2, column=0, sticky="e", padx=(0, 8), pady=4
        )
        ttk.Entry(
            box, textvariable=self.index_language_var, width=12,
        ).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(
            box,
            text="例如 en / zh / ja / fr；自动值只是建议。",
            foreground="#666666",
        ).grid(row=3, column=1, sticky="w")
        ttk.Label(box, text="内容语言：").grid(
            row=4, column=0, sticky="e", padx=(0, 8), pady=4
        )
        ttk.Entry(
            box, textvariable=self.content_language_var, width=26,
        ).grid(row=4, column=1, sticky="ew", pady=4)

        backend = ttk.LabelFrame(box, text="自动派生的 OCR 后端设置", padding=7)
        backend.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.backend_summary_var = tk.StringVar(value="")
        ttk.Label(
            backend, textvariable=self.backend_summary_var,
            justify="left", wraplength=self._wizard_left_width,
        ).pack(anchor="w")


    def _body_page_range_changed(self, _event=None) -> None:
        """Re-sample representatives after the user edits the body-page range."""
        raw = self.dictionary_body_page_range_var.get().strip()
        configured = configured_body_page_indices(len(self.project.images), raw)
        self.working.dictionary_body_page_range = raw
        self.sample_candidates = probable_body_page_indices(
            self.project.images, configured or None,
        )
        new_indices = representative_page_indices(
            self.project.images, 6, configured or None,
        )
        if new_indices == self.sample_indices:
            return
        self.sample_indices = new_indices
        self.template_preview_slot = 0
        self.validation_preview_slot = 0
        self._profile_revision += 1
        self._mark_validation_stale()
        self._analysis_suggestion = {}
        if hasattr(self, "analysis_suggestion_var"):
            self.analysis_suggestion_var.set("正文页码范围已改变，请重新分析当前代表页。")
            self.apply_analysis_button.configure(state="disabled")
        self._start_sample_thumbnail_load()
        if hasattr(self, "notebook"):
            try:
                if self.notebook.index(self.notebook.select()) == 1:
                    self._refresh_template_preview()
            except (tk.TclError, ValueError):
                pass


    def _build_template_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        ttk.Label(
            tab, text="② 正文在哪里？",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            tab,
            text="左侧定义正文与排除区域；右侧始终用一张真实代表页即时预览。A/B 表示相邻扫描页。",
            foreground="#666666", wraplength=self._wizard_left_width,
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))

        body = ttk.LabelFrame(tab, text="正文与分栏", padding=9)
        body.grid(row=2, column=0, sticky="ew")
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="正文栏数：").grid(row=0, column=0, sticky="e", pady=5)
        self.columns_spin = tk.Spinbox(
            body, from_=1, to=8, width=5, textvariable=self.columns_var,
        )
        self.columns_spin.grid(row=0, column=1, sticky="w", pady=5)
        ttk.Label(
            body,
            text="代表页会自动分析并建议栏数；确认后作为本项目的稳定栏数使用。",
            foreground="#666666", wraplength=self._wizard_left_width,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 5))
        ttk.Label(body, text="中央分隔线：").grid(row=2, column=0, sticky="e", pady=5)
        ttk.Combobox(
            body, textvariable=self.separator_var, state="readonly", width=18,
            values=tuple(SEPARATOR_LABEL_TO_VALUE.keys()),
        ).grid(row=2, column=1, sticky="w", pady=5)

        self.analysis_suggestion_var = tk.StringVar(
            value="进入本步骤时会分析当前代表页，也可随时重新分析。"
        )
        ttk.Label(
            body, textvariable=self.analysis_suggestion_var,
            wraplength=self._wizard_left_width,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 4))
        analysis_buttons = ttk.Frame(body)
        analysis_buttons.grid(row=4, column=0, columnspan=2, sticky="w")
        self.analyze_button = ttk.Button(
            analysis_buttons, text="重新分析代表页",
            command=self.analyze_representative_pages,
        )
        self.analyze_button.pack(side="left")
        self.apply_analysis_button = ttk.Button(
            analysis_buttons, text="应用建议",
            command=self.apply_analysis_suggestion, state="disabled",
        )
        self.apply_analysis_button.pack(side="left", padx=(6, 0))

        edges = ttk.LabelFrame(
            tab, text="页眉 / 页尾 / 页边", padding=9,
        )
        edges.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        edges.columnconfigure(1, weight=1)
        self._mode_row(
            edges, 0, "页眉：", self.header_mode_var,
            tuple(HEADER_LABEL_TO_VALUE.keys()),
        )
        ttk.Label(
            edges, text="排除高度%",
        ).grid(row=1, column=0, sticky="e")
        self.header_percent_spin = tk.Spinbox(
            edges, from_=0, to=35, increment=0.5, width=6,
            textvariable=self.header_percent_var,
        )
        self.header_percent_spin.grid(row=1, column=1, sticky="w")
        self._mode_row(
            edges, 2, "页尾：", self.footer_mode_var,
            tuple(FOOTER_LABEL_TO_VALUE.keys()),
        )
        ttk.Label(
            edges, text="排除高度%",
        ).grid(row=3, column=0, sticky="e")
        self.footer_percent_spin = tk.Spinbox(
            edges, from_=0, to=35, increment=0.5, width=6,
            textvariable=self.footer_percent_var,
        )
        self.footer_percent_spin.grid(row=3, column=1, sticky="w")
        ttk.Label(
            edges, text="页边内容：",
        ).grid(row=4, column=0, sticky="e", pady=5)
        ttk.Combobox(
            edges, textvariable=self.side_mode_var, state="readonly", width=22,
            values=tuple(SIDE_LABEL_TO_VALUE.keys()),
        ).grid(row=4, column=1, sticky="w", pady=5)

        ttk.Label(
            edges, text="固定页边宽度%",
        ).grid(row=5, column=0, sticky="e")
        self.side_percent_spin = tk.Spinbox(
            edges, from_=0, to=30, increment=0.5, width=6,
            textvariable=self.side_percent_var,
        )
        self.side_percent_spin.grid(row=5, column=1, sticky="w")

        ttk.Label(
            edges, text="A 页排除宽度%",
        ).grid(row=6, column=0, sticky="e", pady=(4, 0))
        self.side_percent_a_spin = tk.Spinbox(
            edges, from_=0, to=30, increment=0.5, width=6,
            textvariable=self.side_percent_a_var,
        )
        self.side_percent_a_spin.grid(row=6, column=1, sticky="w", pady=(4, 0))
        ttk.Label(
            edges, text="B 页排除宽度%",
        ).grid(row=7, column=0, sticky="e", pady=(4, 0))
        self.side_percent_b_spin = tk.Spinbox(
            edges, from_=0, to=30, increment=0.5, width=6,
            textvariable=self.side_percent_b_var,
        )
        self.side_percent_b_spin.grid(row=7, column=1, sticky="w", pady=(4, 0))

        ttk.Label(
            edges, text="A/B 起始页：",
        ).grid(row=8, column=0, sticky="e", pady=(10, 4))
        self.first_variant_combo = ttk.Combobox(
            edges, textvariable=self.first_variant_var,
            state="readonly", width=8, values=("A", "B"),
        )
        self.first_variant_combo.grid(row=8, column=1, sticky="w", pady=(10, 4))
        ttk.Label(
            edges,
            text=(
                "选“外侧/内侧交替”时，A 与 B 的页边宽度分别控制，"
                "不要求两边比例一致；第一张扫描若属于 B 页，可在这里整体翻转。"
            ),
            foreground="#666666",
            wraplength=self._wizard_left_width,
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(8, 0))

        for variable in (
            self.header_mode_var, self.footer_mode_var, self.side_mode_var,
        ):
            variable.trace_add(
                "write", lambda *_args: self.after_idle(self._refresh_template_controls)
            )
        self._refresh_template_controls()


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
        """Render the representative-page template preview without blocking Tk."""
        if not hasattr(self, "template_preview_frame"):
            return
        for child in self.template_preview_frame.winfo_children():
            child.destroy()
        self._template_photos.clear()
        if not self.sample_indices:
            ttk.Label(self.template_preview_frame, text="没有可预览页面").grid(row=0, column=0)
            self.template_preview_caption_var.set("")
            return

        self.template_preview_slot %= len(self.sample_indices)
        slot = int(self.template_preview_slot)
        index = int(self.sample_indices[slot])
        path = self.project.images[index]
        try:
            settings = self._settings_from_ui()
            header_mode = HEADER_LABEL_TO_VALUE.get(self.header_mode_var.get(), "auto")
            footer_mode = FOOTER_LABEL_TO_VALUE.get(self.footer_mode_var.get(), "none")
            header_percent = max(0.0, min(35.0, float(self.header_percent_var.get())))
            footer_percent = max(0.0, min(35.0, float(self.footer_percent_var.get())))
            self.update_idletasks()
            right_width = int(getattr(self, "right_canvas", self).winfo_width())
            target_width = max(
                420,
                (right_width - 24) if right_width > 100
                else (self._wizard_image_width - 24),
            )
            target_height = max(420, int(self._wizard_height * 0.72))
        except Exception as exc:
            ttk.Label(
                self.template_preview_frame,
                text=f"{path.name}\n预览参数无效：{exc}",
            ).grid(row=0, column=0)
            self.template_preview_caption_var.set(path.name)
            return

        ttk.Label(
            self.template_preview_frame,
            text=f"正在后台生成预览…\n{path.name}",
            justify="center",
        ).grid(row=0, column=0, sticky="n", pady=30)
        self.template_preview_caption_var.set(
            f"{slot + 1}/{len(self.sample_indices)} · {path.name} · 正在生成…"
        )
        worker_key = f"profile-template-preview-{id(self)}"

        def worker():
            with Image.open(path) as opened:
                source = normalize_page_rgb(opened)
            preview = source.copy()
            preview.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
            draw = ImageDraw.Draw(preview, "RGBA")
            w, h = preview.size

            if header_mode == "present":
                draw.rectangle(
                    (0, 0, w, round(h * header_percent / 100.0)),
                    fill=(255, 215, 0, 105),
                )
            if footer_mode == "present":
                draw.rectangle(
                    (0, round(h * (1.0 - footer_percent / 100.0)), w, h),
                    fill=(255, 215, 0, 105),
                )

            side = excluded_source_side(settings, index)
            if side:
                sp = excluded_source_side_percent(settings, index)
                margin = round(w * sp / 100.0)
                if side == "left":
                    draw.rectangle((0, 0, margin, h), fill=(255, 215, 0, 105))
                else:
                    draw.rectangle((w - margin, 0, w, h), fill=(255, 215, 0, 105))

            effective = effective_page_settings(settings, source.size, index)
            analysis_image = page_template_analysis_image(source, effective, index)
            geometry = derive_geometry(analysis_image, effective)
            sx = w / max(1, source.width)
            sy = h / max(1, source.height)
            canonical_w, canonical_h = geometry.transform.canonical_size(source.size)

            if header_mode == "auto" and geometry.top > 0:
                x0, y0, x1, y1 = geometry.transform.canonical_box_to_source(
                    (0, 0, canonical_w, min(canonical_h, geometry.top)),
                    source.size,
                )
                draw.rectangle(
                    (x0 * sx, y0 * sy, x1 * sx, y1 * sy),
                    fill=(255, 215, 0, 105),
                )
            if footer_mode == "auto" and geometry.bottom < canonical_h:
                x0, y0, x1, y1 = geometry.transform.canonical_box_to_source(
                    (0, max(0, geometry.bottom), canonical_w, canonical_h),
                    source.size,
                )
                draw.rectangle(
                    (x0 * sx, y0 * sy, x1 * sx, y1 * sy),
                    fill=(255, 215, 0, 105),
                )
            for path_points in geometry.column_paths:
                points = [
                    geometry.canonical_to_source(x, y)
                    for y, x in path_points.points
                ]
                coords = [
                    coordinate
                    for px, py in points
                    for coordinate in (px * sx, py * sy)
                ]
                if len(coords) >= 4:
                    draw.line(coords, fill=(30, 120, 210, 210), width=2)

            variant = page_variant(settings, index)
            side_text = side or "无页边排除"
            region = ("前部", "中部", "后部")[min(2, slot // 2)]
            caption = (
                f"{region} · {slot + 1}/{len(self.sample_indices)} · "
                f"{variant} 页 · {path.name} · 页边：{side_text}"
            )
            return preview, caption, index, slot

        def done(payload) -> None:
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return
            preview, caption, result_index, result_slot = payload
            if (
                result_slot != self.template_preview_slot
                or result_slot >= len(self.sample_indices)
                or self.sample_indices[result_slot] != result_index
            ):
                return
            for child in self.template_preview_frame.winfo_children():
                child.destroy()
            photo = ImageTk.PhotoImage(preview)
            self._template_photos[:] = [photo]
            ttk.Label(
                self.template_preview_frame, image=photo,
            ).grid(row=0, column=0, sticky="n")
            self.template_preview_caption_var.set(caption)

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return
            for child in self.template_preview_frame.winfo_children():
                child.destroy()
            ttk.Label(
                self.template_preview_frame,
                text=f"{path.name}\n预览失败：{exc}",
            ).grid(row=0, column=0)
            self.template_preview_caption_var.set(path.name)

        self.parent._start_ui_worker(worker_key, worker, done, failed)

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
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="③ 什么才算一个新词条？", font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            tab,
            text="词头结构只控制词头识别，不再偷偷改变横/竖排、分栏或 OCR 语言。",
            foreground="#666666",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))

        ttk.Label(tab, text="词头结构：").grid(row=2, column=0, sticky="e", padx=(0, 8))
        self.headword_combo = ttk.Combobox(
            tab, textvariable=self.headword_profile_var, state="readonly", width=48,
            values=tuple(label for label, _key in self.profile_choices),
        )
        self.headword_combo.grid(row=2, column=1, sticky="ew")
        self.headword_combo.bind("<<ComboboxSelected>>", lambda _e: self._headword_changed())

        ttk.Label(tab, text="自定义结构名称：").grid(row=3, column=0, sticky="e", padx=(0, 8), pady=7)
        self.custom_name_entry = ttk.Entry(tab, textvariable=self.custom_name_var)
        self.custom_name_entry.grid(row=3, column=1, sticky="ew", pady=7)
        self.custom_name_var.trace_add("write", lambda *_args: self.after_idle(self._custom_name_changed))

        self.headword_description_var = tk.StringVar(value="")
        ttk.Label(
            tab, textvariable=self.headword_description_var,
            wraplength=self._wizard_content_width, justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))

        structures = ttk.LabelFrame(
            tab, text="允许的词头结构（决定哪些 parser 通道开放）", padding=10,
        )
        structures.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        structures.columnconfigure(0, weight=1)
        self.headword_structure_frame = structures
        for row, (label, variable) in enumerate((
            ("普通左缘短词可以作为词头", self.ordinary_left_edge_var),
            ("【括号词】可以作为词头", self.cjk_allow_bracketed_var),
            ("大字单字可以作为词头", self.cjk_allow_single_var),
            ("固定符号开头（○ / ● / ◆ …）可以作为词头", self.marker_prefix_var),
            ("编号开头（1. / 2. / …）可以作为词头", self.numbered_prefix_var),
        )):
            ttk.Checkbutton(
                structures, text=label, variable=variable,
                command=self._headword_structure_changed,
            ).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Label(
            structures,
            text="这里决定“谁有资格成为候选”。取消某一项后，该结构不会再靠后续阈值被误救回来。",
            foreground="#666666", wraplength=self._wizard_content_width,
        ).grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.headword_structure_summary_var = tk.StringVar(value="")
        ttk.Label(
            structures, textvariable=self.headword_structure_summary_var,
            foreground="#555555", wraplength=self._wizard_content_width,
        ).grid(row=6, column=0, sticky="w", pady=(4, 0))

        specificity = ttk.LabelFrame(
            tab, text="词头专属性（当前结构的视觉证据）", padding=10,
        )
        specificity.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        specificity.columnconfigure(1, weight=1)
        self.headword_specificity_frame = specificity
        self.headword_specificity_hint_var = tk.StringVar(value="")
        ttk.Label(
            specificity, textvariable=self.headword_specificity_hint_var,
            foreground="#666666", wraplength=self._wizard_left_width,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 7))

        ttk.Label(specificity, text="栏左缘容差：").grid(row=1, column=0, sticky="e", pady=3)
        tk.Spinbox(
            specificity, from_=4, to=120, increment=1, width=7,
            textvariable=self.headword_left_tolerance_var,
        ).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(
            specificity,
            text="px（允许词头起点偏离栏左边界的最大距离；越小越严格）",
            foreground="#666666",
        ).grid(row=1, column=2, sticky="w")

        ttk.Label(specificity, text="文字大小倍率 ≥").grid(row=2, column=0, sticky="e", pady=3)
        tk.Spinbox(
            specificity, from_=0.5, to=3.0, increment=0.02, width=7,
            textvariable=self.headword_height_ratio_var, format="%.2f",
        ).grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(specificity, text="粗体倍率 ≥").grid(row=3, column=0, sticky="e", pady=3)
        tk.Spinbox(
            specificity, from_=0.5, to=3.0, increment=0.02, width=7,
            textvariable=self.headword_boldness_ratio_var, format="%.2f",
        ).grid(row=3, column=1, sticky="w", pady=3)

        ttk.Label(specificity, text="候选强度 ≥").grid(row=4, column=0, sticky="e", pady=3)
        tk.Spinbox(
            specificity, from_=0.0, to=12.0, increment=0.25, width=7,
            textvariable=self.headword_min_score_var, format="%.2f",
        ).grid(row=4, column=1, sticky="w", pady=3)

        self.cjk_specificity_frame = ttk.LabelFrame(
            specificity, text="CJK 单字 / 括号词附加条件", padding=7,
        )
        self.cjk_specificity_frame.grid(
            row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0)
        )
        for row, (label, variable) in enumerate((
            ("必须靠近栏左缘", self.cjk_require_left_edge_var),
            ("释义正文中也经常出现【括号词】", self.cjk_brackets_in_body_var),
            ("只有视觉明显突出时才把单字/括号词当词头", self.cjk_require_visual_var),
        )):
            ttk.Checkbutton(
                self.cjk_specificity_frame, text=label, variable=variable,
                command=self._headword_specificity_changed,
            ).grid(row=row, column=0, sticky="w", pady=2)

        self.headword_tuning_status_var = tk.StringVar(value="")
        ttk.Label(
            specificity, textvariable=self.headword_tuning_status_var,
            foreground="#555555",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))

        help_box = ttk.LabelFrame(tab, text="理解方式", padding=10)
        help_box.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        help_box.columnconfigure(0, weight=1)
        self.headword_help_frame = help_box

    def _build_language_tab(self, tab: ttk.Frame) -> None:
        """Compatibility wrapper; language/OCR now lives in step 1."""
        tab.columnconfigure(0, weight=1)
        self._build_language_section(tab, row=0)


    def _build_validation_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        ttk.Label(
            tab, text="④ 多页测试后再确认",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            tab,
            text="测试只处理代表页，不写 PDIC；PaddleOCR 强制重新识别，不复用旧 OCR 缓存。右侧一次显示一页，可左右翻页。",
            foreground="#666666", wraplength=self._wizard_left_width,
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))

        bar = ttk.Frame(tab)
        bar.grid(row=2, column=0, sticky="ew")
        self.validate_button = ttk.Button(
            bar, text="测试当前 Profile", command=self.validate_profile,
        )
        self.validate_button.pack(side="left")
        self.validation_status_var = tk.StringVar(value="尚未测试")
        ttk.Label(
            bar, textvariable=self.validation_status_var,
            wraplength=max(260, self._wizard_left_width - 160),
        ).pack(side="left", padx=(10, 0))

        self.validation_diagnostic_var = tk.StringVar(
            value="测试方式：PaddleOCR（强制重新识别）｜尚未运行测试"
        )
        ttk.Label(
            tab, textvariable=self.validation_diagnostic_var,
            foreground="#555555", justify="left",
            wraplength=self._wizard_left_width,
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))

        feedback = ttk.LabelFrame(tab, text="结果是否合适？", padding=(8, 6))
        feedback.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        feedback.columnconfigure(3, weight=1)
        ttk.Label(
            feedback,
            text="偏多会按当前词头类型收紧；偏少会放宽。调整后重新测试，直到右侧画线结果合适。",
            foreground="#666666", wraplength=self._wizard_left_width,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 5))
        self.feedback_too_many_button = ttk.Button(
            feedback, text="偏多",
            command=lambda: self._apply_validation_feedback("too_many"),
            state="disabled",
        )
        self.feedback_too_many_button.grid(row=1, column=0, padx=(0, 4))
        self.feedback_good_button = ttk.Button(
            feedback, text="合适",
            command=lambda: self._apply_validation_feedback("good"),
            state="disabled",
        )
        self.feedback_good_button.grid(row=1, column=1, padx=4)
        self.feedback_too_few_button = ttk.Button(
            feedback, text="偏少",
            command=lambda: self._apply_validation_feedback("too_few"),
            state="disabled",
        )
        self.feedback_too_few_button.grid(row=1, column=2, padx=4)
        self.validation_feedback_var = tk.StringVar(value="")
        ttk.Label(
            feedback, textvariable=self.validation_feedback_var,
            wraplength=max(260, self._wizard_left_width - 260),
        ).grid(row=1, column=3, sticky="w", padx=(10, 0))


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

    def _profile_input_changed(self) -> None:
        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_summary()
        if hasattr(self, "template_preview_frame"):
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

    def _specificity_defaults_for_profile(self, key: str) -> tuple[int, float, float, float]:
        temp = replace(self.working)
        temp.ocr_language = _ocr_language_code(self.ocr_language_var.get())
        apply_headword_profile(temp, key)
        for name, value in language_effective_settings(
            temp.ocr_language, temp.layout_writing_mode
        ).items():
            if hasattr(temp, name):
                setattr(temp, name, value)
        return (
            int(getattr(temp, "paddle_left_tolerance", 34)),
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
        self._refresh_summary()

    def _refresh_headword_structure_summary(self) -> None:
        if not hasattr(self, "headword_structure_summary_var"):
            return
        active: list[str] = []
        if self.ordinary_left_edge_var.get():
            active.append("普通左缘短词")
        if self.cjk_allow_bracketed_var.get():
            active.append("【括号词】")
        if self.cjk_allow_single_var.get():
            active.append("大字单字")
        if self.marker_prefix_var.get():
            active.append("固定符号")
        if self.numbered_prefix_var.get():
            active.append("编号前缀")
        self.headword_structure_summary_var.set(
            "当前允许：" + ("、".join(active) if active else "无（不会自动生成词头）")
        )

    def _refresh_headword_specificity_visibility(self) -> None:
        if not hasattr(self, "headword_specificity_frame"):
            return
        self.headword_specificity_frame.grid()
        show_cjk = bool(
            self.cjk_allow_bracketed_var.get() or self.cjk_allow_single_var.get()
        )
        if hasattr(self, "cjk_specificity_frame"):
            if show_cjk:
                self.cjk_specificity_frame.grid()
            else:
                self.cjk_specificity_frame.grid_remove()

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
            Path(__file__).resolve().parent
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
        key = self._current_profile_key()
        try:
            profile = dictionary_profile_preset(key)
        except Exception:
            return
        self.custom_name_entry.configure(state="normal" if key == "custom" else "disabled")
        self.headword_description_var.set(profile.description)
        self._refresh_headword_structure_summary()
        self._refresh_headword_specificity_visibility()
        hints = {
            "latin_regular": "常规边缘：栏边位置是主证据；字号、粗体和词后结构辅助判断。",
            "cjk_visual": "视觉型：大字/括号结构及视觉突出程度是主证据。",
            "numbered_prefix": "编号型：编号前缀是主证据；字号/粗体属于辅助证据。",
            "marker_prefixed": "符号型：○ / ● / ◆ 等固定符号是主证据；字号/粗体属于辅助证据。",
            "custom": "自定义：基础视觉门槛可配合上方 parser 勾选逐页测试。",
        }
        if hasattr(self, "headword_specificity_hint_var"):
            self.headword_specificity_hint_var.set(
                hints.get(key, "当前结构的左缘、字号、粗体与候选强度门槛。")
            )
        self._refresh_headword_tuning_status()

        for child in self.headword_examples_frame.winfo_children():
            child.destroy()
        self._headword_example_photos.clear()

        example_file = HEADWORD_EXAMPLE_FILES.get(key)
        if example_file:
            image = self._headword_example_image(key)
            if image is not None:
                self.update_idletasks()
                right_width = int(getattr(self, "right_canvas", self).winfo_width())
                available = (
                    right_width if right_width > 100 else self._wizard_image_width
                )
                image.thumbnail(
                    (max(320, available - 20), 520), Image.Resampling.LANCZOS,
                )
                photo = ImageTk.PhotoImage(image)
                self._headword_example_photos.append(photo)
                ttk.Label(
                    self.headword_examples_frame, image=photo,
                ).grid(row=0, column=0, columnspan=2, sticky="n", padx=5, pady=5)
            else:
                ttk.Label(
                    self.headword_examples_frame,
                    text=f"缺少样例图片：{example_file}",
                    anchor="center", justify="center",
                ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=30)
        else:
            ttk.Label(
                self.headword_examples_frame,
                text="自定义结构不绑定内置样例，请用右侧多页测试确认识别效果。",
                anchor="center", justify="center",
                wraplength=self._wizard_image_width,
            ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=30)

        for child in self.headword_help_frame.winfo_children():
            child.destroy()
        lines = HEADWORD_HELP_LINES.get(key) or (
            "识别对象：按当前结构预设判断词条起始。",
            "建议：结合第④步多页测试确认是否稳定。",
        )
        for row, line in enumerate(lines):
            ttk.Label(
                self.headword_help_frame,
                text=line, wraplength=self._wizard_content_width, justify="left",
            ).grid(row=row, column=0, sticky="w", pady=3)

    def _ocr_language_changed(self) -> None:
        language = _ocr_language_code(self.ocr_language_var.get())
        auto_index = OCR_TO_INDEX_LANGUAGE.get(language)
        if auto_index:
            self.index_language_var.set(auto_index)
        self._refresh_language_summary()
        self._refresh_summary()

    def _refresh_language_summary(self) -> None:
        language = _ocr_language_code(self.ocr_language_var.get())
        temp = replace(self.working)
        temp.ocr_language = language
        apply_reading_choice(temp, self.reading_var.get())
        derived = language_effective_settings(language, temp.layout_writing_mode)
        self.backend_summary_var.set(
            "PaddleOCR：{paddle}\nTesseract：{tess}\nPSM：{psm}    文字行方向识别：{orientation}".format(
                paddle=derived.get("paddle_language") or "自动",
                tess=derived.get("tesseract_language") or language,
                psm=derived.get("paddle_tesseract_psm", 6),
                orientation="开" if derived.get("paddle_use_textline_orientation") else "关",
            )
        )

    def _settings_from_ui(self) -> AppSettings:
        s = replace(self.working)
        s.dictionary_full_name = self.dictionary_full_name_var.get().strip()
        s.dictionary_abbreviation = self.dictionary_abbreviation_var.get().strip()
        s.dictionary_isbn = self.dictionary_isbn_var.get().strip()
        s.dictionary_body_page_range = self.dictionary_body_page_range_var.get().strip()
        apply_reading_choice(s, self.reading_var.get())
        # Runtime geometry uses the project-confirmed column count. Automatic
        # analysis above is a setup aid, not a hidden per-page detector.
        s.layout_columns_policy = "fixed"
        s.columns = max(1, int(self.columns_var.get()))
        s.layout_column_separator_mode = SEPARATOR_LABEL_TO_VALUE.get(
            self.separator_var.get(), "auto"
        )
        s.profile_header_mode = HEADER_LABEL_TO_VALUE.get(
            self.header_mode_var.get(), "auto"
        )
        s.profile_footer_mode = FOOTER_LABEL_TO_VALUE.get(
            self.footer_mode_var.get(), "auto"
        )
        s.profile_side_content_mode = SIDE_LABEL_TO_VALUE.get(
            self.side_mode_var.get(), "none"
        )
        s.profile_page_pair_mode = (
            "alternate" if s.profile_side_content_mode in {"outer", "inner"} else "same"
        )
        s.profile_first_page_variant = self.first_variant_var.get()
        s.profile_header_percent = max(0.0, min(35.0, float(self.header_percent_var.get())))
        s.profile_footer_percent = max(0.0, min(35.0, float(self.footer_percent_var.get())))
        s.profile_side_percent = max(0.0, min(30.0, float(self.side_percent_var.get())))
        s.profile_side_percent_a = max(
            0.0, min(30.0, float(self.side_percent_a_var.get()))
        )
        s.profile_side_percent_b = max(
            0.0, min(30.0, float(self.side_percent_b_var.get()))
        )
        s.dictionary_custom_profile_name = self.custom_name_var.get().strip()
        s.ocr_language = _ocr_language_code(self.ocr_language_var.get())
        s.dictionary_index_language = self.index_language_var.get().strip()
        s.dictionary_content_language = self.content_language_var.get().strip()
        s.profile_headword_tuning_level = max(
            -2, min(2, int(self.headword_tuning_level_var.get()))
        )
        s.profile_parser_controls_version = 1
        s.profile_allow_ordinary_left_edge = bool(self.ordinary_left_edge_var.get())
        s.profile_allow_numbered_prefix = bool(self.numbered_prefix_var.get())
        s.profile_allow_marker_prefix = bool(self.marker_prefix_var.get())
        s.profile_cjk_allow_single_headword = bool(self.cjk_allow_single_var.get())
        s.profile_cjk_allow_bracketed_headword = bool(self.cjk_allow_bracketed_var.get())
        s.profile_cjk_require_left_edge = bool(self.cjk_require_left_edge_var.get())
        s.profile_cjk_brackets_in_body = bool(self.cjk_brackets_in_body_var.get())
        s.profile_cjk_require_visual_evidence = bool(self.cjk_require_visual_var.get())
        profile_key = self._current_profile_key()
        apply_headword_profile(s, profile_key)
        for name, value in language_effective_settings(s.ocr_language, s.layout_writing_mode).items():
            if hasattr(s, name):
                setattr(s, name, value)
        apply_headword_tuning(s, profile_key, s.profile_headword_tuning_level)
        # Wizard specificity values are explicit project overrides and therefore
        # take precedence over preset/tuning defaults.
        s.paddle_left_tolerance = max(
            4, min(120, int(self.headword_left_tolerance_var.get()))
        )
        s.paddle_height_ratio = max(
            0.5, min(3.0, float(self.headword_height_ratio_var.get()))
        )
        s.paddle_boldness_ratio = max(
            0.5, min(3.0, float(self.headword_boldness_ratio_var.get()))
        )
        s.paddle_min_candidate_score = max(
            0.0, min(12.0, float(self.headword_min_score_var.get()))
        )
        s.profile_setup_version = PROFILE_SETUP_VERSION
        return s

    def _refresh_summary(self) -> None:
        try:
            settings = self._settings_from_ui()
            self.summary_var.set("  ｜  ".join(profile_summary_tags(settings)))
        except Exception:
            return

    def _sample_groups(self) -> list[ttk.LabelFrame]:
        for child in self.sample_frame.winfo_children():
            child.destroy()
        self._sample_cells.clear()
        self._sample_photo_by_slot.clear()
        region_titles = ("前部", "中部", "后部")
        groups: list[ttk.LabelFrame] = []
        for column, title in enumerate(region_titles):
            group = ttk.LabelFrame(self.sample_frame, text=title, padding=5)
            group.grid(row=0, column=column, sticky="nsew", padx=3, pady=2)
            group.columnconfigure(0, weight=1)
            group.rowconfigure(0, weight=1, uniform="sample_row")
            group.rowconfigure(1, weight=1, uniform="sample_row")
            groups.append(group)
        return groups

    def _show_sample_loading_state(self) -> None:
        groups = self._sample_groups()
        self._photos.clear()
        for slot, index in enumerate(self.sample_indices):
            path = self.project.images[index]
            group = groups[min(2, slot // 2)]
            cell = ttk.Frame(group)
            cell.grid(row=slot % 2, column=0, sticky="nsew", pady=3)
            cell.columnconfigure(0, weight=1)
            cell.rowconfigure(0, weight=1)
            self._sample_cells[slot] = cell
            ttk.Label(
                cell, text="正在加载代表页…", anchor="center",
            ).pack(fill="x", ipady=24)
            ttk.Label(cell, text=path.name, wraplength=260).pack(anchor="center", pady=(3, 0))
            ttk.Button(
                cell, text="更换…", command=lambda s=slot: self._choose_sample_page(s),
            ).pack(anchor="center", pady=(3, 0))

    def _start_sample_thumbnail_load(self) -> None:
        if not self.winfo_exists():
            return
        self._thumbnail_load_generation += 1
        generation = self._thumbnail_load_generation
        indices = list(self.sample_indices)
        paths = [self.project.images[index] for index in indices]
        self._show_sample_loading_state()
        self.update_idletasks()
        right_w = int(getattr(self, "right_canvas", self).winfo_width())
        right_h = int(getattr(self, "right_canvas", self).winfo_height())
        available_w = right_w if right_w > 200 else self._wizard_image_width
        available_h = right_h if right_h > 300 else self._wizard_height
        thumb_w = max(180, (available_w - 54) // 3)
        thumb_h = max(220, (available_h - 150) // 2 - 42)

        result_queue: queue.Queue = queue.Queue(maxsize=1)
        self._thumbnail_queue = result_queue

        def worker() -> None:
            results = []
            for slot, (index, path) in enumerate(zip(indices, paths)):
                try:
                    with Image.open(path) as opened:
                        image = normalize_page_rgb(opened)
                    image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
                    results.append((slot, index, path.name, image, None))
                except Exception as exc:
                    results.append((slot, index, path.name, None, str(exc)))
            result_queue.put((generation, results))

        threading.Thread(target=worker, daemon=True).start()
        self.after(50, self._poll_sample_thumbnail_load)

    def _poll_sample_thumbnail_load(self) -> None:
        if self._thumbnail_queue is None:
            return
        try:
            generation, results = self._thumbnail_queue.get_nowait()
        except queue.Empty:
            if self.winfo_exists():
                self.after(50, self._poll_sample_thumbnail_load)
            return
        self._thumbnail_queue = None
        if generation != self._thumbnail_load_generation:
            return
        self._finish_sample_thumbnail_load(results)

    def _render_sample_thumbnail_slot(
        self, slot: int, index: int, name: str,
        image: Image.Image | None, error: str | None,
    ) -> None:
        """Replace one representative-page cell without rebuilding its siblings."""
        if slot >= len(self.sample_indices) or self.sample_indices[slot] != index:
            return
        cell = self._sample_cells.get(slot)
        if cell is None or not cell.winfo_exists():
            return
        for child in cell.winfo_children():
            child.destroy()
        if image is not None:
            photo = ImageTk.PhotoImage(image)
            self._sample_photo_by_slot[slot] = photo
            ttk.Label(cell, image=photo, anchor="center").pack(fill="both", expand=True)
        else:
            self._sample_photo_by_slot.pop(slot, None)
            ttk.Label(
                cell, text=f"缩略图失败：{error}", wraplength=250,
            ).pack(fill="x", ipady=20)
        ttk.Label(cell, text=name, wraplength=260).pack(anchor="center", pady=(3, 0))
        ttk.Button(
            cell, text="更换…", command=lambda s=slot: self._choose_sample_page(s),
        ).pack(anchor="center", pady=(3, 0))

    def _finish_sample_thumbnail_load(self, results) -> None:
        groups = self._sample_groups()
        self._photos.clear()
        for slot, index, name, image, error in results:
            if slot >= len(self.sample_indices) or self.sample_indices[slot] != index:
                continue
            group = groups[min(2, slot // 2)]
            cell = ttk.Frame(group)
            cell.grid(row=slot % 2, column=0, sticky="nsew", pady=3)
            cell.columnconfigure(0, weight=1)
            cell.rowconfigure(0, weight=1)
            self._sample_cells[slot] = cell
            self._render_sample_thumbnail_slot(slot, index, name, image, error)

    def _start_sample_thumbnail_slot_load(self, slot: int) -> None:
        """Decode only one replacement thumbnail and keep all other cells intact."""
        if not self.winfo_exists() or not (0 <= slot < len(self.sample_indices)):
            return
        index = self.sample_indices[slot]
        path = self.project.images[index]
        generation = self._thumbnail_slot_generation.get(slot, 0) + 1
        self._thumbnail_slot_generation[slot] = generation
        token = (slot, generation)
        self._thumbnail_slot_pending.add(token)

        self.update_idletasks()
        right_w = int(getattr(self, "right_canvas", self).winfo_width())
        right_h = int(getattr(self, "right_canvas", self).winfo_height())
        available_w = right_w if right_w > 200 else self._wizard_image_width
        available_h = right_h if right_h > 300 else self._wizard_height
        thumb_w = max(180, (available_w - 54) // 3)
        thumb_h = max(220, (available_h - 150) // 2 - 42)

        def worker() -> None:
            image = None
            error = None
            try:
                with Image.open(path) as opened:
                    image = normalize_page_rgb(opened)
                image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            except Exception as exc:
                error = str(exc)
            self._thumbnail_slot_queue.put(
                (slot, generation, index, path.name, image, error)
            )

        threading.Thread(target=worker, daemon=True).start()
        self.after(50, self._poll_sample_thumbnail_slot_load)

    def _poll_sample_thumbnail_slot_load(self) -> None:
        processed = False
        while True:
            try:
                slot, generation, index, name, image, error = (
                    self._thumbnail_slot_queue.get_nowait()
                )
            except queue.Empty:
                break
            processed = True
            self._thumbnail_slot_pending.discard((slot, generation))
            if self._thumbnail_slot_generation.get(slot) != generation:
                continue
            self._render_sample_thumbnail_slot(slot, index, name, image, error)

        if self._thumbnail_slot_pending and self.winfo_exists():
            self.after(50, self._poll_sample_thumbnail_slot_load)
        elif processed:
            self.update_idletasks()

    def _choose_sample_page(self, slot: int) -> None:
        all_indices = list(range(len(self.project.images)))
        if not all_indices:
            return
        auto_candidates = set(self.sample_candidates)
        picker = tk.Toplevel(self)
        picker.title("更换代表页")
        picker.geometry("680x540")
        picker.transient(self)
        picker.grab_set()

        ttk.Label(
            picker,
            text=(
                "自动抽样会避开 0000_*、目录、附录等明显非正文页；"
                "手动更换时仍可从项目全部页面中选择。"
            ),
            wraplength=640,
        ).pack(anchor="w", padx=10, pady=(10, 6))
        body = ttk.Frame(picker)
        body.pack(fill="both", expand=True, padx=10)
        scrollbar = ttk.Scrollbar(body, orient="vertical")
        listing = tk.Listbox(body, yscrollcommand=scrollbar.set, exportselection=False)
        scrollbar.configure(command=listing.yview)
        listing.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        current = self.sample_indices[slot]
        selected_row = current
        for row, index in enumerate(all_indices):
            path = self.project.images[index]
            status = "正文候选" if index in auto_candidates else "自动略过 · 手动可选"
            listing.insert("end", f"{index + 1:05d}    [{status}]    {path.name}")
            if index == current:
                selected_row = row
        listing.selection_set(selected_row)
        listing.see(selected_row)

        def apply_choice(_event=None) -> None:
            selection = listing.curselection()
            if not selection:
                return
            index = all_indices[int(selection[0])]
            current_index = self.sample_indices[slot]
            if index == current_index:
                picker.destroy()
                return
            if index in self.sample_indices:
                messagebox.showinfo("代表页已使用", "这张页面已经在代表页中，请选择另一张。", parent=picker)
                return
            preview_uses_slot = self.template_preview_slot == slot
            self.sample_indices[slot] = index
            self.template_preview_slot = min(
                self.template_preview_slot, len(self.sample_indices) - 1
            )
            self._profile_revision += 1
            self._mark_validation_stale()
            self._analysis_suggestion = {}
            if hasattr(self, "analysis_suggestion_var"):
                self.analysis_suggestion_var.set("代表页已更换，请重新分析当前代表页。")
                self.apply_analysis_button.configure(state="disabled")

            # A manual replacement changes exactly one representative-page
            # slot. Do not rebuild or re-decode the other five thumbnails.
            self._start_sample_thumbnail_slot_load(slot)

            # The template preview is hidden while representative pages are
            # being edited. Refresh it only when it is actually visible and the
            # replaced slot is the page currently previewed there.
            if preview_uses_slot and hasattr(self, "notebook"):
                try:
                    if self.notebook.index(self.notebook.select()) == 1:
                        self._refresh_template_preview()
                except (tk.TclError, ValueError):
                    pass
            picker.destroy()

        listing.bind("<Double-Button-1>", apply_choice)
        footer = ttk.Frame(picker)
        footer.pack(fill="x", padx=10, pady=10)
        ttk.Button(footer, text="取消", command=picker.destroy).pack(side="right")
        ttk.Button(footer, text="使用此页", command=apply_choice).pack(side="right", padx=(0, 8))

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
        if current == 0 and target == 1 and not self._analysis_suggestion and not self._analysis_running:
            self.analyze_representative_pages(auto_apply=True)

    def analyze_representative_pages(self, auto_apply: bool = False) -> None:
        if self._analysis_running or not self.sample_indices:
            return
        self._analysis_running = True
        self._analysis_revision_started = self._profile_revision
        self._analysis_auto_apply = bool(auto_apply)
        self.analyze_button.configure(state="disabled")
        self.analysis_suggestion_var.set("正在分析代表页版面…")
        settings = self._settings_from_ui()
        indices = list(self.sample_indices)

        def worker() -> None:
            estimates = []
            errors: list[str] = []
            for index in indices:
                path = self.project.images[index]
                try:
                    with Image.open(path) as opened:
                        image = normalize_page_rgb(opened)
                    page_settings = effective_page_settings(settings, image.size, index)
                    analysis_image = page_template_analysis_image(image, page_settings, index)
                    estimates.append(detect_layout_parameters(analysis_image, page_settings))
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
            assert self._analysis_queue is not None
            self._analysis_queue.put((estimates, errors))

        self._analysis_queue = queue.Queue(maxsize=1)
        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_analysis_queue)

    def _poll_analysis_queue(self) -> None:
        if self._analysis_queue is None:
            return
        try:
            estimates, errors = self._analysis_queue.get_nowait()
        except queue.Empty:
            if self.winfo_exists() and self._analysis_running:
                self.after(100, self._poll_analysis_queue)
            return
        self._analysis_queue = None
        self._finish_analysis(estimates, errors)

    def _finish_analysis(self, estimates, errors: list[str]) -> None:
        self._analysis_running = False
        self.analyze_button.configure(state="normal")
        if self._analysis_revision_started != self._profile_revision:
            self._analysis_suggestion = {}
            self._analysis_auto_apply = False
            self.analysis_suggestion_var.set(
                "分析期间 Profile 设置已改变；旧分析结果已丢弃，请重新分析代表页。"
            )
            self.apply_analysis_button.configure(state="disabled")
            return
        if not estimates:
            self.analysis_suggestion_var.set("代表页分析失败；可直接人工选择页面模板。")
            self.apply_analysis_button.configure(state="disabled")
            return
        aggregate, consistency = aggregate_layout_estimates(estimates, columns_policy="detect")
        separators = sum(1 for estimate in estimates if getattr(estimate, "separator_x", None) is not None)
        separator = "present" if separators > len(estimates) / 2 else "absent"
        self._analysis_suggestion = {
            **{name: int(value) for name, value in aggregate.items()},
            "separator": separator,
        }
        sep_text = "有中央分隔线" if separator == "present" else "无明确中央分隔线"
        error_text = f"；{len(errors)} 页未参与" if errors else ""
        self.analysis_suggestion_var.set(
            f"自动建议：{aggregate['columns']}栏 · {sep_text} · {consistency}{error_text}"
        )
        self.apply_analysis_button.configure(state="normal")
        total_samples = len(estimates) + len(errors)
        enough_for_auto = len(estimates) >= max(2, (total_samples + 1) // 2)
        if self._analysis_auto_apply and enough_for_auto:
            self.apply_analysis_suggestion()
            self.analysis_suggestion_var.set(
                f"已采用代表页建议：{aggregate['columns']}栏 · {sep_text} · {consistency}{error_text}；可直接修改。"
            )
        elif self._analysis_auto_apply and not enough_for_auto:
            self.analysis_suggestion_var.set(
                f"自动建议：{aggregate['columns']}栏 · {sep_text} · {consistency}{error_text}；"
                "成功样本不足，未自动应用，请检查代表页后手动决定。"
            )
        self._analysis_auto_apply = False

    def apply_analysis_suggestion(self) -> None:
        if not self._analysis_suggestion:
            return
        self.columns_var.set(int(self._analysis_suggestion.get("columns", self.columns_var.get())))
        for name in (
            "start_y", "bottom_y", "manual_x", "column_width", "gutter",
            "character_height", "row_padding", "geometry_reference_width",
        ):
            if name in self._analysis_suggestion:
                setattr(self.working, name, int(self._analysis_suggestion[name]))
        separator_value = str(self._analysis_suggestion.get("separator", "auto"))
        self.separator_var.set(_label_for_value(
            SEPARATOR_LABEL_TO_VALUE, separator_value, "自动判断",
        ))

    @staticmethod
    def _validation_coverage_summary(
        cache_path: Path | None, entries, geometry, settings: AppSettings,
    ) -> str:
        """Show raw OCR coverage, final-headword coverage and rejection clues."""
        prefix = (
            "测试方式：PaddleOCR（强制重新识别）"
            f"｜列跟踪：{'开' if bool(getattr(settings, 'follow_column_deformation', False)) else '关'}"
        )
        if cache_path is None or not cache_path.exists() or not geometry.column_starts:
            return prefix + "\n诊断缓存未生成；请重新运行【测试当前 Profile】。"
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            columns = list(payload.get("columns") or [])
        except (OSError, ValueError, TypeError) as exc:
            return prefix + f"\n诊断缓存读取失败：{exc}"

        selected_by_column: dict[int, list[float]] = {
            index: [] for index in range(len(geometry.column_starts))
        }
        span = max(1, int(geometry.bottom) - int(geometry.top))
        for entry in entries:
            try:
                u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
                col = min(
                    range(len(geometry.column_starts)),
                    key=lambda idx: abs(geometry.x_at(idx, v) - u),
                )
                selected_by_column[col].append(
                    max(0.0, min(1.0, (float(v) - float(geometry.top)) / span))
                )
            except Exception:
                continue

        parts: list[str] = [prefix]
        for index in range(len(geometry.column_starts)):
            raw_pct = 0
            lower_total = 0
            lower_accepted = 0
            reject_counts: dict[str, int] = {}
            if index < len(columns):
                column = columns[index] or {}
                band_size = list(column.get("band_size") or [])
                band_height = max(1, int(band_size[1])) if len(band_size) >= 2 else span
                raw_bottom = 0
                for record in column.get("ocr_records", []) or []:
                    box = record.get("box") if isinstance(record, dict) else None
                    if isinstance(box, (list, tuple)) and len(box) == 4:
                        try:
                            raw_bottom = max(raw_bottom, int(box[3]))
                        except (TypeError, ValueError):
                            pass
                raw_pct = max(0, min(100, round(raw_bottom * 100 / band_height)))

                for row in column.get("candidates", []) or []:
                    if not isinstance(row, dict) or "meta" in row:
                        continue
                    box = row.get("box")
                    if not isinstance(box, (list, tuple)) or len(box) != 4:
                        continue
                    try:
                        center_y = (float(box[1]) + float(box[3])) / 2.0
                    except (TypeError, ValueError):
                        continue
                    if center_y < band_height * 0.50:
                        continue
                    lower_total += 1
                    if bool(row.get("accepted")):
                        lower_accepted += 1
                    else:
                        reason = str(row.get("reject_reason") or "candidate_rejected")
                        reject_counts[reason] = reject_counts.get(reason, 0) + 1

            selected_rows = selected_by_column.get(index) or []
            selected_pct = (
                max(0, min(100, round(max(selected_rows) * 100)))
                if selected_rows else 0
            )

            nominal_x = int(geometry.column_starts[index])
            path = (
                geometry.column_paths[index]
                if index < len(getattr(geometry, "column_paths", []))
                else None
            )
            drift = 0
            if path is not None:
                try:
                    drift = max(
                        [abs(int(x) - nominal_x) for _y, x in path.points] or [0]
                    )
                except Exception:
                    drift = 0

            if reject_counts:
                top_reasons = sorted(
                    reject_counts.items(), key=lambda item: (-item[1], item[0])
                )[:2]
                reason_text = "、".join(
                    f"{reason}×{count}" for reason, count in top_reasons
                )
            else:
                reason_text = "无"

            warning = ""
            if raw_pct >= 85 and selected_pct <= 65:
                warning = " ⚠原始OCR完整但词头在中途停止"
            parts.append(
                f"{index + 1}栏：原始OCR至{raw_pct}%｜词头至{selected_pct}%｜"
                f"下半页候选{lower_total}（通过{lower_accepted}；拒绝主因：{reason_text}）｜"
                f"左缘最大漂移{drift}px{warning}"
            )
        return "\n".join(parts)


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
        if not self._validation_results:
            return
        if result == "good":
            self.validation_feedback_var.set("已确认当前结果合适，可保存 Profile。")
            self.validation_status_var.set("当前多页测试结果已确认合适")
            return

        old_level = max(-2, min(2, int(self.headword_tuning_level_var.get())))
        delta = 1 if result == "too_many" else -1
        new_level = max(-2, min(2, old_level + delta))
        self.headword_tuning_level_var.set(new_level)

        key = self._current_profile_key()
        if new_level != old_level:
            if key == "cjk_visual":
                self.headword_left_tolerance_var.set(max(
                    4, int(self.headword_left_tolerance_var.get()) - 4 * delta
                ))
                self.headword_height_ratio_var.set(max(
                    0.5, round(float(self.headword_height_ratio_var.get()) + 0.04 * delta, 2)
                ))
                self.headword_boldness_ratio_var.set(max(
                    0.5, round(float(self.headword_boldness_ratio_var.get()) + 0.05 * delta, 2)
                ))
                self.headword_min_score_var.set(max(
                    0.0, round(float(self.headword_min_score_var.get()) + 0.25 * delta, 2)
                ))
                if result == "too_many":
                    # Keep real CJK big-character recall: tighten left-edge and
                    # visible numeric thresholds, but do not silently enable the
                    # extra strong-visual gate that previously dropped true heads.
                    self.cjk_require_left_edge_var.set(True)
            elif key in {"latin_regular", "legacy_spanish_structured"}:
                self.headword_left_tolerance_var.set(max(
                    4, int(self.headword_left_tolerance_var.get()) - 4 * delta
                ))
                self.headword_boldness_ratio_var.set(max(
                    0.5, round(float(self.headword_boldness_ratio_var.get()) + 0.06 * delta, 2)
                ))
                self.headword_min_score_var.set(max(
                    0.0, round(float(self.headword_min_score_var.get()) + 0.50 * delta, 2)
                ))
            elif key in {"numbered_prefix", "marker_prefixed"}:
                self.headword_left_tolerance_var.set(max(
                    4, int(self.headword_left_tolerance_var.get()) - 3 * delta
                ))
            else:
                self.headword_left_tolerance_var.set(max(
                    4, int(self.headword_left_tolerance_var.get()) - 3 * delta
                ))
                self.headword_min_score_var.set(max(
                    0.0, round(float(self.headword_min_score_var.get()) + 0.35 * delta, 2)
                ))

        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_headword_tuning_status()
        self._refresh_summary()
        direction = "收紧" if result == "too_many" else "放宽"
        if new_level == old_level:
            self.validation_feedback_var.set(
                f"已经达到自动{direction}上限（{new_level:+d}）；请在第③步直接勾选/取消不属于本词典的词头结构。"
            )
        else:
            self.validation_feedback_var.set(
                f"已按当前词头类型{direction}到 {new_level:+d} 级；请重新测试。"
            )
        self.validation_status_var.set("识别规则已调整，需要重新测试")
        self._set_feedback_buttons("disabled")

    def validate_profile(self) -> None:
        if self._validation_running:
            return
        if self.parent._ui_worker_key_active("profile-validation"):
            self.validation_status_var.set("上一轮 Profile 测试仍在安全结束，请稍后重试。")
            return
        settings = self._settings_from_ui()
        # Project Profile validates the normal OCR-based workflow even when an
        # old project last saved "普通画线" as its active detection method.
        settings.detection_method = "paddleocr"
        settings.paddle_use_paddleocr = True
        indices = list(self.sample_indices)
        if not indices:
            return
        project = self.project
        project_root = Path(project.root)
        paths = {index: project.images[index] for index in indices}
        self.update_idletasks()
        frame_width = int(self.validation_frame.winfo_width())
        preview_width = max(
            480,
            (frame_width - 20) if frame_width > 100
            else (int(self._wizard_image_width) - 8),
        )
        self._validation_running = True
        self._validation_revision_started = self._profile_revision
        self._validation_stop_event.clear()
        stop_event = self._validation_stop_event
        self.validate_button.configure(state="disabled")
        self.validation_status_var.set("正在强制重新识别并测试代表页…")
        self._validation_results = []
        self.validation_preview_slot = 0
        self.validation_caption_var.set("")
        self.validation_diagnostic_var.set(
            "测试方式：PaddleOCR（强制重新识别）｜正在生成逐栏诊断…"
        )
        self.validation_prev_button.configure(state="disabled")
        self.validation_next_button.configure(state="disabled")
        self._set_feedback_buttons("disabled")
        self.validation_feedback_var.set("")
        for child in self.validation_frame.winfo_children():
            child.destroy()
        ttk.Label(self.validation_frame, text="正在生成测试结果…").grid(
            row=0, column=0, sticky="n", pady=30,
        )
        filter_path = headword_filter_rules_path(project_root, HEADWORD_FILTER_RULES_FILENAME)

        def worker():
            results = []
            for index in indices:
                if stop_event.is_set():
                    break
                path = paths[index]
                try:
                    with Image.open(path) as opened:
                        image = normalize_page_rgb(opened)
                    cache_path = (
                        ocr_cache_root(project_root) / f"{path.stem}.json"
                        if settings.detection_method == "paddleocr" else None
                    )
                    entries, geometry = detect_entries(
                        image, settings,
                        paddle_cache_path=cache_path,
                        force_paddle_refresh=True,
                        paddle_filter_rules_path=filter_path,
                        profile_page_index=index,
                    )
                    preview = ProjectProfileWizard._marker_preview(
                        image, entries, geometry, settings, index, preview_width,
                    )
                    coverage = ProjectProfileWizard._validation_coverage_summary(
                        cache_path, entries, geometry, settings,
                    )
                    results.append((
                        index, path.name, len(entries), len(geometry.column_starts),
                        preview, coverage, None,
                    ))
                except Exception as exc:
                    results.append((index, path.name, 0, 0, None, "", str(exc)))
                if stop_event.is_set():
                    break
            return results

        def done(results) -> None:
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return
            self._validation_running = False
            if stop_event.is_set():
                if self._validation_close_requested:
                    self.after_idle(self.destroy)
                    return
                self.validation_status_var.set("Profile 测试已安全停止。")
                self.validate_button.configure(state="normal")
                return
            self._finish_validation(results)

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return
            self._validation_running = False
            if self._validation_close_requested:
                self.after_idle(self.destroy)
                return
            self.validate_button.configure(state="normal")
            self.validation_status_var.set(f"Profile 测试失败：{exc}")

        self.parent._start_ui_worker(
            "profile-validation", worker, done, failed, wait_on_close=True,
        )

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
        source = image.copy()
        target_width = max(320, int(preview_width))
        target_height = max(
            1, round(source.height * target_width / max(1, source.width)),
        )
        thumb = source.resize(
            (target_width, target_height), Image.Resampling.LANCZOS,
        ).convert("RGBA")
        sx = thumb.width / max(1, source.width)
        sy = thumb.height / max(1, source.height)
        draw = ImageDraw.Draw(thumb, "RGBA")

        def shade_source_box(box: tuple[int, int, int, int]) -> None:
            x0, y0, x1, y1 = box
            if x1 <= x0 or y1 <= y0:
                return
            draw.rectangle(
                (x0 * sx, y0 * sy, x1 * sx, y1 * sy),
                fill=(255, 215, 0, 105),
            )

        canonical_w, canonical_h = geometry.transform.canonical_size(source.size)
        header_mode = str(getattr(settings, "profile_header_mode", "auto") or "auto")
        footer_mode = str(getattr(settings, "profile_footer_mode", "auto") or "auto")
        if header_mode == "auto" and geometry.top > 0:
            shade_source_box(
                geometry.transform.canonical_box_to_source(
                    (0, 0, canonical_w, min(canonical_h, geometry.top)),
                    source.size,
                )
            )
        elif header_mode == "present":
            pct = max(0.0, min(
                35.0, float(getattr(settings, "profile_header_percent", 6.0))
            ))
            margin = round(source.height * pct / 100.0)
            shade_source_box((0, 0, source.width, margin))

        if footer_mode == "auto" and geometry.bottom < canonical_h:
            shade_source_box(
                geometry.transform.canonical_box_to_source(
                    (0, max(0, geometry.bottom), canonical_w, canonical_h),
                    source.size,
                )
            )
        elif footer_mode == "present":
            pct = max(0.0, min(
                35.0, float(getattr(settings, "profile_footer_percent", 5.0))
            ))
            margin = round(source.height * pct / 100.0)
            shade_source_box(
                (0, max(0, source.height - margin), source.width, source.height)
            )

        side = excluded_source_side(settings, page_index)
        if side:
            margin = round(
                source.width
                * excluded_source_side_percent(settings, page_index)
                / 100.0
            )
            if side == "left":
                shade_source_box((0, 0, margin, source.height))
            else:
                shade_source_box((source.width - margin, 0, source.width, source.height))

        for entry in entries:
            u, v = geometry.source_to_canonical(entry.x, entry.y)
            try:
                col = min(
                    range(len(geometry.column_starts)),
                    key=lambda idx: abs(geometry.x_at(idx, v) - u),
                )
                x0 = geometry.x_at(col, v)
                x1 = x0 + max(8, int(geometry.column_widths[col] * 0.55))
                start, end = geometry.transform.canonical_marker_to_source(
                    (x0, v), (x1, v), source.size,
                )
                draw.line(
                    (start[0] * sx, start[1] * sy, end[0] * sx, end[1] * sy),
                    fill=(255, 0, 0, 255), width=1,
                )
            except Exception:
                x, y = round(entry.x * sx), round(entry.y * sy)
                draw.point((x, y), fill=(255, 0, 0, 255))
        return thumb.convert("RGB")

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
        for child in self.validation_frame.winfo_children():
            child.destroy()
        self._validation_photos.clear()
        if not self._validation_results:
            self.validation_caption_var.set("")
            self.validation_diagnostic_var.set(
                "测试方式：PaddleOCR（强制重新识别）｜尚无测试结果"
            )
            self.validation_prev_button.configure(state="disabled")
            self.validation_next_button.configure(state="disabled")
            return

        self.validation_preview_slot %= len(self._validation_results)
        _index, name, count, columns, preview, coverage, error = self._validation_results[self.validation_preview_slot]
        total = len(self._validation_results)
        self.validation_caption_var.set(
            f"{self.validation_preview_slot + 1}/{total} · {name}"
        )
        self.validation_diagnostic_var.set(
            coverage or "测试方式：PaddleOCR（强制重新识别）\n诊断信息未生成"
        )
        state = "normal" if total > 1 else "disabled"
        self.validation_prev_button.configure(state=state)
        self.validation_next_button.configure(state=state)

        cell = ttk.LabelFrame(self.validation_frame, text=name, padding=8)
        cell.grid(row=0, column=0, sticky="ew")
        cell.columnconfigure(0, weight=1)
        if preview is not None:
            display = preview.copy()
            self.update_idletasks()
            right_w = int(getattr(self, "right_canvas", self).winfo_width())
            right_h = int(getattr(self, "right_canvas", self).winfo_height())
            available_w = max(
                360,
                (right_w - 24) if right_w > 100 else self._wizard_image_width - 24,
            )
            available_h = max(
                360,
                (right_h - 120) if right_h > 200 else self._wizard_height - 160,
            )
            if getattr(self, "validation_fit_mode", "height") == "width":
                scale = available_w / max(1, display.width)
            else:
                scale = available_h / max(1, display.height)
            target = (
                max(1, round(display.width * scale)),
                max(1, round(display.height * scale)),
            )
            if target != display.size:
                display = display.resize(target, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(display)
            self._validation_photos.append(photo)
            ttk.Label(cell, image=photo, anchor="n").pack(anchor="n")
            ttk.Label(
                cell, text=f"检出 {count} 个词头 · {columns} 栏",
            ).pack(anchor="w", pady=(4, 0))
        else:
            ttk.Label(
                cell, text=f"测试失败：{error}", wraplength=620,
            ).pack(anchor="w", padx=10, pady=30)

    def _finish_validation(self, results) -> None:
        self._validation_running = False
        self.validate_button.configure(state="normal")
        revision_changed = self._validation_revision_started != self._profile_revision
        self._validation_results = list(results)
        self.validation_preview_slot = 0

        failures = sum(
            1 for _index, _name, _count, _columns, preview, _coverage, _error in results
            if preview is None
        )
        validated_pages = [
            name for _index, name, _count, _columns, preview, _coverage, _error in results
            if preview is not None
        ]
        self.working.profile_last_validated_pages = (
            validated_pages if failures == 0 and not revision_changed else []
        )
        if revision_changed:
            self.validation_status_var.set(
                "测试期间设置已改变；本次结果仅供参考，请按当前设置重新测试"
            )
        elif failures:
            self.validation_status_var.set(
                f"完成：{len(results)-failures}/{len(results)} 页成功；请逐页检查失败页后重新测试"
            )
        else:
            self.validation_status_var.set(
                f"完成：{len(results)} 页均已测试；可用左右按钮逐页检查"
            )
        if results and not revision_changed:
            self._set_feedback_buttons("normal")
        self._render_validation_result()

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
        if self._validation_running:
            self._validation_close_requested = True
            self._validation_stop_event.set()
            self.validation_status_var.set("正在安全结束当前测试页，完成后关闭…")
            return
        self.destroy()
