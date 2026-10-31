"""Physical main workspace Tk widget construction and bindings.

The PictureCaptureApp._build_ui import path and callback signature remain
stable; its live Tk and ttk globals are passed through at invocation.
"""
from __future__ import annotations
from typing import Any


def build_ui(self, *, deps: dict[str, Any]) -> None:
    ttk = deps["ttk"]
    tk = deps["tk"]
    PageListGrid = deps["PageListGrid"]
    PageThumbnailController = deps["PageThumbnailController"]
    bind_context_menu = deps["bind_context_menu"]
    # Keep the legacy information bar permanently visible.  Pack it before
    # the expanding body so Windows DPI/window-size changes cannot push it
    # below the visible client area.  General messages and mouse coordinates
    # use separate variables so moving the mouse no longer overwrites an
    # operation result/error message.
    self.bottom_stack = ttk.Frame(self, style="PC.Status.TFrame")
    self.bottom_stack.pack(side="bottom", fill="x")

    # Batch task bar is normally hidden. It appears above the permanent
    # status bar while a multi-page operation is running.
    self.status_bar = ttk.Frame(self.bottom_stack, style="PC.Status.TFrame")
    self.status_bar.pack(side="bottom", fill="x")
    status_bar = self.status_bar
    ttk.Separator(status_bar, orient="horizontal").pack(side="top", fill="x")
    self.batch_bar = ttk.Frame(status_bar, padding=(4, 1), style="PC.Status.TFrame")
    self.batch_text_var = tk.StringVar(value="")
    self.batch_progress_var = tk.DoubleVar(value=0.0)
    ttk.Label(
        self.batch_bar, textvariable=self.batch_text_var, anchor="w", style="PC.Batch.TLabel"
    ).pack(side="left", padx=(0, 8))
    self.batch_progress = ttk.Progressbar(
        self.batch_bar, variable=self.batch_progress_var, maximum=100.0, length=160, mode="determinate"
    )
    self.batch_progress.pack(side="left", fill="x", expand=True, padx=(0, 8))
    self.batch_pause_button = ttk.Button(
        self.batch_bar, text="暂停", width=8, command=self._toggle_batch_pause,
        style="PC.Compact.TButton",
    )
    self.batch_pause_button.pack(side="left", padx=(0, 5))
    self._attach_tooltip(
        self.batch_pause_button,
        "暂停或继续当前批量任务；已完成页面不会回滚。",
    )
    self.batch_stop_button = ttk.Button(
        self.batch_bar, text="停止", width=8, command=self._request_batch_stop,
        style="PC.Compact.TButton",
    )
    self.batch_stop_button.pack(side="left")
    self._attach_tooltip(
        self.batch_stop_button,
        "请求停止当前批量任务；正在处理的页面完成后安全停止。",
    )

    ttk.Label(
        status_bar,
        textvariable=self.status_var,
        anchor="w",
        padding=(8, 4),
        style="PC.Status.TLabel",
    ).pack(side="left", fill="x", expand=True)
    ttk.Label(
        status_bar, textvariable=self.image_metadata_status_var,
        anchor="e", padding=(8, 4), style="PC.Status.TLabel",
    ).pack(side="right")
    ttk.Label(
        status_bar,
        textvariable=self.cursor_status_var,
        anchor="e",
        padding=(8, 4),
        style="PC.Status.TLabel",
    ).pack(side="right")
    ttk.Separator(status_bar, orient="vertical").pack(side="right", fill="y", padx=2)

    # v2.3 intentionally has no menu bar or separate top toolbar.
    body = ttk.Panedwindow(self, orient="horizontal")
    self.main_paned = body
    body.pack(fill="both", expand=True)
    sidebar_host = ttk.Frame(body, style="PC.Sidebar.TFrame")
    self.sidebar_canvas = tk.Canvas(
        sidebar_host,
        highlightthickness=0,
        borderwidth=0,
        bg=self._main_ui_colors["sidebar"],
    )
    # This outer scrollbar duplicated the functional page-list scrollbar
    # and appeared inert beside the normal-mode list. Keep a reference for
    # compatibility but do not display it. The Treeview owns scrolling.
    self.sidebar_scrollbar = ttk.Scrollbar(
        sidebar_host, orient="vertical", command=self.sidebar_canvas.yview
    )
    self.sidebar_canvas.pack(side="left", fill="both", expand=True)
    sidebar = ttk.Frame(
        self.sidebar_canvas, padding=(7, 0, 6, 5), style="PC.Sidebar.TFrame"
    )
    self._sidebar_window = self.sidebar_canvas.create_window((0, 0), window=sidebar, anchor="nw")
    sidebar.bind("<Configure>", self._resize_sidebar_content)
    self.sidebar_canvas.bind("<Configure>", self._resize_sidebar_content)
    self.bind_all("<MouseWheel>", self._sidebar_mousewheel, add="+")
    self.bind_all("<Button-4>", lambda event: self._sidebar_linux_mousewheel(event, -1), add="+")
    self.bind_all("<Button-5>", lambda event: self._sidebar_linux_mousewheel(event, 1), add="+")
    self.sidebar = sidebar
    viewer = ttk.Frame(body)
    body.add(sidebar_host, weight=0)
    body.add(viewer, weight=1)
    sidebar.columnconfigure(0, weight=1)
    sidebar.rowconfigure(1, weight=1)

    from .workspace_tools import install_workspace_tools
    install_workspace_tools(self, sidebar, sidebar_host)

    page_panel = ttk.Frame(sidebar, padding=(2, 0, 2, 0), style="PC.Sidebar.TFrame")
    self.page_panel = page_panel
    page_panel.grid(row=0, column=0, rowspan=2, sticky="nsew")
    page_panel.columnconfigure(0, weight=1)
    page_panel.rowconfigure(2, weight=1)

    self.page_range_var = tk.StringVar(value="current")
    self.page_range_spec_var = tk.StringVar()
    self.view_zoom_var = tk.StringVar(value="100%")

    nav_area = ttk.Frame(page_panel, style="PC.SectionBody.TFrame")
    nav_area.grid(row=0, column=0, sticky="ew", pady=(0, 5))
    range_row = ttk.Frame(nav_area)
    self.page_range_controls_row = range_row
    range_row.pack(fill="x", pady=(0, 3))
    for label, mode in (("当前", "current"), ("至末页", "to_end"),
                        ("至指定", "to_specified"), ("书签", "bookmarks")):
        ttk.Radiobutton(range_row, text=label, variable=self.page_range_var,
                        value=mode).pack(side="left", padx=(0, 1))
    spec_row = ttk.Frame(nav_area)
    spec_row.pack(fill="x", pady=(0, 4))
    ttk.Radiobutton(spec_row, text="", variable=self.page_range_var,
                    value="specified").pack(side="left")
    page_range_entry = ttk.Entry(spec_row, textvariable=self.page_range_spec_var, width=12)
    page_range_entry.pack(side="left", fill="x", expand=True, padx=(3, 4))
    page_range_entry.bind("<Return>", lambda _event: self.jump_to_page_spec())
    jump_button = ttk.Button(spec_row, text="跳", width=2,
                             command=self.jump_to_page_spec, style="PC.PageNav.TButton")
    jump_button.pack(side="left")
    self._attach_tooltip(jump_button, "跳转到指定页面的第一个有效页面；ENTER为快捷键")

    nav_row = ttk.Frame(nav_area)
    nav_row.pack(fill="x")
    for symbol, command, tip in (
        ("⨇", lambda: self.jump_to_bookmark(-1), "跳转到上一书签"),
        ("⨈", lambda: self.jump_to_bookmark(1), "跳转到下一书签"),
        ("上页", lambda: self.change_page(-1), "切换到上页（Shift + 鼠标右键）"),
        ("下页", lambda: self.change_page(1), "切换到下页（鼠标右键）"),
    ):
        button = ttk.Button(nav_row, text=symbol, width=4 if len(symbol) == 1 else 5,
                            command=command, style="PC.PageNav.TButton")
        button.pack(side="left", padx=(0, 4))
        self._attach_tooltip(button, tip)
    # First-column previews are controlled directly below the 下页 row,
    # not by Settings Center.  The original table remains authoritative.
    thumbnail_controls_host = ttk.Frame(nav_area, style="PC.Sidebar.TFrame")
    thumbnail_controls_host.pack(fill="x")
    list_frame = ttk.Frame(page_panel)
    list_frame.grid(row=2, column=0, sticky="nsew")
    list_frame.columnconfigure(0, weight=1); list_frame.rowconfigure(0, weight=1)
    columns = ("bookmark", "page", "section", "lined", "fill_status", "illustrations")
    self.page_list = ttk.Treeview(
        list_frame,
        columns=columns,
        show="headings",
        selectmode="browse",
        height=12,
        style="PC.Treeview",
    )
    self._page_list_heading_labels = {
        "bookmark": "●", "page": "页面", "section": "域",
        "lined": "线", "fill_status": "填充状态", "illustrations": "图",
    }
    self.page_list.heading("bookmark", text="●", anchor="center")
    self.page_list.heading("page", text="页面", anchor="center")
    self.page_list.heading("section", text="域", anchor="center")
    self.page_list.heading("lined", text="线", anchor="center")
    self.page_list.heading("fill_status", text="填充状态", anchor="center")
    self.page_list.heading("illustrations", text="图", anchor="center")
    self.page_list.heading("bookmark", command=lambda: self._sort_page_list("bookmark"))
    self.page_list.heading("page", command=lambda: self._sort_page_list("page"))
    self.page_list.heading("section", command=lambda: self._sort_page_list("section"))
    self.page_list.heading("lined", command=lambda: self._sort_page_list("lined"))
    self.page_list.heading("fill_status", command=lambda: self._sort_page_list("fill_status"))
    self.page_list.heading("illustrations", command=lambda: self._sort_page_list("illustrations"))
    self.page_list.column("bookmark", width=44, anchor="center", stretch=False)
    self.page_list.column("page", width=180, anchor="center", stretch=False)
    self.page_list.column("section", width=64, anchor="center", stretch=False)
    self.page_list.column("lined", width=68, anchor="center", stretch=False)
    self.page_list.column("fill_status", width=110, anchor="center", stretch=False)
    self.page_list.column("illustrations", width=58, anchor="center", stretch=False)
    self.page_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self._page_list_scroll)
    page_hscroll = ttk.Scrollbar(list_frame, orient="horizontal", command=self._page_list_hscroll)
    self.page_list.configure(yscrollcommand=self._page_list_yscroll,
                             xscrollcommand=page_hscroll.set)
    self.page_list.grid(row=0, column=0, sticky="nsew")
    self._page_index_grid = PageListGrid(self.page_list)
    page_hscroll.grid(row=1, column=0, sticky="ew")
    self.page_scroll.grid(row=0, column=1, sticky="ns")
    self.page_list.bind("<<TreeviewSelect>>", self.on_page_select)
    self.page_list.bind("<Button-1>", self._page_list_bookmark_click, add="+")
    self.page_list.bind("<Double-1>", self._page_list_section_double_click, add="+")
    self.page_list.bind("<MouseWheel>", self._list_mousewheel)
    bind_context_menu(self.page_list, self._page_list_right_click)
    self.page_list.bind("<Configure>", self._page_list_configured)
    self.page_list.bind("<Motion>", self._page_list_section_heading_motion, add="+")
    self.page_list.bind("<Leave>", self._hide_page_list_section_heading_hint, add="+")
    self._page_column_vars = {
        "lined": tk.BooleanVar(value=bool(getattr(self.settings, "page_list_show_lined", True))),
        "fill_status": tk.BooleanVar(value=bool(getattr(self.settings, "page_list_show_fill_status", False))),
        "illustrations": tk.BooleanVar(value=bool(getattr(self.settings, "page_list_show_illustrations", True))),
    }
    self._apply_page_list_display_columns(save=False)
    self._page_thumbnails = PageThumbnailController(
        self, self.page_list, thumbnail_controls_host,
    )

    self.canvas = tk.Canvas(
        viewer, bg=self._main_ui_colors["canvas"], highlightthickness=0
    )
    hbar = ttk.Scrollbar(viewer, orient="horizontal", command=self.canvas.xview)
    vbar = ttk.Scrollbar(viewer, orient="vertical", command=self.canvas.yview)
    self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
    # The ≣ launcher now lives beside 普/O/校 in the workspace rail.
    # Keep the actual zoom tools on the image canvas as an on-demand
    # overlay, rather than showing a second permanent/hover-only icon.
    size_row = ttk.Frame(self.canvas, padding=(3, 2), style="PC.Sidebar.TFrame")
    self.page_size_row = size_row
    zoom_tools = ttk.Frame(size_row, style="PC.Sidebar.TFrame")
    self.page_zoom_tools = zoom_tools
    zoom_tools.pack(side="left")
    for symbol, command, tip in (
        ("−", lambda: self.zoom(0.87), "缩小显示"),
        ("+", lambda: self.zoom(1.15), "放大显示"),
        ("⇔", self.fit_page_width, "占满宽度"),
        ("◧", self.fit_single_column_width, "单栏占满宽度"),
        ("⇕", self.fit_page_height, "占满高度"),
    ):
        if symbol == "+":
            view_zoom_entry = ttk.Entry(
                zoom_tools, textvariable=self.view_zoom_var, width=6,
                justify="center", style="PC.Compact.TEntry",
            )
            view_zoom_entry.pack(side="left", padx=2)
            view_zoom_entry.bind("<Return>", self.apply_view_zoom_text)
            view_zoom_entry.bind("<FocusOut>", self.apply_view_zoom_text)
        button = ttk.Button(
            zoom_tools, text=symbol, width=3, command=command,
            style="PC.Tool.TButton",
        )
        button.pack(side="left", padx=(0, 3))
        self._attach_tooltip(button, tip)

    self.canvas.grid(row=0, column=0, sticky="nsew")
    vbar.grid(row=0, column=1, sticky="ns"); hbar.grid(row=1, column=0, sticky="ew")
    viewer.rowconfigure(0, weight=1); viewer.columnconfigure(0, weight=1)
    self.canvas.bind("<Button-1>", self.canvas_left_click)
    # Explicit modifier binding keeps the new auxiliary gesture discoverable;
    # section and PPP editing retain their existing Shift-click behavior.
    self.canvas.bind("<Shift-Button-1>", self.canvas_left_click)
    self.canvas.bind("<Control-z>", lambda e: self.ref_box_controller.undo(e) if self.ref_box_controller.editing else self._auxiliary_controller.undo(e))
    self.canvas.bind("<Control-y>", lambda e: self.ref_box_controller.redo(e) if self.ref_box_controller.editing else None)
    self.canvas.bind("<F2>", lambda e: self.ref_box_controller.edit_properties() if self.ref_box_controller.editing else None)
    self.canvas.bind("<Escape>", self.ref_box_controller.cancel_capture)
    self.canvas.bind("<Double-Button-1>", self.canvas_left_double_click)
    self.canvas.bind("<B1-Motion>", self.canvas_left_drag)
    self.canvas.bind("<ButtonRelease-1>", self.canvas_left_release)
    bind_context_menu(self.canvas, self.canvas_right_click)
    self.canvas.bind("<Shift-Button-3>", lambda event: self._canvas_shift_right_click(event))
    self.canvas.bind("<Motion>", self.canvas_motion)
    self.canvas.bind("<Leave>", self.canvas_leave)
    self.canvas.bind("<MouseWheel>", self.canvas_mousewheel)
    self.canvas.bind("<Shift-MouseWheel>", self.canvas_shift_mousewheel)
    self.canvas.bind("<Control-MouseWheel>", self.canvas_ctrl_mousewheel)
    self.canvas.bind("<Button-4>", lambda e: self.canvas_linux_mousewheel(e, -1))
    self.canvas.bind("<Button-5>", lambda e: self.canvas_linux_mousewheel(e, 1))

    # Apply persisted collapse states only after all section children exist.
    self._apply_initial_section_states()
