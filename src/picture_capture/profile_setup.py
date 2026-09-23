from __future__ import annotations

import json
import queue
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
    ordered_headword_profiles,
    profile_summary_tags,
    reading_choice_from_settings,
    probable_body_page_indices,
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
        "识别对象：普通拉丁字母词典中，排在释义前、视觉上更醒目的词头。",
        "主要依据：左缘位置、粗体/字号、词头后的音标、词性或变形等结构线索综合判断，不要求固定编号。",
        "适合：英、法、德、西、意、葡等常规字母词典，以及版式相近的双语词典。",
        "通常不算新词条：例句中的加粗词、释义内部的小标题、同一词条中的派生形式，除非它们同时满足词头结构线索。",
        "选择后仍可在【Profile高级】调整视觉阈值；这里不会改变你已经确认的阅读方向、分栏或 OCR 语言。",
    ),
    "numbered_prefix": (
        "识别对象：每个新词条前都有明确数字编号的词典，例如“1. word”或“1 word”。",
        "主要依据：行首 1–4 位数字 + 点号/空格作为强提示；编号本身比粗体或字号更重要。",
        "适合：日文类语词典、编号式术语表，以及每条记录都有稳定序号的参考书。",
        "通常不算新词条：释义内部的例句序号、义项编号或页码；它们若不位于词条起始位置，应由位置/结构规则排除。",
        "如果编号格式非常特殊，可先选这一类，再到【Profile高级】调整前缀规则。",
    ),
    "cjk_visual": (
        "识别对象：中文、日文等 CJK 词典中，以大字单字、括号词或明显视觉强调作为词头的条目。",
        "主要依据：单字/短词的字号、粗细、边缘位置，以及【】〔〕等括号结构；不依赖拉丁词性缩写。",
        "适合：汉字字典、汉语词典、日文汉和辞典，以及“大字词头 + 小字释义”的版式。",
        "通常不算新词条：正文中的普通大字、例句中的括号内容、栏内装饰字符；需要同时满足词条起始位置与视觉结构。",
        "若词头只有一个汉字且行距很紧，后续可结合单行高/字符高度参数微调。",
    ),
    "marker_prefixed": (
        "识别对象：每个新词条前有固定符号的词典，例如 ○、●、◆ 等。",
        "主要依据：词条起始位置的固定符号是强提示，字号或粗体只作为辅助信息。",
        "适合：百科、术语辞典、专题词典中以项目符号分隔条目的版式。",
        "通常不算新词条：释义内部的项目符号、示例列表或装饰符号；它们若不处在词条起始边，应被排除。",
        "如果你的符号不在预设集合中，可在高级规则中补充，而无需更改其他 Profile 维度。",
    ),
    "edge_visual_regular": (
        "识别对象：没有稳定词性语法，但词头总是在栏边、并通过粗体/字号/留白与正文区分的词典。",
        "主要依据：词条起始边 + 视觉突出程度 + 前后空白结构，不假定具体语言。",
        "适合：多语种、专名、地名、人名、专业名词等“视觉规则稳定、语法标记不稳定”的词典。",
        "通常不算新词条：栏中部的粗体强调、正文小标题和交叉引用，除非同时满足起始边结构。",
        "这是比“拉丁字母常规词头”更脚本中立的选项。",
    ),
    "custom": (
        "识别对象：无法被现有结构稳定描述，或你已经在高级参数中人工调好规则的词典。",
        "主要依据：完全沿用当前项目的高级识别参数，不强行套用预设。",
        "适合：特殊古籍、混排词典、实验性版式或高度定制的词头规则。",
        "建议：先给自定义结构起一个项目内名称，再用多页测试验证不同位置、不同页面上的稳定性。",
        "自定义结构同样只负责“什么算词头”，不会覆盖阅读方向、页面模板或 OCR 语言。",
    ),
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
        screen_h = max(600, int(self.winfo_screenheight()))
        width = max(720, int(screen_w * 0.60))
        height = screen_h
        x = max(0, (screen_w - width) // 2)
        y = 0
        self._wizard_content_width = max(560, width - 70)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(720, width), min(650, height))
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close_without_save)
        self._photos: list[ImageTk.PhotoImage] = []
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
        self.cjk_allow_single_var = tk.BooleanVar(
            value=bool(getattr(s, "profile_cjk_allow_single_headword", True))
        )
        self.cjk_allow_bracketed_var = tk.BooleanVar(
            value=bool(getattr(s, "profile_cjk_allow_bracketed_headword", True))
        )
        self.cjk_require_left_edge_var = tk.BooleanVar(
            value=bool(getattr(s, "profile_cjk_require_left_edge", True))
        )
        self.cjk_brackets_in_body_var = tk.BooleanVar(
            value=bool(getattr(s, "profile_cjk_brackets_in_body", False))
        )
        self.cjk_require_visual_var = tk.BooleanVar(
            value=bool(getattr(s, "profile_cjk_require_visual_evidence", False))
        )

        self.profile_choices = ordered_headword_profiles(self.custom_name_var.get())
        self.profile_label_to_key = dict(self.profile_choices)
        self.headword_profile_var = tk.StringVar(value=self._profile_label_for_key(s.dictionary_profile_id))

        detection_vars = (
            self.reading_var, self.columns_var, self.separator_var,
            self.header_mode_var, self.footer_mode_var, self.side_mode_var,
            self.first_variant_var, self.header_percent_var,
            self.footer_percent_var, self.side_percent_var, self.ocr_language_var,
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

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(2, weight=1)
        outer.columnconfigure(0, weight=1)

        title = "依次确认词典信息、阅读方式、页面模板、词头结构和 OCR。"
        ttk.Label(outer, text=title, font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            outer,
            text="软件会抽取前/中/后代表页进行分析；高级阈值仍保留在【更多参数 → Profile高级】中。",
            foreground="#666666",
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))

        self.notebook = ttk.Notebook(outer)
        self.notebook.grid(row=2, column=0, sticky="nsew")
        self.tabs: list[ttk.Frame] = []
        self.tab_contents: list[ttk.Frame] = []
        self.tab_canvases: list[tk.Canvas] = []
        for label in ("1 词典信息与阅读方式", "2 页面模板", "3 词头结构", "4 语言与 OCR", "5 测试与确认"):
            host = ttk.Frame(self.notebook)
            host.rowconfigure(0, weight=1)
            host.columnconfigure(0, weight=1)
            canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0)
            scrollbar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.grid(row=0, column=0, sticky="nsew")
            scrollbar.grid(row=0, column=1, sticky="ns")
            content = ttk.Frame(canvas, padding=12)
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

        self._build_reading_tab(self.tab_contents[0])
        self._build_template_tab(self.tab_contents[1])
        self._build_headword_tab(self.tab_contents[2])
        self._build_language_tab(self.tab_contents[3])
        self._build_validation_tab(self.tab_contents[4])
        self.notebook.bind("<<NotebookTabChanged>>", self._on_wizard_tab_changed, add="+")
        self.bind("<MouseWheel>", self._wizard_mousewheel, add="+")
        self.bind("<Button-4>", lambda event: self._wizard_linux_wheel(event, -1), add="+")
        self.bind("<Button-5>", lambda event: self._wizard_linux_wheel(event, 1), add="+")

        summary_box = ttk.LabelFrame(outer, text="当前 Project Profile", padding=(8, 5))
        summary_box.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.summary_var = tk.StringVar(value="")
        ttk.Label(summary_box, textvariable=self.summary_var, wraplength=1020).pack(anchor="w")

        footer = ttk.Frame(outer)
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(footer, text="上一步", command=lambda: self._move_step(-1)).pack(side="left")
        ttk.Button(footer, text="下一步", command=lambda: self._move_step(1)).pack(side="left", padx=(6, 0))
        ttk.Button(footer, text="取消", command=self._close_without_save).pack(side="right")
        ttk.Button(footer, text="确认并使用", command=self.save_and_close).pack(side="right", padx=(0, 8))

    def _on_wizard_tab_changed(self, _event=None) -> None:
        """Load image-backed content only when its tab becomes visible."""
        try:
            index = self.notebook.index(self.notebook.select())
        except (tk.TclError, ValueError):
            return
        if index == 1:
            self.after_idle(self._refresh_template_preview)
        elif index == 2:
            self.after_idle(self._refresh_headword_description)
        elif index == 4 and self._validation_results:
            self.after_idle(self._render_validation_result)

    def _active_tab_canvas(self) -> tk.Canvas | None:
        try:
            index = self.notebook.index(self.notebook.select())
            return self.tab_canvases[index]
        except (tk.TclError, ValueError, IndexError):
            return None

    def _wizard_mousewheel(self, event) -> str | None:
        if isinstance(event.widget, (tk.Spinbox, ttk.Combobox)):
            return None
        canvas = self._active_tab_canvas()
        if canvas is None:
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        if not delta:
            return None
        canvas.yview_scroll((-1 if delta > 0 else 1) * 3, "units")
        return "break"

    def _wizard_linux_wheel(self, event, direction: int) -> str | None:
        if isinstance(event.widget, (tk.Spinbox, ttk.Combobox)):
            return None
        canvas = self._active_tab_canvas()
        if canvas is None:
            return None
        canvas.yview_scroll(int(direction) * 3, "units")
        return "break"

    def _build_reading_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)

        info = ttk.LabelFrame(tab, text="词典项目详情", padding=(10, 8))
        info.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for col in (1, 3, 5, 7):
            info.columnconfigure(col, weight=1)

        ttk.Label(info, text="词典完整名称：").grid(row=0, column=0, sticky="e", padx=(0, 4))
        ttk.Entry(
            info, textvariable=self.dictionary_full_name_var, width=20,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(info, text="词典缩写名称：").grid(row=0, column=2, sticky="e", padx=(0, 4))
        ttk.Entry(
            info, textvariable=self.dictionary_abbreviation_var, width=11,
        ).grid(row=0, column=3, sticky="ew", padx=(0, 10))

        ttk.Label(info, text="ISBN：").grid(row=0, column=4, sticky="e", padx=(0, 4))
        ttk.Entry(
            info, textvariable=self.dictionary_isbn_var, width=16,
        ).grid(row=0, column=5, sticky="ew", padx=(0, 10))

        ttk.Label(info, text="正文页码范围：").grid(row=0, column=6, sticky="e", padx=(0, 4))
        self.body_page_range_entry = ttk.Entry(
            info, textvariable=self.dictionary_body_page_range_var, width=13,
        )
        self.body_page_range_entry.grid(row=0, column=7, sticky="ew")
        self.body_page_range_entry.bind("<FocusOut>", self._body_page_range_changed)
        self.body_page_range_entry.bind("<Return>", self._body_page_range_changed)

        ttk.Label(
            tab,
            text="阅读方式：页面怎么读？",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=1, column=0, sticky="w")
        ttk.Label(
            tab,
            text="这里只确认实际页面的阅读方向；需要的镜像或旋转由软件自动处理。正文页码范围首次自动填充，之后可直接修改。",
            foreground="#666666",
        ).grid(row=2, column=0, sticky="w", pady=(2, 8))

        choices = ttk.Frame(tab)
        choices.grid(row=3, column=0, sticky="w")
        for column, key in enumerate(("horizontal-ltr", "horizontal-rtl", "vertical-rl", "vertical-lr")):
            ttk.Radiobutton(
                choices, text=READING_LABELS[key], variable=self.reading_var, value=key,
                command=self._reading_changed,
            ).grid(row=0, column=column, sticky="w", padx=(0, 18), pady=4)

        ttk.Label(
            tab,
            text="代表页优先使用上方正文页码范围；未填写或无效时再从疑似正文的前部 / 中部 / 后部抽取，并避开 0000_*、目录、附录等明显非正文页；每一张都可以手动更换。",
            foreground="#666666", wraplength=980,
        ).grid(row=4, column=0, sticky="w", pady=(10, 4))
        samples = ttk.LabelFrame(tab, text="代表页（前部 / 中部 / 后部）", padding=8)
        samples.grid(row=5, column=0, sticky="nsew", pady=(4, 0))
        samples.columnconfigure(0, weight=1)
        samples.columnconfigure(1, weight=1)
        samples.columnconfigure(2, weight=1)
        self.sample_frame = samples

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
        tab.columnconfigure(0, weight=0)
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="② 正文在哪里？", font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            tab,
            text="左侧定义正文与排除区域；右侧始终用一张真实代表页即时预览。A/B 表示相邻扫描页，不强行等同书籍奇偶页。",
            foreground="#666666",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))

        left_stack = ttk.Frame(tab)
        left_stack.grid(row=2, column=0, sticky="nw", padx=(0, 10))
        left_stack.columnconfigure(0, weight=1)

        body = ttk.LabelFrame(left_stack, text="正文与分栏", padding=10)
        body.grid(row=0, column=0, sticky="ew")
        ttk.Label(body, text="正文栏数：").grid(row=0, column=0, sticky="e", pady=5)
        self.columns_spin = tk.Spinbox(
            body, from_=1, to=8, width=5, textvariable=self.columns_var,
        )
        self.columns_spin.grid(row=0, column=1, sticky="w", pady=5)
        ttk.Label(
            body,
            text="代表页会自动分析并建议栏数；确认后作为本项目的稳定栏数使用。",
            foreground="#666666", wraplength=390,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 5))
        ttk.Label(body, text="中央分隔线：").grid(row=2, column=0, sticky="e", pady=5)
        ttk.Combobox(
            body, textvariable=self.separator_var, state="readonly", width=18,
            values=tuple(SEPARATOR_LABEL_TO_VALUE.keys()),
        ).grid(row=2, column=1, sticky="w", pady=5)

        self.analysis_suggestion_var = tk.StringVar(value="进入本步骤时会分析当前代表页，也可随时重新分析。")
        ttk.Label(body, textvariable=self.analysis_suggestion_var, wraplength=390).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(12, 4)
        )
        analysis_buttons = ttk.Frame(body)
        analysis_buttons.grid(row=4, column=0, columnspan=2, sticky="w")
        self.analyze_button = ttk.Button(
            analysis_buttons, text="重新分析代表页", command=self.analyze_representative_pages,
        )
        self.analyze_button.pack(side="left")
        self.apply_analysis_button = ttk.Button(
            analysis_buttons, text="应用建议", command=self.apply_analysis_suggestion, state="disabled",
        )
        self.apply_analysis_button.pack(side="left", padx=(6, 0))

        edges = ttk.LabelFrame(left_stack, text="页眉 / 页尾 / 页边", padding=10)
        edges.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._mode_row(
            edges, 0, "页眉：", self.header_mode_var,
            tuple(HEADER_LABEL_TO_VALUE.keys()),
        )
        ttk.Label(edges, text="排除高度%").grid(row=1, column=0, sticky="e")
        self.header_percent_spin = tk.Spinbox(
            edges, from_=0, to=35, increment=0.5, width=6,
            textvariable=self.header_percent_var,
        )
        self.header_percent_spin.grid(row=1, column=1, sticky="w")
        self._mode_row(
            edges, 2, "页尾：", self.footer_mode_var,
            tuple(FOOTER_LABEL_TO_VALUE.keys()),
        )
        ttk.Label(edges, text="排除高度%").grid(row=3, column=0, sticky="e")
        self.footer_percent_spin = tk.Spinbox(
            edges, from_=0, to=35, increment=0.5, width=6,
            textvariable=self.footer_percent_var,
        )
        self.footer_percent_spin.grid(row=3, column=1, sticky="w")
        ttk.Label(edges, text="页边内容：").grid(row=4, column=0, sticky="e", pady=5)
        ttk.Combobox(
            edges, textvariable=self.side_mode_var, state="readonly", width=22,
            values=tuple(SIDE_LABEL_TO_VALUE.keys()),
        ).grid(row=4, column=1, sticky="w", pady=5)
        ttk.Label(edges, text="页边排除宽度%").grid(row=5, column=0, sticky="e")
        self.side_percent_spin = tk.Spinbox(
            edges, from_=0, to=30, increment=0.5, width=6,
            textvariable=self.side_percent_var,
        )
        self.side_percent_spin.grid(row=5, column=1, sticky="w")
        ttk.Label(edges, text="A/B 起始页：").grid(row=6, column=0, sticky="e", pady=(10, 4))
        self.first_variant_combo = ttk.Combobox(
            edges, textvariable=self.first_variant_var, state="readonly", width=8, values=("A", "B"),
        )
        self.first_variant_combo.grid(row=6, column=1, sticky="w", pady=(10, 4))
        ttk.Label(
            edges,
            text="仅“外侧/内侧交替”需要 A/B：默认 A 页左侧、B 页右侧；若第一张扫描实际属于 B 页，选择 B 即可整体翻转。",
            foreground="#666666", wraplength=390,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))

        preview = ttk.LabelFrame(tab, text="页面模板即时预览", padding=8)
        preview.grid(row=2, column=1, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)
        nav = ttk.Frame(preview)
        nav.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(nav, text="◀ 上一张", command=lambda: self._move_template_preview(-1)).pack(side="left")
        ttk.Button(nav, text="下一张 ▶", command=lambda: self._move_template_preview(1)).pack(side="right")
        self.template_preview_caption_var = tk.StringVar(value="")
        ttk.Label(nav, textvariable=self.template_preview_caption_var).pack(side="left", expand=True)
        self.template_preview_frame = ttk.Frame(preview)
        self.template_preview_frame.grid(row=1, column=0, sticky="nsew")
        self.template_preview_frame.columnconfigure(0, weight=1)

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
        side_present = side_value != "none"
        alternating = side_value in {"outer", "inner"}
        self.columns_spin.configure(state="normal")
        self.header_percent_spin.configure(state="normal" if header_present else "disabled")
        self.footer_percent_spin.configure(state="normal" if footer_present else "disabled")
        self.side_percent_spin.configure(state="normal" if side_present else "disabled")
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
        """Render one representative page with the current exclusion template."""
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
        index = self.sample_indices[self.template_preview_slot]
        path = self.project.images[index]
        try:
            settings = self._settings_from_ui()
            with Image.open(path) as opened:
                source = normalize_page_rgb(opened)
            preview = source.copy()
            preview.thumbnail((540, 560), Image.Resampling.LANCZOS)
            draw = ImageDraw.Draw(preview, "RGBA")
            w, h = preview.size

            header_mode = HEADER_LABEL_TO_VALUE.get(self.header_mode_var.get(), "auto")
            if header_mode == "present":
                hp = max(0.0, min(35.0, float(self.header_percent_var.get())))
                draw.rectangle((0, 0, w, round(h * hp / 100.0)), fill=(100, 100, 100, 80))
            footer_mode = FOOTER_LABEL_TO_VALUE.get(self.footer_mode_var.get(), "none")
            if footer_mode == "present":
                fp = max(0.0, min(35.0, float(self.footer_percent_var.get())))
                draw.rectangle((0, round(h * (1.0 - fp / 100.0)), w, h), fill=(100, 100, 100, 80))

            side = excluded_source_side(settings, index)
            if side:
                sp = max(0.0, min(30.0, float(self.side_percent_var.get())))
                margin = round(w * sp / 100.0)
                if side == "left":
                    draw.rectangle((0, 0, margin, h), fill=(100, 100, 100, 80))
                else:
                    draw.rectangle((w - margin, 0, w, h), fill=(100, 100, 100, 80))

            effective = effective_page_settings(settings, source.size, index)
            analysis_image = page_template_analysis_image(source, effective, index)
            geometry = derive_geometry(analysis_image, effective)
            sx = w / max(1, source.width)
            sy = h / max(1, source.height)
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

            photo = ImageTk.PhotoImage(preview)
            self._template_photos.append(photo)
            ttk.Label(self.template_preview_frame, image=photo).grid(row=0, column=0, sticky="n")
            variant = page_variant(settings, index)
            side_text = excluded_source_side(settings, index) or "无页边排除"
            region = ("前部", "中部", "后部")[min(2, self.template_preview_slot // 2)]
            self.template_preview_caption_var.set(
                f"{region} · {self.template_preview_slot + 1}/{len(self.sample_indices)} · "
                f"{variant} 页 · {path.name} · 页边：{side_text}"
            )
        except Exception as exc:
            ttk.Label(
                self.template_preview_frame,
                text=f"{path.name}\n预览失败：{exc}",
            ).grid(row=0, column=0)
            self.template_preview_caption_var.set(path.name)

    @staticmethod
    def _mode_row(
        parent, row: int, label: str, variable: tk.StringVar, values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", pady=5)
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
        self.headword_examples_var = tk.StringVar(value="")
        ttk.Label(
            tab, textvariable=self.headword_description_var,
            wraplength=self._wizard_content_width, justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))

        examples = ttk.LabelFrame(tab, text="经典样例（局部裁切）", padding=8)
        examples.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        examples.columnconfigure(0, weight=1)
        examples.columnconfigure(1, weight=1)
        examples.columnconfigure(2, weight=1)
        self.headword_examples_frame = examples
        ttk.Label(
            tab, textvariable=self.headword_examples_var,
            wraplength=self._wizard_content_width, justify="left",
            foreground="#555555",
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

        specificity = ttk.LabelFrame(tab, text="词头专属性", padding=10)
        specificity.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        specificity.columnconfigure(0, weight=1)
        self.headword_specificity_frame = specificity
        self.cjk_specificity_widgets: list[ttk.Checkbutton] = []
        for row, (label, variable) in enumerate((
            ("大字单字可作为词头", self.cjk_allow_single_var),
            ("【括号词】可作为词头", self.cjk_allow_bracketed_var),
            ("必须靠近栏左缘", self.cjk_require_left_edge_var),
            ("释义正文中也经常出现【括号词】", self.cjk_brackets_in_body_var),
            ("只有视觉明显突出时才把单字/括号词当词头", self.cjk_require_visual_var),
        )):
            widget = ttk.Checkbutton(
                specificity, text=label, variable=variable,
                command=self._headword_specificity_changed,
            )
            widget.grid(row=row, column=0, sticky="w", pady=2)
            self.cjk_specificity_widgets.append(widget)
        ttk.Label(
            specificity,
            text="这些选项只在“CJK 大字/括号词头”结构下生效；目的是表达版式事实，而不是让你手调 OCR 阈值。",
            foreground="#666666", wraplength=self._wizard_content_width,
        ).grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.headword_tuning_status_var = tk.StringVar(value="")
        ttk.Label(
            specificity, textvariable=self.headword_tuning_status_var,
            foreground="#555555",
        ).grid(row=6, column=0, sticky="w", pady=(4, 0))

        help_box = ttk.LabelFrame(tab, text="理解方式", padding=10)
        help_box.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        help_box.columnconfigure(0, weight=1)
        self.headword_help_frame = help_box

    def _build_language_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="④ 语言与 OCR", font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            tab,
            text="常用语言置前；选择 OCR 语言时会自动填写 2 位索引语言代号，但索引语言输入框仍可随时手动修改。",
            foreground="#666666",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))

        ttk.Label(tab, text="OCR 语言：").grid(row=2, column=0, sticky="e", padx=(0, 8), pady=5)
        combo = ttk.Combobox(
            tab, textvariable=self.ocr_language_var, values=tuple(OCR_LANGUAGE_LABEL_TO_VALUE.keys()),
            state="normal", width=30,
        )
        combo.grid(row=2, column=1, sticky="w", pady=5)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._ocr_language_changed())
        combo.bind("<FocusOut>", lambda _e: self._ocr_language_changed())
        self.ocr_language_var.trace_add("write", lambda *_args: self.after_idle(self._refresh_language_summary))

        ttk.Label(tab, text="索引语言（2 位）：").grid(row=3, column=0, sticky="e", padx=(0, 8), pady=5)
        ttk.Entry(tab, textvariable=self.index_language_var, width=12).grid(row=3, column=1, sticky="w", pady=5)
        ttk.Label(
            tab,
            text="例如 en / zh / ja / fr；自动值只是建议，你可以直接覆盖。",
            foreground="#666666",
        ).grid(row=4, column=1, sticky="w")
        ttk.Label(tab, text="内容语言：").grid(row=5, column=0, sticky="e", padx=(0, 8), pady=5)
        ttk.Entry(tab, textvariable=self.content_language_var, width=28).grid(row=5, column=1, sticky="w", pady=5)

        backend = ttk.LabelFrame(tab, text="自动派生的 OCR 后端设置", padding=10)
        backend.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        self.backend_summary_var = tk.StringVar(value="")
        ttk.Label(backend, textvariable=self.backend_summary_var, justify="left").pack(anchor="w")

    def _build_validation_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(6, weight=1)
        ttk.Label(tab, text="⑤ 多页测试后再确认", font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            tab,
            text="测试只处理代表页，不写 PDIC；PaddleOCR 会强制重新识别，不复用旧 OCR 缓存。红线=检出的词头；半透明灰区=当前 Profile 不参与正文识别的区域。测试结果一次显示一页，可左右翻页。",
            foreground="#666666", wraplength=self._wizard_content_width,
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))
        bar = ttk.Frame(tab)
        bar.grid(row=2, column=0, sticky="ew")
        self.validate_button = ttk.Button(bar, text="测试当前 Profile", command=self.validate_profile)
        self.validate_button.pack(side="left")
        self.validation_status_var = tk.StringVar(value="尚未测试")
        ttk.Label(bar, textvariable=self.validation_status_var).pack(side="left", padx=(10, 0))

        nav = ttk.Frame(tab)
        nav.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.validation_prev_button = ttk.Button(
            nav, text="◀ 上一张", command=lambda: self._move_validation_preview(-1), state="disabled",
        )
        self.validation_prev_button.pack(side="left")
        self.validation_next_button = ttk.Button(
            nav, text="下一张 ▶", command=lambda: self._move_validation_preview(1), state="disabled",
        )
        self.validation_next_button.pack(side="right")
        self.validation_caption_var = tk.StringVar(value="")
        ttk.Label(nav, textvariable=self.validation_caption_var).pack(side="left", expand=True)

        self.validation_diagnostic_var = tk.StringVar(
            value="测试方式：PaddleOCR（强制重新识别）｜尚未运行测试"
        )
        ttk.Label(
            tab, textvariable=self.validation_diagnostic_var,
            foreground="#555555", justify="left",
            wraplength=self._wizard_content_width,
        ).grid(row=4, column=0, sticky="ew", pady=(6, 0))

        feedback = ttk.LabelFrame(tab, text="结果是否合适？", padding=(8, 5))
        feedback.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        feedback.columnconfigure(4, weight=1)
        ttk.Label(
            feedback,
            text="偏多会按当前词头类型收紧规则；偏少会放宽。调整后重新测试，直到结果合适。",
            foreground="#666666", wraplength=self._wizard_content_width,
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 4))
        self.feedback_too_many_button = ttk.Button(
            feedback, text="偏多", command=lambda: self._apply_validation_feedback("too_many"),
            state="disabled",
        )
        self.feedback_too_many_button.grid(row=1, column=0, padx=(0, 4))
        self.feedback_good_button = ttk.Button(
            feedback, text="合适", command=lambda: self._apply_validation_feedback("good"),
            state="disabled",
        )
        self.feedback_good_button.grid(row=1, column=1, padx=4)
        self.feedback_too_few_button = ttk.Button(
            feedback, text="偏少", command=lambda: self._apply_validation_feedback("too_few"),
            state="disabled",
        )
        self.feedback_too_few_button.grid(row=1, column=2, padx=4)
        self.validation_feedback_var = tk.StringVar(value="")
        ttk.Label(
            feedback, textvariable=self.validation_feedback_var,
            wraplength=max(320, self._wizard_content_width - 270),
        ).grid(row=1, column=4, sticky="w", padx=(10, 0))

        self.validation_frame = ttk.Frame(tab)
        self.validation_frame.grid(row=6, column=0, sticky="nsew", pady=(6, 0))
        self.validation_frame.columnconfigure(0, weight=1)


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

    def _headword_changed(self) -> None:
        # A different structure starts from its own balanced defaults; any
        # earlier "偏多/偏少" tuning belonged to the previous structure.
        self.headword_tuning_level_var.set(0)
        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_headword_description()
        self._refresh_summary()

    def _headword_specificity_changed(self) -> None:
        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_headword_tuning_status()
        self._refresh_summary()

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

    def _headword_example_asset(self, profile_key: str, dictionary_name: str) -> Path | None:
        root = Path(__file__).resolve().parent / "data" / "headword_examples"
        safe = "".join(ch for ch in dictionary_name if ch.isalnum() or ch in {"-", "_"})
        stems = (
            f"{profile_key}_{safe}",
            safe,
            profile_key,
        )
        for stem in stems:
            for suffix in (".png", ".jpg", ".jpeg", ".webp"):
                candidate = root / f"{stem}{suffix}"
                if candidate.exists():
                    return candidate
        return None

    def _refresh_headword_description(self) -> None:
        key = self._current_profile_key()
        try:
            profile = dictionary_profile_preset(key)
        except Exception:
            return
        self.custom_name_entry.configure(state="normal" if key == "custom" else "disabled")
        self.headword_description_var.set(profile.description)
        if hasattr(self, "headword_specificity_frame"):
            if key == "cjk_visual":
                self.headword_specificity_frame.grid()
            else:
                self.headword_specificity_frame.grid_remove()
        self._refresh_headword_tuning_status()

        for child in self.headword_examples_frame.winfo_children():
            child.destroy()
        self._headword_example_photos.clear()
        if profile.examples:
            names = []
            for slot, example in enumerate(profile.examples[:3]):
                names.append(example.dictionary)
                cell = ttk.Frame(self.headword_examples_frame)
                cell.grid(row=0, column=slot, sticky="nsew", padx=5, pady=3)
                asset = self._headword_example_asset(key, example.dictionary)
                if asset is not None:
                    try:
                        with Image.open(asset) as opened:
                            image = normalize_page_rgb(opened)
                        image.thumbnail((270, 150), Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(image)
                        self._headword_example_photos.append(photo)
                        ttk.Label(cell, image=photo).pack(fill="x")
                    except Exception:
                        ttk.Label(cell, text="样例图片读取失败", anchor="center").pack(fill="x", ipady=28)
                else:
                    ttk.Label(
                        cell,
                        text=f"待放入局部样例\n{example.dictionary}",
                        anchor="center", justify="center",
                    ).pack(fill="x", ipady=28)
                ttk.Label(cell, text=example.dictionary).pack(anchor="center", pady=(4, 0))
            self.headword_examples_var.set(
                "经典样例：" + "；".join(names) + "。样例区只显示局部裁切图，不回退为整页预览。"
            )
        else:
            ttk.Label(
                self.headword_examples_frame,
                text="此结构暂无固定经典词典样例；可使用当前项目的局部词头截图作为自定义参考。",
                anchor="center",
            ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=18)
            self.headword_examples_var.set("")

        for child in self.headword_help_frame.winfo_children():
            child.destroy()
        lines = HEADWORD_HELP_LINES.get(key) or (
            "识别对象：按当前结构预设判断词条起始。",
            "建议：结合经典样例和第 ⑤ 步多页测试确认是否稳定。",
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
        s.dictionary_custom_profile_name = self.custom_name_var.get().strip()
        s.ocr_language = _ocr_language_code(self.ocr_language_var.get())
        s.dictionary_index_language = self.index_language_var.get().strip()
        s.dictionary_content_language = self.content_language_var.get().strip()
        s.profile_headword_tuning_level = max(
            -2, min(2, int(self.headword_tuning_level_var.get()))
        )
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
        region_titles = ("前部", "中部", "后部")
        groups: list[ttk.LabelFrame] = []
        for column, title in enumerate(region_titles):
            group = ttk.LabelFrame(self.sample_frame, text=title, padding=6)
            group.grid(row=0, column=column, sticky="nsew", padx=4, pady=2)
            group.columnconfigure(0, weight=1)
            groups.append(group)
        return groups

    def _show_sample_loading_state(self) -> None:
        groups = self._sample_groups()
        self._photos.clear()
        for slot, index in enumerate(self.sample_indices):
            path = self.project.images[index]
            group = groups[min(2, slot // 2)]
            cell = ttk.Frame(group)
            cell.grid(row=slot % 2, column=0, sticky="ew", pady=4)
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
        result_queue: queue.Queue = queue.Queue(maxsize=1)
        self._thumbnail_queue = result_queue

        def worker() -> None:
            results = []
            for slot, (index, path) in enumerate(zip(indices, paths)):
                try:
                    with Image.open(path) as opened:
                        image = normalize_page_rgb(opened)
                    image.thumbnail((250, 155), Image.Resampling.LANCZOS)
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

    def _finish_sample_thumbnail_load(self, results) -> None:
        groups = self._sample_groups()
        self._photos.clear()
        for slot, index, name, image, error in results:
            if slot >= len(self.sample_indices) or self.sample_indices[slot] != index:
                continue
            group = groups[min(2, slot // 2)]
            cell = ttk.Frame(group)
            cell.grid(row=slot % 2, column=0, sticky="ew", pady=4)
            if image is not None:
                photo = ImageTk.PhotoImage(image)
                self._photos.append(photo)
                ttk.Label(cell, image=photo).pack()
            else:
                ttk.Label(
                    cell, text=f"缩略图失败：{error}", wraplength=250,
                ).pack(fill="x", ipady=20)
            ttk.Label(cell, text=name, wraplength=260).pack(anchor="center", pady=(3, 0))
            ttk.Button(
                cell, text="更换…", command=lambda s=slot: self._choose_sample_page(s),
            ).pack(anchor="center", pady=(3, 0))

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
            if index in self.sample_indices and index != self.sample_indices[slot]:
                messagebox.showinfo("代表页已使用", "这张页面已经在代表页中，请选择另一张。", parent=picker)
                return
            self.sample_indices[slot] = index
            self.template_preview_slot = min(self.template_preview_slot, len(self.sample_indices) - 1)
            self._profile_revision += 1
            self._mark_validation_stale()
            self._analysis_suggestion = {}
            if hasattr(self, "analysis_suggestion_var"):
                self.analysis_suggestion_var.set("代表页已更换，请重新分析当前代表页。")
                self.apply_analysis_button.configure(state="disabled")
            self._start_sample_thumbnail_load()
            self._refresh_template_preview()
            picker.destroy()

        listing.bind("<Double-Button-1>", apply_choice)
        footer = ttk.Frame(picker)
        footer.pack(fill="x", padx=10, pady=10)
        ttk.Button(footer, text="取消", command=picker.destroy).pack(side="right")
        ttk.Button(footer, text="使用此页", command=apply_choice).pack(side="right", padx=(0, 8))

    def _move_step(self, delta: int) -> None:
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
            "character_height", "row_padding",
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
        if key == "cjk_visual":
            if result == "too_many":
                # CJK false positives are best controlled by demanding a real
                # column-edge start plus visual prominence for bracketed heads.
                self.cjk_require_left_edge_var.set(True)
                self.cjk_require_visual_var.set(True)
            elif result == "too_few":
                # Loosening should first remove the extra visual gate; factual
                # choices such as "正文中也有括号词" remain user-controlled.
                self.cjk_require_visual_var.set(False)

        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_headword_tuning_status()
        self._refresh_summary()
        direction = "收紧" if result == "too_many" else "放宽"
        if new_level == old_level:
            self.validation_feedback_var.set(
                f"已经达到{direction}上限（{new_level:+d}）；可在第③步进一步修改词头专属性。"
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
        settings = self._settings_from_ui()
        # Project Profile validates the normal OCR-based workflow even when an
        # old project last saved "普通画线" as its active detection method.
        # This is a temporary validation copy and does not overwrite that saved
        # project preference.
        settings.detection_method = "paddleocr"
        settings.paddle_use_paddleocr = True
        indices = list(self.sample_indices)
        if not indices:
            return
        self.update_idletasks()
        preview_width = max(480, int(self._wizard_content_width) - 8)
        self._validation_running = True
        self._validation_revision_started = self._profile_revision
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
        filter_path = headword_filter_rules_path(self.project.root, HEADWORD_FILTER_RULES_FILENAME)

        def worker() -> None:
            results = []
            for index in indices:
                path = self.project.images[index]
                try:
                    with Image.open(path) as opened:
                        image = normalize_page_rgb(opened)
                    cache_path = (
                        ocr_cache_root(self.project.root) / f"{path.stem}.json"
                        if settings.detection_method == "paddleocr" else None
                    )
                    entries, geometry = detect_entries(
                        image, settings,
                        paddle_cache_path=cache_path,
                        force_paddle_refresh=True,
                        paddle_filter_rules_path=filter_path,
                        profile_page_index=index,
                    )
                    preview = self._marker_preview(
                        image, entries, geometry, settings, index, preview_width,
                    )
                    coverage = self._validation_coverage_summary(
                        cache_path, entries, geometry, settings,
                    )
                    results.append((
                        index, path.name, len(entries), len(geometry.column_starts),
                        preview, coverage, None,
                    ))
                except Exception as exc:
                    results.append((index, path.name, 0, 0, None, "", str(exc)))
            assert self._validation_queue is not None
            self._validation_queue.put(results)

        self._validation_queue = queue.Queue(maxsize=1)
        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_validation_queue)

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
                fill=(110, 110, 110, 72),
            )

        canonical_w, canonical_h = geometry.transform.canonical_size(source.size)
        if geometry.top > 0:
            shade_source_box(
                geometry.transform.canonical_box_to_source(
                    (0, 0, canonical_w, min(canonical_h, geometry.top)),
                    source.size,
                )
            )
        if geometry.bottom < canonical_h:
            shade_source_box(
                geometry.transform.canonical_box_to_source(
                    (0, max(0, geometry.bottom), canonical_w, canonical_h),
                    source.size,
                )
            )
        if str(getattr(settings, "profile_header_mode", "auto") or "auto") == "present":
            pct = max(0.0, min(35.0, float(getattr(settings, "profile_header_percent", 6.0))))
            margin = round(source.height * pct / 100.0)
            shade_source_box((0, 0, source.width, margin))
        if str(getattr(settings, "profile_footer_mode", "auto") or "auto") == "present":
            pct = max(0.0, min(35.0, float(getattr(settings, "profile_footer_percent", 5.0))))
            margin = round(source.height * pct / 100.0)
            shade_source_box((0, max(0, source.height - margin), source.width, source.height))

        side = excluded_source_side(settings, page_index)
        if side:
            margin = round(source.width * max(
                0.0, min(30.0, float(getattr(settings, "profile_side_percent", 8.0)))
            ) / 100.0)
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
            photo = ImageTk.PhotoImage(preview)
            self._validation_photos.append(photo)
            ttk.Label(cell, image=photo).pack()
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
        try:
            if not self.working.profile_last_validated_pages:
                if not messagebox.askyesno(
                    "Profile 尚未完整验证",
                    "当前设置尚未通过全部代表页测试，或测试后又修改了设置。\n\n"
                    "建议先到【5 测试与确认】运行“测试当前 Profile”。"
                    "是否仍然保存并使用当前设置？",
                    parent=self,
                ):
                    self.notebook.select(self.tabs[4])
                    return
            settings = self._settings_from_ui()
            if self.working.profile_last_validated_pages:
                settings.profile_last_validated_pages = list(self.working.profile_last_validated_pages)
            copy_settings(self.parent.settings, settings)
            self.parent.settings.to_json(settings_path(self.project.root))
            write_project_profile(
                project_profile_path(self.project.root),
                self.parent.settings,
                self.parent.settings.dictionary_profile_id,
                force=True,
            )
            self.parent.sync_quick_settings()
            self.parent.redraw()
            self.parent.status_var.set("Project Profile 已保存并应用")
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Project Profile 保存失败", str(exc), parent=self)

    def _close_without_save(self) -> None:
        if self.new_project and int(getattr(self.parent.settings, "profile_setup_version", 0) or 0) < PROFILE_SETUP_VERSION:
            if not messagebox.askyesno(
                "尚未完成 Project Profile",
                "当前项目尚未完成 Profile 设置。确定先关闭向导吗？以后可从【项目Profile】继续。",
                parent=self,
            ):
                return
        self.destroy()
