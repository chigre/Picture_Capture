"""Project Profile Wizard post-Toplevel lifecycle bootstrapping.

Original class __init__ performs super().__init__(parent); this helper initializes
all settings, GUI state, representative samples, and deferred thumbnail decode.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import queue
    import tkinter as tk
    from tkinter import ttk
    from PIL import ImageTk


def initialize_wizard(self, parent, *, new_project: bool = False, deps) -> None:
    replace = deps["replace"]
    _screen_work_area = deps["_screen_work_area"]
    ImageTk = deps["ImageTk"]
    ttk = deps["ttk"]
    tk = deps["tk"]
    queue = deps["queue"]
    threading = deps["threading"]
    suggested_body_page_range = deps["suggested_body_page_range"]
    configured_body_page_indices = deps["configured_body_page_indices"]
    probable_body_page_indices = deps["probable_body_page_indices"]
    representative_page_indices = deps["representative_page_indices"]
    self.parent = parent
    self.project = parent.project
    if self.project is None:
        self.destroy()
        return
    self.new_project = bool(new_project)
    self.working = replace(parent.settings)
    self.title("建立项目Profile" if self.new_project else "项目Profile")
    self.update_idletasks()
    screen_w = max(800, int(self.winfo_screenwidth()))
    work_x, work_y, work_w, work_h = _screen_work_area(self)
    width = min(work_w, max(720, int(screen_w * 0.80)))
    height = max(1, int(work_h * 0.90))
    x = work_x + max(0, (work_w - width) // 2)
    y = work_y + max(0, (work_h - height) // 2)
    self._wizard_width = width
    self._wizard_height = height
    self._wizard_left_width = max(400, int(width * 0.40) - 36)
    self._wizard_image_width = max(560, int(width * 0.60) - 36)
    self._wizard_content_width = self._wizard_left_width
    self.geometry(f"{width}x{height}+{x}+{y}")
    self.minsize(min(960, width), min(640, height))
    self.transient(parent)
    self.grab_set()
    self.protocol("WM_DELETE_WINDOW", self._close_without_save)
    self._photos: list[ImageTk.PhotoImage] = []
    self._sample_cells: dict[int, ttk.Frame] = {}
    self._sample_photo_by_slot: dict[int, ImageTk.PhotoImage] = {}
    self._thumbnail_slot_queue: queue.Queue = queue.Queue()
    self._thumbnail_slot_generation: dict[int, int] = {}
    self._thumbnail_slot_pending: set[tuple[int, int]] = set()
    self._validation_photos: list[ImageTk.PhotoImage] = []
    self._template_photos: list[ImageTk.PhotoImage] = []
    self._template_preview_canvas: tk.Canvas | None = None
    self._template_line_items: list[int] = []
    self._template_line_paths: list[list[tuple[float, float]]] = []
    self._template_nudge_vector: tuple[float, float] = (0.0, 0.0)
    self._thumbnail_queue: queue.Queue | None = None
    self._thumbnail_load_generation = 0
    self._validation_results: list[tuple] = []
    self.validation_preview_slot = 0
    self._headword_example_photos: list[ImageTk.PhotoImage] = []
    self._validation_running = False
    self._analysis_running = False
    self._profile_revision = 0
    self._analysis_revision_started = -1
    self._validation_revision_started = -1
    self._analysis_suggestion: dict[str, object] = {}
    self._analysis_auto_apply = False
    self._analysis_queue: queue.Queue | None = None
    self._validation_queue: queue.Queue | None = None
    self._validation_stop_event = threading.Event()
    self._validation_close_requested = False
    self._closing = False
    if not str(getattr(self.working, "dictionary_body_page_range", "") or "").strip():
        self.working.dictionary_body_page_range = suggested_body_page_range(self.project.images)
    configured_body = configured_body_page_indices(
        len(self.project.images),
        getattr(self.working, "dictionary_body_page_range", ""),
    )
    self.sample_candidates = probable_body_page_indices(
        self.project.images,
        configured_body or None,
    )
    self.sample_indices = representative_page_indices(
        self.project.images,
        6,
        configured_body or None,
    )
    self.template_preview_slot = 0

    self._build_vars()
    self._build_ui()
    self._show_sample_loading_state()
    self._refresh_language_summary()
    self._refresh_summary()
    self.after(20, self._start_sample_thumbnail_load)

    # Representative-page analysis starts after the user confirms reading
    # direction and enters step 2. This avoids analyzing a vertical/RTL
    # dictionary with an incorrect default transform.

