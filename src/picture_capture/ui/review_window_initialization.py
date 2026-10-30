"""Domain owner for the full ReviewWindow Tk widget initialization after Toplevel.__init__.

The original class constructor remains in app.py to preserve Python's zero-arg
super() semantics; all other original initialization statements live here.
Live app module globals are injected on every call; no Tk root is created.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import ImageTk
    from ..models import AppSettings, Entry as WordEntry


def initialize_review_window(self: Any, parent: Any, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    font = deps["font"]
    ImageTk = deps["ImageTk"]
    _review_window_dimensions = deps["_review_window_dimensions"]
    _format_layout_percent = deps["_format_layout_percent"]
    normalize_content_font_setting = deps["normalize_content_font_setting"]
    _review_editor_font_size = deps["_review_editor_font_size"]
    _format_review_height_percent = deps["_format_review_height_percent"]
    _effective_review_regular_crop_height = deps["_effective_review_regular_crop_height"]
    _effective_review_single_cjk_line_height = deps["_effective_review_single_cjk_line_height"]
    OCR_COMPARE_KEY_TO_LABEL = deps["OCR_COMPARE_KEY_TO_LABEL"]
    WORDSLIST_LOCATOR_KEY_TO_LABEL = deps["WORDSLIST_LOCATOR_KEY_TO_LABEL"]
    LexicalLookupResult = deps["LexicalLookupResult"]
    threading = deps["threading"]
    queue = deps["queue"]
    self.parent = parent
    self.title(f"词条校对 — {parent.current_page.name if parent.current_page else ''}")
    self.update_idletasks()
    screen_w = max(1, self.winfo_screenwidth())
    screen_h = max(1, self.winfo_screenheight())
    width, height = _review_window_dimensions(screen_w, screen_h)
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2)
    # Only the compact index preset places proofreading beside the image.
    mini = getattr(parent, "workspace_mini_page_host", None)
    compact_workspace = (
        getattr(parent, "workspace_mode", "") in {"极简", "紧凑"}
        or (mini is not None and mini.winfo_manager() == "grid")
    )
    if compact_workspace:
        parent.update_idletasks()
        x = max(0, parent.winfo_rootx() + parent.winfo_width())
        y = max(0, parent.winfo_rooty())
        # Tk client height must exclude window decorations.
        from .workspace_tools import _preset_work_geometry
        work_x, work_y, work_w, safe_client_height = _preset_work_geometry(parent)
        work_right = work_x + work_w
        x = min(max(x, work_x), work_right - 1)
        y = work_y  # Align compact proofreading to the usable desktop top.
        width = max(1, work_right - x)
        height = max(1, safe_client_height)
    self.geometry(f"{width}x{height}+{x}+{y}")
    self.minsize(min(300 if compact_workspace else 560, width),
                 min(420, height))
    self.active_index = 0
    # A stored 0 means automatic fit-to-left-pane. Positive values retain
    # the historical explicit/manual percentage mode.
    stored_review_zoom = float(getattr(parent.settings, "review_zoom_percent", 0.0) or 0.0)
    self.review_zoom_auto = stored_review_zoom <= 0
    self.review_zoom = (
        1.0 if self.review_zoom_auto
        else max(0.20, min(2.5, float(stored_review_zoom) / 100.0))
    )
    self.review_zoom_var = tk.StringVar(
        value="自动" if self.review_zoom_auto else f"{_format_layout_percent(self.review_zoom * 100.0)}%"
    )
    # Review typography is deliberately independent from the image zoom.
    # Expose the same persisted font settings directly in the review window
    # so users do not need to return to the detailed-settings dialog.
    self.review_font_family_var = tk.StringVar(
        value=normalize_content_font_setting(parent.settings.review_entry_font_family)
    )
    self.review_font_size_var = tk.StringVar(value=str(_review_editor_font_size(parent.settings)))
    self.review_font_bold_var = tk.BooleanVar(value=bool(parent.settings.review_entry_font_bold))
    self.review_font_italic_var = tk.BooleanVar(value=bool(parent.settings.review_entry_font_italic))
    self.review_simplified_font_family_var = tk.StringVar(
        value=normalize_content_font_setting(
            getattr(parent.settings, "review_simplified_font_family", parent.settings.review_entry_font_family)
        )
    )
    self.review_simplified_font_size_var = tk.StringVar(
        value=str(max(6, int(getattr(parent.settings, "review_simplified_font_size", _review_editor_font_size(parent.settings)))))
    )
    self.review_simplified_font_bold_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "review_simplified_font_bold", parent.settings.review_entry_font_bold))
    )
    self.review_simplified_font_italic_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "review_simplified_font_italic", parent.settings.review_entry_font_italic))
    )
    self.review_left_padding_var = tk.StringVar(value=str(max(0, int(parent.settings.review_entry_left_padding))))
    self.review_vertical_padding_var = tk.StringVar(
        value=str(max(0, min(30, int(parent.settings.review_entry_vertical_padding))))
    )
    self.review_line_height_var = tk.StringVar(
        value=_format_review_height_percent(
            parent.image, max(1, int(parent.settings.character_height))
        )
    )
    self.review_row_padding_var = tk.StringVar(
        value=_format_review_height_percent(
            parent.image, max(0, int(parent.settings.row_padding))
        )
    )
    self.review_regular_crop_height_var = tk.StringVar(
        value=_format_review_height_percent(
            parent.image, _effective_review_regular_crop_height(parent.settings)
        )
    )
    self.review_single_cjk_line_height_var = tk.StringVar(
        value=_format_review_height_percent(
            parent.image, _effective_review_single_cjk_line_height(parent.settings)
        )
    )
    self.review_line_height_px_var = tk.StringVar(
        value=str(max(1, int(parent.settings.character_height)))
    )
    self.review_row_padding_px_var = tk.StringVar(
        value=str(max(0, int(parent.settings.row_padding)))
    )
    self.review_regular_crop_height_px_var = tk.StringVar(
        value=str(_effective_review_regular_crop_height(parent.settings))
    )
    self.review_single_cjk_line_height_px_var = tk.StringVar(
        value=str(_effective_review_single_cjk_line_height(parent.settings))
    )
    self.review_extended_crop_multiplier_var = tk.StringVar(
        value=f"{float(getattr(parent.settings, 'review_extended_crop_height_multiplier', 2.5)):g}"
    )
    self.review_main_ocr_choices_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "review_main_show_ocr_choices", False))
    )
    self.review_main_ocr_background_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "review_main_show_ocr_background", False))
    )
    compare_key = str(getattr(parent.settings, "review_ocr_compare_source", "fusion") or "fusion").lower()
    if compare_key not in self.OCR_COMPARE_KEY_TO_LABEL:
        compare_key = "fusion"
    self.review_ocr_compare_var = tk.StringVar(value=self.OCR_COMPARE_KEY_TO_LABEL[compare_key])
    self.review_show_simplified_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "review_show_simplified", False))
    )
    locator_key = str(getattr(parent.settings, "wordslist_locator_mode", "auto") or "auto").lower()
    if locator_key not in self.WORDSLIST_LOCATOR_KEY_TO_LABEL:
        locator_key = "auto"
    self.wordslist_locator_var = tk.StringVar(value=self.WORDSLIST_LOCATOR_KEY_TO_LABEL[locator_key])
    self.network_lookup_enabled_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "review_network_lookup_enabled", True))
    )
    self.network_lookup_status_var = tk.StringVar(value="网络词汇核验：等待选择词条")
    self.cc_cedict_lookup_var = tk.StringVar(value="CC-CEDICT(?)")
    self.cc_simplified_compare_var = tk.StringVar(value="CC简(?)")
    self.moedict_lookup_var = tk.StringVar(value="萌(?)")
    self.wiktionary_lookup_var = tk.StringVar(value="Wiki(?)")
    self._network_source_urls: dict[str, str] = {}
    self._network_lookup_job: str | None = None
    self._network_lookup_serial = 0
    self._network_lookup_cache: dict[str, LexicalLookupResult] = {}
    self._network_lookup_word = ""
    self._network_result_queue: queue.Queue[tuple[int, str, LexicalLookupResult | None]] = queue.Queue()
    self._network_pending_serials: set[int] = set()
    self._network_poll_job: str | None = None
    self._review_font_apply_job: str | None = None
    self._review_simplified_font_apply_job: str | None = None
    self._review_padding_apply_job: str | None = None
    self._review_vertical_padding_apply_job: str | None = None
    self._review_line_height_apply_job: str | None = None
    self._review_row_padding_apply_job: str | None = None
    self._review_regular_crop_height_apply_job: str | None = None
    self._review_single_cjk_height_apply_job: str | None = None
    self._review_extended_crop_multiplier_job: str | None = None
    self._syncing_review_height_vars = False
    self._review_height_edit_source: dict[str, str] = {}
    self.word_highlight_index: int | None = None
    self.word_selected_local_index: int | None = None
    self.word_list_default_bg = "white"
    self.word_list_default_fg = "#111827"
    # The reference words may exceed 100k rows.  Keep the full data/index in
    # Python, but only render a small contiguous window in the Tk Listbox.
    self.word_window_radius = 250
    self.word_window_start = 0
    self.word_window_indices: list[int] = []
    self.word_keys: list[str] = []
    self.word_exact_index: dict[str, int] = {}
    self.word_exact_indices: dict[str, list[int]] = {}
    self._previous_reference_base_cache: tuple[int, int | None] | None = None
    self.sorted_word_keys: list[str] = []
    self.sorted_word_indices: list[int] = []
    self.word_sort_key_cache: dict[int, tuple[str, str]] = {}
    self.vars: list[tk.StringVar] = []
    # Stable Entry identities corresponding to ``vars``. Main-canvas line
    # insertion can reorder parent.entries while this window remains open.
    self.row_entries: list[WordEntry] = []
    self.editors: list[tk.Entry] = []
    self.editor_frames: list[tk.Frame] = []
    self.simplified_vars: list[tk.StringVar] = []
    self.simplified_editors: list[tk.Entry] = []
    self.simplified_search_buttons: list[tk.Button] = []
    self.simplified_actual_values: list[str | None] = []
    self.simplified_manual_flags: list[bool] = []
    # True only for rows that had no persisted simplified record when the page was opened.
    # Existing sidecar text is authoritative and must never be silently regenerated.
    self.simplified_auto_refresh_flags: list[bool] = []
    self._simplified_page_cache: dict[str, dict[str, dict]] = {}
    self._simplified_dirty_pages: set[str] = set()
    self._rendered_page_stem: str = ""
    self.editor_crop_widths: list[int] = []
    self.ocr_result_buttons: list[tuple[tk.Button, str]] = []
    self.thumbnails: list[ImageTk.PhotoImage] = []
    self.replace_digits = tk.BooleanVar(value=False)
    self.order_scope_var = tk.StringVar(value="current")
    self.review_mode_var = tk.StringVar(value="single")
    # Reuse the main-window 【指定】 text directly so proofreading and
    # every other batch action see the exact same page-range string.
    self.focused_page_range_var = parent.page_range_spec_var
    self.focused_include_mismatch_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "focused_review_include_ocr_mismatch", True))
    )
    self.focused_include_characters_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "focused_review_include_characters", False))
    )
    self.focused_exclude_single_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "focused_review_exclude_single_character", False))
    )
    self.focused_exclude_reference_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "focused_review_exclude_reference_words", False))
    )
    self.focused_characters_var = tk.StringVar(
        value=str(
            getattr(parent.settings, "focused_review_characters", "")
            or "椿,彝,壯,鳥,傅,顔,彝,榖,歴,内,脱,書,鳴"
        )
    )
    self.focused_risk_priority_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "focused_review_risk_queue_enabled", False))
    )
    self.focused_risk_capture_var = tk.BooleanVar(
        value=bool(getattr(parent.settings, "focused_review_risk_witness_capture", False))
    )
    self.focused_batch_size_var = tk.StringVar(
        value=str(max(1, int(getattr(parent.settings, "focused_review_batch_size", 20) or 20)))
    )
    self.filtered_targets: list[dict] = []
    self.filtered_batch_index = 0
    self._filter_rows_active = False
    self.filter_batch_var = tk.StringVar(value="")
    self._filter_scan_serial = 0
    self._filter_render_serial = 0
    self._filter_scan_complete = True
    # Filter-mode render cache stores PIL crops only. Tk/ImageTk objects are
    # still created on the UI thread when a batch becomes visible.
    self._filter_batch_render_cache: dict[tuple[int, tuple], tuple] = {}
    self._filter_prefetch_key: tuple[int, tuple] | None = None
    self._filter_current_batch_targets: list[dict] = []
    self._filter_pending_changes: dict[int, dict[tuple[int, int], dict]] = {}
    self._filter_save_job: str | None = None
    self._filter_save_running = False
    self._filter_close_after_save = False
    self.focused_panel_expanded = tk.BooleanVar(value=False)
    self.digit_map_expanded = tk.BooleanVar(value=False)
    self.accent_panel_expanded = tk.BooleanVar(value=False)
    # Open only the reference word list by default; every other right-side
    # helper stays available behind its collapsible title on demand.
    self.review_right_section_expanded = {
        key: tk.BooleanVar(value=(key == "reference"))
        for key in ("display", "digit", "accent", "ocr", "network", "reference")
    }
    self._review_right_sections: dict[str, dict[str, object]] = {}
    self.autosave_label_var = tk.StringVar(value="")
    saved_digit_map = list(getattr(parent.settings, "review_digit_map", []) or [])
    defaults = list("áéíóúãçñõü")
    saved_digit_map = (saved_digit_map + defaults)[:10]
    self.digit_map_vars = [tk.StringVar(value=str(saved_digit_map[i])) for i in range(10)]
    self.active_candidate: dict | None = None
    # Adjacent-page proofreading prefetch. PIL/image/file parsing runs in a
    # daemon worker; Tk/ImageTk objects are still created only on the UI
    # thread.  This keeps previous/next navigation responsive without
    # changing saved page data or OCR semantics.
    self._prefetch_lock = threading.Lock()
    self._prefetched_pages: dict[int, dict] = {}
    self._prefetch_inflight: set[int] = set()
    self._prefetch_closed = False
    self._review_render_worker_key = f"review-render-{id(self)}"
    self._review_render_focus_index = 0
    self._review_auto_zoom_job: str | None = None
    self._review_auto_zoom_width = 0
    self.review_section_title_font = font.nametofont("TkDefaultFont").copy()
    self.review_section_title_font.configure(weight="bold")
    self._configure_review_styles()
    self._build()
    self.after_idle(self._initialize_review_layout_and_rows)
    self.protocol("WM_DELETE_WINDOW", self._close_review)
    self._update_title()
    # Traces are installed after the widgets are built so construction does
    # not trigger an unnecessary project-settings write.
    for _var in (self.review_font_family_var, self.review_font_size_var,
                 self.review_font_bold_var, self.review_font_italic_var):
        _var.trace_add("write", lambda *_args: self._schedule_review_font_apply())
    for _var in (self.review_simplified_font_family_var, self.review_simplified_font_size_var,
                 self.review_simplified_font_bold_var, self.review_simplified_font_italic_var):
        _var.trace_add("write", lambda *_args: self._schedule_review_simplified_font_apply())
    self.review_left_padding_var.trace_add("write", lambda *_args: self._schedule_review_padding_apply())
    self.review_vertical_padding_var.trace_add("write", lambda *_args: self._schedule_review_vertical_padding_apply())
    self.review_line_height_var.trace_add(
        "write", lambda *_args: self._schedule_review_line_height_apply("percent")
    )
    self.review_line_height_px_var.trace_add(
        "write", lambda *_args: self._schedule_review_line_height_apply("pixel")
    )
    self.review_row_padding_var.trace_add(
        "write", lambda *_args: self._schedule_review_row_padding_apply("percent")
    )
    self.review_row_padding_px_var.trace_add(
        "write", lambda *_args: self._schedule_review_row_padding_apply("pixel")
    )
    self.review_regular_crop_height_var.trace_add(
        "write", lambda *_args: self._schedule_review_regular_crop_height_apply("percent")
    )
    self.review_regular_crop_height_px_var.trace_add(
        "write", lambda *_args: self._schedule_review_regular_crop_height_apply("pixel")
    )
    self.review_single_cjk_line_height_var.trace_add(
        "write", lambda *_args: self._schedule_review_single_cjk_height_apply("percent")
    )
    self.review_single_cjk_line_height_px_var.trace_add(
        "write", lambda *_args: self._schedule_review_single_cjk_height_apply("pixel")
    )
    self.review_extended_crop_multiplier_var.trace_add(
        "write", lambda *_args: self._schedule_review_extended_crop_multiplier_apply()
    )
    for _var in self.digit_map_vars:
        _var.trace_add("write", lambda *_args: self._save_digit_map())
