"""Domain owner for the full SettingsDialog Tk widget initialization after Toplevel.__init__.

The original class constructor remains in app.py to preserve Python's zero-arg
super() semantics; all other original initialization statements live here.
Live app module globals are injected on every call; no Tk root is created.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import Image
    from .. import main_workspace_build
    from ...models import AppSettings


def initialize_settings_dialog(self: Any, parent: Any, initial_tab: str | None = None, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    ttk = deps["ttk"]
    Image = deps["Image"]
    fit_window_to_work_area = deps["fit_window_to_work_area"]
    _build_modern_dialog_heading = deps["_build_modern_dialog_heading"]
    effective_project_profile_id = deps["effective_project_profile_id"]
    project_profile_path = deps["project_profile_path"]
    preferred_font_family = deps["preferred_font_family"]
    _settings_illustration_ui = deps["_settings_illustration_ui"]
    _settings_ref_box_ui = deps["_settings_ref_box_ui"]
    _settings_inference_ui = deps["_settings_inference_ui"]
    DETECTION_LABELS = deps["DETECTION_LABELS"]
    LENS_MODE_LABELS = deps["LENS_MODE_LABELS"]
    LENS_MODE_VALUES = deps["LENS_MODE_VALUES"]
    APPEARANCE_MODE_VALUES = deps["APPEARANCE_MODE_VALUES"]
    OCR_ENGINE_LABELS = deps["OCR_ENGINE_LABELS"]
    OCR_ENGINE_VALUES = deps["OCR_ENGINE_VALUES"]
    _project_templates = deps["_project_templates"]
    self.parent = parent
    self.title("设置中心")
    self.update_idletasks()
    screen_w = max(900, self.winfo_screenwidth())
    screen_h = max(650, self.winfo_screenheight())
    fit_window_to_work_area(
        self,
        min(1120, max(840, int(screen_w * 0.80))),
        max(560, int(screen_h * 0.75)),
        min_width=840,
        min_height=560,
    )
    self.resizable(True, True)
    self.vars: dict[str, tk.Variable] = {}
    self.crop_vars: dict[str, tk.Variable] = {}
    self._crop_specials: dict[str, dict] = {}
    self._casts = {name: cast for _, name, cast in self.FIELDS}
    self._field_meta = {name: (label, cast) for label, name, cast in self.FIELDS}
    self._sort_label_to_value: dict[str, str] = {}
    self._settings_help_title_var = tk.StringVar(value="这里会解释当前设置")
    self._settings_help_body_var = tk.StringVar(
        value="把鼠标停在任一设置项上，或进入输入框，即可看到它控制什么、"
              "什么时候需要调整，以及调大/调小可能带来的影响。"
    )
    self._settings_save_status_var = tk.StringVar(value="✓ 自动保存已开启")
    self._settings_help_current_image: str | None = None
    self._settings_help_original_images: dict[str, Image.Image] = {}
    self._settings_help_image_widgets: list[
        tuple[ttk.Label, ttk.Separator, ttk.LabelFrame]
    ] = []
    self._settings_help_image_job: str | None = None
    self._settings_help_scroll_canvases: list[tk.Canvas] = []

    outer = ttk.Frame(self, padding=(18, 14, 18, 12))
    outer.pack(fill="both", expand=True)
    _build_modern_dialog_heading(
        outer,
        "设置中心",
        "按工作任务整理：第一次使用优先看“常用 / OCR画线”；"
        "普通画线是备用方案，底层阈值、正则和后端参数集中在高级区，不确定时无需修改。",
    )
    self._configure_settings_appearance_styles()
    notebook = ttk.Notebook(outer, style="PC.Settings.TNotebook")
    self.notebook = notebook
    notebook.pack(fill="both", expand=True)
    self._settings_canvases: dict[str, tk.Canvas] = {}

    common_tab = ttk.Frame(notebook)
    normal_tab = ttk.Frame(notebook)
    illustration_tab = ttk.Frame(notebook)
    ref_box_tab = ttk.Frame(notebook)
    performance_tab = ttk.Frame(notebook)
    separator_y_tab = ttk.Frame(notebook)
    ocr_tab = ttk.Frame(notebook)
    display_tab = ttk.Frame(notebook)
    project_tab = ttk.Frame(notebook)
    crop_tab = ttk.Frame(notebook)
    advanced_tab = ttk.Frame(notebook)
    sort_tab = ttk.Frame(notebook)
    rules_tab = ttk.Frame(notebook)
    for tab, label in (
        (common_tab, "常用"),
        (ocr_tab, "OCR画线"),
        (normal_tab, "普通画线"),
        (separator_y_tab, "横线 Y 精修"),
        (illustration_tab, "插图"),
        (ref_box_tab, "REF框"),
        (performance_tab, "性能测试与诊断"),
        (display_tab, "显示/校对"),
        (project_tab, "项目/批量"),
        (crop_tab, "切图"),
        (advanced_tab, "高级"),
        (sort_tab, "排序"),
        (rules_tab, "过滤规则"),
    ):
        notebook.add(tab, text=label)

    self._settings_tabs = {
        "common": common_tab,
        "normal": normal_tab,
        "separator_y": separator_y_tab,
        "illustration": illustration_tab,
        "ref_box": ref_box_tab,
        "performance": performance_tab,
        "ocr": ocr_tab,
        "display": display_tab,
        "project": project_tab,
        "crop": crop_tab,
        "advanced": advanced_tab,
        "profile": advanced_tab,
        "params": common_tab,
        "sort": sort_tab,
        "rules": rules_tab,
    }
    self.select_tab(initial_tab)
    notebook.bind(
        "<<NotebookTabChanged>>",
        lambda _e: self._show_settings_help(
            "设置说明",
            "把鼠标停在任一设置项上，或进入输入框，即可看到它控制什么、"
            "什么时候需要调整，以及调大/调小可能带来的影响。",
        ),
        add="+",
    )

    # Reuse the project profile.
    self._active_profile_key = effective_project_profile_id(
        parent.settings,
        project_profile_path(parent.project.root) if parent.project else None,
    )
    self._profile_selection_changed = False
    self._profile_label_to_key: dict[str, str] = {}

    common = self._scrollable_settings_page(common_tab)
    self._settings_intro(
        common,
        "先确认版面，再用 OCR 画线完成代表页验证",
        "推荐流程：项目Profile → 检测版面参数 → 代表页运行 OCR 画线 → "
        "确认无明显漏线/误线后再批量。OCR画线是默认推荐路径，会同时利用文字、位置和结构证据；"
        "普通画线保留为备用方案，主要用于左缘极稳定的简单版式或 OCR 暂不可用时。",
    )
    workflow = ttk.Frame(common)
    workflow.pack(fill="x", pady=(0, 10))
    profile_button = ttk.Button(
        workflow, text="打开项目Profile…", command=parent.open_project_profile
    )
    profile_button.pack(side="left")
    parent._attach_tooltip(
        profile_button,
        "配置词典信息、阅读方向、页面模板和词头结构，并用代表页测试。",
    )
    layout_button = ttk.Button(
        workflow, text="检测版面参数", command=parent.detect_layout_current
    )
    layout_button.pack(side="left", padx=(6, 0))
    parent._attach_tooltip(
        layout_button,
        "按主界面当前页面范围检测；若页面数量≥2，数值参数取稳健中位数。",
    )
    environment_button = ttk.Button(
        workflow, text="环境中心", command=self.check_ocr_engines
    )
    environment_button.pack(side="left", padx=(6, 0))
    parent._attach_tooltip(
        environment_button,
        "检查 OCR、Tesseract、Lens、OpenCC 等运行环境。",
    )

    mode_group = ttk.LabelFrame(common, text="默认画线方式", padding=(12, 9))
    mode_group.pack(fill="x", pady=(0, 10))
    mode_group.columnconfigure(1, weight=1)
    method_var = tk.StringVar(
        value=DETECTION_LABELS.get(
            parent.settings.detection_method, DETECTION_LABELS["paddleocr"]
        )
    )
    self.vars["detection_method"] = method_var

    combined_mode = ttk.Radiobutton(
        mode_group,
        text="融合画线+OCR",
        variable=method_var,
        value=DETECTION_LABELS["combined"],
    )
    combined_mode.grid(row=0, column=0, sticky="w", pady=3)
    combined_mode_help = ttk.Label(
        mode_group,
        text="普通几何负责稳定定位，OCR负责语义确认与独立救漏；最终统一配对去重。",
        foreground="#666666",
        justify="left",
    )
    combined_mode_help.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=3)
    self._bind_responsive_labels(
        combined_mode_help, combined_mode_help, horizontal_padding=4, min_wrap=100
    )

    ocr_mode = ttk.Radiobutton(
        mode_group,
        text="OCR画线（默认）",
        variable=method_var,
        value=DETECTION_LABELS["paddleocr"],
    )
    ocr_mode.grid(row=1, column=0, sticky="w", pady=3)
    ocr_mode_help = ttk.Label(
        mode_group,
        text="只运行 OCR / parser / 视觉候选链，便于定位 OCR 侧问题。",
        foreground="#666666",
        justify="left",
    )
    ocr_mode_help.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=3)
    self._bind_responsive_labels(
        ocr_mode_help, ocr_mode_help, horizontal_padding=4, min_wrap=100
    )

    normal_mode = ttk.Radiobutton(
        mode_group,
        text="普通画线（单独诊断）",
        variable=method_var,
        value=DETECTION_LABELS["left_edge"],
    )
    normal_mode.grid(row=2, column=0, sticky="w", pady=3)
    normal_mode_help = ttk.Label(
        mode_group,
        text="只运行 VB 左缘几何/墨迹链；速度最快，适合检查缩进型版式的几何基线。",
        foreground="#666666",
        justify="left",
    )
    normal_mode_help.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=3)
    self._bind_responsive_labels(
        normal_mode_help, normal_mode_help, horizontal_padding=4, min_wrap=100
    )

    for widget, title, body in (
        (
            combined_mode,
            "融合画线+OCR",
            "两条成熟路径各自完整运行后再融合：普通模式提供高速、稳定的几何词条边界；"
            "OCR 模式提供词头文字、结构证据和普通模式之外的独立救漏。程序只在同栏、Y位置足够接近时一对一配对；"
            "匹配项输出唯一横线并继承 OCR 文字，未匹配项保留各自救漏能力，最后再用更严格阈值去重。"
            "普通/括号词优先保留 VB 分隔线位置；单个大汉字保留 OCR 的专用自适应精修位置。",
        ),
        (
            ocr_mode,
            "OCR画线（默认）",
            "单独运行现有 OCR 候选链，用于排查 OCR、词头 parser、符号/字高/粗体等结构证据。"
            "原始 OCR 缓存仍可复用。",
        ),
        (
            normal_mode,
            "普通画线（单独诊断）",
            "单独运行恢复的 VB.NET 左缘规则链，只看版面几何、墨迹和正文缩进。"
            "适合验证普通模式本身的定位效果和速度。",
        ),
    ):
        self._bind_help_widget(
            widget,
            lambda t=title, b=body: self._show_settings_help(t, b),
        )
    self._add_setting_group(
        common,
        "常用版面参数",
        self.COMMON_FIELDS,
        intro="这些值同时影响普通画线、OCR画线和后续切图。能自动检测时，优先使用检测结果。",
        help_images=True,
    )

    normal = self._scrollable_settings_page(normal_tab)
    self._settings_intro(
        normal,
        "普通画线（备用）：只使用几何和栏左墨迹",
        "这是二线方案，适合词头基本贴近栏左缘、释义正文有稳定缩进的简单版式，"
        "或 OCR 环境暂不可用时临时使用。若 OCR 可用，仍建议优先从 OCR画线开始。",
    )
    self._add_setting_group(
        normal,
        "常用设置",
        self.NORMAL_COMMON_FIELDS,
        intro="第一次使用通常只需要确认这四项。墨迹判断方式建议保持“自动（推荐）”。",
    )
    self._add_check_group(
        normal,
        "版面行为",
        self.NORMAL_CHECKS,
        intro="【使用自动版面参数】下面的七项决定每页检测后临时更新哪些版面字段；【跟随栏左缘倾斜/弯曲】及其三个百分比参数用于页面局部几何跟踪。",
    )
    self._add_collapsible_settings(
        normal,
        "高级设置（普通画线异常时再展开）",
        self.NORMAL_ADVANCED_FIELDS,
    )

    # Cross-cutting feature, not an OCR-only or ordinary-only option.
    separator_y_page = self._scrollable_settings_page(separator_y_tab)
    self._settings_intro(
        separator_y_page, "横线 Y 精修（所有画线共用）",
        "集中控制 OCR 与普通画线共享的局部墨迹谷精修。"
        "横向分析范围对新项目默认 100%；老项目已保存的取值保持不变。",
    )
    self._add_check_group(
        separator_y_page, "启用与安全检查", self.SEPARATOR_Y_CHECKS,
        intro="白缝安全核验为实验性功能，默认关闭。",
    )
    self._add_setting_group(
        separator_y_page, "精修参数", self.SEPARATOR_Y_FIELDS,
        intro="横向范围 100% 表示在扣除栏边余量后的整栏可用宽度内寻找空白带；"
        "并非保证每条线均不穿字。",
    )

    _settings_illustration_ui.build_illustration_settings_tab(self, illustration_tab)
    _settings_ref_box_ui.build_ref_box_settings_tab(self, ref_box_tab)
    performance_page = self._scrollable_settings_page(performance_tab)
    self._settings_intro(
        performance_page, "性能测试与诊断",
        "本页管理运行时测试开关和性能报告；项目设置会自动保存，"
        "新启动的普通画线子进程继承对应选项。",
    )
    self._add_check_group(
        performance_page, "分析图与性能日志",
        (
            ("启用普通画线性能诊断（导出 Markdown/CSV）", "draw_performance_profile"),
            ("复用已处理的分析图（实验）", "reuse_prepared_analysis"),
        ),
        intro="复用功能可能改变重复去噪语义，务必先比较完整 PDIC。",
    )
    _settings_inference_ui.build_inference_performance_group(self, performance_page)

    ocr_page = self._scrollable_settings_page(ocr_tab)
    self._settings_intro(
        ocr_page,
        "OCR画线（推荐默认）：用文字 + 版式 + 视觉证据判断真正词头",
        "优先使用这一模式。PaddleOCR 负责主识别；可选 Tesseract 作为第二意见，"
        "Google Lens 作为冲突时的第三意见。OCR 原始结果有缓存：参数只改变候选判断时无需重新跑 OCR。",
    )
    self._add_setting_group(
        ocr_page,
        "常用设置",
        self.OCR_COMMON_FIELDS,
        intro="先调识别范围与左缘容差；候选分数、合并阈值等放在高级区。",
    )
    self._add_check_group(
        ocr_page,
        "识别策略",
        self.OCR_COMMON_CHECKS,
        intro="结构/视觉提示用于减少正文误检；双 OCR 会更稳，但会增加运行时间。",
    )
    lens_group = ttk.LabelFrame(ocr_page, text="Google Lens（可选）", padding=(12, 9))
    lens_group.pack(fill="x", pady=(0, 10))
    if "paddle_enable_lens" not in self.vars:
        self.vars["paddle_enable_lens"] = tk.BooleanVar(
            value=bool(parent.settings.paddle_enable_lens)
        )
    lens_enable_check = ttk.Checkbutton(
        lens_group, text="启用 Lens 第三意见",
        variable=self.vars["paddle_enable_lens"],
    )
    lens_enable_check.pack(anchor="w")
    self._bind_help_widget(
        lens_enable_check,
        lambda: self._show_check_help("启用 Lens 第三意见", "paddle_enable_lens"),
    )
    lens_help = ttk.Label(
        lens_group,
        text="建议只在 Paddle/Tesseract 冲突时使用，避免不必要的网络等待。",
        foreground="#666666",
        justify="left",
    )
    lens_help.pack(anchor="w", fill="x", pady=(2, 5))
    self._bind_responsive_labels(
        lens_group, lens_help, horizontal_padding=12, min_wrap=120
    )
    lens_mode_var = tk.StringVar(
        value=LENS_MODE_LABELS.get(
            parent.settings.paddle_lens_mode, LENS_MODE_LABELS["conflict"]
        )
    )
    self.vars["paddle_lens_mode"] = lens_mode_var
    lens_row = ttk.Frame(lens_group)
    lens_row.pack(fill="x")
    ttk.Label(lens_row, text="运行模式：").pack(side="left")
    lens_mode_combo = ttk.Combobox(
        lens_row, textvariable=lens_mode_var, values=tuple(LENS_MODE_VALUES),
        state="readonly", width=34,
    )
    lens_mode_combo.pack(side="left")
    self._bind_help_widget(
        lens_row,
        lambda: self._show_setting_help("paddle_lens_mode"),
    )
    self._add_collapsible_settings(
        ocr_page,
        "高级设置（漏检/误检有明确模式时再展开）",
        self.OCR_ADVANCED_FIELDS,
        self.OCR_ADVANCED_CHECKS,
    )

    display = self._scrollable_settings_page(display_tab)
    self._settings_intro(
        display,
        "显示与校对只改变工作体验，不应该被误认为识别阈值",
        "字体、词框宽度、校对缩放和参考词表都集中在这里。"
        "修改这些项目不会改变普通画线/OCR画线的词头判断。",
    )
    appearance_group = ttk.LabelFrame(display, text="应用外观", padding=(12, 9))
    appearance_group.pack(fill="x", pady=(0, 10))
    appearance_row = ttk.Frame(appearance_group)
    appearance_row.pack(anchor="w", fill="x")
    ttk.Label(appearance_row, text="颜色模式：").pack(side="left")
    appearance_combo = ttk.Combobox(
        appearance_row, textvariable=self.parent.appearance_mode_var,
        values=tuple(APPEARANCE_MODE_VALUES), state="readonly", width=10,
    )
    appearance_combo.pack(side="left", padx=(4, 0))
    appearance_combo.bind("<<ComboboxSelected>>", self.parent._appearance_mode_selected)
    appearance_help = ttk.Label(
        appearance_group,
        text="浅色使用正常界面；深色同步主界面、校对/Profile/设置窗口及扫描图夜间预览；"
             "跟随系统会自动响应 Windows、macOS 与 Linux 的系统颜色模式。"
             "仅改变显示，不修改原图、OCR 输入、PDIC/PPP、切图或导出文件。",
        justify="left",
    )
    appearance_help.pack(anchor="w", fill="x", pady=(4, 0))
    self._bind_responsive_labels(
        appearance_group, appearance_help, horizontal_padding=24, min_wrap=160
    )
    self._add_setting_group(
        display,
        "界面与校对",
        self.DISPLAY_FIELDS,
    )
    self._add_check_group(
        display,
        "显示行为",
        self.DISPLAY_STYLE_CHECKS + self.DISPLAY_CHECKS,
    )

    project_page = self._scrollable_settings_page(project_tab)
    self._settings_intro(
        project_page,
        "项目资料与运行环境",
        "项目名称/语言等资料用于导出和词典制作；运行环境参数只在相应功能启用时生效。",
    )
    self._add_setting_group(
        project_page,
        "项目资料",
        (
            "dictionary_full_name", "dictionary_abbreviation", "dictionary_isbn",
            "dictionary_index_language", "dictionary_content_language",
            "dictionary_body_page_range",
        ),
    )
    self._add_setting_group(
        project_page,
        "运行与性能",
        self.PROJECT_RUNTIME_FIELDS,
        intro="OCR 模型和 Tesseract 路径稳定后不要频繁修改；模型/语言发生变化时应重新 OCR。",
    )
    text_ocr_group = ttk.LabelFrame(
        project_page, text="普通文本 OCR（不是 OCR画线）", padding=(12, 9)
    )
    text_ocr_group.pack(fill="x", pady=(0, 10))
    text_ocr_group.columnconfigure(2, weight=1)
    ocr_engine_var = tk.StringVar(
        value=OCR_ENGINE_LABELS.get(
            parent.settings.ocr_engine, OCR_ENGINE_LABELS["tesseract"]
        )
    )
    self.vars["ocr_engine"] = ocr_engine_var
    ttk.Label(text_ocr_group, text="OCR 引擎：").grid(
        row=0, column=0, sticky="e", padx=(0, 10), pady=4
    )
    ocr_engine_combo = ttk.Combobox(
        text_ocr_group, textvariable=ocr_engine_var,
        values=tuple(OCR_ENGINE_VALUES), state="readonly", width=28,
    )
    ocr_engine_combo.grid(row=0, column=1, sticky="w", pady=4)
    self._bind_help_widget(
        ocr_engine_combo,
        lambda: self._show_setting_help("ocr_engine"),
    )
    text_ocr_help = ttk.Label(
        text_ocr_group,
        text="用于“已有横线后再识别整行文本”的普通 OCR 功能；"
             "OCR画线使用上一个页签中的多引擎流程，两者不要混淆。",
        foreground="#666666",
        justify="left",
    )
    text_ocr_help.grid(row=0, column=2, sticky="ew", padx=(12, 0), pady=4)
    self._bind_responsive_labels(
        text_ocr_help, text_ocr_help, horizontal_padding=4, min_wrap=120
    )
    project_checks = (
        ("OCR 后执行替换规则", "ocr_replace"),
        ("普通 OCR 文本转小写", "lowercase_ocr"),
    )
    self._add_check_group(project_page, "普通 OCR 文本处理", project_checks)

    self._build_crop_settings_tab(crop_tab)

    advanced = self._scrollable_settings_page(advanced_tab)
    self._settings_intro(
        advanced,
        "高级 / 专家参数",
        "这里保留版面语义、OCR 后端和正则规则等底层控制。"
        "如果只是想提高某本词典的识别率，请优先回到“OCR画线”页或【项目Profile】；"
        "只有左缘高度规则的简单版式才优先考虑“普通画线（备用）”。",
    )
    ttk.Button(
        advanced, text="打开项目Profile（推荐）…", command=parent.open_project_profile
    ).pack(anchor="w", pady=(0, 10))
    self._add_setting_group(advanced, "版面与后端", self.EXPERT_FIELDS)

    def _wheel(event) -> str | None:
        selected = notebook.select()
        target = self._settings_canvases.get(str(selected))
        if target is None:
            return None
        if getattr(event, "num", None) == 4:
            target.yview_scroll(-3, "units")
        elif getattr(event, "num", None) == 5:
            target.yview_scroll(3, "units")
        else:
            delta = getattr(event, "delta", 0)
            if delta:
                target.yview_scroll(
                    (-1 if delta > 0 else 1)
                    * max(1, abs(int(delta / 120))) * 3,
                    "units",
                )
        return "break"

    self.bind("<MouseWheel>", _wheel)
    self.bind("<Button-4>", _wheel)
    self.bind("<Button-5>", _wheel)

    # Language-aware collation tab.
    sort_frame = self._scrollable_settings_page(sort_tab)
    sort_frame.columnconfigure(1, weight=1)
    self.sort_language_var = tk.StringVar(value="")
    ttk.Label(sort_frame, text="OCR 语言：").grid(row=0, column=0, sticky="e", pady=4)
    ttk.Label(sort_frame, textvariable=self.sort_language_var).grid(row=0, column=1, sticky="w", pady=4)
    ttk.Label(sort_frame, text="排序预设：").grid(row=1, column=0, sticky="e", pady=4)
    self.sort_mode_var = tk.StringVar(value="")
    self.vars["headword_sort_mode"] = self.sort_mode_var
    self.sort_combo = ttk.Combobox(sort_frame, textvariable=self.sort_mode_var, state="readonly", width=48)
    self.sort_combo.grid(row=1, column=1, sticky="ew", pady=4)
    self.sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._toggle_custom_sort_state())
    self._bind_help_widget(
        self.sort_combo,
        lambda: self._show_setting_help("headword_sort_mode"),
    )

    ttk.Label(sort_frame, text="自定义排序单元：").grid(row=2, column=0, sticky="ne", pady=(10, 4))
    custom_box = ttk.Frame(sort_frame)
    custom_box.grid(row=2, column=1, sticky="ew", pady=(10, 4))
    custom_box.columnconfigure(0, weight=1)
    self.custom_order_var = tk.StringVar(value=getattr(parent.settings, "headword_custom_order", LATIN_ORDER))
    self.vars["headword_custom_order"] = self.custom_order_var
    self.custom_order_entry = ttk.Entry(custom_box, textvariable=self.custom_order_var)
    self.custom_order_entry.grid(row=0, column=0, sticky="ew")
    self._bind_help_widget(
        self.custom_order_entry,
        lambda: self._show_setting_help("headword_custom_order"),
    )
    ttk.Label(custom_box, text="空格分隔；允许多字符单元，如 ch / ll / dz").grid(row=1, column=0, sticky="w", pady=(3, 0))
    self.custom_fold_var = tk.BooleanVar(value=bool(getattr(parent.settings, "headword_custom_fold_accents", True)))
    self.vars["headword_custom_fold_accents"] = self.custom_fold_var
    self.custom_fold_check = ttk.Checkbutton(sort_frame, text="自定义规则中，未单列的重音字母按基础字母排序", variable=self.custom_fold_var)
    self.custom_fold_check.grid(row=3, column=1, sticky="w", pady=4)
    self._bind_help_widget(
        self.custom_fold_check,
        lambda: self._show_setting_help("headword_custom_fold_accents"),
    )
    help_text = (
        "排序只控制词头的比较/索引顺序，不会重排扫描图片，也不会改 PDIC 坐标。\n"
        "预设会随 OCR 语言变化；语言专用预设用于符合对应词典的字母序，始终还可选择通用 Unicode 或自定义。\n"
        "自定义顺序用空格分隔排序单元，可写 ch / ll / dz 等多字符单位；例如旧式西班牙语："
        "a b c ch d e f g h i j k l ll m n ñ o p q r s t u v w x y z。\n"
        "如果重音字母有独立排序地位，应显式列入自定义顺序；否则可用“按基础字母排序”折叠。"
    )
    sort_help = ttk.Label(sort_frame, text=help_text, justify="left")
    sort_help.grid(
        row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0)
    )
    self._bind_responsive_labels(
        sort_frame, sort_help, horizontal_padding=24, min_wrap=180
    )
    self._refresh_sort_choices(initial=True)

    # User-editable OCR headword filter rules.
    rules_tab.columnconfigure(0, weight=1)
    rules_tab.rowconfigure(1, weight=1)
    rules_help = (
        "这是项目级候选覆盖层：用于处理某一本词典反复出现、但不值得改全局 parser/Profile 的例外。每行一条；# 开头为注释。\n"
        "拒绝规则优先于强制接受：reject_lemma_exact / reject_lemma_regex 针对 lemma；"
        "reject_line_contains / reject_line_regex 针对整行。accept_* 可救回已成功解析且位于合法栏左区域的候选，"
        "但不能把任意页眉/噪声变成词头。pos_exclude_exact / pos_exclude_regex 用于排除容易被误当 POS 的固定标签。\n"
        "修改过滤规则通常只需要重新跑候选解析，不必强制重做 PaddleOCR；若问题属于整类词典结构，应优先写入 Project Profile。"
    )
    rules_help_label = ttk.Label(
        rules_tab, text=rules_help, justify="left", padding=(12, 10, 12, 6)
    )
    rules_help_label.grid(row=0, column=0, sticky="ew")
    self._bind_responsive_labels(
        rules_tab, rules_help_label, horizontal_padding=24, min_wrap=180
    )
    rules_editor_frame = ttk.Frame(rules_tab, padding=(12, 0, 12, 6))
    rules_editor_frame.grid(row=1, column=0, sticky="nsew")
    rules_editor_frame.columnconfigure(0, weight=1); rules_editor_frame.rowconfigure(0, weight=1)
    self.rules_text = tk.Text(rules_editor_frame, wrap="none", undo=True, font=(preferred_font_family(self, ("Consolas", "Menlo", "DejaVu Sans Mono"), fallback_named_font="TkFixedFont"), 10), padx=8, pady=8, height=18)
    rules_ybar = ttk.Scrollbar(rules_editor_frame, orient="vertical", command=self.rules_text.yview)
    rules_xbar = ttk.Scrollbar(rules_editor_frame, orient="horizontal", command=self.rules_text.xview)
    self.rules_text.configure(yscrollcommand=rules_ybar.set, xscrollcommand=rules_xbar.set)
    self.rules_text.grid(row=0, column=0, sticky="nsew"); rules_ybar.grid(row=0, column=1, sticky="ns"); rules_xbar.grid(row=1, column=0, sticky="ew")
    rules_buttons = ttk.Frame(rules_tab, padding=(12, 0, 12, 10))
    rules_buttons.grid(row=2, column=0, sticky="ew")
    ttk.Button(rules_buttons, text="恢复默认规则", command=self.restore_default_rules).pack(side="left")
    ttk.Button(rules_buttons, text="导入规则…", command=self.import_rules).pack(side="left", padx=(8, 0))
    ttk.Button(rules_buttons, text="导出规则…", command=self.export_rules).pack(side="left", padx=(8, 0))
    self.rules_status_var = tk.StringVar(value="")
    ttk.Label(rules_buttons, textvariable=self.rules_status_var).pack(side="right")
    self.load_rules_editor()

    ttk.Separator(outer, orient="horizontal").pack(fill="x")
    footer = ttk.Frame(outer, padding=(0, 10, 0, 0))
    footer.pack(fill="x")
    ttk.Label(
        footer,
        textvariable=self._settings_save_status_var,
        foreground="#666666",
    ).pack(side="left")
    ttk.Button(
        footer, text="关闭", command=self._close_validated
    ).pack(side="right")
    ttk.Button(
        footer, text="校验当前设置",
        command=lambda: self._validate_settings_now(),
    ).pack(side="right", padx=(0, 8))
    _project_templates.add_default_button(footer, self)
    self.bind("<Control-s>", lambda _event: self._validate_settings_now())
    self.bind("<Escape>", lambda _event: self._close_validated())
    self.protocol("WM_DELETE_WINDOW", self._close_validated)
    self._autosave_job: str | None = None
    self._autosave_ready = True
    for _name, _var in self.vars.items():
        try:
            _var.trace_add("write", lambda *_args: self._schedule_autosave())
        except Exception:
            pass
    for _name, _var in self.crop_vars.items():
        try:
            _var.trace_add("write", lambda *_args: self._schedule_autosave())
        except Exception:
            pass
    # Keep the dialog modeless.
    # Do not use transient()/grab_set(), which would keep this window in
    # front and block interaction with the main workspace.
