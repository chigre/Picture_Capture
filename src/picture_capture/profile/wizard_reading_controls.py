"""Project Profile Wizard dictionary identity, reading direction and OCR controls."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tkinter import ttk


def build_reading_tab(self, tab: ttk.Frame, *, deps) -> None:
    ttk = deps["ttk"]
    READING_LABELS = deps["READING_LABELS"]
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
    from ..ui.profile_wizard_illustrated import add_wizard_layout_selector
    add_wizard_layout_selector(self, tab, row=6)

    ttk.Label(
        tab,
        text="右侧代表页优先使用正文页码范围；未填写或无效时再从疑似正文的前部 / 中部 / 后部抽取。每一张都可在右侧手动更换。",
        foreground="#666666", wraplength=self._wizard_left_width,
    ).grid(row=5, column=0, sticky="w", pady=(10, 0))



def build_language_section(self, parent: ttk.Frame, *, row: int, deps) -> None:
    ttk = deps["ttk"]
    tk = deps["tk"]
    OCR_LANGUAGE_LABEL_TO_VALUE = deps["OCR_LANGUAGE_LABEL_TO_VALUE"]
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




def body_page_range_changed(self, _event=None, *, deps) -> None:
    tk = deps["tk"]
    configured_body_page_indices = deps["configured_body_page_indices"]
    probable_body_page_indices = deps["probable_body_page_indices"]
    representative_page_indices = deps["representative_page_indices"]
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




def refresh_language_summary(self, *, deps) -> None:
    _ocr_language_code = deps["_ocr_language_code"]
    replace = deps["replace"]
    apply_reading_choice = deps["apply_reading_choice"]
    language_effective_settings = deps["language_effective_settings"]
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

