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
from .processing import column_index, detect_entries
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
    sample_page_indices,
)
from .project_storage import (
    headword_filter_rules_path,
    ocr_cache_root,
    profile_path as project_profile_path,
    settings_path,
)


COMMON_OCR_LANGUAGES = (
    "eng", "chi_sim", "chi_tra", "jpn", "ara", "deu", "spa", "ita", "por", "fra",
)

SEPARATOR_LABEL_TO_VALUE = {
    "自动判断": "auto",
    "有中央分隔线": "present",
    "无中央分隔线": "absent",
}
HEADER_FOOTER_LABEL_TO_VALUE = {
    "自动检测": "auto",
    "没有": "none",
    "有，排除固定区域": "present",
}
SIDE_LABEL_TO_VALUE = {
    "无页边占位内容": "none",
    "左侧固定": "left",
    "右侧固定": "right",
    "A/B 页外侧交替": "outer",
    "A/B 页内侧交替": "inner",
}
PAIR_LABEL_TO_VALUE = {
    "所有页面相同": "same",
    "A/B 页交替": "alternate",
}


def _label_for_value(mapping: dict[str, str], value: str, fallback: str) -> str:
    for label, mapped in mapping.items():
        if mapped == value:
            return label
    return fallback


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
        self.geometry("1120x820")
        self.minsize(900, 650)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close_without_save)
        self._photos: list[ImageTk.PhotoImage] = []
        self._validation_photos: list[ImageTk.PhotoImage] = []
        self._validation_running = False
        self._analysis_running = False
        self._analysis_suggestion: dict[str, object] = {}
        self._analysis_queue: queue.Queue | None = None
        self._validation_queue: queue.Queue | None = None
        self.sample_indices = sample_page_indices(len(self.project.images), 6)

        self._build_vars()
        self._build_ui()
        self._load_sample_thumbnails()
        self._refresh_headword_description()
        self._refresh_language_summary()
        self._refresh_summary()

        if self.new_project or int(getattr(parent.settings, "profile_setup_version", 0) or 0) < PROFILE_SETUP_VERSION:
            self.after(350, self.analyze_representative_pages)

    def _build_vars(self) -> None:
        s = self.working
        self.reading_var = tk.StringVar(value=reading_choice_from_settings(s))
        self.columns_policy_var = tk.StringVar(value=str(s.layout_columns_policy or "detect"))
        self.columns_var = tk.IntVar(value=max(1, int(s.columns)))
        self.separator_var = tk.StringVar(value=_label_for_value(
            SEPARATOR_LABEL_TO_VALUE, str(s.layout_column_separator_mode or "auto"), "自动判断",
        ))
        self.header_mode_var = tk.StringVar(value=_label_for_value(
            HEADER_FOOTER_LABEL_TO_VALUE,
            str(getattr(s, "profile_header_mode", "auto") or "auto"),
            "自动检测",
        ))
        self.footer_mode_var = tk.StringVar(value=_label_for_value(
            HEADER_FOOTER_LABEL_TO_VALUE,
            str(getattr(s, "profile_footer_mode", "auto") or "auto"),
            "自动检测",
        ))
        self.side_mode_var = tk.StringVar(value=_label_for_value(
            SIDE_LABEL_TO_VALUE,
            str(getattr(s, "profile_side_content_mode", "none") or "none"),
            "无页边占位内容",
        ))
        self.page_pair_var = tk.StringVar(value=_label_for_value(
            PAIR_LABEL_TO_VALUE,
            str(getattr(s, "profile_page_pair_mode", "same") or "same"),
            "所有页面相同",
        ))
        self.first_variant_var = tk.StringVar(value=str(getattr(s, "profile_first_page_variant", "A") or "A"))
        self.header_percent_var = tk.DoubleVar(value=float(getattr(s, "profile_header_percent", 6.0)))
        self.footer_percent_var = tk.DoubleVar(value=float(getattr(s, "profile_footer_percent", 5.0)))
        self.side_percent_var = tk.DoubleVar(value=float(getattr(s, "profile_side_percent", 8.0)))
        self.ocr_language_var = tk.StringVar(value=str(s.ocr_language or "eng"))
        self.index_language_var = tk.StringVar(value=str(s.dictionary_index_language or ""))
        self.content_language_var = tk.StringVar(value=str(s.dictionary_content_language or ""))
        self.custom_name_var = tk.StringVar(value=str(getattr(s, "dictionary_custom_profile_name", "") or ""))

        self.profile_choices = ordered_headword_profiles(self.custom_name_var.get())
        self.profile_label_to_key = dict(self.profile_choices)
        self.headword_profile_var = tk.StringVar(value=self._profile_label_for_key(s.dictionary_profile_id))

        traced = (
            self.reading_var, self.columns_policy_var, self.columns_var, self.separator_var,
            self.header_mode_var, self.footer_mode_var, self.side_mode_var,
            self.page_pair_var, self.first_variant_var, self.header_percent_var,
            self.footer_percent_var, self.side_percent_var, self.ocr_language_var,
            self.index_language_var, self.content_language_var,
        )
        for var in traced:
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
        for label in ("1 阅读方式", "2 页面模板", "3 词头结构", "4 语言与 OCR", "5 测试与确认"):
            frame = ttk.Frame(self.notebook, padding=12)
            self.notebook.add(frame, text=label)
            self.tabs.append(frame)

        self._build_reading_tab(self.tabs[0])
        self._build_template_tab(self.tabs[1])
        self._build_headword_tab(self.tabs[2])
        self._build_language_tab(self.tabs[3])
        self._build_validation_tab(self.tabs[4])

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

    def _build_reading_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        ttk.Label(
            tab,
            text="① 页面怎么读？",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            tab,
            text="这里只描述阅读方向。镜像/旋转等 canonical 变换由软件自动推导，不要求用户理解。",
            foreground="#666666",
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))

        choices = ttk.Frame(tab)
        choices.grid(row=2, column=0, sticky="w")
        for row, key in enumerate(("horizontal-ltr", "horizontal-rtl", "vertical-rl", "vertical-lr")):
            ttk.Radiobutton(
                choices, text=READING_LABELS[key], variable=self.reading_var, value=key,
                command=self._reading_changed,
            ).grid(row=row, column=0, sticky="w", pady=4)

        samples = ttk.LabelFrame(tab, text="代表页（前部 / 中部 / 后部）", padding=8)
        samples.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        self.sample_frame = samples

    def _build_template_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="② 正文在哪里？", font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            tab,
            text="页面模板负责分栏、页眉/页尾和页边占位内容；A/B 表示相邻扫描页，不强行等同书籍奇偶页。",
            foreground="#666666",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))

        left = ttk.LabelFrame(tab, text="正文与分栏", padding=10)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 5))
        right = ttk.LabelFrame(tab, text="页眉 / 页尾 / 页边", padding=10)
        right.grid(row=2, column=1, sticky="nsew", padx=(5, 0))

        ttk.Radiobutton(left, text="栏数自动分析", variable=self.columns_policy_var, value="detect").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=3
        )
        ttk.Radiobutton(left, text="固定栏数", variable=self.columns_policy_var, value="fixed").grid(
            row=1, column=0, sticky="w", pady=3
        )
        tk.Spinbox(left, from_=1, to=8, width=5, textvariable=self.columns_var).grid(
            row=1, column=1, sticky="w", pady=3
        )
        ttk.Label(left, text="中央分隔线：").grid(row=2, column=0, sticky="e", pady=5)
        ttk.Combobox(
            left, textvariable=self.separator_var, state="readonly", width=18,
            values=tuple(SEPARATOR_LABEL_TO_VALUE.keys()),
        ).grid(row=2, column=1, sticky="w", pady=5)

        self.analysis_suggestion_var = tk.StringVar(value="尚未分析代表页")
        ttk.Label(left, textvariable=self.analysis_suggestion_var, wraplength=430).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(12, 4)
        )
        analysis_buttons = ttk.Frame(left)
        analysis_buttons.grid(row=4, column=0, columnspan=2, sticky="w")
        self.analyze_button = ttk.Button(
            analysis_buttons, text="重新分析代表页", command=self.analyze_representative_pages,
        )
        self.analyze_button.pack(side="left")
        self.apply_analysis_button = ttk.Button(
            analysis_buttons, text="应用建议", command=self.apply_analysis_suggestion, state="disabled",
        )
        self.apply_analysis_button.pack(side="left", padx=(6, 0))

        self._mode_row(right, 0, "页眉：", self.header_mode_var)
        ttk.Label(right, text="排除高度%").grid(row=1, column=0, sticky="e")
        tk.Spinbox(right, from_=0, to=35, increment=0.5, width=6, textvariable=self.header_percent_var).grid(
            row=1, column=1, sticky="w"
        )
        self._mode_row(right, 2, "页尾：", self.footer_mode_var)
        ttk.Label(right, text="排除高度%").grid(row=3, column=0, sticky="e")
        tk.Spinbox(right, from_=0, to=35, increment=0.5, width=6, textvariable=self.footer_percent_var).grid(
            row=3, column=1, sticky="w"
        )
        ttk.Label(right, text="页边内容：").grid(row=4, column=0, sticky="e", pady=5)
        ttk.Combobox(
            right, textvariable=self.side_mode_var, state="readonly", width=22,
            values=tuple(SIDE_LABEL_TO_VALUE.keys()),
        ).grid(row=4, column=1, sticky="w", pady=5)
        ttk.Label(right, text="页边排除宽度%").grid(row=5, column=0, sticky="e")
        tk.Spinbox(right, from_=0, to=30, increment=0.5, width=6, textvariable=self.side_percent_var).grid(
            row=5, column=1, sticky="w"
        )
        ttk.Label(right, text="页面模板：").grid(row=6, column=0, sticky="e", pady=(10, 4))
        ttk.Combobox(
            right, textvariable=self.page_pair_var, state="readonly", width=22,
            values=tuple(PAIR_LABEL_TO_VALUE.keys()),
        ).grid(row=6, column=1, sticky="w", pady=(10, 4))
        ttk.Label(right, text="项目第一张图：").grid(row=7, column=0, sticky="e")
        ttk.Combobox(
            right, textvariable=self.first_variant_var, state="readonly", width=8, values=("A", "B"),
        ).grid(row=7, column=1, sticky="w")
        ttk.Label(
            right,
            text="outer：A 页左侧 / B 页右侧；inner 相反。若第一张扫描实际属于 B 页，选择 B 即可整体翻转。",
            foreground="#666666", wraplength=430,
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))

    @staticmethod
    def _mode_row(parent, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", pady=5)
        ttk.Combobox(
            parent, textvariable=variable, state="readonly", width=22,
            values=tuple(HEADER_FOOTER_LABEL_TO_VALUE.keys()),
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
            tab, textvariable=self.headword_description_var, wraplength=820, justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 4))
        ttk.Label(
            tab, textvariable=self.headword_examples_var, wraplength=820, justify="left",
            foreground="#555555",
        ).grid(row=5, column=0, columnspan=2, sticky="w")

        ttk.LabelFrame(tab, text="理解方式", padding=10).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(16, 0)
        )
        help_box = tab.grid_slaves(row=6, column=0)[0]
        ttk.Label(
            help_box,
            text=(
                "常规文字词头：粗体/左缘/结构线索为主；  编号前缀：如 1. word 或 1 word；\n"
                "CJK 大字/括号：如 亜、七、【案件】；  符号前缀：词头前有固定符号；\n"
                "自定义结构：保留你为当前词典调好的规则，并可起项目内名称。"
            ),
            justify="left",
        ).pack(anchor="w")

    def _build_language_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="④ 语言与 OCR", font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            tab,
            text="这里只选语义语言；Paddle/Tesseract 语言、PSM 与方向识别由语言 + 阅读方向自动推导。",
            foreground="#666666",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))

        ttk.Label(tab, text="OCR 语言：").grid(row=2, column=0, sticky="e", padx=(0, 8), pady=5)
        combo = ttk.Combobox(
            tab, textvariable=self.ocr_language_var, values=COMMON_OCR_LANGUAGES,
            state="normal", width=26,
        )
        combo.grid(row=2, column=1, sticky="w", pady=5)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_language_summary())
        combo.bind("<FocusOut>", lambda _e: self._refresh_language_summary())
        self.ocr_language_var.trace_add("write", lambda *_args: self.after_idle(self._refresh_language_summary))

        ttk.Label(tab, text="索引语言：").grid(row=3, column=0, sticky="e", padx=(0, 8), pady=5)
        ttk.Entry(tab, textvariable=self.index_language_var, width=28).grid(row=3, column=1, sticky="w", pady=5)
        ttk.Label(tab, text="内容语言：").grid(row=4, column=0, sticky="e", padx=(0, 8), pady=5)
        ttk.Entry(tab, textvariable=self.content_language_var, width=28).grid(row=4, column=1, sticky="w", pady=5)

        backend = ttk.LabelFrame(tab, text="自动派生的 OCR 后端设置", padding=10)
        backend.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(14, 0))
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
            text="测试只处理代表页，不写 PDIC。预览中的红线是当前 Profile 检出的词头锚点。",
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

    def _reading_changed(self) -> None:
        self._refresh_language_summary()
        self._refresh_summary()

    def _headword_changed(self) -> None:
        self._refresh_headword_description()
        self._refresh_summary()

    def _custom_name_changed(self) -> None:
        current = self._current_profile_key()
        self.profile_choices = ordered_headword_profiles(self.custom_name_var.get())
        self.profile_label_to_key = dict(self.profile_choices)
        self.headword_combo.configure(values=tuple(label for label, _key in self.profile_choices))
        self.headword_profile_var.set(self._profile_label_for_key(current))
        self._refresh_headword_description()
        self._refresh_summary()

    def _refresh_headword_description(self) -> None:
        key = self._current_profile_key()
        try:
            profile = dictionary_profile_preset(key)
        except Exception:
            return
        self.custom_name_entry.configure(state="normal" if key == "custom" else "disabled")
        self.headword_description_var.set(profile.description)
        if profile.examples:
            self.headword_examples_var.set(
                "经典样例：" + "；".join(example.dictionary for example in profile.examples)
            )
        else:
            self.headword_examples_var.set("经典样例：通用兼容型（无固定词典绑定）")

    def _refresh_language_summary(self) -> None:
        language = self.ocr_language_var.get().strip() or "eng"
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
        s.layout_columns_policy = self.columns_policy_var.get()
        s.columns = max(1, int(self.columns_var.get()))
        s.layout_column_separator_mode = SEPARATOR_LABEL_TO_VALUE.get(
            self.separator_var.get(), "auto"
        )
        s.profile_header_mode = HEADER_FOOTER_LABEL_TO_VALUE.get(
            self.header_mode_var.get(), "auto"
        )
        s.profile_footer_mode = HEADER_FOOTER_LABEL_TO_VALUE.get(
            self.footer_mode_var.get(), "auto"
        )
        s.profile_side_content_mode = SIDE_LABEL_TO_VALUE.get(
            self.side_mode_var.get(), "none"
        )
        s.profile_page_pair_mode = PAIR_LABEL_TO_VALUE.get(
            self.page_pair_var.get(), "same"
        )
        s.profile_first_page_variant = self.first_variant_var.get()
        s.profile_header_percent = max(0.0, min(35.0, float(self.header_percent_var.get())))
        s.profile_footer_percent = max(0.0, min(35.0, float(self.footer_percent_var.get())))
        s.profile_side_percent = max(0.0, min(30.0, float(self.side_percent_var.get())))
        s.dictionary_custom_profile_name = self.custom_name_var.get().strip()
        s.ocr_language = self.ocr_language_var.get().strip() or "eng"
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
        for slot, index in enumerate(self.sample_indices):
            path = self.project.images[index]
            try:
                with Image.open(path) as opened:
                    image = normalize_page_rgb(opened)
                image.thumbnail((280, 175), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self._photos.append(photo)
                cell = ttk.Frame(self.sample_frame)
                cell.grid(row=slot // 3, column=slot % 3, padx=5, pady=5, sticky="n")
                ttk.Label(cell, image=photo).pack()
                ttk.Label(cell, text=path.name).pack(anchor="center")
            except Exception as exc:
                ttk.Label(self.sample_frame, text=f"{path.name}\n{exc}").grid(
                    row=slot // 3, column=slot % 3, padx=5, pady=5
                )

    def _move_step(self, delta: int) -> None:
        current = self.notebook.index(self.notebook.select())
        target = max(0, min(len(self.tabs) - 1, current + int(delta)))
        self.notebook.select(self.tabs[target])

    def analyze_representative_pages(self) -> None:
        if self._analysis_running or not self.sample_indices:
            return
        self._analysis_running = True
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
                    estimates.append(detect_layout_parameters(image, page_settings))
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
        if not estimates:
            self.analysis_suggestion_var.set("代表页分析失败；可直接人工选择页面模板。")
            self.apply_analysis_button.configure(state="disabled")
            return
        aggregate, consistency = aggregate_layout_estimates(estimates, columns_policy="detect")
        separators = sum(1 for estimate in estimates if getattr(estimate, "separator_x", None) is not None)
        separator = "present" if separators > len(estimates) / 2 else "absent"
        self._analysis_suggestion = {
            "columns": int(aggregate["columns"]),
            "separator": separator,
        }
        sep_text = "有中央分隔线" if separator == "present" else "无明确中央分隔线"
        error_text = f"；{len(errors)} 页未参与" if errors else ""
        self.analysis_suggestion_var.set(
            f"自动建议：{aggregate['columns']}栏 · {sep_text} · {consistency}{error_text}"
        )
        self.apply_analysis_button.configure(state="normal")

    def apply_analysis_suggestion(self) -> None:
        if not self._analysis_suggestion:
            return
        self.columns_policy_var.set("fixed")
        self.columns_var.set(int(self._analysis_suggestion.get("columns", self.columns_var.get())))
        separator_value = str(self._analysis_suggestion.get("separator", "auto"))
        self.separator_var.set(_label_for_value(
            SEPARATOR_LABEL_TO_VALUE, separator_value, "自动判断",
        ))

    def validate_profile(self) -> None:
        if self._validation_running:
            return
        settings = self._settings_from_ui()
        indices = sample_page_indices(len(self.project.images), 4)
        if not indices:
            return
        self._validation_running = True
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
        thumb.thumbnail((480, 330), Image.Resampling.LANCZOS)
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
        self._validation_photos.clear()
        failures = 0
        validated_pages: list[str] = []
        for slot, (_index, name, count, columns, preview, error) in enumerate(results):
            cell = ttk.LabelFrame(self.validation_frame, text=name, padding=6)
            cell.grid(row=slot // 2, column=slot % 2, sticky="nsew", padx=5, pady=5)
            if preview is not None:
                photo = ImageTk.PhotoImage(preview)
                self._validation_photos.append(photo)
                ttk.Label(cell, image=photo).pack()
                ttk.Label(cell, text=f"检出 {count} 个词头 · {columns} 栏").pack(anchor="w", pady=(4, 0))
                validated_pages.append(name)
            else:
                failures += 1
                ttk.Label(cell, text=f"测试失败：{error}", wraplength=430).pack(anchor="w")
        self.working.profile_last_validated_pages = validated_pages
        if failures:
            self.validation_status_var.set(f"完成：{len(results)-failures}/{len(results)} 页成功；请检查失败页")
        else:
            self.validation_status_var.set(f"完成：{len(results)} 页均已测试，可确认或返回调整")

    def save_and_close(self) -> None:
        try:
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
