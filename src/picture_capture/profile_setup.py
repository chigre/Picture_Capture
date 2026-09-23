from __future__ import annotations

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
    apply_reading_choice,
    copy_settings,
    effective_page_settings,
    excluded_source_side,
    ordered_headword_profiles,
    profile_summary_tags,
    reading_choice_from_settings,
    probable_body_page_indices,
    representative_page_indices,
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
        width = min(1120, max(780, int(screen_w * 0.90)))
        height = min(820, max(540, int(screen_h * 0.88)))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(900, width), min(650, height))
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close_without_save)
        self._photos: list[ImageTk.PhotoImage] = []
        self._validation_photos: list[ImageTk.PhotoImage] = []
        self._template_photos: list[ImageTk.PhotoImage] = []
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
        self.sample_candidates = probable_body_page_indices(self.project.images)
        self.sample_indices = representative_page_indices(self.project.images, 6)
        self.template_preview_slot = 0

        self._build_vars()
        self._build_ui()
        self._load_sample_thumbnails()
        self._refresh_headword_description()
        self._refresh_language_summary()
        self._refresh_summary()

        # Representative-page analysis starts after the user confirms reading
        # direction and enters step 2. This avoids analyzing a vertical/RTL
        # dictionary with an incorrect default transform.

    def _build_vars(self) -> None:
        s = self.working
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
        for var in (self.index_language_var, self.content_language_var):
            var.trace_add("write", lambda *_args: self.after_idle(self._refresh_summary))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(2, weight=1)
        outer.columnconfigure(0, weight=1)

        title = "第一次只确认 4 件事：页面怎么读、正文在哪里、什么算词头、用什么 OCR。"
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
        for label in ("1 阅读方式", "2 页面模板", "3 词头结构", "4 语言与 OCR", "5 测试与确认"):
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
        ttk.Label(
            tab,
            text="① 页面怎么读？",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            tab,
            text="这里只确认实际页面的阅读方向；需要的镜像或旋转由软件自动处理。",
            foreground="#666666",
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))

        choices = ttk.Frame(tab)
        choices.grid(row=2, column=0, sticky="w")
        for column, key in enumerate(("horizontal-ltr", "horizontal-rtl", "vertical-rl", "vertical-lr")):
            ttk.Radiobutton(
                choices, text=READING_LABELS[key], variable=self.reading_var, value=key,
                command=self._reading_changed,
            ).grid(row=0, column=column, sticky="w", padx=(0, 18), pady=4)

        ttk.Label(
            tab,
            text="代表页会优先从疑似正文范围的前部 / 中部 / 后部抽取，并避开 0000_*、目录、附录等明显非正文页；每一张都可以手动更换。",
            foreground="#666666", wraplength=980,
        ).grid(row=3, column=0, sticky="w", pady=(10, 4))
        samples = ttk.LabelFrame(tab, text="代表页（前部 / 中部 / 后部）", padding=8)
        samples.grid(row=4, column=0, sticky="nsew", pady=(4, 0))
        samples.columnconfigure(0, weight=1)
        samples.columnconfigure(1, weight=1)
        samples.columnconfigure(2, weight=1)
        self.sample_frame = samples

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
        self.after_idle(self._refresh_template_preview)

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
        if hasattr(self, "template_preview_frame"):
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
            tab, textvariable=self.headword_description_var, wraplength=900, justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))

        examples = ttk.LabelFrame(tab, text="经典样例（局部裁切）", padding=8)
        examples.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        examples.columnconfigure(0, weight=1)
        examples.columnconfigure(1, weight=1)
        examples.columnconfigure(2, weight=1)
        self.headword_examples_frame = examples
        ttk.Label(
            tab, textvariable=self.headword_examples_var, wraplength=900, justify="left",
            foreground="#555555",
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

        help_box = ttk.LabelFrame(tab, text="理解方式", padding=10)
        help_box.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 0))
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
        tab.rowconfigure(3, weight=1)
        ttk.Label(tab, text="⑤ 多页测试后再确认", font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            tab,
            text="测试只处理代表页，不写 PDIC。红线=检出的词头；半透明灰区=当前 Profile 不参与正文识别的区域。",
            foreground="#666666",
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))
        bar = ttk.Frame(tab)
        bar.grid(row=2, column=0, sticky="ew")
        self.validate_button = ttk.Button(bar, text="测试当前 Profile", command=self.validate_profile)
        self.validate_button.pack(side="left")
        self.validation_status_var = tk.StringVar(value="尚未测试")
        ttk.Label(bar, textvariable=self.validation_status_var).pack(side="left", padx=(10, 0))

        self.validation_frame = ttk.Frame(tab)
        self.validation_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        self.validation_frame.columnconfigure(0, weight=1)
        self.validation_frame.columnconfigure(1, weight=1)

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
        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_headword_description()
        self._refresh_summary()

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
                        ttk.Label(cell, image=photo).pack()
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
                text=line, wraplength=900, justify="left",
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
        apply_headword_profile(s, self._current_profile_key())
        for name, value in language_effective_settings(s.ocr_language, s.layout_writing_mode).items():
            if hasattr(s, name):
                setattr(s, name, value)
        s.profile_setup_version = PROFILE_SETUP_VERSION
        return s

    def _refresh_summary(self) -> None:
        try:
            settings = self._settings_from_ui()
            self.summary_var.set("  ｜  ".join(profile_summary_tags(settings)))
        except Exception:
            return

    def _load_sample_thumbnails(self) -> None:
        for child in self.sample_frame.winfo_children():
            child.destroy()
        self._photos.clear()
        region_titles = ("前部", "中部", "后部")
        groups: list[ttk.LabelFrame] = []
        for column, title in enumerate(region_titles):
            group = ttk.LabelFrame(self.sample_frame, text=title, padding=6)
            group.grid(row=0, column=column, sticky="nsew", padx=4, pady=2)
            group.columnconfigure(0, weight=1)
            groups.append(group)

        for slot, index in enumerate(self.sample_indices):
            path = self.project.images[index]
            group = groups[min(2, slot // 2)]
            local_row = slot % 2
            cell = ttk.Frame(group)
            cell.grid(row=local_row, column=0, sticky="ew", pady=4)
            try:
                with Image.open(path) as opened:
                    image = normalize_page_rgb(opened)
                image.thumbnail((250, 155), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self._photos.append(photo)
                ttk.Label(cell, image=photo).pack()
            except Exception as exc:
                ttk.Label(cell, text=f"缩略图失败：{exc}", wraplength=250).pack()
            ttk.Label(cell, text=path.name, wraplength=260).pack(anchor="center", pady=(3, 0))
            ttk.Button(
                cell, text="更换…", command=lambda s=slot: self._choose_sample_page(s),
            ).pack(anchor="center", pady=(3, 0))

    def _choose_sample_page(self, slot: int) -> None:
        if not self.sample_candidates:
            return
        picker = tk.Toplevel(self)
        picker.title("更换代表页")
        picker.geometry("620x520")
        picker.transient(self)
        picker.grab_set()

        ttk.Label(
            picker,
            text="选择一张正文代表页。列表已优先排除 0000_*、目录、附录等明显非正文页。",
            wraplength=580,
        ).pack(anchor="w", padx=10, pady=(10, 6))
        body = ttk.Frame(picker)
        body.pack(fill="both", expand=True, padx=10)
        scrollbar = ttk.Scrollbar(body, orient="vertical")
        listing = tk.Listbox(body, yscrollcommand=scrollbar.set, exportselection=False)
        scrollbar.configure(command=listing.yview)
        listing.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        current = self.sample_indices[slot]
        selected_row = 0
        for row, index in enumerate(self.sample_candidates):
            path = self.project.images[index]
            listing.insert("end", f"{index + 1:05d}    {path.name}")
            if index == current:
                selected_row = row
        if self.sample_candidates:
            listing.selection_set(selected_row)
            listing.see(selected_row)

        def apply_choice(_event=None) -> None:
            selection = listing.curselection()
            if not selection:
                return
            index = self.sample_candidates[int(selection[0])]
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
            self._load_sample_thumbnails()
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

    def validate_profile(self) -> None:
        if self._validation_running:
            return
        settings = self._settings_from_ui()
        indices = list(self.sample_indices)
        if not indices:
            return
        self._validation_running = True
        self._validation_revision_started = self._profile_revision
        self.validate_button.configure(state="disabled")
        self.validation_status_var.set("正在测试代表页…")
        for child in self.validation_frame.winfo_children():
            child.destroy()
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
                        paddle_filter_rules_path=filter_path,
                        profile_page_index=index,
                    )
                    preview = self._marker_preview(image, entries, geometry, settings, index)
                    results.append((index, path.name, len(entries), len(geometry.column_starts), preview, None))
                except Exception as exc:
                    results.append((index, path.name, 0, 0, None, str(exc)))
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
    def _marker_preview(image: Image.Image, entries, geometry, settings: AppSettings, page_index: int) -> Image.Image:
        source = image.copy()
        thumb = source.copy()
        thumb.thumbnail((500, 360), Image.Resampling.LANCZOS)
        thumb = thumb.convert("RGBA")
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
                    fill=(255, 0, 0, 255), width=2,
                )
            except Exception:
                x, y = entry.x * sx, entry.y * sy
                draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(255, 0, 0, 255))
        return thumb.convert("RGB")

    def _finish_validation(self, results) -> None:
        self._validation_running = False
        self.validate_button.configure(state="normal")
        revision_changed = self._validation_revision_started != self._profile_revision
        self._validation_photos.clear()
        failures = 0
        validated_pages: list[str] = []
        for slot, (_index, name, count, columns, preview, error) in enumerate(results):
            cell = ttk.LabelFrame(self.validation_frame, text=name, padding=6)
            cell.grid(row=slot // 2, column=slot % 2, sticky="nsew", padx=6, pady=6)
            if preview is not None:
                photo = ImageTk.PhotoImage(preview)
                self._validation_photos.append(photo)
                ttk.Label(cell, image=photo).pack()
                ttk.Label(cell, text=f"检出 {count} 个词头 · {columns} 栏").pack(anchor="w", pady=(4, 0))
                validated_pages.append(name)
            else:
                failures += 1
                ttk.Label(cell, text=f"测试失败：{error}", wraplength=430).pack(anchor="w")
        # Treat the Profile as validated only when every representative page
        # completed successfully. Partial success is useful diagnostically but
        # must not survive as a misleading "validated" state.
        self.working.profile_last_validated_pages = (
            validated_pages if failures == 0 and not revision_changed else []
        )
        if revision_changed:
            self.validation_status_var.set(
                "测试期间设置已改变；本次结果仅供参考，请按当前设置重新测试"
            )
        elif failures:
            self.validation_status_var.set(
                f"完成：{len(results)-failures}/{len(results)} 页成功；请检查失败页后重新测试"
            )
        else:
            self.validation_status_var.set(f"完成：{len(results)} 页均已测试，可确认或返回调整")

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
