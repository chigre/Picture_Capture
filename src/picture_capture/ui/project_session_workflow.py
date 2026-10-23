"""GUI project session lifecycle: recent-project launcher to page restoration.

Canonical methods for project-center cards, recent-project state and metadata,
startup/load project transaction, per-page load and review synchronization.
The source PictureCaptureApp retains nine callable Tk signatures, including
the native static tooltip helper, with runtime patchpoint-compatible delegation.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectSessionDeps:
    """Original app-level project, Tk and persistence helpers bound live per call."""
    Path: object
    tk: object
    ttk: object
    font: object
    messagebox: object
    Image: object
    ImageTk: object
    json: object
    ProjectController: object
    ProjectState: object
    STORAGE_DIRNAME: object
    _project_templates: object
    has_legacy_project_data: object
    is_managed_project: object
    migrate_legacy_project: object
    load_recent_projects: object
    recent_project_stub_details: object
    remove_recent_project: object
    set_recent_project_pinned: object
    touch_recent_project: object
    settings_path: object
    ocr_cache_root: object
    pdic_path: object
    ppp_read_path_for_image: object
    read_page_sections: object
    read_pdic: object
    read_ppp: object
    normalize_page_rgb: object
    normalize_appearance_mode: object
    themed_display_image: object


def open_recent_project(self, deps: ProjectSessionDeps) -> None:
    """Show recent projects as a modern, information-focused card list."""
    Path = deps.Path
    tk = deps.tk
    ttk = deps.ttk
    font = deps.font
    messagebox = deps.messagebox
    Image = deps.Image
    ImageTk = deps.ImageTk
    load_recent_projects = deps.load_recent_projects
    recent_project_stub_details = deps.recent_project_stub_details
    remove_recent_project = deps.remove_recent_project
    set_recent_project_pinned = deps.set_recent_project_pinned
    themed_display_image = deps.themed_display_image

    dialog = tk.Toplevel(self)
    dialog.title("项目中心")
    dialog.transient(self)
    self._recent_projects_dialog = dialog

    screen_w = max(900, int(dialog.winfo_screenwidth()))
    screen_h = max(650, int(dialog.winfo_screenheight()))
    width = min(screen_w - 80, max(780, int(screen_w * 0.58)))
    height = min(screen_h - 100, max(520, int(screen_h * 0.68)))
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2)
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    dialog.minsize(min(760, width), min(460, height))

    default_font = font.nametofont("TkDefaultFont").copy()
    title_font = default_font.copy()
    title_font.configure(size=max(14, abs(int(default_font.cget("size"))) + 6), weight="bold")
    card_title_font = default_font.copy()
    card_title_font.configure(size=max(11, abs(int(default_font.cget("size"))) + 2), weight="bold")
    meta_font = default_font.copy()
    meta_size = int(default_font.cget("size"))
    meta_font.configure(size=max(8, abs(meta_size) - 1) * (-1 if meta_size < 0 else 1))

    host = ttk.Frame(dialog, padding=(20, 16, 20, 18))
    host.pack(fill="both", expand=True)
    host.columnconfigure(0, weight=1)
    host.rowconfigure(3, weight=1)

    header = ttk.Frame(host)
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="最近项目", font=title_font).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        header,
        text="继续上次工作；最近打开的项目排在最前。路径失效的记录可从列表清理，不会删除项目文件。",
        foreground="#666666",
        wraplength=max(520, width - 80),
    ).grid(row=1, column=0, sticky="w", pady=(3, 0))

    tools = ttk.Frame(host)
    tools.grid(row=1, column=0, sticky="ew", pady=(14, 8))
    tools.columnconfigure(1, weight=1)
    search_var = tk.StringVar(value="")
    ttk.Label(tools, text="搜索项目").grid(row=0, column=0, sticky="w")
    search_entry = ttk.Entry(tools, textvariable=search_var)
    search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 10))
    count_var = tk.StringVar(value="")
    ttk.Label(tools, textvariable=count_var, foreground="#666666").grid(
        row=0, column=2, sticky="e"
    )

    def create_new_project() -> None:
        try:
            dialog.destroy()
        finally:
            self.open_project()

    ttk.Separator(host, orient="horizontal").grid(
        row=2, column=0, sticky="ew", pady=(0, 10)
    )

    list_host = ttk.Frame(host)
    list_host.grid(row=3, column=0, sticky="nsew")
    list_host.columnconfigure(0, weight=1)
    list_host.rowconfigure(0, weight=1)
    canvas = tk.Canvas(list_host, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(list_host, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    cards = ttk.Frame(canvas)
    cards.columnconfigure(0, weight=1)
    cards_window = canvas.create_window((0, 0), window=cards, anchor="nw")
    cards.bind(
        "<Configure>",
        lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.bind(
        "<Configure>",
        lambda event: canvas.itemconfigure(cards_window, width=event.width),
    )

    state: dict[str, object] = {
        "rows": [], "details": [], "cover_images": {}, "cover_photos": [],
    }

    def open_selected(root: Path, row: dict[str, object]) -> None:
        if not root.is_dir():
            messagebox.showerror(
                "无法打开项目", f"项目路径不存在：\n{root}", parent=dialog
            )
            return
        try:
            self._load_project(
                root,
                target_page=str(row.get("last_page") or "").strip() or None,
                target_index=row.get("last_page_index"),
            )
        except Exception as exc:
            messagebox.showerror("无法打开项目", str(exc), parent=dialog)
            return
        dialog.destroy()

    from ..project.folder_launcher import add_open_folder_button

    def copy_path(root: Path) -> None:
        dialog.clipboard_clear()
        dialog.clipboard_append(str(root))
        self.status_var.set("项目路径已复制")

    def remove_one(root: Path) -> None:
        remove_recent_project(root)
        refresh_recent_data()

    def remove_missing() -> None:
        missing = [
            Path(str(detail["path"]))
            for detail in state.get("details", [])
            if not bool(detail["exists"])
        ]
        if not missing:
            return
        if not messagebox.askyesno(
            "清理失效项目",
            f"从最近项目列表移除 {len(missing)} 个路径失效的记录？\n\n"
            "只清理列表记录，不会删除任何项目文件。",
            parent=dialog,
        ):
            return
        for root in missing:
            remove_recent_project(root)
        refresh_recent_data()

    cleanup_button = ttk.Button(
        tools, text="清理失效项", command=remove_missing, state="disabled"
    )
    cleanup_button.grid(row=0, column=3, sticky="e", padx=(10, 0))
    ttk.Button(
        tools, text="新建项目", command=create_new_project
    ).grid(row=0, column=4, sticky="e", padx=(8, 0))

    def bind_open(widget, root: Path, row: dict[str, object]) -> None:
        try:
            widget.configure(cursor="hand2")
        except tk.TclError:
            pass
        widget.bind(
            "<Button-1>",
            lambda _event, p=root, r=dict(row): open_selected(p, r),
        )

    def card_menu(button: ttk.Button, root: Path) -> None:
        pinned = any(
            str(row.get("path")) == str(root) and bool(row.get("pinned"))
            for row in state["rows"]
        )
        menu = tk.Menu(dialog, tearoff=False)
        self._apply_current_appearance(menu)
        menu.add_command(label="复制项目路径", command=lambda: copy_path(root))
        menu.add_command(
            label="取消置顶" if pinned else "置顶项目",
            command=lambda: (set_recent_project_pinned(root, not pinned), refresh_recent_data()),
        )
        menu.add_separator()
        from ..project.metadata_cache import clear_cached_details
        menu.add_command(
            label="重新扫描项目元数据",
            command=lambda p=root: (clear_cached_details(p), refresh_recent_data()),
        )
        menu.add_command(
            label="从最近项目移除（不删除文件）",
            command=lambda: remove_one(root),
        )
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())

    def rebuild(*_args) -> None:
        for child in cards.winfo_children():
            child.destroy()
        state["cover_photos"] = []

        rows = list(state.get("rows", []))
        details = list(state.get("details", []))
        covers = dict(state.get("cover_images", {}))
        query = search_var.get().strip().casefold()

        paired = []
        for row, detail in zip(rows, details):
            haystack = " ".join((
                str(detail["full_name"]),
                str(detail["abbreviation"]),
                str(detail["path"]),
                str(detail.get("last_page") or ""),
            )).casefold()
            if query and query not in haystack:
                continue
            paired.append((row, detail))

        missing_count = sum(1 for detail in details if not bool(detail["exists"]))
        count_var.set(
            f"{len(paired)} 个项目"
            + (f" · {missing_count} 个路径失效" if missing_count else "")
        )
        cleanup_button.configure(state="normal" if missing_count else "disabled")

        if not paired:
            empty = ttk.Frame(cards, padding=(18, 50))
            empty.grid(row=0, column=0, sticky="ew")
            ttk.Label(empty, text="没有匹配的项目" if query else "还没有最近项目", font=card_title_font).pack()
            ttk.Label(
                empty,
                text="换一个关键词试试。" if query else "打开或新建项目后，它会出现在这里。",
                foreground="#777777",
            ).pack(pady=(6, 0))
            return

        for row_index, (row, detail) in enumerate(paired):
            root = Path(str(detail["path"]))
            exists = bool(detail["exists"])
            card = ttk.Frame(cards, padding=(14, 11), relief="solid", borderwidth=1)
            card.grid(row=row_index, column=0, sticky="ew", padx=(2, 8), pady=(0, 9))
            card.columnconfigure(1, weight=1)

            full_name = str(detail["full_name"] or root.name)
            abbreviation = str(detail["abbreviation"] or "").strip()
            tile_text = (abbreviation or full_name or "?")[:2].upper()
            cover_source = str(detail.get("cover_source") or "none")
            tile_holder = tk.Frame(
                card, width=76, height=96,
                bg="#f4f6f8" if exists else "#f2f2f2", bd=0, relief="flat",
            )
            tile_holder.grid_propagate(False)
            tile = tk.Label(
                tile_holder, bg="#f4f6f8" if exists else "#f2f2f2",
                fg="#315a97" if exists else "#777777", font=card_title_font,
                bd=0, relief="flat", compound="center",
            )
            tile.place(x=0, y=0, relwidth=1, relheight=1)
            cover_image = covers.get(str(root))
            if isinstance(cover_image, Image.Image):
                cover_photo = ImageTk.PhotoImage(
                    themed_display_image(cover_image, self.appearance_mode)
                )
                state["cover_photos"].append(cover_photo)
                tile.configure(image=cover_photo)
            else:
                tile.configure(text=tile_text, bg="#eaf0fb" if exists else "#f2f2f2")
            tile_holder.grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, 12))

            if cover_source == "cover":
                cover_tip = "项目封面。可替换项目图片文件夹中的 _cover.jpg（也支持 PNG/JPEG/WebP；兼容旧名 _project_cover.*）；该文件不会计入正文图片。"
            elif cover_source == "first_page":
                cover_tip = "当前用项目第一张图片作为预览。可在项目图片文件夹放置 _cover.jpg（也支持 PNG/JPEG/WebP；兼容旧名 _project_cover.*）作为项目封面；该文件不会计入正文图片。"
            else:
                cover_tip = "暂无封面预览。可在项目图片文件夹放置 _cover.jpg（也支持 PNG/JPEG/WebP；兼容旧名 _project_cover.*）作为项目封面；该文件不会计入正文图片。"
            self._attach_tooltip(tile_holder, cover_tip)
            self._attach_tooltip(tile, cover_tip)

            content = ttk.Frame(card)
            content.grid(row=0, column=1, rowspan=3, sticky="nsew")
            content.columnconfigure(0, weight=1)
            title_row = ttk.Frame(content)
            title_row.grid(row=0, column=0, sticky="ew")
            name_label = ttk.Label(title_row, text=("📌 " if row.get("pinned") else "") + full_name, font=card_title_font)
            name_label.pack(side="left")
            if abbreviation:
                ttk.Label(title_row, text=f"  ·  {abbreviation}", foreground="#666666").pack(side="left")
            status = tk.Label(
                title_row, text="检查中" if detail.get("checking") else ("可用" if exists else "路径失效"), padx=8, pady=2,
                bg="#e9f6ee" if exists else "#fff0ee", fg="#247245" if exists else "#b42318",
                font=meta_font,
            )
            status.pack(side="left", padx=(10, 0))
            image_count = int(detail["image_count"])
            position_text = str(detail.get("position_text") or "—")
            last_page = str(detail.get("last_page") or "").strip()
            resume = f"{last_page} · {position_text}" if last_page and position_text != last_page else position_text
            meta_text = f"{image_count:,} 张图片    ·    上次停留：{resume}    ·    最近活动：{detail['last_edited'] or '—'}"
            meta_label = ttk.Label(content, text=meta_text, foreground="#555555")
            meta_label.grid(row=1, column=0, sticky="w", pady=(5, 0))
            path_label = ttk.Label(content, text=str(root), foreground="#888888" if exists else "#b42318", font=meta_font)
            path_label.grid(row=2, column=0, sticky="ew", pady=(5, 0))

            actions = ttk.Frame(card)
            actions.grid(row=0, column=2, rowspan=3, sticky="ne", padx=(12, 0))
            open_button = ttk.Button(
                actions, text="打开", command=lambda p=root, r=dict(row): open_selected(p, r),
                state="normal" if exists else "disabled", width=8,
            )
            open_button.pack(side="left")
            add_open_folder_button(actions, root, dialog, exists)
            more_button = ttk.Button(actions, text="⋯", width=3)
            more_button.configure(command=lambda b=more_button, p=root: card_menu(b, p))
            more_button.pack(side="left", padx=(5, 0))
            if exists:
                for widget in (card, tile_holder, tile, content, title_row, name_label, meta_label, path_label):
                    bind_open(widget, root, row)

            def update_wrap(_event=None, label=path_label, owner=content) -> None:
                try:
                    label.configure(wraplength=max(240, owner.winfo_width() - 10))
                except tk.TclError:
                    pass
            content.bind("<Configure>", update_wrap, add="+")
            self._attach_tooltip(path_label, "项目路径；单击打开项目。" if exists else "该路径当前不存在。")
        canvas.yview_moveto(0.0)
        self._apply_current_appearance(dialog)

    def refresh_recent_data() -> None:
        count_var.set("正在后台读取最近项目…")
        cleanup_button.configure(state="disabled")
        key = f"recent-projects-{id(dialog)}"
        # A previous refresh may still be decoding preview images.
        self._invalidate_ui_worker(f"{key}-previews")
        self._invalidate_ui_worker(f"{key}-details")

        def worker():
            return load_recent_projects()

        from ..project.preview_cache import load_project_center_previews

        def alive() -> bool:
            try:
                return bool(dialog.winfo_exists())
            except tk.TclError:
                return False

        def previews_done(covers) -> None:
            if not alive():
                return
            state["cover_images"] = covers
            rebuild()

        from ..project.metadata_cache import details_with_cache

        def details_done(details) -> None:
            if not alive():
                return
            state["details"] = details
            rebuild()
            self._start_ui_worker(
                f"{key}-previews",
                lambda: load_project_center_previews(details),
                previews_done,
            )

        def done(rows) -> None:
            if not alive():
                return
            state["rows"] = rows
            state["details"] = [recent_project_stub_details(row) for row in rows]
            state["cover_images"] = {}
            # First paint is independent of per-project directory scanning.
            rebuild()
            self._start_ui_worker(
                f"{key}-details",
                lambda: details_with_cache(rows),
                details_done,
                failed,
            )

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            if alive():
                count_var.set(f"读取最近项目失败：{exc}")
        self._start_ui_worker(key, worker, done, failed)

    self._recent_projects_rebuild = rebuild

    def clear_recent_refs(event=None) -> None:
        if event is not None and getattr(event, "widget", None) is not dialog:
            return
        if self.__dict__.get("_recent_projects_dialog") is dialog:
            self.__dict__.pop("_recent_projects_dialog", None)
            self.__dict__.pop("_recent_projects_rebuild", None)

    dialog.bind("<Destroy>", clear_recent_refs, add="+")
    search_var.trace_add("write", rebuild)
    search_entry.bind("<Escape>", lambda _event: search_var.set(""))
    dialog.bind(
        "<MouseWheel>",
        lambda event: canvas.yview_scroll(
            (-1 if int(getattr(event, "delta", 0) or 0) > 0 else 1) * 3,
            "units",
        ),
        add="+",
    )
    dialog.bind(
        "<Button-4>", lambda _event: canvas.yview_scroll(-3, "units"), add="+"
    )
    dialog.bind(
        "<Button-5>", lambda _event: canvas.yview_scroll(3, "units"), add="+"
    )

    refresh_recent_data()
    search_entry.focus_set()


def _attach_tooltip(
    deps: ProjectSessionDeps, widget: tk.Widget, message: str) -> None:
    """Attach a lightweight native Tk tooltip without external dependencies."""
    tk = deps.tk
    ttk = deps.ttk

    popup: list[tk.Toplevel | None] = [None]

    def show(_event=None) -> None:
        if popup[0] is not None:
            return
        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{widget.winfo_rootx() + 12}+{widget.winfo_rooty() + widget.winfo_height() + 4}")
        ttk.Label(tip, text=message, padding=(6, 3), relief="solid").pack()
        popup[0] = tip

    def hide(_event=None) -> None:
        if popup[0] is not None:
            popup[0].destroy()
            popup[0] = None

    widget.bind("<Enter>", show, add="+")
    widget.bind("<Leave>", hide, add="+")
    widget.bind("<Destroy>", hide, add="+")


def _project_controller_for_call(self, deps: ProjectSessionDeps) -> ProjectController:
    ProjectController = deps.ProjectController
    controller = self.__dict__.get("project_controller")
    if controller is None:
        controller = ProjectController(self)
        self.__dict__["project_controller"] = controller
    return controller


def _choose_new_project_image_suffix(self, deps: ProjectSessionDeps, root: Path) -> str | None:
    return self._project_controller_for_call().choose_new_project_image_suffix(root)


def open_project(self, deps: ProjectSessionDeps) -> None:
    self._project_controller_for_call().open_project()


def _load_project(
    self, deps: ProjectSessionDeps, root: Path, *, requested_suffix: str | None = None,
    target_page: str | None = None, target_index: object = None,
    target_view_scale: float | None = None,
    launch_profile_setup: bool = False,
    parameter_template_root: Path | None = None,
) -> None:
    """Prepare project files off-thread and commit the prepared state on Tk."""
    Path = deps.Path
    tk = deps.tk
    messagebox = deps.messagebox
    Image = deps.Image
    json = deps.json
    ProjectState = deps.ProjectState
    STORAGE_DIRNAME = deps.STORAGE_DIRNAME
    _project_templates = deps._project_templates
    has_legacy_project_data = deps.has_legacy_project_data
    is_managed_project = deps.is_managed_project
    migrate_legacy_project = deps.migrate_legacy_project
    touch_recent_project = deps.touch_recent_project
    settings_path = deps.settings_path
    ocr_cache_root = deps.ocr_cache_root
    pdic_path = deps.pdic_path
    ppp_read_path_for_image = deps.ppp_read_path_for_image
    read_page_sections = deps.read_page_sections
    read_pdic = deps.read_pdic
    read_ppp = deps.read_ppp
    normalize_page_rgb = deps.normalize_page_rgb
    themed_display_image = deps.themed_display_image

    if self._batch_active:
        self.status_var.set("批量任务运行中，结束或停止后再切换项目。")
        return
    if self._ui_worker_key_active("project-load"):
        self.status_var.set("已有项目正在后台打开，请完成后再选择其他项目。")
        return
    if self._ui_worker_key_active("profile-validation"):
        self.status_var.set("Project Profile 测试仍在安全结束；完成后再切换项目。")
        return
    if self._preprocess_mode_active():
        self._set_preprocess_mode(False, analyze=False)
    root = root.expanduser().resolve()
    if self.project is not None and root == Path(self.project.root).expanduser().resolve():
        self.status_var.set("当前项目已经打开；保留当前编辑状态，不执行后台重载。")
        return
    self._flush_deferred_page_save()
    for job_name in ("_page_meta_job", "_page_list_sort_job"):
        job = getattr(self, job_name, None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            setattr(self, job_name, None)
    self._page_meta_generation = int(getattr(self, "_page_meta_generation", 0)) + 1
    pending_quick_job = getattr(self, "_quick_autosave_job", None)
    if pending_quick_job is not None:
        try:
            self.after_cancel(pending_quick_job)
        except tk.TclError:
            pass
        self._quick_autosave_job = None
        if self.project is not None:
            self.apply_quick_settings(show_status=False, persist=True, silent_errors=True)
    if self.project and self.current_page and self.image is not None:
        self.save_pdic(silent=True)
        self._save_normalized_ppp()
        self.settings.to_json(settings_path(self.project.root))

    migrate = False
    if has_legacy_project_data(root) and not is_managed_project(root):
        migrate = messagebox.askyesno(
            "整理旧版项目",
            "检测到旧版 Picture Capture 项目结构。\n\n"
            f"建议把软件生成的数据集中整理到 {STORAGE_DIRNAME} 文件夹。"
            "原始扫描图片和 wordslist.txt 等用户文件不会移动。\n\n"
            "选择“是”将在后台安全整理；选择“否”则本次继续使用旧目录结构。",
            parent=self,
        )
    canvas_available = max(500, int(self.canvas.winfo_width()) - 24)
    appearance_mode = self.appearance_mode
    self.status_var.set(f"正在后台打开项目：{root}")

    def worker():
        migration_detail = ""
        if migrate:
            from .. import __version__
            report = migrate_legacy_project(root, __version__)
            migration_detail = f"已整理 {report.files_copied} 个文件到 {STORAGE_DIRNAME}"
            if report.warnings:
                migration_detail += f"；{len(report.warnings)} 项旧文件未能清理，可稍后手工检查"
        project = ProjectState.open(root)
        if launch_profile_setup:
            _project_templates.apply_parameters_to_project(project, parameter_template_root)
        if not project.images:
            raise ValueError("目录中没有 tif/tiff/png/jpg/jpeg/bmp 图片")
        suffix = PictureCaptureApp._normalize_suffix(requested_suffix) if requested_suffix else PictureCaptureApp._normalize_suffix(project.settings.image_suffix)
        matching = [page for page in project.images if page.suffix.lower() == suffix]
        if matching:
            project.images = matching
            project.settings.image_suffix = suffix
        else:
            project.settings.image_suffix = project.images[0].suffix.lower()

        selected_index = 0
        if target_page:
            for index, page in enumerate(project.images):
                if page.name == target_page or page.stem == Path(target_page).stem:
                    selected_index = index
                    break
            else:
                try:
                    numeric = int(target_index)
                    if 0 <= numeric < len(project.images):
                        selected_index = numeric
                except (TypeError, ValueError):
                    pass
        else:
            try:
                numeric = int(target_index)
                if 0 <= numeric < len(project.images):
                    selected_index = numeric
            except (TypeError, ValueError):
                pass

        page = project.images[selected_index]
        with Image.open(page) as opened:
            image = normalize_page_rgb(opened)
        entries = read_pdic(pdic_path(page))
        polygons = read_ppp(ppp_read_path_for_image(page))
        page_sections = read_page_sections(page)
        cache_path = ocr_cache_root(project.root) / f"{page.stem}.json"
        ocr_payload: dict = {}
        if cache_path.exists():
            try:
                loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    ocr_payload = loaded
            except Exception:
                ocr_payload = {}
        if target_view_scale is None:
            view_scale = min(1.0, canvas_available / max(1, image.width))
        else:
            view_scale = min(3.0, max(0.08, float(target_view_scale)))
        display_size = (
            max(1, round(image.width * view_scale)),
            max(1, round(image.height * view_scale)),
        )
        display_image = themed_display_image(
            image.resize(display_size, Image.Resampling.LANCZOS),
            appearance_mode,
        )
        payload = {
            "project_root": str(project.root), "index": selected_index, "image": image,
            "entries": entries, "polygons": polygons, "page_sections": page_sections,
            "ocr_payload": ocr_payload,
            "display_size": display_size, "display_image": display_image,
            "view_scale": view_scale, "appearance_mode": appearance_mode,
        }
        try:
            touch_recent_project(project.root)
            recent_warning = ""
        except (OSError, ValueError, TypeError) as exc:
            recent_warning = str(exc)
        return project, selected_index, payload, view_scale, migration_detail, recent_warning

    def done(result) -> None:
        project, selected_index, payload, view_scale, migration_detail, recent_warning = result
        if self.project and self.current_page and self.image is not None:
            self._flush_deferred_page_save()
            self.save_pdic(silent=True)
            self._save_normalized_ppp()
            self.settings.to_json(settings_path(self.project.root))
        self._pending_page_index = None
        self._invalidate_ui_worker("page-load")
        self.current_page = None
        self.image = None
        self.entries = []
        self.polygons = []
        self.page_sections = []
        self._section_editing = False
        self._drag_section_boundary = None
        self._pending_section_editor_index = None
        self.current_index = -1
        self.ocr_review_candidates = []
        self.candidate_check_vars = {}
        self._display_photo_cache_key = None
        self._display_geometry_cache = None
        self._display_geometry_cache_key = None
        self.project = project
        self._project_words = set(project.words)
        self.settings = project.settings
        previews = self.__dict__.get("_page_thumbnails")
        if previews is not None:
            previews.load_preferences()  # Clear previous project's preview images.
        self._preprocess_results.clear()
        self._preprocess_photo = None
        self._preprocess_photo_cache_key = None
        self.preprocess_auto_deskew_var.set(
            bool(self.settings.preprocess_auto_deskew)
        )
        self.preprocess_safety_var.set(
            str(int(self.settings.preprocess_safety_margin_px))
        )
        self.preprocess_geometry_var.set(
            {
                "deskew": "轻量：旋转+裁边",
                "perspective": "自动透视",
                "dewarp": "UVDoc展平（Paddle高级）",
                "uvdoc": "UVDoc展平（Paddle高级）",
                "auto": "自动几何（推荐）",
            }.get(
                str(
                    getattr(
                        self.settings, "preprocess_geometry_mode", "auto"
                    ) or "auto"
                ),
                "自动几何（推荐）",
            )
        )
        self.preprocess_export_canvas_var.set(
            bool(
                getattr(
                    self.settings,
                    "preprocess_export_canvas_enabled",
                    False,
                )
            )
        )
        self.preprocess_export_canvas_mode_var.set(
            {
                "batch_max": "本批最大裁剪尺寸",
                "custom": "自定义尺寸",
            }.get(
                str(
                    getattr(
                        self.settings,
                        "preprocess_export_canvas_mode",
                        "batch_max",
                    ) or "batch_max"
                ),
                "本批最大裁剪尺寸",
            )
        )
        self.preprocess_export_canvas_width_var.set(
            str(
                int(
                    getattr(
                        self.settings,
                        "preprocess_export_canvas_width",
                        0,
                    ) or 0
                )
            )
        )
        self.preprocess_export_canvas_height_var.set(
            str(
                int(
                    getattr(
                        self.settings,
                        "preprocess_export_canvas_height",
                        0,
                    ) or 0
                )
            )
        )
        self.preprocess_export_margin_top_var.set(
            str(int(getattr(self.settings, "preprocess_export_margin_top", 0) or 0))
        )
        self.preprocess_export_margin_bottom_var.set(
            str(int(getattr(self.settings, "preprocess_export_margin_bottom", 0) or 0))
        )
        self.preprocess_export_margin_left_var.set(
            str(int(getattr(self.settings, "preprocess_export_margin_left", 0) or 0))
        )
        self.preprocess_export_margin_right_var.set(
            str(int(getattr(self.settings, "preprocess_export_margin_right", 0) or 0))
        )
        self.preprocess_export_align_x_var.set(
            {
                "left": "左对齐",
                "center": "居中",
                "right": "右对齐",
            }.get(
                str(
                    getattr(
                        self.settings,
                        "preprocess_export_align_x",
                        "center",
                    ) or "center"
                ),
                "居中",
            )
        )
        self.preprocess_export_align_y_var.set(
            {
                "top": "顶端对齐",
                "center": "居中",
                "bottom": "底部对齐",
            }.get(
                str(
                    getattr(
                        self.settings,
                        "preprocess_export_align_y",
                        "top",
                    ) or "top"
                ),
                "顶端对齐",
            )
        )
        self.preprocess_status_var.set("未分析")
        if recent_warning:
            self._recent_projects_warning = recent_warning
        if hasattr(self, "_page_column_vars"):
            self._page_column_vars["lined"].set(bool(getattr(self.settings, "page_list_show_lined", True)))
            self._page_column_vars["fill_status"].set(bool(getattr(self.settings, "page_list_show_fill_status", False)))
            self._page_column_vars["illustrations"].set(bool(getattr(self.settings, "page_list_show_illustrations", True)))
            self._apply_page_list_display_columns(save=False)
        self.hide_var.set(bool(self.settings.hide_overlays))
        self.polygon_var.set(bool(self.settings.polygon_mode))
        self.polygon_draw_var.set(False)
        if self.polygon_draw_button is not None:
            self.polygon_draw_button.configure(text="编辑插图", style="PC.Compact.TButton")
        trace_was_ready = self._quick_trace_ready
        self._quick_trace_ready = False
        try:
            self.sync_quick_settings()
        finally:
            self._quick_trace_ready = trace_was_ready
        self._display_geometry_cache = None
        self._display_geometry_cache_key = None
        self._page_meta_generation += 1
        generation = self._page_meta_generation
        self._word_fill_mismatch_pages.clear()
        self._word_fill_check_status = {}
        self._word_fill_source_path = None
        self._old_new_compare_source_path = None
        old_compare = self.old_new_compare_window
        if old_compare is not None:
            try:
                if old_compare.winfo_exists():
                    old_compare.destroy()
            except tk.TclError:
                pass
            self.old_new_compare_window = None
        self._word_fill_source_signature = None
        self._word_fill_source_mapping = None
        self._word_fill_source_present_pages = None
        self._load_word_fill_status()
        self._clear_lined_cell_overlays()
        for item in self.page_list.get_children():
            self.page_list.delete(item)
        for index, page in enumerate(project.images):
            self.page_list.insert(
                "", "end", iid=str(index), values=(
                    "●" if page.stem in self._bookmark_stems() else "",
                    page.stem, self._page_section_count_text(index),
                    "", self._word_fill_status_text(index), "",
                ),
            )
        if self._page_list_sort_column:
            self._apply_page_list_sort(ensure_current_visible=False)
        else:
            self._update_page_list_sort_headings()
        self._page_meta_job = self.after_idle(lambda g=generation: self._refresh_page_metadata_step(g, 0))
        self.view_scale = view_scale
        self._set_page_list_selection(selected_index, ensure_visible=True)
        self.load_page(selected_index, preloaded=payload, skip_current_save=True)
        # Only warm after the selected page and Treeview viewport are ready.
        self._page_thumbnails.project_rows_ready()
        self._save_session_state()
        if launch_profile_setup:
            # A new project starts from the documented release workspace even
            # when the previous project/session left other sections expanded.
            # Existing projects still restore the user's remembered session.
            self._apply_new_project_sidebar_defaults()
        storage_hint = f"｜数据目录 {STORAGE_DIRNAME}" if is_managed_project(project.root) else "｜旧版目录结构"
        prefix = f"{migration_detail}｜" if migration_detail else ""
        self.status_var.set(
            f"{prefix}已打开 {project.root}｜{len(project.images)} 页｜图片后缀 {self.settings.image_suffix}｜词表 {len(project.words)} 条{storage_hint}"
        )
        if launch_profile_setup:
            self.after_idle(lambda: self.open_project_profile(new_project=True))

    def failed(exc, detail) -> None:
        if detail:
            print(detail)
        self.show_error("无法打开项目", exc)

    self._start_ui_worker(
        "project-load", worker, done, failed, wait_on_close=True,
    )


def on_page_select(self, deps: ProjectSessionDeps, _event: tk.Event) -> None:
    self.page_controller.on_page_select(_event)


def _request_page_load(
    self, deps: ProjectSessionDeps, index: int, *, reset_zoom: bool = False,
    current_already_saved: bool = False, force: bool = False,
) -> bool:
    return self.page_controller.request_page_load(
        index,
        reset_zoom=reset_zoom,
        current_already_saved=current_already_saved,
        force=force,
    )


def load_page(
    self, deps: ProjectSessionDeps, index: int, reset_zoom: bool = False, *,
    preloaded: dict | None = None, skip_current_save: bool = False,
) -> None:
    Image = deps.Image
    ImageTk = deps.ImageTk
    json = deps.json
    touch_recent_project = deps.touch_recent_project
    ocr_cache_root = deps.ocr_cache_root
    pdic_path = deps.pdic_path
    read_page_sections = deps.read_page_sections
    read_pdic = deps.read_pdic
    read_ppp = deps.read_ppp
    normalize_page_rgb = deps.normalize_page_rgb
    normalize_appearance_mode = deps.normalize_appearance_mode
    if not self.project or not (0 <= index < len(self.project.images)):
        return
    from .review_page_sync import save_review_before_page_change, refresh_review_after_page_change
    if self._batch_active and not self._can_save_current_during_batch_navigation():
        skip_current_save = True
    review_saved = save_review_before_page_change(self, index, already_saved=skip_current_save)
    self._pending_page_index = None
    self._invalidate_ui_worker("page-load")
    self._flush_deferred_page_save()
    if (
        self.current_page and self.image and index != self.current_index
        and not skip_current_save and not self._preprocess_mode_active()
    ):
        if self._can_save_current_during_batch_navigation():
            self._save_current_page_by_mode(sync_editors=not review_saved)
    from ..proofreading.transactions import recover_pending_for_page
    try:
        target_page = self.project.images[index]
        trusted_manual_path = (
            ocr_cache_root(self.project.root)
            / f"{target_page.stem}_manual_selection.json"
        )
        if not recover_pending_for_page(target_page, manual_path=trusted_manual_path):
            self.status_var.set(
                "R3 校对事务恢复需要人工处理：磁盘状态与恢复标记不匹配，本次未切页。"
            )
            return
    except (OSError, ValueError, RuntimeError):
        self.status_var.set(
            "R3 校对事务恢复失败：未读取可能不一致的 PDIC/简体配对。"
        )
        return
    self.current_index = index; self.current_page = self.project.images[index]
    self._auxiliary_controller.load_page(self.current_page)
    self.ref_box_controller.load_page(self.current_page)
    use_preloaded = bool(
        preloaded
        and preloaded.get("index") == index
        and preloaded.get("project_root") == str(self.project.root)
        and isinstance(preloaded.get("image"), Image.Image)
    )
    from ..preprocess.image_metadata_status import image_dpi, image_status
    if use_preloaded:
        source_dpi = preloaded.get("source_dpi")
        self.image = preloaded["image"]
        self.page_sections = list(preloaded.get("page_sections") or [])
        # Use authoritative SECTION state after preload.
        latest_sections = read_page_sections(self.current_page)
        if latest_sections != self.page_sections:
            self.page_sections = latest_sections
        self.entries = list(preloaded.get("entries") or [])
        self._sort_entries_reading_order()
        ocr_payload = preloaded.get("ocr_payload") if isinstance(preloaded.get("ocr_payload"), dict) else {}
        self.ocr_review_candidates = list(ocr_payload.get("review_candidates") or [])
        self._restore_entry_ocr_metadata(ocr_payload)
        self._review_controller_for_call().load_ocr_review_candidates(
            preloaded_candidates=self.ocr_review_candidates,
        )
        self.polygons = list(preloaded.get("polygons") or [])
    else:
        with Image.open(self.current_page) as opened:
            source_dpi = image_dpi(opened.info)
            self.image = normalize_page_rgb(opened)
        self.page_sections = read_page_sections(self.current_page)
        self.entries = read_pdic(pdic_path(self.current_page))
        self._sort_entries_reading_order()
        self._restore_entry_ocr_metadata()
        self._load_ocr_review_candidates()
        self.polygons = read_ppp(self._ppp_read_path(self.current_page))
    self.image_metadata_status_var.set(image_status(self.image.width, self.image.height, source_dpi))
    self.new_polygon = []
    self._preprocess_photo = None
    self._preprocess_photo_cache_key = None
    self._section_editing = False
    self._drag_section_boundary = None
    self.update_idletasks()
    if reset_zoom:
        available = max(500, self.canvas.winfo_width() - 24)
        self.view_scale = min(1.0, available / self.image.width)

    if self.settings.bottom_y <= 0:
        self.settings.bottom_y = int(self.image.height)
    self.cursor_canvas_xy = None
    self.sync_quick_settings()
    self._update_view_zoom_label()
    if use_preloaded and not reset_zoom:
        expected_size = (
            max(1, round(self.image.width * self.view_scale)),
            max(1, round(self.image.height * self.view_scale)),
        )
        if (
            preloaded.get("display_size") == expected_size
            and abs(float(preloaded.get("view_scale", -1.0)) - float(self.view_scale)) < 1e-9
            and isinstance(preloaded.get("display_image"), Image.Image)
            and normalize_appearance_mode(preloaded.get("appearance_mode")) == self.appearance_mode
            and not self.binary_preview_var.get()
        ):
            self.photo = ImageTk.PhotoImage(preloaded["display_image"])
            self._display_photo_cache_key = (
                id(self.image), expected_size[0], expected_size[1], False, self.appearance_mode,
            )
    self.redraw()
    self._set_idle_cursor_status()
    # Reset scroll, preserving zoom.
    self.canvas.xview_moveto(0.0)
    self.canvas.yview_moveto(0.0)
    self._set_page_list_selection(index, ensure_visible=True)
    quality = self._current_page_quality_text()
    suffix = f"｜{quality}" if quality else ""
    self.status_var.set(f"{self.current_page.name}｜{self.image.width}×{self.image.height}｜{len(self.entries)} 个词条{suffix}")
    if self._preprocess_mode_active():
        existing_preprocess = self._preprocess_result_for_page(index)
        self._set_current_preprocess_status(existing_preprocess)
        if existing_preprocess is None:
            self.after_idle(lambda: self.analyze_preprocess_current(silent=True))
    if self._pending_section_editor_index == index:
        self._pending_section_editor_index = None
        if self.page_sections:
            self._set_section_editing(True)
            self.redraw()
            self.status_var.set(
                f"SECTION 编辑：当前页 {len(self.page_sections)} 个；拖动虚线定位Section，双击左键确认并退出编辑。"
            )
    try:
        touch_recent_project(
            self.project.root,
            last_page=self.current_page.name,
            last_page_index=self.current_index,
        )
    except (OSError, ValueError, TypeError):
        pass
    self._restore_workspace_layout()
    refresh_review_after_page_change(self, preloaded if use_preloaded else None)
    self._save_session_state()


