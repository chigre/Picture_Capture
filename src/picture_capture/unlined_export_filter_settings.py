from __future__ import annotations

"""Filter controls for Layout-derived unlined-row export.

The options live in the existing ``QT/_CropSettings.json`` store because they
belong to the crop/export workflow.  The master switch enables optional export
filters; currently the first filter is ``blank`` based on foreground-ink ratio
measured on the original Layout row crop before any white-border trimming.
"""

from functools import wraps
from pathlib import Path
import json
import os
import tempfile
from typing import Any, Iterable
import tkinter as tk
from tkinter import ttk

from .project_storage import crop_settings_path

CROP_SETTINGS_FILENAME = "_CropSettings.json"
FILTER_ENABLED_KEY = "unlined_export_filter_enabled"
FILTER_BLANK_KEY = "unlined_export_filter_blank"
BLANK_INK_PERCENT_KEY = "unlined_export_blank_ink_percent"
FILTER_LABEL = "未画线行导出过滤"
BLANK_LABEL = "空白"
DEFAULT_BLANK_INK_PERCENT = 0.8
MIN_BLANK_INK_PERCENT = 0.0
MAX_BLANK_INK_PERCENT = 10.0

FILTER_HELP = (
    "开启后，【未画线行导出】会按后面的子条件筛选 Layout 已恢复但当前没有 PDIC 横线的文字行。"
    "目前可选【空白】；如果没有勾选任何子条件，则等同于不过滤。"
)
BLANK_HELP = (
    "只导出接近空白的未画线行。空白判断在白边裁切之前进行：先估计该切片自己的纸张背景亮度，"
    "再计算明显暗于背景的有效墨迹像素占比。墨迹占比不高于设定阈值时视为接近空白。"
    "全白切片也会保留并导出，便于检查 Layout 是否恢复了不存在的文字行。"
)
THRESHOLD_HELP = (
    "接近空白的最大有效墨迹占比。默认 0.8%。值越大，越多含少量字迹/污点的切片会被归为接近空白；"
    "值越小越严格。该比例基于原始 Layout 行框计算，不受后续白边裁切影响。"
)


def _settings_path(project_root: Path) -> Path:
    return crop_settings_path(Path(project_root), CROP_SETTINGS_FILENAME)


def _read_payload(project_root: Path) -> dict[str, Any]:
    path = _settings_path(project_root)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def load_unlined_filter_settings(project_root: Path) -> tuple[bool, bool, float]:
    payload = _read_payload(Path(project_root))
    try:
        threshold = float(payload.get(BLANK_INK_PERCENT_KEY, DEFAULT_BLANK_INK_PERCENT))
    except (TypeError, ValueError):
        threshold = DEFAULT_BLANK_INK_PERCENT
    threshold = max(MIN_BLANK_INK_PERCENT, min(MAX_BLANK_INK_PERCENT, threshold))
    return (
        bool(payload.get(FILTER_ENABLED_KEY, False)),
        bool(payload.get(FILTER_BLANK_KEY, False)),
        float(threshold),
    )


def save_unlined_filter_settings(
    project_root: Path,
    *,
    enabled: bool,
    blank: bool,
    blank_ink_percent: float,
) -> Path:
    path = _settings_path(Path(project_root))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_payload(Path(project_root))
    payload[FILTER_ENABLED_KEY] = bool(enabled)
    payload[FILTER_BLANK_KEY] = bool(blank)
    payload[BLANK_INK_PERCENT_KEY] = float(max(
        MIN_BLANK_INK_PERCENT,
        min(MAX_BLANK_INK_PERCENT, float(blank_ink_percent)),
    ))

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return path


def _walk_widgets(root: tk.Misc) -> Iterable[tk.Misc]:
    for child in root.winfo_children():
        yield child
        yield from _walk_widgets(child)


def _widget_text(widget: tk.Misc) -> str:
    try:
        return str(widget.cget("text") or "")
    except (tk.TclError, AttributeError):
        return ""


def _find_crop_tab(dialog: Any) -> tk.Misc | None:
    for widget in _walk_widgets(dialog):
        if not isinstance(widget, ttk.Notebook):
            continue
        try:
            for tab_id in widget.tabs():
                if "切图" in str(widget.tab(tab_id, "text") or ""):
                    return dialog.nametowidget(tab_id)
        except tk.TclError:
            continue
    return None


def _find_crop_group(tab: tk.Misc) -> tk.Misc:
    frames = [widget for widget in _walk_widgets(tab) if isinstance(widget, ttk.LabelFrame)]
    for wanted in ("通用切图规则", "单行切图", "批量切图"):
        for frame in frames:
            if wanted in _widget_text(frame):
                return frame
    return frames[0] if frames else tab


def _next_grid_row(parent: tk.Misc) -> int:
    rows: list[int] = []
    for child in parent.winfo_children():
        try:
            info = child.grid_info()
            if info:
                rows.append(int(info.get("row", 0)))
        except (tk.TclError, TypeError, ValueError):
            pass
    return max(rows, default=-1) + 1


def _project_root(dialog: Any) -> Path | None:
    project = getattr(getattr(dialog, "parent", None), "project", None)
    root = getattr(project, "root", None)
    return Path(root) if root is not None else None


def _persist(dialog: Any) -> None:
    root = _project_root(dialog)
    if root is None:
        return
    try:
        enabled = bool(dialog.unlined_export_filter_enabled_var.get())
        blank = bool(dialog.unlined_export_filter_blank_var.get())
        threshold = float(dialog.unlined_export_blank_ink_percent_var.get())
    except Exception:
        return
    save_unlined_filter_settings(
        root,
        enabled=enabled,
        blank=blank,
        blank_ink_percent=threshold,
    )


def _install_controls(dialog: Any) -> None:
    if getattr(dialog, "_pc_unlined_filter_controls", None) is not None:
        return
    root = _project_root(dialog)
    tab = _find_crop_tab(dialog)
    if root is None or tab is None:
        return
    group = _find_crop_group(tab)
    enabled, blank, threshold = load_unlined_filter_settings(root)

    enabled_var = tk.BooleanVar(value=enabled)
    blank_var = tk.BooleanVar(value=blank)
    threshold_var = tk.DoubleVar(value=threshold)
    dialog.unlined_export_filter_enabled_var = enabled_var
    dialog.unlined_export_filter_blank_var = blank_var
    dialog.unlined_export_blank_ink_percent_var = threshold_var

    master = ttk.Checkbutton(
        group,
        text=FILTER_LABEL,
        variable=enabled_var,
        command=lambda: (_sync_state(), _persist(dialog)),
    )
    blank_check = ttk.Checkbutton(
        group,
        text=BLANK_LABEL,
        variable=blank_var,
        command=lambda: (_sync_state(), _persist(dialog)),
    )
    threshold_label = ttk.Label(group, text="空白墨迹占比≤")
    threshold_spin = ttk.Spinbox(
        group,
        from_=MIN_BLANK_INK_PERCENT,
        to=MAX_BLANK_INK_PERCENT,
        increment=0.1,
        textvariable=threshold_var,
        width=6,
        command=lambda: _persist(dialog),
    )
    percent_label = ttk.Label(group, text="%")

    def _sync_state() -> None:
        master_on = bool(enabled_var.get())
        blank_on = bool(blank_var.get())
        try:
            blank_check.configure(state="normal" if master_on else "disabled")
            state = "normal" if (master_on and blank_on) else "disabled"
            threshold_spin.configure(state=state)
            threshold_label.configure(state=state)
            percent_label.configure(state=state)
        except tk.TclError:
            pass

    manager = ""
    try:
        manager = next(
            (str(child.winfo_manager() or "") for child in group.winfo_children() if child.winfo_manager()),
            "",
        )
    except tk.TclError:
        manager = ""

    info_widgets: list[tk.Misc] = []
    try:
        if manager == "grid":
            row = _next_grid_row(group)
            master.grid(row=row, column=0, columnspan=2, sticky="w", pady=(5, 2))
            master_info = ttk.Label(group, text="ⓘ", foreground="#6b7280", cursor="hand2")
            master_info.grid(row=row, column=2, sticky="w", padx=(8, 0))
            info_widgets.append(master_info)

            child_row = row + 1
            blank_check.grid(row=child_row, column=0, sticky="w", padx=(22, 6), pady=2)
            threshold_label.grid(row=child_row, column=1, sticky="e", padx=(4, 2))
            threshold_spin.grid(row=child_row, column=2, sticky="w")
            percent_label.grid(row=child_row, column=3, sticky="w", padx=(2, 0))
        else:
            master.pack(anchor="w", pady=(5, 2))
            child = ttk.Frame(group)
            child.pack(anchor="w", padx=(22, 0), pady=2)
            blank_check.pack(in_=child, side="left")
            threshold_label.pack(in_=child, side="left", padx=(10, 2))
            threshold_spin.pack(in_=child, side="left")
            percent_label.pack(in_=child, side="left", padx=(2, 0))
    except tk.TclError:
        for widget in (master, blank_check, threshold_label, threshold_spin, percent_label):
            try:
                widget.destroy()
            except tk.TclError:
                pass
        return

    def _show_help(text: str, title: str) -> None:
        try:
            dialog.help_title_var.set(title)
            dialog.help_body_var.set(text)
        except Exception:
            pass

    for widget in (master, *info_widgets):
        for event in ("<Enter>", "<FocusIn>", "<Button-1>"):
            try:
                widget.bind(event, lambda _e, t=FILTER_HELP: _show_help(t, FILTER_LABEL), add="+")
            except tk.TclError:
                pass
    for widget in (blank_check,):
        for event in ("<Enter>", "<FocusIn>", "<Button-1>"):
            try:
                widget.bind(event, lambda _e, t=BLANK_HELP: _show_help(t, BLANK_LABEL), add="+")
            except tk.TclError:
                pass
    for widget in (threshold_label, threshold_spin, percent_label):
        for event in ("<Enter>", "<FocusIn>"):
            try:
                widget.bind(event, lambda _e, t=THRESHOLD_HELP: _show_help(t, "空白墨迹占比阈值"), add="+")
            except tk.TclError:
                pass

    threshold_spin.bind("<FocusOut>", lambda _e: _persist(dialog), add="+")
    threshold_spin.bind("<Return>", lambda _e: _persist(dialog), add="+")
    _sync_state()
    dialog._pc_unlined_filter_controls = (master, blank_check, threshold_spin)


def install_unlined_export_filter_settings_ui(app_module: Any) -> None:
    dialog = app_module.SettingsDialog
    if bool(getattr(dialog, "_pc_unlined_filter_settings_installed", False)):
        return

    # The integrated crop writer has a fixed historical schema.  Re-append our
    # optional keys after any crop-settings save so they can never be dropped.
    for method_name in (
        "_save_integrated_crop_settings",
        "save", "_save", "apply", "_apply", "save_settings", "_save_settings",
        "apply_settings", "_apply_settings", "save_and_close", "_save_and_close",
    ):
        original = getattr(dialog, method_name, None)
        if not callable(original) or bool(getattr(original, "_pc_unlined_filter_wrapped", False)):
            continue

        @wraps(original)
        def wrapped(self, *args, __original=original, **kwargs):
            result = __original(self, *args, **kwargs)
            _persist(self)
            return result

        wrapped._pc_unlined_filter_wrapped = True  # type: ignore[attr-defined]
        setattr(dialog, method_name, wrapped)

    original_init = dialog.__init__

    @wraps(original_init)
    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _install_controls(self)

    dialog.__init__ = wrapped_init
    dialog._pc_unlined_filter_settings_installed = True


__all__ = [
    "BLANK_INK_PERCENT_KEY",
    "DEFAULT_BLANK_INK_PERCENT",
    "FILTER_BLANK_KEY",
    "FILTER_ENABLED_KEY",
    "load_unlined_filter_settings",
    "save_unlined_filter_settings",
    "install_unlined_export_filter_settings_ui",
]
