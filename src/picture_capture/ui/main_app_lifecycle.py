"""Main-window durable worker, batch shutdown and save/close lifecycle.

Runs on the original Tk event thread with the existing public callbacks.
"""
from __future__ import annotations
from typing import Any

def on_close(self, *, deps: dict[str, Any]) -> None:
    messagebox = deps["messagebox"]
    tk = deps["tk"]
    settings_path = deps["settings_path"]
    if getattr(self, "_batch_active", False):
        if not messagebox.askyesno(
            "批量任务正在运行",
            "当前批量任务尚未结束。是否停止任务并在当前页处理完成后退出？",
            parent=self,
        ):
            return
        self._batch_close_after_stop = True
        self._request_batch_stop()
        return

    # Durable one-shot workers must finish their success/error cleanup
    # boundary before the process can disappear.
    if self._ui_worker_close_wait:
        if not self._ui_close_requested:
            self._ui_close_requested = True
            for key in tuple(self._ui_worker_generations):
                self._invalidate_ui_worker(key)
            self.status_var.set("正在完成后台文件操作，完成后自动退出…")
            try:
                self.withdraw()
            except tk.TclError:
                pass
            if self._ui_worker_poll_job is None:
                self._ui_worker_poll_job = self.after(40, self._poll_ui_worker_queue)
        return

    try:
        self._cancel_system_appearance_poll()
        self._ui_worker_shutdown = True
        self._ui_close_requested = True
        for key in tuple(self._ui_worker_generations):
            self._invalidate_ui_worker(key)
        if self._ui_worker_poll_job is not None:
            try:
                self.after_cancel(self._ui_worker_poll_job)
            except tk.TclError:
                pass
            self._ui_worker_poll_job = None
        self._flush_deferred_page_save()
        if self.project and self.current_page and self.image is not None:
            try:
                self.save_pdic(silent=True)
                self._save_normalized_ppp()
                self.settings.to_json(settings_path(self.project.root))
            except (OSError, ValueError, tk.TclError):
                pass
        self._save_session_state()
    finally:
        self.destroy()


# The source-coordinate safety policy is pure and belongs with the main UI
# guard, not with the Tk composition root.  Keep the historical app function
# as a live delegate because external users may patch it at call time.
def transformed_geometry_pending(settings: Any) -> bool:
    """Refuse editing when the configured image transform lacks an adapter."""
    return str(getattr(settings, "layout_transform", "identity") or "identity") not in {
        "identity", "mirror_x", "rotate_ccw90", "rotate_cw90",
    }


# Main editing guard retains the original Tk/worker transaction policy.

def guard(self, *, deps: dict[str, Any]) -> bool:
    messagebox = deps["messagebox"]
    if self._preprocess_mode_active():
        self.status_var.set("预处理模式中：普通编辑已锁定，请先退出预处理模式。")
        return False
    if getattr(self, "_batch_active", False):
        if not self._claim_page_for_manual_edit():
            return False
    if not self.project or not self.current_page or self.image is None:
        messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
        return False
    return True


def _guard_transformed_geometry(self, action: str, *, deps: dict[str, Any]) -> bool:
    transformed_geometry_pending = deps["transformed_geometry_pending"]
    if not transformed_geometry_pending(self.settings):
        return True
    message = (
        f"{action}尚未启用 {self.settings.layout_transform} 的完整 原图坐标适配；"
        "为避免写入错误 PDIC 或方向错误的切图，本次操作已取消。"
    )
    self.status_var.set(message)
    return False


def clear_entries(self, *, deps: dict[str, Any]) -> None:
    """Never clear source-coordinate markers before edit guard and confirmation."""
    messagebox = deps["messagebox"]
    if self.guard() and messagebox.askyesno(
        "清除画线", "清除当前页全部词条标记？", parent=self,
    ):
        self.entries.clear()
        self.redraw()


def show_error(self, title: str, exc: Exception, *, deps: dict[str, Any]) -> None:
    """Report UI errors with the same status, modal and traceback ordering."""
    messagebox = deps["messagebox"]
    traceback = deps["traceback"]
    self.status_var.set(f"{title}：{exc}")
    messagebox.showerror(
        title, f"{exc}\n\n详细信息已输出到终端。", parent=self,
    )
    traceback.print_exc()
