"""Project Profile Wizard layout and navigation without lifecycle ownership.

The legacy class forwards live Tk/ttk bindings on every call.
"""
from __future__ import annotations


def build_ui(self, *, deps) -> None:
    ttk = deps["ttk"]
    tk = deps["tk"]
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
        "1 词典与阅读",
        "2 页面模板",
        "3 词头结构",
        "4 测试确认",
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

    summary_box = ttk.LabelFrame(left_panel, text="当前项目Profile", padding=(8, 5))
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



def apply_initial_pane_split(self, *, deps) -> None:
    tk = deps["tk"]
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



def apply_left_wraps(self, *, deps) -> None:
    ttk = deps["ttk"]
    tk = deps["tk"]
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



def show_right_image_page(self, index: int, *, deps) -> None:
    tk = deps["tk"]
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




def on_wizard_tab_changed(self, _event=None, *, deps) -> None:
    tk = deps["tk"]
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

