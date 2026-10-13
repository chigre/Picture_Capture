from __future__ import annotations

from typing import Any
import tkinter as tk


def schedule_autosave(dialog: Any) -> None:
    if not getattr(dialog, "_autosave_ready", False):
        return
    if hasattr(dialog, "_settings_save_status_var"):
        dialog._settings_save_status_var.set("● 有改动，正在自动保存…")
    job = getattr(dialog, "_autosave_job", None)
    if job is not None:
        try:
            dialog.after_cancel(job)
        except tk.TclError:
            pass
    dialog._autosave_job = dialog.after(450, dialog._run_autosave)


def run_autosave(dialog: Any) -> None:
    dialog._autosave_job = None
    ok = dialog.save(close=False, show_errors=False)
    if hasattr(dialog, "_settings_save_status_var"):
        dialog._settings_save_status_var.set(
            "✓ 已自动保存"
            if ok
            else "⚠ 当前输入暂未保存；关闭时会提示需要修正的项目"
        )


def validate_settings_now(dialog: Any) -> bool:
    ok = dialog.save(close=False, show_errors=True)
    if hasattr(dialog, "_settings_save_status_var"):
        dialog._settings_save_status_var.set(
            "✓ 当前设置有效并已保存" if ok else "⚠ 请修正无效设置"
        )
    return ok


def close_validated(dialog: Any) -> None:
    job = getattr(dialog, "_autosave_job", None)
    if job is not None:
        try:
            dialog.after_cancel(job)
        except tk.TclError:
            pass
        dialog._autosave_job = None
    dialog.save(close=True, show_errors=True)


def physical_row_projection_width_percent(value: object) -> float:
    """Validate the project-persisted percent of column width.

    A native Spinbox does not prevent arbitrary pasted text, so reject values
    outside its range on save instead of silently clamping project settings.
    """
    try:
        percent = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("物理行墨迹投影采样宽度必须是 10–100% 的数字。") from exc
    if not 10.0 <= percent <= 100.0:  # also rejects nan and infinities
        raise ValueError("物理行墨迹投影采样宽度必须在 10–100% 单栏宽之间。")
    return percent
