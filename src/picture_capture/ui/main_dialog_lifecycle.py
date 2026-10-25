"""Main-window Settings, Profile, Guide, Environment and Review dialog lifecycle.

Single-instance Tk windows are opened on the original main event thread.
Call-time collaborators preserve picture_capture.app monkeypatch contracts.
"""
from __future__ import annotations
from typing import Any

def show_help_dialog(self, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    UsageGuideWindow = deps["UsageGuideWindow"]
    existing = self.__dict__.get("_usage_guide_window")
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                existing._refresh_context()
                return
        except tk.TclError:
            pass
    window = UsageGuideWindow(self)
    self._usage_guide_window = window
    window.bind(
        "<Destroy>",
        lambda event, w=window: self.__dict__.pop("_usage_guide_window", None)
        if event.widget is w else None,
        add="+",
    )

def show_environment_center(self, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    EnvironmentCenterWindow = deps["EnvironmentCenterWindow"]
    existing = self.__dict__.get("_environment_center_window")
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                existing.refresh()
                return
        except tk.TclError:
            pass
    window = EnvironmentCenterWindow(self)
    self._environment_center_window = window
    window.bind(
        "<Destroy>",
        lambda event, w=window: self.__dict__.pop("_environment_center_window", None)
        if event.widget is w else None,
        add="+",
    )

def open_settings(self, initial_tab: str | None = None, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    SettingsDialog = deps["SettingsDialog"]
    # Pull unsaved quick-panel values (notably OCR language) into the settings
    # object first so language-dependent options are immediately correct.
    if not self.apply_quick_settings(show_status=False, persist=False):
        return
    existing = self.__dict__.get("_settings_dialog")
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.select_tab(initial_tab)
                existing.deiconify()
                existing.lift()
                return
        except tk.TclError:
            pass
    dialog = SettingsDialog(self, initial_tab=initial_tab)
    self._settings_dialog = dialog
    dialog.bind(
        "<Destroy>",
        lambda event, w=dialog: self.__dict__.pop("_settings_dialog", None)
        if event.widget is w else None,
        add="+",
    )

def open_project_profile(self, new_project: bool = False, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    messagebox = deps["messagebox"]
    ProjectProfileWizard = deps["ProjectProfileWizard"]
    if not self.project:
        messagebox.showinfo("尚未打开", "请先打开或新建词典项目。", parent=self)
        return
    if self._batch_active:
        self.status_var.set("批量任务运行中，结束或停止后再打开 Project Profile。")
        return
    # Keep the wizard's working copy aligned with any unsaved/debounced
    # quick-panel edits made immediately before opening Project Profile.
    if not self.apply_quick_settings(show_status=False, persist=False, silent_errors=True):
        return
    existing = self.__dict__.get("_project_profile_wizard")
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return
        except tk.TclError:
            pass
    wizard = ProjectProfileWizard(self, new_project=new_project)
    self._project_profile_wizard = wizard
    wizard.bind(
        "<Destroy>",
        lambda event, w=wizard: self.__dict__.pop("_project_profile_wizard", None)
        if event.widget is w else None,
        add="+",
    )

def open_review(self, *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    ReviewWindow = deps["ReviewWindow"]
    if not (self.guard() and self.entries):
        return
    if self.review_window is not None:
        try:
            if self.review_window.winfo_exists():
                self.review_window.lift()
                self.review_window.focus_force()
                return
        except tk.TclError:
            pass
        self.review_window = None
    # Capture any text still being edited on the main canvas before the
    # review window starts using the shared Entry objects.
    self._sync_entry_editor_texts()
    # Keep the established behavior: proofreading starts with both main
    # canvas OCR aids disabled, even though their controls now live in the
    # main Auxiliary Options section.
    self.settings.review_main_show_ocr_choices = False
    self.settings.review_main_show_ocr_background = False
    if hasattr(self, "quick_bool_vars"):
        for name in ("review_main_show_ocr_choices", "review_main_show_ocr_background"):
            if name in self.quick_bool_vars:
                self.quick_bool_vars[name].set(False)
    review = ReviewWindow(self)
    self.review_window = review
    # Proofreading owns OCR selection while it is open, so simplify the
    # main canvas immediately (unless the user re-enables either aid).
    self.redraw()
