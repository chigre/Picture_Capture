from __future__ import annotations

"""Restore Settings Center parameter details on the controls users actually use.

The compact Settings layout intentionally moved long explanations out of the
left form and into the existing right-side detail pane.  The first implementation
bound help to several container Frames rather than to their Entry/Combobox
children.  Tk widget events do not bubble to those parent Frames, so focusing the
real input could leave the right pane on its generic placeholder and make the
parameter explanations appear to have disappeared.

This runtime repair is deliberately presentation-only.  It runs after the compact
Settings builder is installed, binds every Settings variable to the concrete
widget that owns it, and refreshes a few descriptions whose wording predates the
shared OCR channel and the current Layout Core ordinary-drawing path.
"""

import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable


_SETTING_HELP_OVERRIDES = {
    "paddle_lens_mode": (
        "作用：控制 Google Lens 在共享 OCR 通道中的调用方式。off 表示 Lens 完全不运行；"
        "diagnostic 会采集 Lens 结果但不让它参与最终文字投票；conflict 只在本地 OCR 冲突或缺失时调用；"
        "full 允许 Lens 全量参与。\n\n"
        "注意：仅勾选“Google Lens”但把这里设为 off，并不构成一个可运行的 Lens OCR 配置。"
        "通常建议使用 conflict。"
    ),
    "ocr_engine": (
        "兼容字段：这是旧版单 OCR 选择。当前主流程的【仅OCR】和【OCR画线】都使用同一套共享 OCR 通道，"
        "以 PaddleOCR / Tesseract / Google Lens 三个开关及 Lens 运行模式为准。\n\n"
        "旧项目或非 GUI 调用在三个共享开关都未提供有效选择时，才可能读取此字段作为兼容回退；"
        "日常项目不应通过它切换共享 OCR 通道。"
    ),
}

_CHECK_HELP_OVERRIDES = {
    "paddle_use_paddleocr": (
        "开启：把 PaddleOCR 加入共享 OCR 通道。【仅OCR】与【OCR画线】都会复用这一选择；"
        "它可以与 Tesseract、Google Lens 同时开启。\n\n"
        "关闭：只是不让共享通道执行 PaddleOCR，不会自动关闭其他已启用 OCR。"
    ),
    "paddle_compare_tesseract": (
        "开启：把 Tesseract 加入共享 OCR 通道，与 PaddleOCR 在同一图像/候选带上运行。"
        "【仅OCR】可据此比较或选择文字；【OCR画线】则把相同 OCR 证据交给成熟 parser/边界判定。\n\n"
        "需要本机可用的 Tesseract 与相应语言包。"
    ),
    "paddle_enable_lens": (
        "开启：允许 Google Lens 进入共享 OCR 通道；是否真的调用以及是否参与结果，由【Lens 运行模式】决定。\n\n"
        "若运行模式仍为 off，Lens 实际不会执行。Lens 是网络 OCR，不建议作为唯一的默认本地识别来源。"
    ),
    "ordinary_auto_layout": (
        "开启：每页【普通画线】先由当前 Layout Core 解析页面几何和最终行角色，再把所选的逐页版面字段"
        "作为本页临时值使用；结果不会写回下一页。\n\n"
        "当前普通画线的主路径直接消费 Layout Core 的最终 entry 行；只有 Layout 无法形成可用栏结构时，"
        "才进入历史几何 fallback。"
    ),
}


def _descendants(root: tk.Misc) -> Iterable[tk.Misc]:
    for child in root.winfo_children():
        yield child
        yield from _descendants(child)


def _widget_variable(widget: tk.Misc, option: str) -> str:
    try:
        return str(widget.cget(option) or "")
    except (tk.TclError, AttributeError):
        return ""


def _bind_runtime_parameter_help(dialog: Any) -> None:
    """Bind right-pane help to concrete input/check widgets after construction."""

    variables = {
        str(variable): name
        for name, variable in dict(getattr(dialog, "vars", {})).items()
        if variable is not None
    }
    if not variables:
        return

    for widget in _descendants(dialog):
        text_variable = _widget_variable(widget, "textvariable")
        check_variable = _widget_variable(widget, "variable")
        name = variables.get(text_variable) or variables.get(check_variable)
        if not name:
            continue

        is_check = isinstance(widget, (ttk.Checkbutton, tk.Checkbutton))
        if is_check:
            try:
                label = str(widget.cget("text") or name)
            except tk.TclError:
                label = name

            def callback(n=name, l=label) -> None:
                dialog._show_check_help(l, n)
        else:
            show_layout_image = name in getattr(dialog, "SETTING_HELP_IMAGES", {})

            def callback(n=name, hi=show_layout_image) -> None:
                dialog._show_setting_help(n, show_layout_image=hi)

        dialog._bind_help_widget(widget, callback)
        try:
            widget.bind("<Button-1>", lambda _event, cb=callback: cb(), add="+")
        except tk.TclError:
            pass


def install_settings_help_restore(app_module: Any) -> None:
    """Install the post-build Settings help binding/wording repair once."""

    dialog_class = app_module.SettingsDialog
    if bool(getattr(dialog_class, "_pc_settings_help_restore_installed", False)):
        return

    # Copy before updating so no other compatibility layer holding the original
    # dictionaries is mutated unexpectedly.
    dialog_class.SETTING_HELP = dict(getattr(dialog_class, "SETTING_HELP", {}))
    dialog_class.CHECK_HELP = dict(getattr(dialog_class, "CHECK_HELP", {}))
    dialog_class.SETTING_HELP.update(_SETTING_HELP_OVERRIDES)
    dialog_class.CHECK_HELP.update(_CHECK_HELP_OVERRIDES)

    original_init = dialog_class.__init__

    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _bind_runtime_parameter_help(self)

    wrapped_init._pc_settings_help_restore = True  # type: ignore[attr-defined]
    dialog_class.__init__ = wrapped_init
    dialog_class._pc_settings_help_restore_installed = True


__all__ = ["install_settings_help_restore"]
