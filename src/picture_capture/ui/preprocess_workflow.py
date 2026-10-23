"""GUI preprocessing settings, manual perspective, analysis, export and preview owner.

24 complete preprocessing UI methods, with unchanged original Tk callbacks.
The heavy PictureCaptureApp retains method signatures and captures original
mutable GUI/preprocessing globals at call time. No circular app import.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class PreprocessUiDeps:
    """Original app globals resolved live for each preprocessing UI callback."""
    Path: object
    replace: object
    csv: object
    json: object
    re: object
    tk: object
    font: object
    messagebox: object
    ttk: object
    Image: object
    ImageTk: object
    pdic_path: object
    AppSettings: object
    ProjectState: object
    fit_window_to_work_area: object
    normalize_page_rgb: object
    themed_display_image: object
    PreprocessAnalysis: object
    preprocess_analysis_is_current: object
    analyze_preprocess_path: object
    clear_manual_perspective_quad: object
    geometry_corrected_image: object
    load_preprocess_analysis: object
    load_manual_perspective_quad: object
    overlay_excluded_regions: object
    output_canvas_info: object
    preprocess_metadata_output_root: object
    preprocess_preview_output_root: object
    preprocess_processed_output_root: object
    promote_processed_pages: object
    preprocess_result_summary: object
    save_preprocess_analysis: object
    save_manual_perspective_quad: object
    save_processed_page: object
    save_review_preview: object
    export_diagnostic_json: object
    export_summary_csv: object
    perspective_from_quad: object
    _screen_work_area: object
    ocr_cache_root: object
    ppp_read_path_for_image: object
    settings_path: object


def _preprocess_mode_active(self, deps: PreprocessUiDeps) -> bool:
    return bool(
        hasattr(self, "preprocess_mode_var") and self.preprocess_mode_var.get()
    )


def _preprocess_config(self, deps: PreprocessUiDeps) -> tuple[int, bool, str]:
    try:
        safety = int(round(float(str(self.preprocess_safety_var.get()).strip())))
    except (TypeError, ValueError):
        safety = int(getattr(self.settings, "preprocess_safety_margin_px", 20))
    safety = max(0, min(500, safety))
    geometry_label = str(self.preprocess_geometry_var.get() or "").strip()
    geometry_mode = {
        "自动几何（推荐）": "auto",
        "轻量：旋转+裁边": "deskew",
        "自动透视": "perspective",
        "UVDoc展平（Paddle高级）": "uvdoc",
    }.get(geometry_label, "auto")
    return safety, bool(self.preprocess_auto_deskew_var.get()), geometry_mode


def _preprocess_export_config(
    self, deps: PreprocessUiDeps,
) -> tuple[bool, str, int, int, int, int, int, int, str, str]:
    enabled = bool(self.preprocess_export_canvas_var.get())
    mode_label = str(self.preprocess_export_canvas_mode_var.get() or "").strip()
    mode = {
        "本批最大裁剪尺寸": "batch_max",
        "自定义尺寸": "custom",
    }.get(mode_label, "batch_max")

    def bounded_int(variable, setting_name: str) -> int:
        try:
            value = int(round(float(str(variable.get()).strip())))
        except (TypeError, ValueError):
            value = int(getattr(self.settings, setting_name, 0) or 0)
        return max(0, min(100000, value))

    width = bounded_int(
        self.preprocess_export_canvas_width_var,
        "preprocess_export_canvas_width",
    )
    height = bounded_int(
        self.preprocess_export_canvas_height_var,
        "preprocess_export_canvas_height",
    )
    margin_top = bounded_int(
        self.preprocess_export_margin_top_var,
        "preprocess_export_margin_top",
    )
    margin_bottom = bounded_int(
        self.preprocess_export_margin_bottom_var,
        "preprocess_export_margin_bottom",
    )
    margin_left = bounded_int(
        self.preprocess_export_margin_left_var,
        "preprocess_export_margin_left",
    )
    margin_right = bounded_int(
        self.preprocess_export_margin_right_var,
        "preprocess_export_margin_right",
    )
    align_x = {
        "左对齐": "left",
        "居中": "center",
        "右对齐": "right",
    }.get(str(self.preprocess_export_align_x_var.get() or "").strip(), "center")
    align_y = {
        "顶端对齐": "top",
        "居中": "center",
        "底部对齐": "bottom",
    }.get(str(self.preprocess_export_align_y_var.get() or "").strip(), "top")
    return (
        enabled, mode, width, height,
        margin_top, margin_bottom, margin_left, margin_right,
        align_x, align_y,
    )


def _preprocess_export_settings_changed(self, deps: PreprocessUiDeps, _event=None) -> None:
    settings_path = deps.settings_path
    (
        enabled, mode, width, height,
        margin_top, margin_bottom, margin_left, margin_right,
        align_x, align_y,
    ) = self._preprocess_export_config()
    self.preprocess_export_canvas_width_var.set(str(width))
    self.preprocess_export_canvas_height_var.set(str(height))
    self.preprocess_export_margin_top_var.set(str(margin_top))
    self.preprocess_export_margin_bottom_var.set(str(margin_bottom))
    self.preprocess_export_margin_left_var.set(str(margin_left))
    self.preprocess_export_margin_right_var.set(str(margin_right))
    self.settings.preprocess_export_canvas_enabled = enabled
    self.settings.preprocess_export_canvas_mode = mode
    self.settings.preprocess_export_canvas_width = width
    self.settings.preprocess_export_canvas_height = height
    self.settings.preprocess_export_margin_top = margin_top
    self.settings.preprocess_export_margin_bottom = margin_bottom
    self.settings.preprocess_export_margin_left = margin_left
    self.settings.preprocess_export_margin_right = margin_right
    self.settings.preprocess_export_align_x = align_x
    self.settings.preprocess_export_align_y = align_y
    if self.project is not None:
        self.project.settings.preprocess_export_canvas_enabled = enabled
        self.project.settings.preprocess_export_canvas_mode = mode
        self.project.settings.preprocess_export_canvas_width = width
        self.project.settings.preprocess_export_canvas_height = height
        self.project.settings.preprocess_export_margin_top = margin_top
        self.project.settings.preprocess_export_margin_bottom = margin_bottom
        self.project.settings.preprocess_export_margin_left = margin_left
        self.project.settings.preprocess_export_margin_right = margin_right
        self.project.settings.preprocess_export_align_x = align_x
        self.project.settings.preprocess_export_align_y = align_y
        try:
            self.settings.to_json(settings_path(self.project.root))
        except OSError:
            pass
    if self._preprocess_mode_active():
        self._set_current_preprocess_status(
            self._preprocess_result_for_page(self.current_index)
        )


def _preprocess_settings_changed(self, deps: PreprocessUiDeps, _event=None) -> None:
    settings_path = deps.settings_path
    safety, auto_deskew, geometry_mode = self._preprocess_config()
    self.preprocess_safety_var.set(str(safety))
    self.settings.preprocess_safety_margin_px = safety
    self.settings.preprocess_auto_deskew = auto_deskew
    self.settings.preprocess_geometry_mode = geometry_mode
    if self.project is not None:
        self.project.settings.preprocess_safety_margin_px = safety
        self.project.settings.preprocess_auto_deskew = auto_deskew
        self.project.settings.preprocess_geometry_mode = geometry_mode
        try:
            self.settings.to_json(settings_path(self.project.root))
        except OSError:
            pass
    self._preprocess_photo = None
    self._preprocess_photo_cache_key = None
    if self._preprocess_mode_active() and self.project and self.current_page:
        self.preprocess_status_var.set("预处理参数已改变；当前页结果需要重新分析。")
        self.analyze_preprocess_current(silent=True)


def _set_workspace_preprocess_locked(self, deps: PreprocessUiDeps, locked: bool) -> None:
    """Disable ordinary-edit controls while preserving page navigation."""
    tk = deps.tk
    ttk = deps.ttk
    section_keys = ("normal", "aux", "ocr", "actions", "postproduction")
    if locked:
        if self._preprocess_locked_widgets:
            return
        compact_titles = {
            "normal": "一、版面参数",
            "aux": "二、显示设置",
            "ocr": "三、共享 OCR 通道 / OCR画线",
            "actions": "四、画线 / OCR / 插图 / 校对",
            "postproduction": "五、后期词典制作",
        }
        compact_sections = getattr(self, "workspace_tools_sections", {})
        for key in section_keys:
            section = self._collapsible_sections.get(key)
            extra = compact_sections.get(compact_titles.get(key, ""))
            widgets = (section, extra) if extra is not section else (section,)
            stack = [
                widget for holder in widgets if holder is not None
                for widget in holder.winfo_children()
            ]
            while stack:
                widget = stack.pop()
                try:
                    stack.extend(widget.winfo_children())
                except tk.TclError:
                    pass
                if isinstance(widget, ttk.Widget):
                    try:
                        was_disabled = "disabled" in widget.state()
                        widget.state(["disabled"])
                        self._preprocess_locked_widgets.append((widget, was_disabled))
                    except tk.TclError:
                        pass
                else:
                    try:
                        if "state" in widget.keys():
                            old_state = widget.cget("state")
                            widget.configure(state="disabled")
                            self._preprocess_locked_widgets.append((widget, old_state))
                    except tk.TclError:
                        pass
        for widget in getattr(self, "project_footer_buttons", ()):
            try:
                if isinstance(widget, ttk.Widget):
                    was_disabled = "disabled" in widget.state()
                    widget.state(["disabled"])
                    self._preprocess_locked_widgets.append((widget, was_disabled))
                else:
                    old_state = widget.cget("state")
                    widget.configure(state="disabled")
                    self._preprocess_locked_widgets.append((widget, old_state))
            except tk.TclError:
                pass
        return

    remembered = self._preprocess_locked_widgets
    self._preprocess_locked_widgets = []
    for widget, previous in remembered:
        try:
            if isinstance(widget, ttk.Widget):
                widget.state(["disabled" if bool(previous) else "!disabled"])
            else:
                widget.configure(state=previous)
        except tk.TclError:
            pass


def _preprocess_blocking_window_name(self, deps: PreprocessUiDeps) -> str | None:
    tk = deps.tk
    candidates = (
        ("review_window", "词条校对"),
        ("ocr_review_window", "OCR词头冲突复核"),
        ("old_new_compare_window", "新旧比较"),
        ("_settings_dialog", "设置中心"),
        ("_project_profile_wizard", "项目Profile"),
    )
    for attr, label in candidates:
        window = self.__dict__.get(attr)
        if window is None:
            continue
        try:
            if window.winfo_exists():
                return label
        except tk.TclError:
            continue
    return None


def toggle_preprocess_mode(self, deps: PreprocessUiDeps) -> None:
    self._set_preprocess_mode(not self._preprocess_mode_active())


def _set_preprocess_mode(self, deps: PreprocessUiDeps, active: bool, *, analyze: bool = True) -> None:
    messagebox = deps.messagebox
    active = bool(active)
    if active and (not self.project or self.current_page is None or self.image is None):
        self.preprocess_mode_var.set(False)
        messagebox.showinfo(
            "图片预处理", "请先打开包含扫描图片的项目目录。", parent=self,
        )
        return
    if active:
        blocker = self._preprocess_blocking_window_name()
        if blocker is not None:
            self.preprocess_mode_var.set(False)
            messagebox.showinfo(
                "图片预处理",
                f"请先关闭【{blocker}】，再进入预处理模式。\n\n"
                "预处理模式不会与其他可修改项目数据的窗口并行运行。",
                parent=self,
            )
            return
    if active and self._batch_active:
        self.preprocess_mode_var.set(False)
        self.status_var.set("当前批量任务运行中；结束后再进入预处理模式。")
        return

    self.preprocess_mode_var.set(active)
    if self.preprocess_mode_button is not None:
        self.preprocess_mode_button.configure(
            text="退出预处理模式" if active else "进入预处理模式"
        )
    if active:
        self.ref_box_controller.stop_edit()
        self._section_editing = False
        self._drag_section_boundary = None
        self.polygon_draw_var.set(False)
        self.new_polygon.clear()
        self._set_workspace_preprocess_locked(True)
        section = self._collapsible_sections.get("preprocess")
        if section is not None:
            self._set_section_expanded(section, True)
        self.status_var.set(
            "已进入预处理模式：几何纠正后重新检测版面并裁边；画线、OCR、SECTION 和后期制作已锁定。"
        )
        self.redraw()
        if analyze:
            self.analyze_preprocess_current(silent=True)
    else:
        self._invalidate_ui_worker("preprocess-current")
        self._set_workspace_preprocess_locked(False)
        self._preprocess_photo = None
        self._preprocess_photo_cache_key = None
        self.preprocess_status_var.set("未进入预处理模式")
        if self.image is not None:
            self.redraw()
        self.status_var.set("已退出预处理模式，恢复普通编辑功能。")


def _default_preprocess_corner_quad(deps: PreprocessUiDeps, image: Image.Image) -> tuple[float, ...]:
    width, height = image.size
    inset = max(4, round(min(width, height) * 0.012))
    return (
        float(inset), float(inset),
        float(max(inset + 1, width - 1 - inset)), float(inset),
        float(max(inset + 1, width - 1 - inset)),
        float(max(inset + 1, height - 1 - inset)),
        float(inset), float(max(inset + 1, height - 1 - inset)),
    )


def edit_preprocess_corners(self, deps: PreprocessUiDeps) -> None:
    tk = deps.tk
    font = deps.font
    messagebox = deps.messagebox
    ttk = deps.ttk
    Image = deps.Image
    ImageTk = deps.ImageTk
    normalize_page_rgb = deps.normalize_page_rgb
    load_manual_perspective_quad = deps.load_manual_perspective_quad
    save_manual_perspective_quad = deps.save_manual_perspective_quad
    perspective_from_quad = deps.perspective_from_quad
    _screen_work_area = deps._screen_work_area
    if not self.project or self.current_page is None or self.image is None:
        messagebox.showinfo("手动四角", "请先打开包含扫描图片的项目。", parent=self)
        return
    if self._ui_worker_key_active("preprocess-current") or self._batch_active:
        self.status_var.set("预处理任务正在运行；完成后再编辑手动四角。")
        return
    if not self._preprocess_mode_active():
        self._set_preprocess_mode(True, analyze=False)
        if not self._preprocess_mode_active():
            return

    project = self.project
    page = self.current_page
    source = normalize_page_rgb(self.image)
    existing = load_manual_perspective_quad(project.root, page)
    initial = existing or self._default_preprocess_corner_quad(source)
    points = [
        [float(initial[index]), float(initial[index + 1])]
        for index in range(0, 8, 2)
    ]

    window = tk.Toplevel(self)
    window.title(f"手动四角透视｜{page.name}")
    window.transient(self)
    work_x, work_y, work_w, work_h = _screen_work_area(self)
    max_w = max(640, min(1280, work_w - 120))
    max_h = max(520, min(920, work_h - 180))
    scale = min(
        1.0,
        max_w / max(1, source.width),
        (max_h - 90) / max(1, source.height),
    )
    display_size = (
        max(1, round(source.width * scale)),
        max(1, round(source.height * scale)),
    )

    body = ttk.Frame(window, padding=8)
    body.pack(fill="both", expand=True)
    canvas = tk.Canvas(
        body,
        width=display_size[0],
        height=display_size[1],
        highlightthickness=1,
        highlightbackground="#888888",
        cursor="crosshair",
    )
    canvas.pack(fill="both", expand=True)
    photo = ImageTk.PhotoImage(
        source.resize(display_size, Image.Resampling.LANCZOS)
    )
    canvas.create_image(0, 0, image=photo, anchor="nw", tags=("page",))
    window._manual_corner_photo = photo  # type: ignore[attr-defined]

    labels = ("左上", "右上", "右下", "左下")
    drag_state: dict[str, int | None] = {"index": None}

    def redraw_handles() -> None:
        canvas.delete("manual-corners")
        coords = [
            coordinate * scale
            for point in points
            for coordinate in point
        ]
        canvas.create_polygon(
            *coords,
            fill="",
            outline="#ff7a00",
            width=3,
            tags=("manual-corners",),
        )
        radius = 7
        for index, (x, y) in enumerate(points):
            cx = x * scale
            cy = y * scale
            canvas.create_oval(
                cx - radius, cy - radius,
                cx + radius, cy + radius,
                fill="#ff7a00",
                outline="white",
                width=2,
                tags=("manual-corners",),
            )
            canvas.create_text(
                cx + 11, cy - 11,
                text=labels[index],
                fill="#d35400",
                anchor="sw",
                font=(AUTO_FONT_FAMILY, 10, "bold"),
                tags=("manual-corners",),
            )

    def nearest_handle(event: tk.Event) -> int | None:
        best: tuple[float, int] | None = None
        for index, (x, y) in enumerate(points):
            dx = float(event.x) - x * scale
            dy = float(event.y) - y * scale
            distance = dx * dx + dy * dy
            if best is None or distance < best[0]:
                best = (distance, index)
        if best is not None and best[0] <= 22.0 * 22.0:
            return best[1]
        return None

    def press(event: tk.Event) -> str:
        drag_state["index"] = nearest_handle(event)
        return "break"

    def drag(event: tk.Event) -> str:
        index = drag_state.get("index")
        if index is None:
            return "break"
        x = max(0.0, min(float(source.width - 1), float(event.x) / max(scale, 1e-9)))
        y = max(0.0, min(float(source.height - 1), float(event.y) / max(scale, 1e-9)))
        points[int(index)] = [x, y]
        redraw_handles()
        return "break"

    def release(_event: tk.Event) -> str:
        drag_state["index"] = None
        return "break"

    canvas.bind("<ButtonPress-1>", press)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<ButtonRelease-1>", release)
    redraw_handles()

    ttk.Label(
        body,
        text=(
            "拖动四个橙色控制点到页面/正文平面的四角。坐标保存在原扫描图上；"
            "小角度纠偏后会同步变换四点，再做透视纠正，最后重新检测版面并裁边。"
        ),
        wraplength=max(560, display_size[0]),
        anchor="w",
    ).pack(fill="x", pady=(7, 4))

    controls = ttk.Frame(body)
    controls.pack(fill="x")

    def reset_handles() -> None:
        defaults = self._default_preprocess_corner_quad(source)
        for index in range(4):
            points[index] = [
                float(defaults[index * 2]),
                float(defaults[index * 2 + 1]),
            ]
        redraw_handles()

    def apply_handles() -> None:
        quad = tuple(coordinate for point in points for coordinate in point)
        try:
            perspective_from_quad(quad, source.size)
        except Exception as exc:
            messagebox.showerror(
                "手动四角无效", str(exc), parent=window,
            )
            return
        save_manual_perspective_quad(project.root, page, quad)
        self._preprocess_results.pop(page.name, None)
        self._preprocess_photo = None
        self._preprocess_photo_cache_key = None
        window.destroy()
        self.status_var.set(f"已保存 {page.name} 手动四角；正在重新分析。")
        self.analyze_preprocess_current(silent=True)

    ttk.Button(
        controls, text="恢复整页四角", command=reset_handles,
        style="PC.Compact.TButton",
    ).pack(side="left")
    ttk.Button(
        controls, text="取消", command=window.destroy,
        style="PC.Compact.TButton",
    ).pack(side="right")
    ttk.Button(
        controls, text="应用四角", command=apply_handles,
        style="PC.Primary.TButton",
    ).pack(side="right", padx=(0, 6))

    window.update_idletasks()
    target_w = min(work_w, max(660, window.winfo_reqwidth()))
    target_h = min(work_h, max(560, window.winfo_reqheight()))
    x = work_x + max(0, (work_w - target_w) // 2)
    y = work_y + max(0, (work_h - target_h) // 2)
    window.geometry(f"{target_w}x{target_h}+{x}+{y}")
    window.grab_set()
    window.focus_force()


def reset_preprocess_corners(self, deps: PreprocessUiDeps) -> None:
    clear_manual_perspective_quad = deps.clear_manual_perspective_quad
    if not self.project or self.current_page is None:
        return
    page = self.current_page
    clear_manual_perspective_quad(self.project.root, page)
    self._preprocess_results.pop(page.name, None)
    self._preprocess_photo = None
    self._preprocess_photo_cache_key = None
    self.status_var.set(f"已重置 {page.name} 手动四角；恢复自动几何纠正。")
    if self._preprocess_mode_active():
        self.analyze_preprocess_current(silent=True)


def _preprocess_result_for_page(self, deps: PreprocessUiDeps, index: int) -> PreprocessAnalysis | None:
    preprocess_analysis_is_current = deps.preprocess_analysis_is_current
    load_preprocess_analysis = deps.load_preprocess_analysis
    load_manual_perspective_quad = deps.load_manual_perspective_quad
    if not self.project or not (0 <= index < len(self.project.images)):
        return None
    page = self.project.images[index]
    safety, auto_deskew, geometry_mode = self._preprocess_config()
    manual_quad = load_manual_perspective_quad(self.project.root, page)
    cached = self._preprocess_results.get(page.name)
    if cached is not None and preprocess_analysis_is_current(
        cached, page,
        safety_margin_px=safety,
        auto_deskew=auto_deskew,
        geometry_mode=geometry_mode,
        manual_perspective_quad=manual_quad,
    ):
        return cached
    loaded = load_preprocess_analysis(self.project.root, page)
    if loaded is not None and preprocess_analysis_is_current(
        loaded, page,
        safety_margin_px=safety,
        auto_deskew=auto_deskew,
        geometry_mode=geometry_mode,
        manual_perspective_quad=manual_quad,
    ):
        self._preprocess_results[page.name] = loaded
        return loaded
    self._preprocess_results.pop(page.name, None)
    return None


def _set_current_preprocess_status(self, deps: PreprocessUiDeps, analysis: PreprocessAnalysis | None) -> None:
    tk = deps.tk
    preprocess_result_summary = deps.preprocess_result_summary
    if analysis is None:
        self.preprocess_status_var.set("当前页尚未分析")
        return
    warning = ""
    if analysis.warnings:
        warning = "｜" + "；".join(analysis.warnings[:2])
        if len(analysis.warnings) > 2:
            warning += f"；另 {len(analysis.warnings) - 2} 项"
    x0, y0, x1, y1 = analysis.crop_box
    content_width = max(1, int(x1) - int(x0))
    content_height = max(1, int(y1) - int(y0))
    layout_note = f"｜内容框 {content_width}×{content_height}px"
    try:
        (
            canvas_enabled, canvas_mode, page_width, page_height,
            margin_top, margin_bottom, margin_left, margin_right,
            _align_x, _align_y,
        ) = self._preprocess_export_config()
    except (AttributeError, tk.TclError):
        canvas_enabled = False
    if canvas_enabled:
        if canvas_mode == "custom" and page_width > 0 and page_height > 0:
            effective_width = max(
                page_width, content_width + margin_left + margin_right
            )
            effective_height = max(
                page_height, content_height + margin_top + margin_bottom
            )
            layout_note += (
                f"｜页面 {effective_width}×{effective_height}px"
                f"｜版心 {effective_width - margin_left - margin_right}"
                f"×{effective_height - margin_top - margin_bottom}px"
            )
        else:
            layout_note += "｜页面=按本批最大内容框+页边空"
    self.preprocess_status_var.set(
        preprocess_result_summary(analysis) + layout_note + warning
    )


def analyze_preprocess_current(self, deps: PreprocessUiDeps, *, silent: bool = False) -> None:
    replace = deps.replace
    messagebox = deps.messagebox
    PreprocessAnalysis = deps.PreprocessAnalysis
    analyze_preprocess_path = deps.analyze_preprocess_path
    load_manual_perspective_quad = deps.load_manual_perspective_quad
    preprocess_result_summary = deps.preprocess_result_summary
    save_preprocess_analysis = deps.save_preprocess_analysis
    if not self.project or self.current_page is None:
        if not silent:
            messagebox.showinfo("图片预处理", "请先打开项目。", parent=self)
        return
    if not self._preprocess_mode_active():
        self._set_preprocess_mode(True, analyze=False)
        if not self._preprocess_mode_active():
            return
    if self._batch_active:
        self.status_var.set("批量任务运行中，当前页分析将在任务结束后进行。")
        return

    page = self.current_page
    page_index = self.current_index
    project = self.project
    settings = replace(self.settings)
    safety, auto_deskew, geometry_mode = self._preprocess_config()
    manual_quad = load_manual_perspective_quad(project.root, page)
    current = self._preprocess_result_for_page(page_index)
    if current is not None:
        self._set_current_preprocess_status(current)
        self.redraw()
        return

    if self._ui_worker_key_active("preprocess-current"):
        self.preprocess_status_var.set(
            f"{page.name} 尚未分析｜正在完成上一页分析，完成后将继续当前页。"
        )
        return

    self.preprocess_status_var.set(f"正在分析 {page.name}…")
    self.status_var.set(f"图片预处理：正在后台分析 {page.name}…")

    def worker():
        return analyze_preprocess_path(
            page, settings,
            safety_margin_px=safety,
            auto_deskew=auto_deskew,
            geometry_mode=geometry_mode,
            manual_perspective_quad=manual_quad,
        )

    def done(analysis: PreprocessAnalysis) -> None:
        if self.project is not project:
            return
        save_preprocess_analysis(project.root, page, analysis)
        self._preprocess_results[page.name] = analysis
        if self.current_index == page_index and self.current_page == page:
            self._preprocess_photo = None
            self._preprocess_photo_cache_key = None
            self._set_current_preprocess_status(analysis)
            self.redraw()
            self.status_var.set(
                f"图片预处理分析完成：{page.name}｜{preprocess_result_summary(analysis)}"
            )
        elif self._preprocess_mode_active() and self.current_page is not None:
            self.after_idle(lambda: self.analyze_preprocess_current(silent=True))

    def failed(exc, detail) -> None:
        if detail:
            print(detail)
        if self.project is project and self.current_page == page:
            self.preprocess_status_var.set(f"分析失败：{exc}")
            if not silent:
                self.show_error("图片预处理分析失败", exc)
        elif self.project is project and self._preprocess_mode_active():
            self.after_idle(lambda: self.analyze_preprocess_current(silent=True))

    self._start_ui_worker("preprocess-current", worker, done, failed)


def analyze_preprocess_selected(self, deps: PreprocessUiDeps) -> None:
    replace = deps.replace
    messagebox = deps.messagebox
    analyze_preprocess_path = deps.analyze_preprocess_path
    load_manual_perspective_quad = deps.load_manual_perspective_quad
    save_preprocess_analysis = deps.save_preprocess_analysis
    if not self.project:
        messagebox.showinfo("图片预处理", "请先打开项目。", parent=self)
        return
    if not self._preprocess_mode_active():
        self._set_preprocess_mode(True, analyze=False)
        if not self._preprocess_mode_active():
            return
    if self._ui_worker_key_active("preprocess-current"):
        self.status_var.set("当前页预处理分析仍在进行；完成后再启动范围分析。")
        return
    try:
        indices = self.selected_page_indices()
    except ValueError as exc:
        self.show_error("页面范围无效", exc)
        return
    project = self.project
    settings = replace(self.settings)
    safety, auto_deskew, geometry_mode = self._preprocess_config()

    def worker(index, _position, _total):
        page = project.images[int(index)]
        manual_quad = load_manual_perspective_quad(project.root, page)
        analysis = analyze_preprocess_path(
            page, settings,
            safety_margin_px=safety,
            auto_deskew=auto_deskew,
            geometry_mode=geometry_mode,
            manual_perspective_quad=manual_quad,
        )
        save_preprocess_analysis(project.root, page, analysis)
        return int(index), analysis

    def done(_completed, _total, _stopped, results, error):
        if error is not None or self.project is not project:
            return
        normal = 0
        review = 0
        for index, analysis in results:
            page = project.images[int(index)]
            self._preprocess_results[page.name] = analysis
            if analysis.status == "review":
                review += 1
            else:
                normal += 1
        current = self._preprocess_result_for_page(self.current_index)
        self._preprocess_photo = None
        self._preprocess_photo_cache_key = None
        self._set_current_preprocess_status(current)
        self.redraw()
        self.status_var.set(
            f"预处理分析完成：正常 {normal} 页｜需检查 {review} 页。"
        )

    self._start_batch_task(
        "图片预处理分析", indices, worker,
        on_done=done,
        item_label=lambda index: project.images[int(index)].name,
        refresh_page_quality=False,
        allow_page_navigation=True,
    )


def show_preprocess_diagnostics(self, deps: PreprocessUiDeps) -> None:
    """Show the current page's detailed preprocessing diagnostics on demand."""
    json = deps.json
    tk = deps.tk
    messagebox = deps.messagebox
    ttk = deps.ttk
    fit_window_to_work_area = deps.fit_window_to_work_area
    preprocess_result_summary = deps.preprocess_result_summary
    if not self.project or self.current_page is None:
        messagebox.showinfo("诊断信息", "请先打开项目。", parent=self)
        return
    analysis = self._preprocess_result_for_page(self.current_index)
    if analysis is None:
        messagebox.showinfo(
            "诊断信息",
            "当前页尚无预处理结果。请先执行【分析所选范围】。",
            parent=self,
        )
        return

    existing = getattr(self, "_preprocess_diagnostics_window", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.destroy()
        except tk.TclError:
            pass

    window = tk.Toplevel(self)
    self._preprocess_diagnostics_window = window
    window.title(f"预处理诊断信息｜{self.current_page.name}")
    window.transient(self)
    fit_window_to_work_area(
        window, 920, 720, min_width=700, min_height=500,
    )

    body = ttk.Frame(window, padding=10)
    body.pack(fill="both", expand=True)
    body.columnconfigure(0, weight=1)
    body.rowconfigure(1, weight=1)

    ttk.Label(
        body,
        text=preprocess_result_summary(analysis),
        style="PC.FieldLabel.TLabel",
        wraplength=860,
        anchor="w",
    ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

    text_frame = ttk.Frame(body)
    text_frame.grid(row=1, column=0, sticky="nsew")
    text_frame.columnconfigure(0, weight=1)
    text_frame.rowconfigure(0, weight=1)
    text_widget = tk.Text(
        text_frame,
        wrap="none",
        undo=False,
        padx=8,
        pady=8,
    )
    yscroll = ttk.Scrollbar(
        text_frame, orient="vertical", command=text_widget.yview,
    )
    xscroll = ttk.Scrollbar(
        text_frame, orient="horizontal", command=text_widget.xview,
    )
    text_widget.configure(
        yscrollcommand=yscroll.set,
        xscrollcommand=xscroll.set,
    )
    text_widget.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")
    xscroll.grid(row=1, column=0, sticky="ew")

    warnings = list(analysis.warnings or ())
    header_lines = [
        f"页面：{self.current_page.name}",
        f"状态：{'需检查' if analysis.status == 'review' else '正常'}",
        f"方法：{analysis.method}",
        f"几何模式：{analysis.geometry_mode}",
    ]

    valid_indices = tuple(
        int(value)
        for value in analysis.perspective_row_valid_column_indices
    )
    if valid_indices:
        header_lines.extend(
            [
                "",
                "分栏水平诊断（before → after）：",
            ]
        )
        top_before = analysis.perspective_row_before_column_top_angles_deg
        top_after = analysis.perspective_row_after_column_top_angles_deg
        mid_before = analysis.perspective_row_before_column_middle_angles_deg
        mid_after = analysis.perspective_row_after_column_middle_angles_deg
        bottom_before = analysis.perspective_row_before_column_bottom_angles_deg
        bottom_after = analysis.perspective_row_after_column_bottom_angles_deg
        trend_before = analysis.perspective_row_before_column_trends_deg
        trend_after = analysis.perspective_row_after_column_trends_deg
        row_counts = analysis.perspective_row_column_row_counts
        for pos, column_index in enumerate(valid_indices):
            def value(seq, default=0.0):
                return float(seq[pos]) if pos < len(seq) else float(default)

            rows = (
                int(row_counts[column_index])
                if 0 <= column_index < len(row_counts)
                else 0
            )
            header_lines.append(
                f"- 第 {column_index + 1} 栏"
                f"（{rows} 行）："
                f"上 {value(top_before):+.3f}°→{value(top_after):+.3f}°；"
                f"中 {value(mid_before):+.3f}°→{value(mid_after):+.3f}°；"
                f"下 {value(bottom_before):+.3f}°→{value(bottom_after):+.3f}°；"
                f"趋势 {value(trend_before):+.3f}°→{value(trend_after):+.3f}°"
            )
        header_lines.append(
            "最差残余区域："
            f"{analysis.perspective_row_after_worst_region_deg:.3f}°"
            + (
                f"（第 {analysis.perspective_row_after_worst_column_index + 1} 栏）"
                if analysis.perspective_row_after_worst_column_index >= 0
                else ""
            )
        )
        if analysis.perspective_horizontal_vp_column_spread_deg > 0:
            header_lines.append(
                "各栏 VP 方向分歧 P90："
                f"{analysis.perspective_horizontal_vp_column_spread_deg:.3f}°"
            )
    elif analysis.line_geometry_valid_columns:
        indices = tuple(
            int(value)
            for value in analysis.line_geometry_valid_column_indices
        )
        header_lines.extend(["", "原始分栏行几何："])
        for pos, column_index in enumerate(indices):
            rows = (
                int(analysis.line_geometry_column_row_counts[column_index])
                if 0 <= column_index < len(analysis.line_geometry_column_row_counts)
                else 0
            )
            trend = (
                float(analysis.line_geometry_column_trends_deg[pos])
                if pos < len(analysis.line_geometry_column_trends_deg)
                else 0.0
            )
            header_lines.append(
                f"- 第 {column_index + 1} 栏：{rows} 行，趋势 {trend:+.3f}°"
            )
        header_lines.append(
            "最差局部角："
            f"{analysis.line_geometry_worst_region_angle_deg:.3f}°"
        )

    header_lines.extend(
        [
            "",
            "警告：" if warnings else "警告：无",
        ]
    )
    if warnings:
        header_lines.extend(f"- {item}" for item in warnings)
    header_lines.extend(
        [
            "",
            "完整诊断参数（JSON）：",
            json.dumps(
                analysis.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        ]
    )
    diagnostic_text = "\n".join(header_lines)
    text_widget.insert("1.0", diagnostic_text)
    text_widget.configure(state="disabled")

    buttons = ttk.Frame(body)
    buttons.grid(row=2, column=0, sticky="e", pady=(8, 0))

    def copy_all() -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(diagnostic_text)
            self.status_var.set(
                f"已复制预处理诊断信息：{self.current_page.name}"
            )
        except tk.TclError:
            pass

    ttk.Button(
        buttons, text="复制全部", command=copy_all,
        style="PC.Compact.TButton",
    ).pack(side="left")
    ttk.Button(
        buttons, text="关闭", command=window.destroy,
        style="PC.Compact.TButton",
    ).pack(side="left", padx=(6, 0))
    window.bind("<Escape>", lambda _event: window.destroy())
    window.protocol("WM_DELETE_WINDOW", window.destroy)


def promote_preprocessed_working_images(self, deps: PreprocessUiDeps) -> None:
    """Replace root working scans with the verified processed export set."""
    json = deps.json
    messagebox = deps.messagebox
    pdic_path = deps.pdic_path
    promote_processed_pages = deps.promote_processed_pages
    ocr_cache_root = deps.ocr_cache_root
    ppp_read_path_for_image = deps.ppp_read_path_for_image
    if not self.project:
        messagebox.showinfo("设为工作图片", "请先打开项目。", parent=self)
        return
    if self._batch_active or self._ui_worker_key_active("preprocess-current"):
        self.status_var.set("预处理任务仍在运行；完成后再设为工作图片。")
        return

    project = self.project
    try:
        indices = self.selected_page_indices()
    except ValueError as exc:
        self.show_error("页面范围无效", exc)
        return
    pages = [project.images[int(index)] for index in indices]
    if not pages:
        return

    # Any existing coordinate-bearing work may no longer match after crop/
    # projective correction. Warn explicitly, but do not silently delete it.
    ordinary_data_pages = 0
    for page in pages:
        try:
            has_data = (
                pdic_path(page).is_file()
                or ppp_read_path_for_image(page).is_file()
                or (ocr_cache_root(project.root) / f"{page.stem}.json").is_file()
            )
        except OSError:
            has_data = False
        if has_data:
            ordinary_data_pages += 1

    warning = (
        "\n\n注意：检测到 "
        f"{ordinary_data_pages} 页已有 PDIC/PPP/OCR 坐标数据。"
        "预处理会改变页面坐标，这些旧坐标可能不再适用；软件不会自动删除它们。"
        if ordinary_data_pages
        else ""
    )
    confirmed = messagebox.askyesno(
        "设为工作图片",
        "将只把当前所选范围的预处理图片设为后续工作图片。\n\n"
        f"所选页面：{len(pages)} 页\n"
        "所选原扫描图：移动到项目根目录下的 __before__\n"
        "所选处理后图片：以相同文件名写回项目根目录\n"
        "未选页面：保持原样，可之后采用其他预处理方式\n"
        "预处理导出和诊断文件：继续保留，不会删除\n\n"
        "__before__ 可逐批累积不同页面的首代原图；"
        "其中已经存在的同名页面绝不覆盖。"
        f"{warning}\n\n"
        "确认继续吗？",
        parent=self,
    )
    if not confirmed:
        return

    root = project.root
    target_page = self.current_page.name if self.current_page is not None else None
    target_index = self.current_index
    target_view_scale = float(self.view_scale)
    suffix = str(self.settings.image_suffix or "").strip() or None

    try:
        backup, promoted = promote_processed_pages(root, pages)
    except Exception as exc:
        self.show_error("设为工作图片失败", exc)
        return

    messagebox.showinfo(
        "设为工作图片",
        f"已切换所选 {len(promoted)} 页。\n\n"
        f"这些页面的原扫描图已保存在：{backup}\n"
        "处理后图片现在位于项目根目录，并将作为这些页面后续 OCR、画线和切图的工作图片；"
        "其他未选页面保持原样。\n\n"
        "建议接下来重新检测版面参数；旧坐标型结果如来自原图，应重新生成。",
        parent=self,
    )

    # Reload the same project from disk so page dimensions, thumbnails and
    # all downstream geometry use the promoted images immediately.
    if self._preprocess_mode_active():
        self._set_preprocess_mode(False, analyze=False)
    self._preprocess_results.clear()
    self.current_page = None
    self.image = None
    self.photo = None
    self.current_index = -1
    self.project = None
    self._load_project(
        root,
        requested_suffix=suffix,
        target_page=target_page,
        target_index=target_index,
        target_view_scale=target_view_scale,
    )


def jump_preprocess_review(self, deps: PreprocessUiDeps, delta: int) -> None:
    if not self.project:
        return
    if not self._preprocess_mode_active():
        self._set_preprocess_mode(True, analyze=False)
        if not self._preprocess_mode_active():
            return
    step = -1 if int(delta) < 0 else 1
    start = self.current_index + step
    stop = -1 if step < 0 else len(self.project.images)
    for index in range(start, stop, step):
        analysis = self._preprocess_result_for_page(index)
        if analysis is not None and analysis.status == "review":
            self._request_page_load(index)
            return
    self.status_var.set(
        "后面没有已分析的“需检查”页面。" if step > 0
        else "前面没有已分析的“需检查”页面。"
    )


def _preprocess_analysis_for_export(
    self, deps: PreprocessUiDeps, project: ProjectState, page: Path, settings: AppSettings,
    safety: float, auto_deskew: bool, geometry_mode: str,
) -> PreprocessAnalysis:
    preprocess_analysis_is_current = deps.preprocess_analysis_is_current
    analyze_preprocess_path = deps.analyze_preprocess_path
    load_preprocess_analysis = deps.load_preprocess_analysis
    load_manual_perspective_quad = deps.load_manual_perspective_quad
    save_preprocess_analysis = deps.save_preprocess_analysis
    manual_quad = load_manual_perspective_quad(project.root, page)
    analysis = load_preprocess_analysis(project.root, page)
    if analysis is None or not preprocess_analysis_is_current(
        analysis, page,
        safety_margin_px=safety,
        auto_deskew=auto_deskew,
        geometry_mode=geometry_mode,
        manual_perspective_quad=manual_quad,
    ):
        analysis = analyze_preprocess_path(
            page, settings,
            safety_margin_px=safety,
            auto_deskew=auto_deskew,
            geometry_mode=geometry_mode,
            manual_perspective_quad=manual_quad,
        )
        save_preprocess_analysis(project.root, page, analysis)
    return analysis


def export_preprocess_previews(self, deps: PreprocessUiDeps) -> None:
    replace = deps.replace
    messagebox = deps.messagebox
    preprocess_preview_output_root = deps.preprocess_preview_output_root
    save_review_preview = deps.save_review_preview
    if not self.project:
        messagebox.showinfo("图片预处理", "请先打开项目。", parent=self)
        return
    if self._ui_worker_key_active("preprocess-current"):
        self.status_var.set("当前页预处理分析仍在进行；完成后再导出检查小图。")
        return
    try:
        indices = self.selected_page_indices()
    except ValueError as exc:
        self.show_error("页面范围无效", exc)
        return
    project = self.project
    settings = replace(self.settings)
    safety, auto_deskew, geometry_mode = self._preprocess_config()
    output = preprocess_preview_output_root(project.root)

    def worker(index, _position, _total):
        page = project.images[int(index)]
        analysis = self._preprocess_analysis_for_export(
            project, page, settings, safety, auto_deskew, geometry_mode,
        )
        destination = output / f"{page.stem}_preview.jpg"
        save_review_preview(page, analysis, destination)
        return int(index), analysis, destination

    def done(_completed, _total, _stopped, results, error):
        if error is not None or self.project is not project:
            return
        for index, analysis, _destination in results:
            self._preprocess_results[project.images[int(index)].name] = analysis
        self.status_var.set(f"检查小图已导出：{output}")

    self._start_batch_task(
        "导出预处理检查小图", indices, worker,
        on_done=done,
        item_label=lambda index: project.images[int(index)].name,
        refresh_page_quality=False,
        allow_page_navigation=True,
    )


def export_preprocess_images(self, deps: PreprocessUiDeps) -> None:
    replace = deps.replace
    csv = deps.csv
    json = deps.json
    re = deps.re
    messagebox = deps.messagebox
    output_canvas_info = deps.output_canvas_info
    preprocess_metadata_output_root = deps.preprocess_metadata_output_root
    preprocess_processed_output_root = deps.preprocess_processed_output_root
    save_processed_page = deps.save_processed_page
    export_diagnostic_json = deps.export_diagnostic_json
    export_summary_csv = deps.export_summary_csv
    if not self.project:
        messagebox.showinfo("图片预处理", "请先打开项目。", parent=self)
        return
    if self._ui_worker_key_active("preprocess-current"):
        self.status_var.set("当前页预处理分析仍在进行；完成后再导出预处理图片。")
        return
    try:
        indices = self.selected_page_indices()
    except ValueError as exc:
        self.show_error("页面范围无效", exc)
        return

    project = self.project
    settings = replace(self.settings)
    safety, auto_deskew, geometry_mode = self._preprocess_config()
    (
        canvas_enabled,
        canvas_mode,
        canvas_width,
        canvas_height,
        margin_top,
        margin_bottom,
        margin_left,
        margin_right,
        align_x,
        align_y,
    ) = self._preprocess_export_config()
    if canvas_enabled and canvas_mode == "custom":
        if canvas_width <= 0 or canvas_height <= 0:
            messagebox.showerror(
                "统一最终页面",
                "指定页面尺寸时，宽度和高度都必须大于 0 px。",
                parent=self,
            )
            return

    output = preprocess_processed_output_root(project.root)
    metadata_output = preprocess_metadata_output_root(project.root)

    # Stage 1 analyzes every page before writing images. This makes it
    # possible to resolve one common batch canvas that is guaranteed to fit
    # the largest retained crop, even when a custom requested size is too
    # small. No scan content is rescaled.
    def analyze_worker(index, _position, _total):
        page = project.images[int(index)]
        analysis = self._preprocess_analysis_for_export(
            project, page, settings, safety, auto_deskew, geometry_mode,
        )
        return int(index), analysis

    def analyzed(_completed, _total, stopped, results, error):
        if error is not None or self.project is not project:
            return
        for index, analysis in results:
            self._preprocess_results[project.images[int(index)].name] = analysis
        if stopped or not results:
            self.status_var.set("预处理图片导出已停止在分析阶段；尚未写入最终图片。")
            return

        analysis_by_index = {
            int(index): analysis for index, analysis in results
        }
        content_widths = [
            max(1, analysis.crop_box[2] - analysis.crop_box[0])
            for analysis in analysis_by_index.values()
        ]
        content_heights = [
            max(1, analysis.crop_box[3] - analysis.crop_box[1])
            for analysis in analysis_by_index.values()
        ]
        max_content_width = max(content_widths)
        max_content_height = max(content_heights)

        minimum_page_width = (
            max_content_width + margin_left + margin_right
        )
        minimum_page_height = (
            max_content_height + margin_top + margin_bottom
        )
        if canvas_enabled:
            if canvas_mode == "batch_max":
                requested_width = minimum_page_width
                requested_height = minimum_page_height
            else:
                requested_width = canvas_width
                requested_height = canvas_height
            effective_width = max(requested_width, minimum_page_width)
            effective_height = max(requested_height, minimum_page_height)
        else:
            requested_width = 0
            requested_height = 0
            effective_width = 0
            effective_height = 0

        export_items = [
            int(index) for index, _analysis in results
        ]

        def export_worker(index, _position, _total):
            page = project.images[int(index)]
            analysis = analysis_by_index[int(index)]
            canvas = output_canvas_info(
                analysis,
                enabled=canvas_enabled,
                mode=canvas_mode,
                requested_width=requested_width,
                requested_height=requested_height,
                canvas_width=effective_width if canvas_enabled else None,
                canvas_height=effective_height if canvas_enabled else None,
                margin_top=margin_top,
                margin_bottom=margin_bottom,
                margin_left=margin_left,
                margin_right=margin_right,
                align_x=align_x,
                align_y=align_y,
            )
            destination = output / page.name
            save_processed_page(
                page, analysis, destination, canvas=canvas,
            )
            metadata_destination = (
                metadata_output / f"{page.stem}.preprocess.json"
            )
            export_diagnostic_json(
                page,
                analysis,
                metadata_destination,
                output_path=destination,
                canvas=canvas,
                settings=settings,
            )
            return (
                int(index), analysis, destination, canvas,
                metadata_destination,
            )

        def exported(_done, _export_total, export_stopped, export_results, export_error):
            if export_error is not None or self.project is not project:
                return
            summary_records = []
            for (
                index,
                analysis,
                destination,
                canvas,
                _metadata_destination,
            ) in sorted(export_results, key=lambda item: int(item[0])):
                page = project.images[int(index)]
                self._preprocess_results[page.name] = analysis
                summary_records.append(
                    (page, analysis, destination, canvas)
                )
            summary_path = output.parent / "preprocess_summary.csv"
            export_summary_csv(summary_records, summary_path)

            canvas_note = ""
            if canvas_enabled:
                body_width = (
                    effective_width - margin_left - margin_right
                )
                body_height = (
                    effective_height - margin_top - margin_bottom
                )
                canvas_note = (
                    f"｜最终页面 {effective_width}×{effective_height}px"
                    f"｜版心 {body_width}×{body_height}px"
                    f"（页边 上{margin_top}/左{margin_left}/"
                    f"下{margin_bottom}/右{margin_right}px；"
                    f"X {self.preprocess_export_align_x_var.get()} / "
                    f"Y {self.preprocess_export_align_y_var.get()}）"
                )
                if (
                    canvas_mode == "custom"
                    and (
                        effective_width > requested_width
                        or effective_height > requested_height
                    )
                ):
                    canvas_note += (
                        f"｜自定义 {requested_width}×{requested_height}px "
                        "不足，已整批扩容且未缩放正文"
                    )
            stop_note = "｜已安全停止，汇总仅含已完成页" if export_stopped else ""
            self.status_var.set(
                f"预处理图片已导出：{output}"
                f"｜诊断参数：{metadata_output}"
                f"｜汇总：{summary_path.name}"
                f"{canvas_note}{stop_note}｜原扫描图未修改。"
            )

        def start_export_stage() -> None:
            self._start_batch_task(
                "导出预处理图片", export_items, export_worker,
                on_done=exported,
                item_label=lambda index: project.images[int(index)].name,
                refresh_page_quality=False,
                allow_page_navigation=True,
            )

        # _finish_batch_task clears the current batch callback/thread after
        # invoking us, so schedule stage 2 for the next Tk turn instead of
        # starting it re-entrantly inside the stage-1 completion callback.
        self.after_idle(start_export_stage)

    self._start_batch_task(
        "分析预处理导出范围", indices, analyze_worker,
        on_done=analyzed,
        item_label=lambda index: project.images[int(index)].name,
        refresh_page_quality=False,
        allow_page_navigation=True,
    )


def _get_preprocess_display_photo(
    self, deps: PreprocessUiDeps, size: tuple[int, int], analysis: PreprocessAnalysis | None,
) -> ImageTk.PhotoImage:
    Image = deps.Image
    ImageTk = deps.ImageTk
    themed_display_image = deps.themed_display_image
    geometry_corrected_image = deps.geometry_corrected_image
    overlay_excluded_regions = deps.overlay_excluded_regions
    if self.image is None:
        raise RuntimeError("没有可显示的页面图像")
    analysis_key = (
        None if analysis is None else round(float(analysis.applied_angle_deg), 4),
        None if analysis is None else analysis.geometry_mode,
        None if analysis is None else round(float(analysis.geometry_strength_px), 3),
        None if analysis is None else tuple(int(value) for value in analysis.crop_box),
    )
    key = (
        id(self.image), int(size[0]), int(size[1]),
        analysis_key, self.appearance_mode,
    )
    if self._preprocess_photo is not None and self._preprocess_photo_cache_key == key:
        return self._preprocess_photo

    if analysis is not None:
        corrected_key = (id(self.image), id(analysis))
        if (
            self._preprocess_corrected_image is None
            or self._preprocess_corrected_image_key != corrected_key
        ):
            self._preprocess_corrected_image = geometry_corrected_image(
                self.image, analysis,
            )
            self._preprocess_corrected_image_key = corrected_key
        display = self._preprocess_corrected_image.resize(
            size, Image.Resampling.LANCZOS
        )
    else:
        self._preprocess_corrected_image = None
        self._preprocess_corrected_image_key = None
        display = self.image.resize(size, Image.Resampling.LANCZOS)
    display = themed_display_image(display, self.appearance_mode)
    if analysis is not None:
        sx = size[0] / max(1, analysis.source_width)
        sy = size[1] / max(1, analysis.source_height)
        x0, y0, x1, y1 = analysis.crop_box
        display = overlay_excluded_regions(
            display,
            (
                round(x0 * sx), round(y0 * sy),
                round(x1 * sx), round(y1 * sy),
            ),
        )
    self._preprocess_photo = ImageTk.PhotoImage(display)
    self._preprocess_photo_cache_key = key
    return self._preprocess_photo


def _redraw_preprocess_preview(self, deps: PreprocessUiDeps, size: tuple[int, int]) -> None:
    analysis = self._preprocess_result_for_page(self.current_index)
    photo = self._get_preprocess_display_photo(size, analysis)
    self.canvas.create_image(0, 0, image=photo, anchor="nw", tags="page")
    self.canvas.configure(scrollregion=(0, 0, size[0], size[1]))
    self._set_current_preprocess_status(analysis)


