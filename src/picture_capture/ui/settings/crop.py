from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from ...coordinate_space import SOURCE_COORDINATE_SPACE
from ...crop.settings import (
    CROP_SETTINGS_VERSION,
    DEFAULT_UNLINED_BLANK_INK_PERCENT,
    MAX_UNLINED_BLANK_INK_PERCENT,
    MIN_UNLINED_BLANK_INK_PERCENT,
    SINGLE_LINE_MERGE_KEY,
    UNLINED_BLANK_INK_PERCENT_KEY,
    UNLINED_FILTER_BLANK_KEY,
    UNLINED_FILTER_ENABLED_KEY,
)
from ...project_storage import qt_root
from ...single_line_merge_settings import (
    MERGE_HELP,
    MERGE_LABEL,
    load_merge_by_page,
    save_merge_by_page,
)
from ...unlined_export_filter_settings import (
    BLANK_HELP,
    BLANK_LABEL,
    FILTER_HELP,
    FILTER_LABEL,
    THRESHOLD_HELP,
    load_unlined_filter_settings,
    save_unlined_filter_settings,
)
from ..dialogs.crop_settings import CropSettingsDialog


def crop_nonnegative_int(value: object, label: str) -> int:
    try:
        number = int(str(value).strip() or "0")
    except ValueError as exc:
        raise ValueError(f"{label}必须是整数") from exc
    if number < 0:
        raise ValueError(f"{label}不能小于0")
    return number


def build_crop_settings_tab(dialog, tab: ttk.Frame) -> None:
    """Build the integrated crop settings page inside Settings Center."""
    page = dialog._scrollable_settings_page(tab)
    dialog._settings_intro(
        page,
        "切图设置：词条切图 / 插图切图共用",
        "Section=0 页面使用这里的通用上下边界；Section>0 页面由主界面"
        "【六、页面列表】中的 Section 边界接管。所有坐标均为全分辨率原图 X/Y。",
    )

    saved = dialog.parent._load_crop_settings()
    project = getattr(dialog.parent, "project", None)
    project_root = (
        Path(project.root)
        if project is not None and getattr(project, "root", None) is not None
        else None
    )
    merge_by_page = (
        load_merge_by_page(project_root)
        if project_root is not None
        else bool(saved.get(SINGLE_LINE_MERGE_KEY, False))
    )
    if project_root is not None:
        filter_enabled, filter_blank, blank_ink_percent = (
            load_unlined_filter_settings(project_root)
        )
    else:
        filter_enabled = bool(saved.get(UNLINED_FILTER_ENABLED_KEY, False))
        filter_blank = bool(saved.get(UNLINED_FILTER_BLANK_KEY, False))
        try:
            blank_ink_percent = float(
                saved.get(
                    UNLINED_BLANK_INK_PERCENT_KEY,
                    DEFAULT_UNLINED_BLANK_INK_PERCENT,
                )
            )
        except (TypeError, ValueError):
            blank_ink_percent = DEFAULT_UNLINED_BLANK_INK_PERCENT
        blank_ink_percent = max(
            MIN_UNLINED_BLANK_INK_PERCENT,
            min(MAX_UNLINED_BLANK_INK_PERCENT, blank_ink_percent),
        )
    defaults = {
        "general_top_y": int(saved.get("general_top_y", dialog.parent.settings.start_y)),
        "general_bottom_y": int(saved.get("general_bottom_y", 0)),
        "entry_left_padding_x": int(saved.get("entry_left_padding_x", 0)),
        "entry_right_padding_x": int(saved.get("entry_right_padding_x", 0)),
        "integrate_illustrations": bool(saved.get("integrate_illustrations", True)),
        "polygon_margin": int(saved.get("polygon_margin", 0)),
        "parallel_workers": int(
            saved.get("parallel_workers", dialog.parent.settings.crop_parallel_workers)
        ),
        SINGLE_LINE_MERGE_KEY: bool(merge_by_page),
        UNLINED_FILTER_ENABLED_KEY: bool(filter_enabled),
        UNLINED_FILTER_BLANK_KEY: bool(filter_blank),
        UNLINED_BLANK_INK_PERCENT_KEY: float(blank_ink_percent),
    }
    dialog._crop_specials = (
        dict(saved.get("special_pages", {}))
        if isinstance(saved.get("special_pages", {}), dict)
        else {}
    )
    for name, value in defaults.items():
        if name == UNLINED_BLANK_INK_PERCENT_KEY:
            dialog.crop_vars[name] = tk.DoubleVar(value=float(value))
        else:
            dialog.crop_vars[name] = (
                tk.BooleanVar(value=value)
                if isinstance(value, bool)
                else tk.StringVar(value=str(value))
            )

    general = ttk.LabelFrame(page, text="通用切图规则", padding=(12, 10))
    general.pack(fill="x", pady=(0, 10))
    general.columnconfigure(1, weight=1)
    general.columnconfigure(3, weight=1)

    ttk.Label(general, text="一般页切图上边界 Y（原图）：").grid(
        row=0, column=0, sticky="e", pady=4
    )
    ttk.Entry(
        general, textvariable=dialog.crop_vars["general_top_y"], width=12
    ).grid(row=0, column=1, sticky="w", padx=(8, 18), pady=4)
    ttk.Label(general, text="一般页切图下边界 Y（原图）：").grid(
        row=0, column=2, sticky="e", pady=4
    )
    ttk.Entry(
        general, textvariable=dialog.crop_vars["general_bottom_y"], width=12
    ).grid(row=0, column=3, sticky="w", padx=(8, 0), pady=4)
    top_bottom_help = ttk.Label(
        general,
        text="0 = 页面底部；仅用于 Section=0 页面。Section>0 时以该页 Section 边界为准。",
        foreground="#666666",
        justify="left",
    )
    top_bottom_help.grid(
        row=1, column=0, columnspan=4, sticky="w", pady=(0, 6)
    )

    ttk.Label(general, text="词条 X 左侧额外留白：").grid(
        row=2, column=0, sticky="e", pady=4
    )
    ttk.Entry(
        general, textvariable=dialog.crop_vars["entry_left_padding_x"], width=12
    ).grid(row=2, column=1, sticky="w", padx=(8, 18), pady=4)
    ttk.Label(general, text="词条 X 右侧额外留白：").grid(
        row=2, column=2, sticky="e", pady=4
    )
    ttk.Entry(
        general, textvariable=dialog.crop_vars["entry_right_padding_x"], width=12
    ).grid(row=2, column=3, sticky="w", padx=(8, 0), pady=4)
    ttk.Label(
        general,
        text="单位：原图像素；运行时不按页面宽度或窗口缩放换算。",
        foreground="#666666",
    ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(0, 6))

    ttk.Checkbutton(
        general,
        text="综合插图计算词条切图信息",
        variable=dialog.crop_vars["integrate_illustrations"],
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=4)
    ttk.Label(
        general,
        text="关闭后：词条只按自身矩形切图；PPP 不扩框/不联合/不参与词条切图顺序。",
        foreground="#666666",
    ).grid(row=4, column=2, columnspan=2, sticky="w", pady=4)

    ttk.Label(general, text="PPP 多边形外扩（原图）：").grid(
        row=5, column=0, sticky="e", pady=4
    )
    ttk.Entry(
        general, textvariable=dialog.crop_vars["polygon_margin"], width=12
    ).grid(row=5, column=1, sticky="w", padx=(8, 18), pady=4)
    ttk.Label(general, text="并行进程：").grid(
        row=5, column=2, sticky="e", pady=4
    )
    ttk.Entry(
        general, textvariable=dialog.crop_vars["parallel_workers"], width=12
    ).grid(row=5, column=3, sticky="w", padx=(8, 0), pady=4)
    ttk.Label(
        general,
        text="PPP 外扩单位为原图像素；并行进程 0 = 自动，允许 0–8。",
        foreground="#666666",
    ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(0, 4))

    if project_root is not None:
        def persist_merge_by_page() -> None:
            try:
                enabled = bool(dialog.crop_vars[SINGLE_LINE_MERGE_KEY].get())
            except Exception:
                return
            save_merge_by_page(project_root, enabled)

        merge_check = ttk.Checkbutton(
            general,
            text=MERGE_LABEL,
            variable=dialog.crop_vars[SINGLE_LINE_MERGE_KEY],
            command=persist_merge_by_page,
        )
        merge_check.grid(row=7, column=0, columnspan=2, sticky="w", pady=4)
        merge_info = ttk.Label(general, text="ⓘ", foreground="#6b7280", cursor="hand2")
        merge_info.grid(row=7, column=2, sticky="w", padx=(8, 0))

        def show_merge_help() -> None:
            dialog._show_settings_help(MERGE_LABEL, MERGE_HELP)

        dialog._bind_help_widget(merge_check, show_merge_help)
        dialog._bind_help_widget(merge_info, show_merge_help)
        merge_info.bind("<Button-1>", lambda _event: show_merge_help(), add="+")

    if project_root is not None:
        def persist_unlined_filter() -> None:
            try:
                enabled = bool(dialog.crop_vars[UNLINED_FILTER_ENABLED_KEY].get())
                blank = bool(dialog.crop_vars[UNLINED_FILTER_BLANK_KEY].get())
                threshold = float(
                    dialog.crop_vars[UNLINED_BLANK_INK_PERCENT_KEY].get()
                )
            except Exception:
                return
            save_unlined_filter_settings(
                project_root,
                enabled=enabled,
                blank=blank,
                blank_ink_percent=threshold,
            )

        filter_master = ttk.Checkbutton(
            general,
            text=FILTER_LABEL,
            variable=dialog.crop_vars[UNLINED_FILTER_ENABLED_KEY],
        )
        filter_info = ttk.Label(
            general, text="ⓘ", foreground="#6b7280", cursor="hand2"
        )
        filter_blank_check = ttk.Checkbutton(
            general,
            text=BLANK_LABEL,
            variable=dialog.crop_vars[UNLINED_FILTER_BLANK_KEY],
        )
        filter_threshold_label = ttk.Label(general, text="空白墨迹占比≤")
        filter_threshold_spin = ttk.Spinbox(
            general,
            from_=MIN_UNLINED_BLANK_INK_PERCENT,
            to=MAX_UNLINED_BLANK_INK_PERCENT,
            increment=0.1,
            textvariable=dialog.crop_vars[UNLINED_BLANK_INK_PERCENT_KEY],
            width=6,
        )
        filter_percent_label = ttk.Label(general, text="%")

        def sync_unlined_filter_state() -> None:
            master_on = bool(
                dialog.crop_vars[UNLINED_FILTER_ENABLED_KEY].get()
            )
            blank_on = bool(dialog.crop_vars[UNLINED_FILTER_BLANK_KEY].get())
            try:
                filter_blank_check.configure(
                    state="normal" if master_on else "disabled"
                )
                state = "normal" if (master_on and blank_on) else "disabled"
                filter_threshold_spin.configure(state=state)
                filter_threshold_label.configure(state=state)
                filter_percent_label.configure(state=state)
            except tk.TclError:
                pass

        filter_master.configure(
            command=lambda: (sync_unlined_filter_state(), persist_unlined_filter())
        )
        filter_blank_check.configure(
            command=lambda: (sync_unlined_filter_state(), persist_unlined_filter())
        )
        filter_threshold_spin.configure(command=persist_unlined_filter)

        filter_master.grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(5, 2)
        )
        filter_info.grid(row=8, column=2, sticky="w", padx=(8, 0))
        filter_blank_check.grid(
            row=9, column=0, sticky="w", padx=(22, 6), pady=2
        )
        filter_threshold_label.grid(
            row=9, column=1, sticky="e", padx=(4, 2)
        )
        filter_threshold_spin.grid(row=9, column=2, sticky="w")
        filter_percent_label.grid(row=9, column=3, sticky="w", padx=(2, 0))

        def show_filter_help() -> None:
            dialog._show_settings_help(FILTER_LABEL, FILTER_HELP)

        def show_blank_help() -> None:
            dialog._show_settings_help(BLANK_LABEL, BLANK_HELP)

        def show_threshold_help() -> None:
            dialog._show_settings_help("空白墨迹占比阈值", THRESHOLD_HELP)

        dialog._bind_help_widget(filter_master, show_filter_help)
        dialog._bind_help_widget(filter_info, show_filter_help)
        dialog._bind_help_widget(filter_blank_check, show_blank_help)
        for widget in (
            filter_threshold_label,
            filter_threshold_spin,
            filter_percent_label,
        ):
            dialog._bind_help_widget(widget, show_threshold_help)
        filter_info.bind("<Button-1>", lambda _event: show_filter_help(), add="+")
        filter_blank_check.bind(
            "<Button-1>", lambda _event: show_blank_help(), add="+"
        )
        filter_threshold_spin.bind(
            "<FocusOut>", lambda _event: persist_unlined_filter(), add="+"
        )
        filter_threshold_spin.bind(
            "<Return>", lambda _event: persist_unlined_filter(), add="+"
        )
        sync_unlined_filter_state()

    section_info = ttk.LabelFrame(page, text="特殊页面范围", padding=(12, 10))
    section_info.pack(fill="x", pady=(0, 10))
    section_label = ttk.Label(
        section_info,
        text="特殊页面请在主界面【六、页面列表】的 Section 列双击设置。"
             "Section=1 可直接拖动单一上/下边界；Section≥2 可设置多个阅读区。",
        justify="left",
    )
    section_label.pack(anchor="w", fill="x")
    dialog._bind_responsive_labels(
        section_info, section_label, horizontal_padding=12, min_wrap=160
    )

    ttk.Label(
        page,
        text="本页签与设置中心其他设置一样自动保存；不再弹出独立【切图设置】窗口。",
        foreground="#666666",
    ).pack(anchor="w", pady=(0, 4))


def crop_settings_payload(dialog) -> dict:
    if not dialog.crop_vars:
        return dialog.parent._load_crop_settings()
    top = crop_nonnegative_int(
        dialog.crop_vars["general_top_y"].get(), "一般页切图上边界"
    )
    bottom = crop_nonnegative_int(
        dialog.crop_vars["general_bottom_y"].get(), "一般页切图下边界"
    )
    entry_left = crop_nonnegative_int(
        dialog.crop_vars["entry_left_padding_x"].get(), "词条左侧额外留白"
    )
    entry_right = crop_nonnegative_int(
        dialog.crop_vars["entry_right_padding_x"].get(), "词条右侧额外留白"
    )
    margin = crop_nonnegative_int(
        dialog.crop_vars["polygon_margin"].get(), "PPP多边形外扩"
    )
    workers = crop_nonnegative_int(
        dialog.crop_vars["parallel_workers"].get(), "并行进程数"
    )
    if workers > 8:
        raise ValueError("切图并行进程数必须为 0–8")
    if bottom and bottom <= top:
        raise ValueError("一般页切图下边界必须大于上边界，或填0表示页面底部")
    try:
        blank_ink_percent = float(
            dialog.crop_vars[UNLINED_BLANK_INK_PERCENT_KEY].get()
        )
    except (TypeError, ValueError, tk.TclError):
        blank_ink_percent = DEFAULT_UNLINED_BLANK_INK_PERCENT
    blank_ink_percent = max(
        MIN_UNLINED_BLANK_INK_PERCENT,
        min(MAX_UNLINED_BLANK_INK_PERCENT, blank_ink_percent),
    )
    return {
        "version": CROP_SETTINGS_VERSION,
        "coordinate_space": SOURCE_COORDINATE_SPACE,
        "general_top_y": top,
        "general_bottom_y": bottom,
        "entry_left_padding_x": entry_left,
        "entry_right_padding_x": entry_right,
        "integrate_illustrations": bool(
            dialog.crop_vars["integrate_illustrations"].get()
        ),
        "polygon_margin": margin,
        "parallel_workers": workers,
        SINGLE_LINE_MERGE_KEY: bool(
            dialog.crop_vars[SINGLE_LINE_MERGE_KEY].get()
        ),
        UNLINED_FILTER_ENABLED_KEY: bool(
            dialog.crop_vars[UNLINED_FILTER_ENABLED_KEY].get()
        ),
        UNLINED_FILTER_BLANK_KEY: bool(
            dialog.crop_vars[UNLINED_FILTER_BLANK_KEY].get()
        ),
        UNLINED_BLANK_INK_PERCENT_KEY: blank_ink_percent,
        "special_pages": dict(dialog._crop_specials),
    }


def save_integrated_crop_settings(dialog) -> None:
    payload = crop_settings_payload(dialog)
    dialog.parent.settings.crop_parallel_workers = int(payload["parallel_workers"])
    if not dialog.parent.project:
        return
    path = qt_root(dialog.parent.project.root) / CropSettingsDialog.CONFIG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
