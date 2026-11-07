"""Original main-window global ttk appearance and scoped workspace styles.

Application methods keep their original signatures and pass their live Tk/ttk
style functions into these pure-owner UI methods on each invocation.
"""
from __future__ import annotations
from typing import Any
import tkinter as tk
from tkinter import ttk


def configure_global_appearance(self, *, deps: dict[str, Any]) -> None:
    ttk = deps["ttk"]
    tk = deps["tk"]
    normalize_appearance_mode = deps["normalize_appearance_mode"]
    appearance_palette = deps["appearance_palette"]
    """Configure the active ttk theme for the global light/dark appearance."""
    style = ttk.Style(self)
    mode = normalize_appearance_mode(self.appearance_mode)
    palette = appearance_palette(mode)

    # ttk.Combobox popdowns are classic Tk Listboxes on common Tk builds;
    # style.configure("TCombobox", ...) does not recolor that popup.
    for pattern, value in (
        ("*TCombobox*Listbox.background", palette["input_bg"]),
        ("*TCombobox*Listbox.foreground", palette["input_fg"]),
        ("*TCombobox*Listbox.selectBackground", palette["selection"]),
        ("*TCombobox*Listbox.selectForeground", palette["selection_fg"]),
    ):
        try:
            self.option_add(pattern, value)
        except tk.TclError:
            pass

    if mode == "light":
        try:
            if self._light_ttk_theme in style.theme_names():
                style.theme_use(self._light_ttk_theme)
        except tk.TclError:
            pass
        self.configure(bg=palette["bg"])
        return

    try:
        if "PCDark" not in style.theme_names():
            parent_theme = "clam" if "clam" in style.theme_names() else self._light_ttk_theme
            style.theme_create("PCDark", parent=parent_theme)
        style.theme_use("PCDark")
    except tk.TclError:
        pass

    style.configure(".", background=palette["surface"], foreground=palette["text"])
    style.configure("TFrame", background=palette["surface"])
    style.configure("TLabel", background=palette["surface"], foreground=palette["text"])
    style.configure("TLabelframe", background=palette["surface"], foreground=palette["text"])
    style.configure("TLabelframe.Label", background=palette["surface"], foreground=palette["text"])
    style.configure(
        "TButton", background=palette["button"], foreground=palette["text"],
        anchor="center", justify="center",
        bordercolor=palette["border"], lightcolor=palette["button"], darkcolor=palette["button"],
    )
    style.map(
        "TButton",
        background=[("active", palette["button_hover"]), ("pressed", palette["selection"])],
        foreground=[("disabled", palette["muted"]), ("!disabled", palette["text"])],
    )
    for style_name in ("TCheckbutton", "TRadiobutton"):
        style.configure(style_name, background=palette["surface"], foreground=palette["text"])
        style.map(
            style_name,
            background=[("active", palette["surface_alt"])],
            foreground=[("disabled", palette["muted"]), ("!disabled", palette["text"])],
        )
    for style_name in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure(
            style_name,
            fieldbackground=palette["input_bg"],
            foreground=palette["input_fg"],
            background=palette["button"],
            bordercolor=palette["border"],
            insertcolor=palette["input_fg"],
            arrowcolor=palette["text"],
        )
        style.map(
            style_name,
            fieldbackground=[("readonly", palette["surface_alt"]), ("disabled", palette["surface_alt"])],
            foreground=[("readonly", palette["text"]), ("disabled", palette["muted"])],
        )
    style.configure("TNotebook", background=palette["bg"], bordercolor=palette["border"])
    style.configure(
        "TNotebook.Tab", background=palette["surface_alt"], foreground=palette["muted"],
        padding=(10, 5),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", palette["surface"]), ("active", palette["button_hover"])],
        foreground=[("selected", palette["text"]), ("active", palette["text"])],
    )
    style.configure(
        "Treeview",
        background=palette["surface"],
        fieldbackground=palette["surface"],
        foreground=palette["text"],
        bordercolor=palette["border"],
    )
    style.map(
        "Treeview",
        background=[("selected", palette["selection"])],
        foreground=[("selected", palette["selection_fg"])],
    )
    style.configure(
        "Treeview.Heading",
        background=palette["surface_alt"], foreground=palette["text"],
        bordercolor=palette["border"], relief="flat",
    )
    style.map("Treeview.Heading", background=[("active", palette["button_hover"])])
    style.configure("TSeparator", background=palette["border"])
    style.configure("TPanedwindow", background=palette["border"])
    style.configure(
        "TScrollbar",
        background=palette["button"],
        troughcolor=palette["surface_alt"],
        bordercolor=palette["border"],
        arrowcolor=palette["text"],
        lightcolor=palette["button"],
        darkcolor=palette["button"],
    )
    style.map("TScrollbar", background=[("active", palette["button_hover"])])
    style.configure(
        "TMenubutton",
        background=palette["button"], foreground=palette["text"],
        bordercolor=palette["border"], arrowcolor=palette["text"],
    )
    style.configure(
        "TScale",
        background=palette["surface"], troughcolor=palette["surface_alt"],
        bordercolor=palette["border"],
    )
    style.configure(
        "TProgressbar", background=palette["accent"], troughcolor=palette["surface_alt"],
        bordercolor=palette["border"],
    )
    self.configure(bg=palette["bg"])


def configure_main_workspace_styles(self, *, deps: dict[str, Any]) -> None:
    ttk = deps["ttk"]
    appearance_palette = deps["appearance_palette"]
    """Configure a scoped, dense visual system for the main workspace only.

    Do not switch the global ttk theme here. Secondary windows, especially
    proofreading, intentionally keep their existing appearance; every style
    below is opt-in through a PC.* style name.
    """
    style = ttk.Style(self)
    base = appearance_palette(self.appearance_mode)
    if self.appearance_mode == "dark":
        colors = {
            "sidebar": base["bg"],
            "footer": base["surface"],
            "status": base["bg"],
            "batch": base["surface_alt"],
            "border": base["border"],
            "text": base["text"],
            "muted": base["muted"],
            "button": base["button"],
            "button_hover": base["button_hover"],
            "button_border": base["border"],
            "primary": base["accent"],
            "primary_hover": base["accent_hover"],
            "success": base["success"],
            "success_hover": base["success_hover"],
            "tree_selected": base["selection"],
            "canvas": base["canvas"],
            "ruler_margin": "#20252b",
        }
    else:
        native_background = str(style.lookup("TFrame", "background") or "#f6f7f9")
        colors = {
            "sidebar": native_background,
            "footer": "#f1f3f6",
            "status": "#f6f7f9",
            "batch": "#eef2f6",
            "border": "#d8dde5",
            "text": "#000000",
            "muted": "#68707b",
            "button": "#f4f5f7",
            "button_hover": "#e7eaee",
            "button_border": "#d3d8df",
            "primary": "#4F7CAC",
            "primary_hover": "#416A94",
            "success": "#69A875",
            "success_hover": "#588F64",
            "tree_selected": "#dce8f7",
            "canvas": "#e9edf2",
            "ruler_margin": "#f1f3f6",
        }
    self._main_ui_colors = colors

    style.configure("PC.Sidebar.TFrame", background=colors["sidebar"])
    style.configure("PC.Footer.TFrame", background=colors["footer"])
    style.configure("PC.Status.TFrame", background=colors["status"])
    style.configure("PC.Batch.TFrame", background=colors["batch"])
    style.configure("PC.SectionBody.TFrame", background=colors["sidebar"])

    style.configure(
        "PC.Section.TLabelframe",
        background=colors["sidebar"],
        borderwidth=0,
        relief="flat",
    )
    style.configure(
        "PC.SectionTitle.TLabel",
        background=colors["sidebar"],
        foreground=colors["text"],
        font=self.section_title_font,
        padding=(0, 2, 0, 1),
    )
    style.configure(
        "PC.FieldLabel.TLabel",
        background=colors["sidebar"],
        foreground=colors["text"],
    )
    style.configure(
        "PC.Footer.TLabel",
        background=colors["footer"],
        foreground=colors["muted"],
    )
    style.configure(
        "PC.Status.TLabel",
        background=colors["status"],
        foreground=colors["muted"],
    )
    style.configure(
        "PC.Batch.TLabel",
        background=colors["batch"],
        foreground=colors["text"],
    )

    # Keep rail controls the same font and compact geometry in both themes.
    style.configure("PC.Rail.TButton", font="TkDefaultFont",
                    padding=(0, 0), relief="flat", borderwidth=0,
                    anchor="center", justify="center")
    style.configure("PC.QuickRail.TButton", font="TkDefaultFont",
                    padding=(0, 0), relief="flat", borderwidth=0,
                    anchor="center", justify="center")
    # Different ttk themes inherit different caption alignment defaults.
    for button_style in (
        "PC.Compact.TButton", "PC.Tool.TButton", "PC.Footer.TButton",
        "PC.PageNav.TButton", "PC.SimplePage.TButton",
        "PC.WindowMode.TButton", "PC.WindowProject.TButton",
        "PC.WindowQuick.TButton", "PC.Workspace80.TButton",
    ):
        style.configure(button_style, anchor="center", justify="center")
    style.configure("PC.CompactPage.Treeview", rowheight=22,
                    font=self.compact_page_font, background=base["surface"],
                    fieldbackground=base["surface"], foreground=colors["text"])
    style.configure("PC.CompactPage.Treeview.Heading",
                    font=self.compact_page_font, padding=(3, 3))
    style.configure("PC.Compact.TButton", padding=(7, 3))
    style.configure(
        "PC.EditActive.TButton",
        padding=(7, 3),
        background="#ffd166",
        foreground=colors["text"],
    )
    style.map(
        "PC.EditActive.TButton",
        background=[("active", "#f3c451"), ("pressed", "#eab843")],
    )
    style.configure("PC.Tool.TButton", padding=(4, 2))
    style.configure("PC.PageNav.TButton", padding=(0, 0))
    style.configure("PC.SimplePage.TButton", padding=(0, 0))
    style.configure("PC.Footer.TButton", padding=(7, 3))
    style.configure(
        "PC.Footer.TCheckbutton",
        background=colors["footer"],
        foreground=colors["text"],
        padding=(5, 2),
    )
    style.map(
        "PC.Footer.TCheckbutton",
        background=[("active", colors["footer"])],
        foreground=[("disabled", colors["muted"]), ("!disabled", colors["text"])],
    )
    style.configure("PC.Compact.TEntry", padding=(4, 2))
    style.configure("PC.Footer.TEntry", padding=(4, 2))

    style.configure(
        "PC.Treeview",
        rowheight=26,
        borderwidth=0,
        relief="flat",
        background=base["surface"],
        fieldbackground=base["surface"],
        foreground=colors["text"],
    )
    style.configure(
        "PC.Treeview.Heading",
        padding=(3, 4),
        relief="solid",
        borderwidth=1,
        font=self.section_title_font,
    )
    style.map(
        "PC.Treeview",
        background=[("selected", colors["tree_selected"])],
        foreground=[("selected", colors["text"])],
    )


# Physical Tk main-window lifecycle and appearance callbacks.

def _app_icon_toplevel_mapped(self, event: tk.Event, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    widget = getattr(event, "widget", None)
    if not isinstance(widget, tk.Toplevel) or self._app_icon_photo is None:
        return
    if getattr(widget, "_pc_app_icon_applied", False):
        return
    # Mark before iconphoto(): on Windows, changing the window icon while a
    # Toplevel is mapping may itself produce another Map notification.
    # The guard keeps icon propagation idempotent and prevents a remap loop.
    widget._pc_app_icon_applied = True
    try:
        widget.iconphoto(False, self._app_icon_photo)
    except tk.TclError:
        pass

def _maximize_main_window(self, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    _screen_work_area = deps["_screen_work_area"]
    """Start the main window maximized, with cross-platform fallbacks."""
    try:
        self.state("zoomed")
        return
    except tk.TclError:
        pass
    try:
        self.attributes("-zoomed", True)
    except tk.TclError:
        try:
            work_x, work_y, work_w, work_h = _screen_work_area(self)
            self.geometry(f"{work_w}x{work_h}+{work_x}+{work_y}")
        except tk.TclError:
            pass

def _apply_current_appearance(self, root: tk.Misc, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    apply_classic_widget_appearance = deps["apply_classic_widget_appearance"]
    apply_native_titlebar_appearance = deps["apply_native_titlebar_appearance"]
    try:
        if not root.winfo_exists():
            return
        apply_classic_widget_appearance(root, self.appearance_mode)
        if not isinstance(root, (tk.Tk, tk.Toplevel)):
            return
        apply_native_titlebar_appearance(root, self.appearance_mode)
        # A transient Toplevel can disappear between the existence check
        # and the first child traversal (e.g. a tooltip during startup).
        stack = list(root.winfo_children())
    except tk.TclError:
        return
    while stack:
        widget = stack.pop()
        if isinstance(widget, tk.Toplevel):
            apply_native_titlebar_appearance(widget, self.appearance_mode)
        try:
            stack.extend(widget.winfo_children())
        except tk.TclError:
            pass

def _appearance_toplevel_mapped(self, event: tk.Event, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    widget = getattr(event, "widget", None)
    if widget is None:
        return
    try:
        if not widget.winfo_exists():
            return
    except tk.TclError:
        return
    # Applying a native title-bar appearance may itself trigger another
    # <Map> event on Windows.  Keep only one pending idle callback per
    # Toplevel so icon/titlebar refreshes cannot form a remap loop.
    if getattr(widget, "_pc_appearance_map_pending", False):
        return
    widget._pc_appearance_map_pending = True

    def apply_mapped_appearance(w=widget) -> None:
        try:
            self._apply_current_appearance(w)
        finally:
            try:
                w._pc_appearance_map_pending = False
            except (AttributeError, tk.TclError):
                pass

    try:
        # The callback belongs to the mapped window: destroying a tooltip
        # automatically removes its pending Tcl callback.
        widget.after_idle(apply_mapped_appearance)
    except tk.TclError:
        widget._pc_appearance_map_pending = False

def _appearance_mode_selected(self, _event: tk.Event | None = None, *, deps: dict[str, Any]) -> None:
    APPEARANCE_MODE_VALUES = deps["APPEARANCE_MODE_VALUES"]
    self.set_appearance_mode(
        APPEARANCE_MODE_VALUES.get(self.appearance_mode_var.get(), "light")
    )

def _cancel_system_appearance_poll(self, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    if self._system_appearance_job is not None:
        try:
            self.after_cancel(self._system_appearance_job)
        except tk.TclError:
            pass
        self._system_appearance_job = None
    self._invalidate_ui_worker("system-appearance-detect")

def _schedule_system_appearance_poll(self, delay_ms: int = 2500, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    if self.appearance_preference != "system" or self._ui_worker_shutdown:
        return
    if self._system_appearance_job is not None:
        try:
            self.after_cancel(self._system_appearance_job)
        except tk.TclError:
            pass
    self._system_appearance_job = self.after(
        max(0, int(delay_ms)), self._poll_system_appearance
    )

def _poll_system_appearance(self, *, deps: dict[str, Any]) -> None:
    detect_system_appearance_mode = deps["detect_system_appearance_mode"]
    normalize_appearance_mode = deps["normalize_appearance_mode"]
    self._system_appearance_job = None
    if self.appearance_preference != "system" or self._ui_worker_shutdown:
        return

    def worker() -> str:
        return detect_system_appearance_mode()

    def done(mode: str) -> None:
        if self.appearance_preference != "system":
            return
        resolved = normalize_appearance_mode(mode)
        if resolved != self.appearance_mode:
            self._apply_resolved_appearance(resolved)
        self._schedule_system_appearance_poll()

    def failed(exc, detail) -> None:
        if detail:
            print(detail)
        if self.appearance_preference == "system":
            self._schedule_system_appearance_poll()

    self._start_ui_worker("system-appearance-detect", worker, done, failed)

def set_appearance_mode(self, mode: object, *, persist: bool = True, deps: dict[str, Any]) -> None:
    normalize_appearance_preference = deps["normalize_appearance_preference"]
    APPEARANCE_MODE_LABELS = deps["APPEARANCE_MODE_LABELS"]
    """Set light/dark/system preference without changing project data."""
    preference = normalize_appearance_preference(mode)
    self.appearance_preference = preference
    label = APPEARANCE_MODE_LABELS[preference]
    if self.appearance_mode_var.get() != label:
        self.appearance_mode_var.set(label)
    self._cancel_system_appearance_poll()
    if preference == "system":
        self._schedule_system_appearance_poll(delay_ms=0)
    else:
        self._apply_resolved_appearance(preference)
    if persist:
        self._save_session_state()
