from __future__ import annotations

from typing import Any
from copy import deepcopy
from dataclasses import fields
import re
import tkinter as tk
from tkinter import messagebox


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
        raw = str(values[name].get()).strip()
        # Tk Spinbox may receive Chinese/full-width decimal punctuation on
        # Windows IMEs. Normalize only decimal marks, never relax the bounds.
        canonical = raw.translate(str.maketrans("，,．。", "...."))
        try:
            numeric = float(canonical)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} 当前输入 {raw!r} 不是有效数字；请使用小数点，如 0.25。") from exc
        if not lower <= numeric <= upper:
            raise ValueError(
                f"{name} 当前输入 {raw!r}（读取值 {numeric:g}），"
                f"必须在 {lower}–{upper} 之间。"
            )
        if name == "separator_y_ink_safe_ink_threshold" and not numeric.is_integer():
            raise ValueError(f"{name} 必须为整数。")
        if canonical != raw and hasattr(values[name], "set"):
            values[name].set(canonical)


def validate_ref_box_controls(values: dict[str, Any]) -> None:
    """Reject invalid REF settings before any AppSettings fields are assigned."""
    limits = {
        "ref_box_fill_opacity": (0.0, 100.0),
        "ref_box_filled_opacity": (0.0, 100.0),
        "ref_text_label_background_opacity": (0.0, 100.0),
        "ref_text_label_gap": (0.0, 60.0),
        "ref_text_label_padding": (0.0, 24.0),
        "ref_box_font_size": (6.0, 72.0),
        "ref_box_width_lines": (0.25, 20.0),
        "ref_box_height_lines": (0.25, 20.0),
        "ref_match_threshold": (0.60, 0.999),
        "ref_match_scale_tolerance_percent": (0.0, 50.0),
    }
    from math import isfinite
    for key, (lower, upper) in limits.items():
        if key not in values:
            continue
        try:
            requested = float(values[key].get())
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{key} 需要有效数字。") from exc
        if not isfinite(requested) or not lower <= requested <= upper:
            raise ValueError(f"{key} 必须在 {lower}–{upper} 之间。")
        if key in {"ref_text_label_gap", "ref_text_label_padding"} and not requested.is_integer():
            raise ValueError(f"{key} 必须为整数。")
        if key == "ref_box_font_size" and not requested.is_integer():
            raise ValueError("REF 字号必须为整数。")
    for key in ("ref_box_fill_color", "ref_box_filled_color", "ref_box_text_color", "ref_text_label_background_color"):
        if key in values:
            from PIL import ImageColor
            try:
                value = str(values[key].get())
                if not value.startswith("#") or len(value) != 7:
                    raise ValueError("expected #RRGGBB")
                ImageColor.getrgb(value)
            except ValueError as exc:
                raise ValueError(f"{key} 必须是 #RRGGBB 颜色。") from exc
    if "ref_ocr_extract_regex" in values:
        pattern = str(values["ref_ocr_extract_regex"].get())
        if len(pattern) > 2000:
            raise ValueError("OCR REF 提取正则不能超过 2000 字符。")
        if pattern.strip():
            try:
                re.compile(pattern, re.DOTALL)
            except re.error as exc:
                raise ValueError(f"OCR REF 提取正则无效：{exc}") from exc


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


def _save_without_partial_settings(dialog: Any, *, close: bool, show_errors: bool) -> bool:
    """A rejected save must not leave some settings changed in memory."""
    settings = dialog.parent.settings
    snapshot = {
        field.name: deepcopy(getattr(settings, field.name))
        for field in fields(settings)
    }
    ok = dialog.save(close=close, show_errors=show_errors)
    if not ok:
        for name, value in snapshot.items():
            setattr(settings, name, value)
    return ok


def run_autosave(dialog: Any) -> None:
    dialog._autosave_job = None
    ok = _save_without_partial_settings(dialog, close=False, show_errors=False)
    if hasattr(dialog, "_settings_save_status_var"):
        dialog._settings_save_status_var.set(
            "✓ 已自动保存"
            if ok
            else "⚠ 当前输入暂未保存；关闭时会提示需要修正的项目"
        )


def validate_settings_now(dialog: Any) -> bool:
    ok = _save_without_partial_settings(dialog, close=False, show_errors=True)
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
    if _save_without_partial_settings(dialog, close=True, show_errors=False):
        return
    reason = str(getattr(dialog, "_last_settings_error", "") or "当前设置存在无效输入")
    if messagebox.askyesno(
        "设置未保存",
        f"{reason}\n\n是否放弃未保存的输入并关闭设置中心？\n选择“否”可返回继续修改。",
        parent=dialog,
        default="no",
    ):
        dialog.destroy()
