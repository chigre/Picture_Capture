"""Tk-independent implementation of the historical main application startup.\n\nThe stable ``PictureCaptureApp.__init__`` owns the actual Tk super-call, then\npasses live module globals into this implementation at invocation time.\n"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Entry as WordEntry, PolygonRegion, ProjectState
    from ..persistence.page_sections import PageSection
    from ..preprocess.pipeline import PreprocessAnalysis
    from .dialogs.ocr_conflict import OCRConflictReviewDialog
    from .dialogs.old_new_comparison import OldNewComparisonWindow
    from .dialogs.usage_guide import UsageGuideWindow


def initialize_main_app(self, *, deps) -> None:
    """Initialize the existing app instance after ``tk.Tk.__init__``."""
    ImageTk = deps["ImageTk"]
    Path = deps["Path"]
    Image = deps["Image"]
    tk = deps["tk"]
    fit_window_to_work_area = deps["fit_window_to_work_area"]
    AppSettings = deps["AppSettings"]
    AuxiliaryLineEdits = deps["AuxiliaryLineEdits"]
    queue = deps["queue"]
    threading = deps["threading"]
    SessionController = deps["SessionController"]
    normalize_appearance_preference = deps["normalize_appearance_preference"]
    APPEARANCE_MODE_LABELS = deps["APPEARANCE_MODE_LABELS"]
    ttk = deps["ttk"]
    font = deps["font"]
    AuxiliaryLineController = deps["AuxiliaryLineController"]
    CanvasController = deps["CanvasController"]
    CropController = deps["CropController"]
    DetectionController = deps["DetectionController"]
    ExportController = deps["ExportController"]
    HeadwordController = deps["HeadwordController"]
    _parse_words_of_pages_text = deps["_parse_words_of_pages_text"]
    _fill_page_entries = deps["_fill_page_entries"]
    IllustrationController = deps["IllustrationController"]
    RefBoxController = deps["RefBoxController"]
    ProjectController = deps["ProjectController"]
    PageController = deps["PageController"]
    ReviewController = deps["ReviewController"]
    attach_nonbmp_unicode_input = deps["attach_nonbmp_unicode_input"]
    app_module_file = deps["app_module_file"]
    self._app_icon_photo: ImageTk.PhotoImage | None = None
    self._app_icon_registered = False
    self._app_icon_error: str | None = None
    icon_path = Path(app_module_file).resolve().parent / "data" / "app_icon.png"
    try:
        if not icon_path.exists():
            self._app_icon_error = f"icon asset not found: {icon_path}"
        else:
            with Image.open(icon_path) as icon_image:
                self._app_icon_photo = ImageTk.PhotoImage(icon_image.convert("RGBA"))
    except (tk.TclError, OSError) as exc:
        self._app_icon_photo = None
        self._app_icon_error = f"{type(exc).__name__}: {exc} (path={icon_path})"
    if self._app_icon_photo is not None:
        # Prefer Tk's default icon so future Toplevels inherit it. Some
        # window-manager/headless combinations reject the default flag, so
        # fall back to explicitly setting the root icon instead.
        try:
            self.iconphoto(True, self._app_icon_photo)
            self._app_icon_registered = True
        except tk.TclError:
            try:
                self.iconphoto(False, self._app_icon_photo)
                self._app_icon_registered = True
            except tk.TclError:
                pass
    # Reapply icon to mapped secondary windows.
    self.bind_class("Toplevel", "<Map>", self._app_icon_toplevel_mapped, add="+")
    self.title("Picture Capture")
    fit_window_to_work_area(self, 1440, 900, min_width=1, min_height=680)
    self.project: ProjectState | None = None
    self._project_words: set[str] = set()
    self.settings = AppSettings()
    self.current_index = -1
    self.current_page: Path | None = None
    self.image: Image.Image | None = None
    self.photo: ImageTk.PhotoImage | None = None
    self.view_scale = 1.0
    self.entries: list[WordEntry] = []
    self.polygons: list[PolygonRegion] = []
    self.page_sections: list[PageSection] = []
    self._section_editing = False
    self._drag_section_boundary: tuple[int, str] | None = None
    self._ruler_hint: tk.Toplevel | None = None
    self._pending_section_editor_index: int | None = None
    self.new_polygon: list[tuple[int, int]] = []
    self.overlay_widgets: list[tk.Widget] = []
    self.entry_editor_bindings: list[tuple[tk.Entry, WordEntry]] = []
    self.status_var = tk.StringVar(value="请选择一个词典扫描项目目录")
    self.cursor_status_var = tk.StringVar(value="坐标：—｜缩放 100%｜词条 0")
    self.image_metadata_status_var = tk.StringVar(value="—×— px")
    self.hide_var = tk.BooleanVar(value=False)
    # polygon_var controls visibility of saved illustration polygons.
    # polygon_draw_var is a separate, explicit editing mode.
    self.polygon_var = tk.BooleanVar(value=False)
    self.polygon_draw_var = tk.BooleanVar(value=False)
    self.auxiliary_mode_var = tk.BooleanVar(value=False)
    self._auxiliary_edits = AuxiliaryLineEdits()
    self._auxiliary_drag = None
    self.crop_preview_var = tk.BooleanVar(value=False)
    self.binary_preview_var = tk.BooleanVar(value=False)
    self.display_mode_var = tk.StringVar(value="原图+标注")
    self._display_mode_syncing = False
    # Non-destructive scan preprocessing reuses the main canvas and page list.
    self.preprocess_mode_var = tk.BooleanVar(value=False)
    self.preprocess_auto_deskew_var = tk.BooleanVar(
        value=bool(self.settings.preprocess_auto_deskew)
    )
    self.preprocess_safety_var = tk.StringVar(
        value=str(int(self.settings.preprocess_safety_margin_px))
    )
    self.preprocess_geometry_var = tk.StringVar(
        value={
            "deskew": "轻量：旋转+裁边",
            "perspective": "自动透视",
            "dewarp": "UVDoc展平（Paddle高级）",
            "uvdoc": "UVDoc展平（Paddle高级）",
            "auto": "自动几何（推荐）",
        }.get(
            str(getattr(self.settings, "preprocess_geometry_mode", "auto") or "auto"),
            "自动几何（推荐）",
        )
    )
    self.preprocess_export_canvas_var = tk.BooleanVar(
        value=bool(getattr(self.settings, "preprocess_export_canvas_enabled", False))
    )
    self.preprocess_export_canvas_mode_var = tk.StringVar(
        value={
            "batch_max": "本批最大裁剪尺寸",
            "custom": "自定义尺寸",
        }.get(
            str(getattr(self.settings, "preprocess_export_canvas_mode", "batch_max") or "batch_max"),
            "本批最大裁剪尺寸",
        )
    )
    self.preprocess_export_canvas_width_var = tk.StringVar(
        value=str(int(getattr(self.settings, "preprocess_export_canvas_width", 0) or 0))
    )
    self.preprocess_export_canvas_height_var = tk.StringVar(
        value=str(int(getattr(self.settings, "preprocess_export_canvas_height", 0) or 0))
    )
    self.preprocess_export_margin_top_var = tk.StringVar(
        value=str(int(getattr(self.settings, "preprocess_export_margin_top", 0) or 0))
    )
    self.preprocess_export_margin_bottom_var = tk.StringVar(
        value=str(int(getattr(self.settings, "preprocess_export_margin_bottom", 0) or 0))
    )
    self.preprocess_export_margin_left_var = tk.StringVar(
        value=str(int(getattr(self.settings, "preprocess_export_margin_left", 0) or 0))
    )
    self.preprocess_export_margin_right_var = tk.StringVar(
        value=str(int(getattr(self.settings, "preprocess_export_margin_right", 0) or 0))
    )
    self.preprocess_export_align_x_var = tk.StringVar(
        value={
            "left": "左对齐", "center": "居中", "right": "右对齐",
        }.get(
            str(getattr(self.settings, "preprocess_export_align_x", "center") or "center"),
            "居中",
        )
    )
    self.preprocess_export_align_y_var = tk.StringVar(
        value={
            "top": "顶端对齐", "center": "居中", "bottom": "底部对齐",
        }.get(
            str(getattr(self.settings, "preprocess_export_align_y", "top") or "top"),
            "顶端对齐",
        )
    )
    self.preprocess_status_var = tk.StringVar(value="未分析")
    self._preprocess_results: dict[str, PreprocessAnalysis] = {}
    self._preprocess_photo: ImageTk.PhotoImage | None = None
    self._preprocess_photo_cache_key: tuple | None = None
    self._preprocess_corrected_image: Image.Image | None = None
    self._preprocess_corrected_image_key: tuple[int, int] | None = None
    self._preprocess_locked_widgets: list[tuple[tk.Misc, object]] = []
    self.preprocess_mode_button: ttk.Button | None = None
    self.polygon_draw_button: ttk.Button | None = None
    # PPP label editors and vertex-drag state are rebuilt with each canvas redraw.
    self.polygon_label_bindings: list[tuple[tk.Entry, PolygonRegion]] = []
    self._polygon_canvas_items: dict[int, dict] = {}
    self._drag_polygon_vertex: tuple[int, int] | None = None
    self._drag_polygon_edge: tuple[int, str] | None = None
    self._quick_autosave_job: str | None = None
    self._quick_trace_ready = False
    self.autosave_var = tk.BooleanVar(value=True)
    self.autosave_job: str | None = None
    self.cursor_canvas_xy: tuple[float, float] | None = None
    self.ocr_review_candidates: list[dict] = []
    self.candidate_check_vars: dict[str, tk.BooleanVar] = {}
    # v2.9.4: keep page pixels and foreground edit widgets on separate
    # lifecycles. Candidate checkbox edits only touch the corresponding
    # entry overlay; the expensive resized background PhotoImage is reused
    # until either the page object or view scale changes.
    self._display_photo_cache_key: tuple | None = None
    self._display_geometry_cache_key: tuple | None = None
    self._display_geometry_cache = None
    self._entry_visuals: dict[int, dict] = {}
    # Checkbox edits are immediately committed to the in-memory page model,
    # then PDIC/manual-selection disk writes are coalesced for a few hundred
    # milliseconds. Every page/project/batch boundary force-flushes them.
    self._deferred_save_job: str | None = None
    self._deferred_save_page: Path | None = None
    self._deferred_save_snapshot = None
    self._deferred_save_delay_ms = 300
    self._pending_manual_override_path: Path | None = None
    self._pending_manual_override_payload: dict | None = None
    self.ocr_review_window: OCRConflictReviewDialog | None = None
    self.review_window: tk.Toplevel | None = None
    # (page_index, x, y) of the proofreading row mirrored on the main canvas.
    self._review_entry_highlight_target: tuple[int, int, int] | None = None
    # Keep the RGBA PhotoImage alive while the translucent review marker is shown.
    self._review_entry_highlight_photo: ImageTk.PhotoImage | None = None
    self.old_new_compare_window: OldNewComparisonWindow | None = None
    # Session-only source for 【新旧比较】.  The first comparison asks the
    # user to choose a page-aware wordslist TXT, then reuses it until changed.
    self._old_new_compare_source_path: Path | None = None
    self._usage_guide_window: UsageGuideWindow | None = None
    self._page_meta_generation = 0
    self._page_meta_job: str | None = None
    # v2.9.11: page-list headings are clickable. Sorting only changes the
    # Treeview display order; stable iids remain project page indices, so
    # selection/navigation always resolves to the original page.
    self._page_list_sort_column: str | None = None
    self._page_list_sort_descending = False
    self._page_list_sort_job: str | None = None
    # Pages whose line count disagreed with the last page-aware TXT fill.
    # Only the ``画线`` cell is overlaid in pale red; the page-name cell
    # remains untouched so the warning is visually scoped to the count issue.
    self._word_fill_mismatch_pages: set[int] = set()
    # v2.9.9: persist the last page-aware fill count check so pale-red
    # mismatch cells survive application/project reopen. Matching pages are
    # stored too, allowing later manual line-count edits to recompute the
    # warning against the remembered TXT count.
    self._word_fill_check_status: dict[str, dict] = {}
    # v2.9.8: selecting a large page-aware TXT and actually filling PDICs
    # are separate actions.  The parsed page->words mapping is cached after
    # the first fill so correcting a mismatch range never requires choosing
    # or reparsing the same 190k-word source again.
    self._word_fill_source_path: Path | None = None
    self._word_fill_source_signature: tuple[str, int, int] | None = None
    self._word_fill_source_mapping: dict[str, list[str]] | None = None
    # v2.9.10: remember which project pages were explicitly represented in
    # the selected TXT. An empty list and a completely absent page are not
    # the same thing for the visible fill-status column.
    self._word_fill_source_present_pages: set[str] | None = None
    self._page_lined_overlays: dict[int, tk.Label] = {}
    # v2.9.12: the visible fill-status cell carries its own semantic color
    # (match/mismatch/stale/no-data), while the legacy mismatch warning in
    # the 画线 cell is retained for compatibility and quick scanning.
    self._page_fill_status_overlays: dict[int, tk.Label] = {}
    # v2.9.13: cell-overlay repaints are coalesced.  Older builds queued an
    # after_idle repaint for every row metadata update/scroll callback; on
    # large dictionaries that turned startup into thousands of redundant
    # full-list scans.  Keep at most one pending repaint instead.
    self._page_overlay_refresh_job: str | None = None
    # Batch work runs off Tk; pause/stop at page boundaries.
    self._batch_queue: queue.Queue = queue.Queue()
    self._batch_thread: threading.Thread | None = None
    self._batch_pause_event = threading.Event()
    self._batch_pause_event.set()
    self._batch_stop_event = threading.Event()
    self._batch_active = False
    self._batch_parallel = False
    # Foreground edits are page-state locked to protect background PDIC.
    self._batch_foreground_pages = False
    # Navigation is independent from the task write lock.
    self._batch_allow_page_navigation = False
    self._batch_allow_pdic_edits = False
    self._batch_page_states: dict[int, str] = {}
    self._batch_state_lock = threading.Lock()
    self._batch_skipped_count = 0
    self._batch_poll_job: str | None = None
    self._batch_close_after_stop = False
    self._batch_on_done = None
    self._batch_title = ""
    # One-shot background jobs use a separate queue from multi-page batch
    # work. Workers never call Tk; per-key generations discard stale results.
    self._ui_worker_queue: queue.Queue = queue.Queue()
    self._ui_worker_poll_job: str | None = None
    self._ui_worker_generations: dict[str, int] = {}
    self._ui_worker_handlers: dict[tuple[str, int], tuple] = {}
    self._ui_worker_active: set[tuple[str, int]] = set()
    self._ui_worker_close_wait: set[tuple[str, int]] = set()
    self._ui_worker_shutdown = False
    self._ui_close_requested = False
    self._pending_page_index: int | None = None
    self.session_controller = SessionController(self)
    self._session_path = self._default_session_state_path()
    self._last_session = self._read_session_state()
    stored_mode = self._last_session.get("workspace_mode", "最大")
    self.workspace_mode = (
        "紧凑" if stored_mode in {"最简", "简单"} else stored_mode
        if stored_mode in {"极简", "紧凑", "正常", "最大"} else "最大"
    )
    self._restore_workspace_mode_pending = True
    requested_appearance = normalize_appearance_preference(
        self._last_session.get("appearance_mode")
    )
    self.appearance_preference = requested_appearance
    self.appearance_mode = "light"
    self.appearance_mode_var = tk.StringVar(
        value=APPEARANCE_MODE_LABELS[requested_appearance]
    )
    self._system_appearance_job: str | None = None
    self._light_ttk_theme = str(ttk.Style(self).theme_use())
    self._configure_global_appearance()
    self.section_expanded = {
        "preprocess": False,
        "normal": True,
        "aux": False,
        "ocr": False,
        "actions": False,
        "postproduction": False,
        "pages": True,
    }
    stored_sections = self._last_session.get("section_expanded", {})
    if isinstance(stored_sections, dict):
        for key in tuple(self.section_expanded):
            if key in stored_sections:
                self.section_expanded[key] = bool(stored_sections[key])
    self._collapsible_sections: dict[str, ttk.LabelFrame] = {}
    self.section_title_font = font.nametofont("TkDefaultFont").copy()
    self.section_title_font.configure(weight="bold")
    # Keep miniature page rows at 90%, with separate 80% range controls.
    default_page_font = font.nametofont("TkDefaultFont")
    self.compact_page_font = default_page_font.copy()
    base_size = int(default_page_font.cget("size"))
    compact_size = max(7, round(base_size * 0.9)) if base_size > 0 else min(-7, round(base_size * 0.9))
    self.compact_page_font.configure(size=compact_size)
    self._configure_main_workspace_styles()
    self._auxiliary_controller = AuxiliaryLineController(self)
    self.canvas_controller = CanvasController(self)
    self.crop_controller = CropController(self)
    self.detection_controller = DetectionController(self)
    self.export_controller = ExportController(self)
    self.headword_controller = HeadwordController(
        self,
        parse_words_of_pages_text=_parse_words_of_pages_text,
        fill_page_entries=_fill_page_entries,
    )
    self.illustration_controller = IllustrationController(self)
    self.ref_box_controller = RefBoxController(self)
    self.project_controller = ProjectController(self)
    self.page_controller = PageController(self)
    self.review_controller = ReviewController(self)
    self._build_ui()
    self.bind_class("Toplevel", "<Map>", self._appearance_toplevel_mapped, add="+")
    self.set_appearance_mode(requested_appearance, persist=False)
    self.protocol("WM_DELETE_WINDOW", self.on_close)
    self.toggle_autosave()
    # Avoid maximize -> restore-to-compact flicker during session startup.
    if self.workspace_mode == "最大":
        self.after_idle(self._maximize_main_window)
    self.after_idle(self._ensure_sidebar_navigation_width)
    self.after_idle(self.restore_last_session)
    attach_nonbmp_unicode_input(self)
