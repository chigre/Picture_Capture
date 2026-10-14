from __future__ import annotations

from typing import Any
import tkinter as tk


def validate_projection_width(values: dict[str, Any]) -> None:
    """Reject invalid values before the Settings Center mutates the project.

    Spinbox endpoints are advisory: typed strings, nonfinite floats and
    out-of-range values must be rejected before any other field is assigned.
    """
    field = values.get("physical_row_projection_width_percent")
    if field is None:
        return
    try:
        requested = float(field.get())
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(
            "物理行墨迹投影采样宽度必须在 10–100% 单栏宽之间。"
        ) from exc
    if not 10.0 <= requested <= 100.0:
        raise ValueError("物理行墨迹投影采样宽度必须在 10–100% 单栏宽之间。")


def validate_separator_gap_controls(values: dict[str, Any]) -> None:
    """Validate all controls before any project setting is mutated."""
    limits = {
        "separator_y_ink_safe_max_fraction": (0.01, 0.30),
        "separator_y_ink_safe_ink_threshold": (0.0, 255.0),
        "separator_y_ink_safe_existing_ink_ratio": (0.0, 0.20),
        "separator_y_ink_safe_gap_ink_ratio": (0.0, 0.10),
    }
    for name, (lower, upper) in limits.items():
        if name not in values:
            continue
        try:
            numeric = float(values[name].get())
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} 只能输入数字。") from exc
        if not lower <= numeric <= upper:
            raise ValueError(f"{name} 必须在 {lower}–{upper} 之间。")
        if name == "separator_y_ink_safe_ink_threshold" and not numeric.is_integer():
            raise ValueError(f"{name} 必须为整数。")


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
