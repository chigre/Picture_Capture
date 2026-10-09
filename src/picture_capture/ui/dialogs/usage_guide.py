from __future__ import annotations

import tkinter as tk
from tkinter import font, ttk

from ...appearance import usage_guide_palette
from ...ui_compat import screen_work_area
from ..text_wrap import _label_measure, _normalize_ui_paragraphs, _wrap_mixed_ui_text


class UsageGuideWindow(tk.Toplevel):
    """Modern, task-oriented in-app guide for the main Picture Capture workflow."""

    PAGES = (
        (
            "quick",
            "快速开始",
            "第一次使用时，按这条路径走最稳妥：先确定结构，再做代表页验证，最后批量处理。",
            (
                (
                    "01", "从【项目中心】建立项目并完成【项目Profile】",
                    "在主界面【项目中心】中新建或打开词典目录。新项目会自动进入【项目Profile】，依次确认词典信息、"
                    "阅读方式、页面模板、词头结构和代表页测试；若目录内有多种扫描图片格式，创建时只选择一次本项目使用的后缀。"
                ),
                (
                    "02", "先检测版面，再用百分比标尺核对",
                    "在【一、版面参数】选择有代表性的页面范围，运行【检测版面参数】。选择 2 页及以上时，"
                    "数值参数采用稳健中位数，分栏数按多数页面确定。主界面显示正文栏数、正文起始Y、首栏X、单栏宽和栏间空；四个几何参数同时提供 % 与 px，双向联动；"
                    "四边百分比标尺默认开启，可直接辅助人工核对和填写。"
                ),
                (
                    "03", "默认先用 OCR画线验证代表页",
                    "先在 1–3 张典型页面运行蓝色【OCR画线(默认)】。若需要普通几何补漏，再运行【融合画线+OCR】；"
                    "【普通画线】和【仅OCR】可分别用于几何定位与已有线补文字。模型和原图没有变化时保留“使用有效缓存（推荐）”。"
                ),
                (
                    "04", "先校对误差模式，再决定是否调参",
                    "用【词条校对】检查漏检、误检、OCR 拼写和顺序。若只是少量个案，直接校对通常比继续调全局参数更安全；"
                    "只有出现稳定、重复的错误模式时，再到【设置中心】针对性调整。主界面【二～五】默认折叠，需要时点击标题展开。"
                ),
                (
                    "05", "正式切图前一定先预览",
                    "进入【设置中心 → 切图】确认上下边界、左右留白和插图关系，再在主界面选择“切图预览”检查完整 Crop Plan。"
                    "确认无误后再执行【词条切图】或【插图切图】。"
                ),
                (
                    "06", "最后生成索引、PicDic 或训练资料",
                    "完成校对和切图后，再使用【导出PicDic索引】、【PicDic制作】或【导出训练标记包】。"
                    "需要阶段性留档时可用【备份PDIC】。"
                ),
            ),
        ),
        (
            "profile",
            "项目Profile",
            "项目Profile 是新项目的配置入口：先描述词典与页面结构，再用代表页验证，而不是先从高级阈值开始调。",
            (
                (
                    "01", "四步完成基础配置",
                    "依次完成【1 词典与阅读 / 2 页面模板 / 3 词头结构 / 4 测试确认】。"
                    "词典名称、语言和正文页码范围属于项目资料；阅读方向、页面模板和词头结构会直接影响后续版面与 OCR 解释。"
                ),
                (
                    "02", "页面模板先解决整页结构",
                    "页眉、页尾、固定页边内容、A/B 页交替和栏数应先在页面模板中确定。右侧始终显示当前代表页，"
                    "栏左线可逐像素微调；如果整页都偏，不要先去改 OCR 候选阈值。"
                ),
                (
                    "03", "词头结构按“词头前—本体—词头后”描述",
                    "可分别描述普通左缘词、编号前缀、固定符号、括号词、大字单字以及 POS/词形/变体/发音等词后证据。"
                    "特殊词典可配置固定符号集，并从真实扫描页采集视觉标记样本。"
                ),
                (
                    "04", "代表页测试通过后再确认",
                    "在【4 测试确认】用多张代表页检查漏检、误检和结构覆盖；修改 Profile 后应重新测试。"
                    "确认并使用后，设置保存为当前项目的 Profile，不会改写内置预设。"
                ),
            ),
        ),
        (
            "layout",
            "版面与Section",
            "版面参数解决整页几何；Section 解决同一页内一个或多个独立阅读区域。两者都应先于批量 OCR 和切图确认。",
            (
                (
                    "01", "多页检测使用稳健汇总",
                    "【检测版面参数】读取主界面页面范围：单页直接采用检测值，2 页及以上时数值参数取稳健中位数，"
                    "分栏数按多数页面确定。检测后仍应在代表页上目视确认。"
                ),
                (
                    "02", "百分比只是界面读数",
                    "主界面的正文起始Y、首栏X、单栏宽和栏间空以百分比显示，后台仍使用原图像素。"
                    "四边百分比标尺默认开启，只辅助人工读数和填写，不参与 OCR、画线、Section 或切图计算。"
                ),
                (
                    "03", "特殊页面用 Section",
                    "双击页面列表的 Section 单元格可设置 0–10：0 表示普通页；1 可作为单个特殊页面的上下有效范围；"
                    "2–10 表示多个独立阅读区。设置后拖动蓝色虚线上下边界，再次双击同一单元格结束编辑。"
                ),
                (
                    "04", "Section 会统一影响阅读区域",
                    "Section 边界会共同约束手工新增词条、OCR、阅读顺序和整词条切图；Section 之间的空白不参与这些流程。"
                    "Section=0 时，切图继续使用【设置中心 → 切图】中的一般页边界。"
                ),
            ),
        ),
        (
            "drawing",
            "画线与 OCR",
            "OCR画线是默认方式；普通画线、仅OCR和融合画线+OCR分别用于几何定位、已有线补文字和双路径互补。",
            (
                (
                    "A", "融合画线：默认推荐",
                    "优先运行【融合画线】。普通模式与 OCR 模式各自完成检测和精修后，程序按同栏 Y 位置一对一融合，"
                    "匹配项继承 OCR 文字且只保留一条横线，双方未匹配项继续承担救漏；融合结束后，对仍无文字的普通救漏线"
                    "自动执行【普通画线后OCR文字】同款局部 PaddleOCR：普通行与大字行使用不同高度框，但绝不改变画线数量或坐标。"
                    "共享 OCR 通道默认只启用 PaddleOCR；Tesseract 与 Google Lens 可同时启用；【仅OCR】与【OCR画线】共用这些选择。"
                ),
                (
                    "B", "有效缓存：OCR 不必每次重跑",
                    "保持“使用有效缓存（推荐）”即可。缓存会在真正影响原始 OCR 的设置、模型或图像变化时自动失效；"
                    "仅调整候选判定参数时通常无需强制重新识别。"
                ),
                (
                    "C", "普通画线也可独立补 OCR 文字",
                    "普通画线只依赖栏位置、墨迹和行高；定位确认后可直接运行【普通画线后OCR文字】。"
                    "该步骤把现有画线当作唯一几何真值，只做局部 PaddleOCR 补字；普通行和大字行使用不同高度框，"
                    "不会新增、删除或移动画线，默认只填写空白词条。"
                ),
                (
                    "D", "页面范围会影响批量任务",
                    "页面列表上方可选“当前页 / 当前页至末页 / 指定范围”。检测版面、画线、插图识别和切图等批量操作"
                    "都会读取这里的范围；指定范围可使用类似 12~18,23,31 的写法。"
                ),
                (
                    "E", "主画布是最后的人工控制层",
                    "左键可手动增加词条线；Delete 或反引号键可删除当前词条。普通模式下右键进入下一页。"
                    "鼠标滚轮纵向滚动，Shift + 滚轮横向滚动，Ctrl + 滚轮缩放。四边标尺仅用于读数，不参与 OCR、画线或切图。"
                ),
                (
                    "F", "不要把高级参数当作第一步",
                    "候选置信度、最低候选分、同行合并等参数已经移到【设置中心 → OCR画线 → 高级设置】。"
                    "先通过代表页判断具体错误类型，再调整对应参数，避免为解决一个个案破坏整本词典的稳定性。"
                ),
            ),
        ),
        (
            "review",
            "校对与词表",
            "校对窗口的目标不是重新做 OCR，而是把“图像—候选—词条—简体—参考词表”集中到一个连续工作流里。",
            (
                (
                    "01", "进入【词条校对】后逐条处理",
                    "左侧查看对应切图，右侧直接编辑词条。PaddleOCR / Tesseract / Lens 的可用候选会集中显示，"
                    "需要时单击候选即可填入；主界面 OCR 辅助显示会默认收起，减少重复信息。"
                ),
                (
                    "02", "参考词表用于定位，不代替人工判断",
                    "加载 wordslist 后，右侧只显示当前词附近的窗口。自动定位会根据同源连续顺序或外部索引排序选择策略；"
                    "如果词条确实缺失或词表不同源，不应为了“对齐词表”而强行改写扫描页内容。"
                ),
                (
                    "03", "繁简与网络核验是辅助证据",
                    "【简体化词条】使用 OpenCC 生成初始结果，人工修改后会独立保存；【重新简体化】可按当前页重新生成。CC-CEDICT、萌典、维基词典和网络搜索用于快速核验，"
                    "其中“未检出”只表示当前来源没有精确命中，不等于词条不存在。"
                ),
                (
                    "04", "删除和保存保持联动",
                    "校对行左侧【X】和反引号快捷键都会删除当前词条，并同步清理对应简化记录。"
                    "自动保存、翻页、关闭校对窗口都会保存当前修改，避免只改了显示但没有落盘。"
                ),
                (
                    "05", "完成一段后再做顺序检查",
                    "词头顺序核对会根据 OCR 语言选择相应排序预设，也支持 Unicode 和自定义多字符排序单元。"
                    "顺序异常更适合用于发现跳词、误识别或重复词，而不是自动删除候选。"
                ),
                (
                    "06", "重点筛选用于集中处理高风险词条",
                    "【重点筛选校对】可按 OCR 不匹配、指定字符等条件快速聚合需要复核的词条；筛选范围直接复用主界面【指定】范围。"
                    "【与OCR比较】决定当前不匹配来源；需要时可直接填充所选 OCR 结果。"
                ),
            ),
        ),
        (
            "illustration",
            "插图与切图",
            "插图、词条和 Crop Plan 使用同一套页面坐标关系；先确认关联，再切图。",
            (
                (
                    "01", "插图识别先生成 PPP，再人工修正",
                    "【插图识别】按当前页面范围检测插图并写入 PPP。自动区域使用 AUTO 标签；重复识别只替换旧 AUTO 区域，"
                    "人工绘制的多边形会保留。"
                ),
                (
                    "02", "【编辑插图】负责精修关系",
                    "可新增多边形、拖动现有顶点或矩形边，并修改 PPP 名称。名称与词头一致时会被视为关联插图；"
                    "关联是否正确会直接影响后续词条切图与独立插图导出。"
                ),
                (
                    "03", "先在【设置中心 → 切图】统一边界",
                    "词条切图和插图切图共用一般页上下边界、左右留白和插图外扩。Section>0 的特殊页面由主界面 Section 边界接管；"
                    "切图边界和 OCR 的页眉/正文边界仍是两套独立参数。"
                ),
                (
                    "04", "用“切图预览”检查最终关系",
                    "关联 PPP 完整位于或部分相交于词条范围时，会按当前 Crop Plan 并入词条切图；完全位于词条外部时，"
                    "才单独生成 (P数字) 图片。预览正确后再批量切图。"
                ),
            ),
        ),
        (
            "post",
            "后期制作",
            "这里处理的是已经校对过的项目成果：切图、索引、PicDic、备份与训练数据。",
            (
                (
                    "01", "【词条切图】生成 PWW",
                    "按页面范围读取当前 PDIC、PPP 和切图设置，生成完整词条图片。批量切图可使用 CPU 多进程；"
                    "底部任务条会显示进度，并提供暂停和停止。"
                ),
                (
                    "02", "【插图切图】处理独立插图",
                    "仅对 Crop Plan 判断为独立导出的插图生成图片；与词条关联的插图会按设置并入词条，不重复导出。"
                ),
                (
                    "03", "【PicDic制作】以切图结果为准",
                    "PicDic 制作读取已经生成的完整词条切图及 manifest，并处理跨页连续词条。"
                    "如果切图尚未完成或图片缺失，应先回到切图阶段，而不是直接修改索引。"
                ),
                (
                    "04", "PDIC 备份用于阶段性回退",
                    "在大批量校对、自动填充或规则调整前可先【备份PDIC】。需要恢复时使用【恢复PDIC】，"
                    "恢复范围仍受主界面当前页面范围约束。"
                ),
                (
                    "05", "训练标记包是独立输出",
                    "【导出训练标记包】会收集页面、标记与项目上下文，用于后续模型/规则验证；它不会替代日常 PDIC/PPP 保存。"
                ),
            ),
        ),
        (
            "navigation",
            "导航与排错",
            "先分清“版面不对、OCR 环境不对、候选规则不对、还是个别词条不对”，排错会快很多。",
            (
                (
                    "⌨", "常用鼠标与快捷操作",
                    "主画布：左键加线；Delete / 反引号删除；普通模式右键下一页；滚轮纵向滚动；"
                    "Shift + 滚轮横向滚动；Ctrl + 滚轮缩放。校对窗口中反引号可删除当前行。"
                ),
                (
                    "1", "整页位置都偏：先查版面参数",
                    "如果整页的栏位置、页眉、行距或切线整体偏移，优先重新检测/检查【一、版面参数】和【项目Profile】页面模板，"
                    "不要先调候选置信度。"
                ),
                (
                    "2", "OCR 完全不可用：先检测环境",
                    "点击【环境中心】查看 PaddleOCR / PaddlePaddle、Tesseract、Google Lens、OpenCC 和 CC-CEDICT 状态。"
                    "环境问题应先修复安装或设备配置，再判断识别算法。"
                ),
                (
                    "3", "稳定漏检/误检：再查 OCR 高级设置",
                    "只有当多页重复出现同一种漏检或误检时，才值得进入【设置中心 → OCR画线 → 高级设置】调整结构门槛。"
                    "调整后只在代表页重新验证，不要直接全书重跑。"
                ),
                (
                    "4", "只有少量拼写错：直接校对",
                    "如果画线位置正确，只是个别 OCR 拼写错误，直接在【词条校对】选择候选或人工修改通常更高效，"
                    "没有必要为了几个词重新改变全局参数。"
                ),
                (
                    "5", "设置中心的保存规则",
                    "设置中心会自动保存有效输入；Ctrl+S 用于立即校验并保存，Esc 或关闭窗口也会先校验。"
                    "如果底部提示“当前输入暂未保存”，先修正无效值再关闭。"
                ),
            ),
        ),
    )

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.parent_app = parent
        self.title("Picture Capture · 帮助中心")
        screen_w = max(900, self.winfo_screenwidth())
        screen_h = max(650, self.winfo_screenheight())
        work_x, work_y, work_w, work_h = screen_work_area(self)
        width = min(work_w, 1040, int(screen_w * 0.82))
        height = min(work_h, 780, int(screen_h * 0.86))
        x = work_x + max(0, (work_w - width) // 2)
        y = work_y + max(0, (work_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(820, width), min(600, height))
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())

        self._colors = usage_guide_palette("light")
        self.configure(bg=self._colors["bg"])
        base = font.nametofont("TkDefaultFont").copy()
        self._title_font = base.copy()
        self._title_font.configure(size=max(16, abs(int(base.cget("size"))) + 7), weight="bold")
        self._page_title_font = base.copy()
        self._page_title_font.configure(size=max(14, abs(int(base.cget("size"))) + 5), weight="bold")
        self._card_title_font = base.copy()
        self._card_title_font.configure(size=max(10, abs(int(base.cget("size"))) + 1), weight="bold")
        self._meta_font = base.copy()
        self._meta_font.configure(size=max(8, abs(int(base.cget("size"))) - 1))

        self._page_map = {item[0]: item for item in self.PAGES}
        self._nav_buttons: dict[str, tk.Button] = {}
        self._wrap_labels: list[tuple[tk.Label, int]] = []
        self._current_page = "quick"
        self._build()
        self._show_page("quick")
        self._refresh_context()
        self.bind("<FocusIn>", lambda _event: self._refresh_context(), add="+")

    def refresh_appearance(self) -> None:
        """Refresh the guide palette without losing the current page/search."""
        self._colors = usage_guide_palette("light")
        self.configure(bg=self._colors["bg"])
        query = self.search_var.get().strip()
        if query:
            self._search_changed()
        else:
            self._show_page(self._current_page)
        self.parent_app._apply_current_appearance(self)

    def _build(self) -> None:
        colors = self._colors
        shell = tk.Frame(self, bg=colors["bg"])
        shell.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(shell, bg=colors["bg"])
        header.pack(fill="x", pady=(0, 14))
        tk.Label(
            header, text="帮助中心", bg=colors["bg"], fg=colors["text"],
            font=self._title_font, anchor="w",
        ).pack(anchor="w")
        header_subtitle_text = (
            "按当前版本真实工作流组织：从项目Profile、版面/Section、画线和校对，到切图、PicDic 与常见排错。"
        )
        header_subtitle = tk.Label(
            header,
            text=header_subtitle_text,
            bg=colors["bg"], fg=colors["muted"], anchor="w", justify="left",
        )
        header_subtitle.pack(anchor="w", fill="x", pady=(4, 0))
        self._context_var = tk.StringVar()
        context_label = tk.Label(
            header, textvariable=self._context_var, bg=colors["bg"], fg=colors["accent"],
            font=self._meta_font, anchor="w", justify="left",
        )
        context_label.pack(anchor="w", fill="x", pady=(7, 0))

        def resize_header(event: tk.Event) -> None:
            wrap = max(320, int(event.width) - 8)
            try:
                header_subtitle.configure(
                    text=_wrap_mixed_ui_text(
                        header_subtitle_text, _label_measure(header_subtitle), wrap
                    ),
                    wraplength=0,
                )
                context_label.configure(wraplength=wrap)
            except tk.TclError:
                pass

        header.bind("<Configure>", resize_header, add="+")

        body = tk.Frame(shell, bg=colors["bg"])
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(
            body, bg=colors["sidebar"], width=190,
            highlightthickness=1, highlightbackground=colors["border"],
        )
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        sidebar.grid_propagate(False)

        search_block = tk.Frame(sidebar, bg=colors["sidebar"])
        search_block.pack(fill="x", padx=12, pady=(13, 8))
        tk.Label(
            search_block, text="查找", bg=colors["sidebar"], fg=colors["muted"],
            font=self._meta_font, anchor="w",
        ).pack(anchor="w", pady=(0, 4))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_block, textvariable=self.search_var)
        search_entry.pack(fill="x")
        self.search_var.trace_add("write", lambda *_args: self._search_changed())

        nav = tk.Frame(sidebar, bg=colors["sidebar"])
        nav.pack(fill="x", padx=8, pady=(2, 8))
        for key, title, _subtitle, _cards in self.PAGES:
            button = tk.Button(
                nav, text=title, command=lambda k=key: self._select_page(k),
                anchor="w", relief="flat", bd=0, padx=10, pady=8,
                bg=colors["sidebar"], fg=colors["text"],
                activebackground=colors["accent_soft"], activeforeground=colors["accent"],
                highlightthickness=0, takefocus=False, cursor="hand2",
            )
            # Navigation buttons manage their palette directly because their
            # selected state changes frequently. Skipping the generic reversible
            # classic mapper avoids a light-palette flash on every page switch.
            button._pc_skip_classic_appearance = True
            button.pack(fill="x", pady=1)
            self._nav_buttons[key] = button

        tk.Frame(sidebar, bg=colors["border"], height=1).pack(fill="x", padx=12, pady=(4, 8))
        tk.Label(
            sidebar, text="遇到问题时", bg=colors["sidebar"], fg=colors["muted"],
            font=self._meta_font, anchor="w",
        ).pack(fill="x", padx=14)
        sidebar_hint_text = "先判断是版面、OCR 环境、规则，还是单个词条问题，再进入对应页面。"
        sidebar_hint = tk.Label(
            sidebar,
            text=sidebar_hint_text,
            bg=colors["sidebar"], fg=colors["muted"], justify="left", anchor="nw",
        )
        sidebar_hint.configure(
            text=_wrap_mixed_ui_text(
                sidebar_hint_text, _label_measure(sidebar_hint), 150
            ),
            wraplength=0,
        )
        sidebar_hint.pack(fill="x", padx=14, pady=(4, 12))

        content_shell = tk.Frame(
            body, bg=colors["surface"],
            highlightthickness=1, highlightbackground=colors["border"],
        )
        content_shell.grid(row=0, column=1, sticky="nsew")
        content_shell.grid_rowconfigure(0, weight=1)
        content_shell.grid_columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            content_shell, bg=colors["surface"], highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(content_shell, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._content = tk.Frame(self._canvas, bg=colors["surface"])
        self._content_window = self._canvas.create_window(
            (0, 0), window=self._content, anchor="nw",
        )
        self._content.bind(
            "<Configure>",
            lambda _event: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
            add="+",
        )
        self._canvas.bind("<Configure>", self._resize_content, add="+")
        self.bind("<MouseWheel>", self._mousewheel, add="+")
        self.bind("<Button-4>", lambda _event: self._canvas.yview_scroll(-3, "units"), add="+")
        self.bind("<Button-5>", lambda _event: self._canvas.yview_scroll(3, "units"), add="+")

        footer = tk.Frame(shell, bg=colors["bg"])
        footer.pack(fill="x", pady=(12, 0))
        tk.Label(
            footer, text="常用入口", bg=colors["bg"], fg=colors["muted"],
            font=self._meta_font,
        ).pack(side="left")

        def action_button(label: str, command) -> tk.Button:
            button = tk.Button(
                footer, text=label, command=command,
                relief="flat", bd=0, padx=10, pady=5,
                bg="#e8edf3", fg=colors["text"],
                activebackground="#dce4ec", activeforeground=colors["text"],
                cursor="hand2",
            )
            button.pack(side="left", padx=(7, 0))
            return button

        self._profile_button = action_button("项目Profile", self.parent_app.open_project_profile)
        self._layout_button = action_button("检测版面参数", self.parent_app.detect_layout_current)
        action_button("环境中心", self.parent_app.check_ocr_engines)
        action_button("设置中心", self.parent_app.open_settings)
        tk.Button(
            footer, text="关闭", command=self.destroy,
            relief="flat", bd=0, padx=12, pady=5,
            bg=colors["accent"], fg="#ffffff",
            activebackground="#416A94", activeforeground="#ffffff",
            cursor="hand2",
        ).pack(side="right")

    def _refresh_context(self) -> None:
        project = getattr(self.parent_app, "project", None)
        if project is None:
            self._context_var.set("当前：尚未打开项目 · 可先从主界面的【项目中心】新建或打开项目")
            state = "disabled"
        else:
            settings = getattr(self.parent_app, "settings", None)
            full_name = str(getattr(settings, "dictionary_full_name", "") or "").strip()
            name = full_name or getattr(project.root, "name", str(project.root))
            total = len(getattr(project, "images", []) or [])
            index = int(getattr(self.parent_app, "current_index", 0) or 0)
            page = f"{index + 1}/{total}" if total else "—"
            self._context_var.set(f"当前项目：{name} · 当前页：{page}")
            state = "normal"
        for button in (self._profile_button, self._layout_button):
            try:
                button.configure(state=state)
            except tk.TclError:
                pass

    def _select_page(self, key: str) -> None:
        self._current_page = key
        if self.search_var.get():
            self.search_var.set("")
        self._show_page(key)

    def _search_changed(self) -> None:
        query = self.search_var.get().strip().casefold()
        if not query:
            self._show_page(self._current_page)
            return
        matches: list[tuple[str, str, str]] = []
        for _key, page_title, page_subtitle, cards in self.PAGES:
            if query in page_title.casefold() or query in page_subtitle.casefold():
                matches.extend((page_title, title, body) for _badge, title, body in cards)
                continue
            for _badge, title, body in cards:
                if query in title.casefold() or query in body.casefold():
                    matches.append((page_title, title, body))
        self._render_search(query, matches)

    def _set_nav_state(self, active: str | None) -> None:
        colors = usage_guide_palette(
            getattr(self.parent_app, "appearance_mode", "light")
        )
        for key, button in self._nav_buttons.items():
            selected = key == active
            button.configure(
                bg=colors["accent_soft"] if selected else colors["sidebar"],
                fg=colors["accent"] if selected else colors["text"],
                activebackground=colors["accent_soft"],
                activeforeground=colors["accent"],
                font=(font.nametofont("TkDefaultFont").actual("family"), 9, "bold" if selected else "normal"),
            )

    def _clear_content(self) -> None:
        for child in self._content.winfo_children():
            child.destroy()
        self._wrap_labels.clear()
        self._canvas.yview_moveto(0.0)

    def _register_wrapped_label(
        self,
        label: tk.Label,
        *,
        safety: int = 10,
    ) -> None:
        """Use character-aware pixel wrapping instead of Tk's word-only wrapping."""
        raw = _normalize_ui_paragraphs(label.cget("text"))
        label._pc_wrap_source = raw
        safe = max(0, int(safety))
        self._wrap_labels.append((label, safe))
        # Bound the initial requested width so the label cannot enlarge its
        # parent before the first real layout pass.
        label.configure(
            text=_wrap_mixed_ui_text(raw, _label_measure(label), 520),
            wraplength=0,
        )

        def refresh(_event=None) -> None:
            self._refresh_one_wrapped_label(label, safe)

        label.bind("<Configure>", refresh, add="+")
        self.after_idle(refresh)

    def _refresh_one_wrapped_label(self, label: tk.Label, safety: int) -> None:
        try:
            if not label.winfo_exists():
                return
            label_width = int(label.winfo_width())
            master_width = int(label.master.winfo_width())
            content_width = int(self._content.winfo_width())
            cap = max(100, content_width - 56)
            if label_width <= 20 or label_width > cap:
                label_width = min(max(1, master_width), cap)
            if label_width <= 20:
                return
            available = max(60, label_width - max(0, int(safety)))
            raw = getattr(label, "_pc_wrap_source", label.cget("text"))
            rendered = _wrap_mixed_ui_text(raw, _label_measure(label), available)
            if label.cget("text") != rendered or int(float(label.cget("wraplength"))) != 0:
                label.configure(text=rendered, wraplength=0)
        except (tk.TclError, TypeError, ValueError):
            return

    def _refresh_wrapped_labels(self) -> None:
        for label, safety in tuple(self._wrap_labels):
            self._refresh_one_wrapped_label(label, safety)

    def _show_page(self, key: str) -> None:
        page = self._page_map.get(key)
        if page is None:
            return
        self._set_nav_state(key)
        self._clear_content()
        _page_key, title, subtitle, cards = page
        self._add_page_heading(title, subtitle)
        if key == "quick":
            self._add_callout(
                "推荐原则",
                "先用代表页证明“版面 + Profile + OCR”组合可靠，再扩大页面范围。"
                "软件的高级设置用于解决稳定重复的问题，不是首次使用时必须逐项填写的清单。",
            )
        for badge, card_title, body in cards:
            self._add_card(badge, card_title, body)
        # Apply before returning to Tk's event loop so newly built guide content
        # is never painted once with the light palette in dark mode.
        self.parent_app._apply_current_appearance(self)

    def _render_search(self, query: str, matches: list[tuple[str, str, str]]) -> None:
        self._set_nav_state(None)
        self._clear_content()
        self._add_page_heading(
            f"搜索：{self.search_var.get().strip()}",
            f"在帮助中心中找到 {len(matches)} 条匹配内容。",
        )
        if not matches:
            self._add_callout(
                "没有找到匹配内容",
                "可以尝试更短的关键词，例如“Profile”“Section”“OCR”“校对”“切图”“插图”“PicDic”或“缓存”。",
            )
            self.parent_app._apply_current_appearance(self)
            return
        for page_title, title, body in matches:
            self._add_card(page_title[:6], title, body)
        self.parent_app._apply_current_appearance(self)

    def _add_page_heading(self, title: str, subtitle: str) -> None:
        colors = self._colors
        holder = tk.Frame(self._content, bg=colors["surface"])
        holder.pack(fill="x", padx=24, pady=(22, 12))
        tk.Label(
            holder, text=title, bg=colors["surface"], fg=colors["text"],
            font=self._page_title_font, anchor="w",
        ).pack(anchor="w")
        label = tk.Label(
            holder, text=subtitle, bg=colors["surface"], fg=colors["muted"],
            anchor="w", justify="left",
        )
        label.pack(fill="x", pady=(5, 0))
        self._register_wrapped_label(label, safety=8)

    def _add_callout(self, title: str, body: str) -> None:
        colors = self._colors
        border = tk.Frame(self._content, bg="#cfddeb")
        border.pack(fill="x", padx=24, pady=(0, 12))
        card = tk.Frame(border, bg="#f1f6fb")
        card.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(
            card, text=title, bg="#f1f6fb", fg=colors["accent"],
            font=self._card_title_font, anchor="w",
        ).pack(fill="x", padx=14, pady=(11, 3))
        label = tk.Label(
            card, text=body, bg="#f1f6fb", fg=colors["text"],
            justify="left", anchor="w",
        )
        label.pack(fill="x", padx=14, pady=(0, 12))
        self._register_wrapped_label(label, safety=10)

    def _add_card(self, badge: str, title: str, body: str) -> None:
        colors = self._colors
        border = tk.Frame(self._content, bg=colors["border"])
        border.pack(fill="x", padx=24, pady=(0, 10))
        card = tk.Frame(border, bg=colors["surface"])
        card.pack(fill="both", expand=True, padx=1, pady=1)
        card.grid_columnconfigure(1, weight=1)

        badge_label = tk.Label(
            card, text=badge, bg=colors["accent_soft"], fg=colors["accent"],
            font=self._meta_font, padx=7, pady=3,
        )
        badge_label.grid(row=0, column=0, sticky="nw", padx=(14, 10), pady=(13, 0))

        tk.Label(
            card, text=title, bg=colors["surface"], fg=colors["text"],
            font=self._card_title_font, anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(13, 3))

        label = tk.Label(
            card, text=body, bg=colors["surface"], fg=colors["muted"],
            justify="left", anchor="w",
        )
        label.grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=(0, 13))
        self._register_wrapped_label(label, safety=10)

    def _resize_content(self, event: tk.Event) -> None:
        width = max(420, int(event.width) - 2)
        self._canvas.itemconfigure(self._content_window, width=width)
        # Labels are created/recreated after canvas Configure events when the
        # user changes help pages. Recalculate from each label's actual width
        # after Tk has completed that layout pass instead of reusing one global
        # wraplength for every card.
        self.after_idle(self._refresh_wrapped_labels)

    def _mousewheel(self, event: tk.Event) -> str | None:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta:
            self._canvas.yview_scroll((-1 if delta > 0 else 1) * 3, "units")
            return "break"
        return None


__all__ = ["UsageGuideWindow"]
