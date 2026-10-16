from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from ...coordinate_space import SOURCE_COORDINATE_SPACE
from ...crop.settings import (
    CROP_SETTINGS_VERSION,
    DEFAULT_UNLINED_LEFT_WHITE_PERCENT,
    MAX_UNLINED_LEFT_WHITE_PERCENT,
    MIN_UNLINED_LEFT_WHITE_PERCENT,
    SINGLE_LINE_MERGE_KEY,
    UNLINED_LEFT_WHITE_PERCENT_KEY,
    UNLINED_FILTER_BLANK_KEY,
    UNLINED_FILTER_ENABLED_KEY,
)
from ...project_storage import qt_root
from ...formats import write_text_atomic
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


# The integrated crop tab uses custom controls instead of SETTING_HELP fields.
# Every editable control needs a dedicated right-side explanation. The merge
# and unlined-filter controls retain their existing dedicated HELP texts.
CROP_CONTROL_HELP = {
    "general_top_y": ("一般页切图上边界 Y", "作用：Section=0 的普通页面开始切图的原图 Y 像素位置。Section>0 的页面使用本页 Section 上界而不是此值。调整：上移可能包含页眉，下移可能截掉最上方的词条。"),
    "general_bottom_y": ("一般页切图下边界 Y", "作用：Section=0 页面切图结束的原图 Y 像素位置。0 表示整页底部；非零值必须大于上边界。调整：上移可能截断最后的正文，下移可能包含页脚。"),
    "entry_left_padding_x": ("词条 X 左侧额外留白", "作用：在现有词条矩形左边额外保留的原图像素，不随 GUI 缩放变化。调大可保留突出栏左的符号，过大会纳入页边噪声或邻栏。"),
    "entry_right_padding_x": ("词条 X 右侧额外留白", "作用：在词条矩形右侧额外保留的原图像素。调大有利于保留词头末尾和标记，但也会增加邻栏或插图进入输出范围的风险。"),
    "integrate_illustrations": ("综合插图计算词条切图信息", "作用：允许已标注的 PPP 插图参与词条范围扩展、联合和输出顺序。关闭后词条按自身矩形处理，PPP 不再参与词条框调整；独立插图切图功能不受影响。"),
    "polygon_margin": ("PPP 多边形外扩", "作用：插图 ROI 外沿额外增加的原图像素距离，避免图案贴边被切掉。增加会保留更多外部空白或邻近文字；并非缩放整张插图。"),
    "parallel_workers": ("切图并行进程", "作用：决定词条/插图 PNG 导出时同时处理的页面数。0 为自动，1 为串行，最多 8；高分辨率页面开更多进程会增加内存压力和磁盘写入峰值，资源不足时优先用 1–2。它不是插图自动识别的并行设置。"),
    "entry_width_mode": ("词条统一宽度模式", "作用：全项目最宽＝按实际生成的词条 PNG 最大宽度补齐；固定像素＝按下方目标宽度补齐；不补齐＝各输出保持自己的宽度。补齐仅向右增加画布，不压缩或裁剪原内容。"),
    "entry_fixed_width": ("词条固定宽度", "作用：仅在词条宽度模式选择【固定像素】时生效。目标值采用导出 PNG 像素；实际词条比目标值宽时保留原内容，不把图像强行缩小。"),
    "illustration_pad_to_entry_width": ("插图宽度补齐至词条宽度", "作用：启用后，较窄插图 PNG 以词条输出目标宽度补齐空白；比目标更宽的插图不缩小。关闭时插图保持实际 ROI 宽度。"),
    "entry_transparent_background": ("词条白色背景转透明", "作用：导出词条 PNG 时把纯白背景像素转换为透明，不会修改扫描原图或 PDIC。适合透明底词典；关闭则保留白底。浅灰、噪声和非白色像素不保证透明。"),
    "illustration_transparent_background": ("插图背景转透明", "作用：插图多边形 ROI 外部在导出 PNG 时使用透明背景，并处理纯白像素；关闭时多边形外为白色。不会改变 PPP 顶点或原始扫描图。"),
}


def bind_crop_control_help(dialog, container: ttk.Frame) -> None:
    """Attach field-specific help to all custom crop widgets via their Tk vars.

    Variables are allocated before controls. Avoid manually wrapping every
    Entry/Radio/Checkbutton, and do not overwrite the four dedicated unlined
    filter/merge help bindings.
    """
    keys_by_tkvar = {
        str(dialog.crop_vars[name]): name
        for name in CROP_CONTROL_HELP if name in dialog.crop_vars
    }
    def visit(widget) -> None:
        if widget is not container:
            for option in ("textvariable", "variable"):
                try:
                    tkvar = str(widget.cget(option) or "")
                except (tk.TclError, KeyError):
                    continue
                name = keys_by_tkvar.get(tkvar)
                if name is not None:
                    title, body = CROP_CONTROL_HELP[name]
                    dialog._bind_help_widget(
                        widget,
                        lambda title=title, body=body:
                            dialog._show_settings_help(title, body),
                    )
                    break
        for child in widget.winfo_children():
            visit(child)
    visit(container)


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
        filter_enabled, filter_blank, left_white_percent = (
            load_unlined_filter_settings(project_root)
        )
    else:
        filter_enabled = bool(saved.get(UNLINED_FILTER_ENABLED_KEY, False))
        filter_blank = bool(saved.get(UNLINED_FILTER_BLANK_KEY, False))
        try:
            left_white_percent = float(
                saved.get(
                    UNLINED_LEFT_WHITE_PERCENT_KEY,
                    DEFAULT_UNLINED_LEFT_WHITE_PERCENT,
                )
            )
        except (TypeError, ValueError):
            left_white_percent = DEFAULT_UNLINED_LEFT_WHITE_PERCENT
        if not MIN_UNLINED_LEFT_WHITE_PERCENT <= left_white_percent <= MAX_UNLINED_LEFT_WHITE_PERCENT:
            left_white_percent = DEFAULT_UNLINED_LEFT_WHITE_PERCENT
    defaults = {
        "general_top_y": int(saved.get("general_top_y", dialog.parent.settings.start_y)),
        "general_bottom_y": int(saved.get("general_bottom_y", 0)),
        "entry_left_padding_x": int(saved.get("entry_left_padding_x", 0)),
        "entry_right_padding_x": int(saved.get("entry_right_padding_x", 0)),
        "integrate_illustrations": bool(saved.get("integrate_illustrations", True)),
        "polygon_margin": int(saved.get("polygon_margin", 0)),
        "entry_width_mode": str(saved.get("entry_width_mode", "auto")),
        "entry_fixed_width": int(saved.get("entry_fixed_width", 1350)),
        "illustration_pad_to_entry_width": bool(saved.get("illustration_pad_to_entry_width", True)),
        "entry_transparent_background": bool(saved.get("entry_transparent_background", False)),
        "illustration_transparent_background": bool(saved.get("illustration_transparent_background", False)),
        "parallel_workers": int(
            saved.get("parallel_workers", dialog.parent.settings.crop_parallel_workers)
        ),
        SINGLE_LINE_MERGE_KEY: bool(merge_by_page),
        UNLINED_FILTER_ENABLED_KEY: bool(filter_enabled),
        UNLINED_FILTER_BLANK_KEY: bool(filter_blank),
        UNLINED_LEFT_WHITE_PERCENT_KEY: float(left_white_percent),
    }
    dialog._crop_specials = (
        dict(saved.get("special_pages", {}))
        if isinstance(saved.get("special_pages", {}), dict)
        else {}
    )
    for name, value in defaults.items():
        if name == UNLINED_LEFT_WHITE_PERCENT_KEY:
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
                    dialog.crop_vars[UNLINED_LEFT_WHITE_PERCENT_KEY].get()
                )
            except Exception:
                return
            save_unlined_filter_settings(
                project_root,
                enabled=enabled,
                blank=blank,
                left_white_percent=threshold,
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
        filter_threshold_label = ttk.Label(general, text="左侧连续白宽占比>")
        filter_threshold_spin = ttk.Spinbox(
            general,
            from_=MIN_UNLINED_LEFT_WHITE_PERCENT,
            to=MAX_UNLINED_LEFT_WHITE_PERCENT,
            increment=1.0,
            textvariable=dialog.crop_vars[UNLINED_LEFT_WHITE_PERCENT_KEY],
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
            dialog._show_settings_help("左侧连续白宽占比阈值", THRESHOLD_HELP)

        dialog._bind_help_widget(filter_master, show_filter_help)
        dialog._bind_help_widget(filter_info, show_filter_help)
        dialog._bind_help_widget(filter_blank_check, show_blank_help)
        filter_master.bind(
            "<Button-1>", lambda _event: show_filter_help(), add="+"
        )
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


    export_frame = ttk.LabelFrame(page, text="导出 PNG：宽度与透明背景", padding=(12, 10))
    export_frame.pack(fill="x", pady=(0, 10))
    width_var = dialog.crop_vars["entry_width_mode"]
    ttk.Label(export_frame, text="词条统一宽度：").grid(row=0, column=0, sticky="w")
    for column, value, label in (
        (1, "auto", "全项目最宽（推荐）"),
        (2, "fixed", "固定像素"),
        (3, "off", "不补齐"),
    ):
        ttk.Radiobutton(
            export_frame, text=label, value=value, variable=width_var,
        ).grid(row=0, column=column, sticky="w", padx=(8, 0))
    ttk.Label(export_frame, text="固定宽度 (px)：").grid(row=1, column=0, sticky="w", pady=(8, 2))
    fixed_entry = ttk.Entry(
        export_frame, textvariable=dialog.crop_vars["entry_fixed_width"], width=10,
    )
    fixed_entry.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 2))

    def sync_fixed_width(*_args) -> None:
        fixed_entry.configure(state="normal" if width_var.get() == "fixed" else "disabled")

    width_var.trace_add("write", sync_fixed_width)
    sync_fixed_width()
    ttk.Label(
        export_frame,
        text="只向右侧补充画布，不缩放或裁剪；插图超出目标宽度时保留原宽。",
        foreground="#666666",
    ).grid(row=2, column=0, columnspan=4, sticky="w")
    ttk.Checkbutton(
        export_frame, text="插图宽度不足时补齐至词条宽度",
        variable=dialog.crop_vars["illustration_pad_to_entry_width"],
    ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(7, 2))
    ttk.Checkbutton(
        export_frame, text="词条：将纯白背景转透明",
        variable=dialog.crop_vars["entry_transparent_background"],
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=2)
    ttk.Checkbutton(
        export_frame, text="插图：将背景转透明",
        variable=dialog.crop_vars["illustration_transparent_background"],
    ).grid(row=4, column=2, columnspan=2, sticky="w", pady=2)
    ttk.Label(
        export_frame,
        text="插图多边形始终抠出原 ROI；关闭透明时轮廓外为白色，开启时轮廓外及纯白像素透明。",
        foreground="#666666",
    ).grid(row=5, column=0, columnspan=4, sticky="w")

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

    bind_crop_control_help(dialog, page)


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
        left_white_percent = float(
            dialog.crop_vars[UNLINED_LEFT_WHITE_PERCENT_KEY].get()
        )
    except (TypeError, ValueError, tk.TclError):
        left_white_percent = DEFAULT_UNLINED_LEFT_WHITE_PERCENT
    if not MIN_UNLINED_LEFT_WHITE_PERCENT <= left_white_percent <= MAX_UNLINED_LEFT_WHITE_PERCENT:
        raise ValueError("左侧连续白宽占比阈值必须在 0–100% 之间")
    width_mode = (
        str(dialog.crop_vars["entry_width_mode"].get())
        if "entry_width_mode" in dialog.crop_vars else "auto"
    )
    if width_mode not in {"off", "auto", "fixed"}:
        raise ValueError("词条宽度模式无效")
    fixed_width = crop_nonnegative_int(
        dialog.crop_vars["entry_fixed_width"].get()
        if "entry_fixed_width" in dialog.crop_vars else "1350", "手动词条宽度"
    )
    if width_mode == "fixed" and fixed_width < 1:
        raise ValueError("手动词条宽度必须大于0")
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
        "entry_width_mode": width_mode,
        "entry_fixed_width": fixed_width,
        "illustration_pad_to_entry_width": bool(dialog.crop_vars["illustration_pad_to_entry_width"].get()) if "illustration_pad_to_entry_width" in dialog.crop_vars else True,
        "entry_transparent_background": bool(dialog.crop_vars["entry_transparent_background"].get()) if "entry_transparent_background" in dialog.crop_vars else False,
        "illustration_transparent_background": bool(dialog.crop_vars["illustration_transparent_background"].get()) if "illustration_transparent_background" in dialog.crop_vars else False,
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
        UNLINED_LEFT_WHITE_PERCENT_KEY: left_white_percent,
        "special_pages": dict(dialog._crop_specials),
    }


def save_integrated_crop_settings(dialog) -> None:
    payload = crop_settings_payload(dialog)
    dialog.parent.settings.crop_parallel_workers = int(payload["parallel_workers"])
    if not dialog.parent.project:
        return
    path = qt_root(dialog.parent.project.root) / CropSettingsDialog.CONFIG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(
        path, json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )
