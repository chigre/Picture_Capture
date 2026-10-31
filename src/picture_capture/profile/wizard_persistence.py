"""Explicit Profile wizard save, step transitions and close behavior; no schema changes."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import AppSettings


def persist_current_profile(
    self, *, finalize: bool = False, apply_runtime: bool = False,

    deps,
) -> AppSettings:
    replace = deps["replace"]
    copy_settings = deps["copy_settings"]
    settings_path = deps["settings_path"]
    write_project_profile = deps["write_project_profile"]
    project_profile_path = deps["project_profile_path"]
    """Write current Wizard fields so navigation/closing cannot lose work."""
    settings = self._settings_from_ui()
    if not finalize:
        # A partial Wizard save is a recoverable draft, not proof that a
        # new-project Profile has completed the full setup workflow.
        settings.profile_setup_version = int(
            getattr(self.working, "profile_setup_version", 0) or 0
        )
    settings.profile_last_validated_pages = list(
        getattr(self.working, "profile_last_validated_pages", []) or []
    )
    copy_settings(self.parent.settings, settings)
    self.parent.settings.to_json(settings_path(self.project.root))
    write_project_profile(
        project_profile_path(self.project.root),
        self.parent.settings,
        self.parent.settings.dictionary_profile_id,
        force=True,
    )
    self.working = replace(settings)
    self.parent.sync_quick_settings()
    if apply_runtime:
        self.parent.redraw()
    return settings



def save_profile_progress(
    self, *, finalize: bool = False, apply_runtime: bool = False,
    status: str = "Project Profile 当前内容已保存",

    deps,
) -> bool:
    messagebox = deps["messagebox"]
    try:
        self._persist_current_profile(
            finalize=finalize, apply_runtime=apply_runtime,
        )
        self.parent.status_var.set(status)
        return True
    except Exception as exc:
        messagebox.showerror(
            "Project Profile 保存失败", str(exc), parent=self,
        )
        return False



def move_step(self, delta: int) -> None:
    # 上一步 / 下一步 are explicit save points.
    if not self._save_profile_progress():
        return
    current = self.notebook.index(self.notebook.select())
    target = max(0, min(len(self.tabs) - 1, current + int(delta)))
    self.notebook.select(self.tabs[target])
    if (current == 0 and target == 1 and self.working.dictionary_layout_kind != "illustrated"
            and not self._analysis_suggestion and not self._analysis_running):
        self.analyze_representative_pages(auto_apply=True)



def save_and_close(self, *, deps) -> None:
    messagebox = deps["messagebox"]
    # The confirmation button saves immediately, even if the user chooses
    # to go back to validation instead of closing the Wizard.
    if not self._save_profile_progress(
        finalize=False,
        status="Project Profile 当前内容已保存",
    ):
        return
    try:
        if not self.working.profile_last_validated_pages:
            if not messagebox.askyesno(
                "Profile 尚未完整验证",
                "当前设置尚未通过全部代表页测试，或测试后又修改了设置。\n\n"
                "建议先到【4 测试与确认】运行“测试当前 Profile”。"
                "是否仍然保存并使用当前设置？",
                parent=self,
            ):
                self.notebook.select(self.tabs[3])
                return
        if not self._save_profile_progress(
            finalize=True,
            apply_runtime=True,
            status="Project Profile 已保存并应用",
        ):
            return
        self._closing = True
        if self._validation_running:
            self._validation_close_requested = True
            self._validation_stop_event.set()
            self.validation_status_var.set("正在安全结束当前测试页，完成后关闭…")
            return
        self.destroy()
    except Exception as exc:
        messagebox.showerror("Project Profile 保存失败", str(exc), parent=self)



def close_without_save(self, *, deps) -> None:
    messagebox = deps["messagebox"]
    PROFILE_SETUP_VERSION = deps["PROFILE_SETUP_VERSION"]
    # 关闭也先保存当前页；因此误关窗口不会丢掉尚未切页的输入。
    if not self._save_profile_progress(
        finalize=False,
        apply_runtime=True,
        status="Project Profile 当前内容已保存",
    ):
        return
    if self.new_project and int(
        getattr(self.parent.settings, "profile_setup_version", 0) or 0
    ) < PROFILE_SETUP_VERSION:
        if not messagebox.askyesno(
            "尚未完成 Project Profile",
            "当前内容已经保存。项目 Profile 尚未完整确认，确定先关闭吗？"
            "以后可从【项目Profile】继续。",
            parent=self,
        ):
            return
    self._closing = True
    if self._validation_running:
        self._validation_close_requested = True
        self._validation_stop_event.set()
        self.validation_status_var.set("正在安全结束当前测试页，完成后关闭…")
        return
    self.destroy()

