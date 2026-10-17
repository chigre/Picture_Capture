"""Machine-local draw inference controls, owned by Settings Center performance tab.

These preferences remain in runtime_environment, not project/AppSettings.
Only newly created OCR/TextDetection engines pick up changed values.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from ...runtime_environment import (
    clear_runtime_caches, runtime_setting, save_runtime_setting,
)


DRAW_DEVICE_OPTIONS = (("auto", "自动"), ("cpu", "仅 CPU"), ("gpu", "优先 GPU"))
MKLDNN_OPTIONS = (("auto", "自动"), ("on", "尝试启用"), ("off", "关闭"))


def validate_draw_inference_values(
    device: str, mkldnn: str, workers: str, *, cpu_limit: int,
) -> tuple[str, str, str]:
    """Validate the entire selection before modifying any machine-local key."""
    device = str(device).strip().lower()
    mkldnn = str(mkldnn).strip().lower()
    workers = str(workers).strip().lower()
    if device not in {key for key, _ in DRAW_DEVICE_OPTIONS}:
        raise ValueError("推理设备必须选择自动、仅 CPU 或优先 GPU")
    if mkldnn not in {key for key, _ in MKLDNN_OPTIONS}:
        raise ValueError("oneDNN 加速必须选择自动、尝试启用或关闭")
    if workers != "auto":
        try:
            count = int(workers)
        except ValueError as exc:
            raise ValueError(f"CPU 进程数请输入 auto 或 1–{cpu_limit} 的整数") from exc
        if not 1 <= count <= max(1, int(cpu_limit)):
            raise ValueError(f"CPU 进程数请输入 auto 或 1–{cpu_limit} 的整数")
        workers = str(count)
    return device, mkldnn, workers


def build_inference_performance_group(dialog, parent: ttk.Frame) -> None:
    """Display the former Environment Center dialog *inline* in Settings Center."""
    cpu_limit = max(1, os.cpu_count() or 1)
    current = {
        "paddle_device": str(runtime_setting("paddle_device", "auto") or "auto"),
        "paddle_mkldnn": str(runtime_setting("paddle_mkldnn", "auto") or "auto"),
        "paddle_cpu_workers": str(runtime_setting("paddle_cpu_workers", "auto") or "auto"),
    }
    device = tk.StringVar(master=dialog, value=current["paddle_device"])
    mkldnn = tk.StringVar(master=dialog, value=current["paddle_mkldnn"])
    workers = tk.StringVar(master=dialog, value=current["paddle_cpu_workers"])
    if device.get() not in {value for value, _ in DRAW_DEVICE_OPTIONS}:
        device.set("auto")
    if mkldnn.get() not in {value for value, _ in MKLDNN_OPTIONS}:
        mkldnn.set("auto")
    try:
        validate_draw_inference_values(device.get(), mkldnn.get(), workers.get(), cpu_limit=cpu_limit)
    except ValueError:
        workers.set("auto")

    group = ttk.LabelFrame(parent, text="画线性能设置（仅当前电脑）", padding=(12, 10))
    group.pack(fill="x", pady=(0, 10))
    ttk.Label(
        group,
        text="同时影响普通画线 TextDetection 与 OCR 画线 PaddleOCR。"
             "这些参数仅保存在本机，不随词典项目迁移，也不受上方项目设置自动保存控制。",
        wraplength=650, justify="left",
    ).pack(anchor="w", pady=(0, 10))

    def add_radios(title: str, variable: tk.StringVar, options: tuple[tuple[str, str], ...]) -> None:
        frame = ttk.LabelFrame(group, text=title, padding=(10, 5))
        frame.pack(fill="x", pady=(0, 7))
        for value, label in options:
            ttk.Radiobutton(frame, text=label, value=value, variable=variable).pack(side="left", padx=(0, 16))

    add_radios("推理设备", device, DRAW_DEVICE_OPTIONS)
    add_radios("MKL-DNN（oneDNN）CPU 加速", mkldnn, MKLDNN_OPTIONS)
    worker_frame = ttk.LabelFrame(group, text="CPU 页面并行进程数", padding=(10, 5))
    worker_frame.pack(fill="x", pady=(0, 7))
    ttk.Label(worker_frame, text=f"自动或整数 1–{cpu_limit}：").pack(side="left")
    ttk.Combobox(
        worker_frame, textvariable=workers, width=9,
        values=("auto", "1", "2", "4", "6", "8", "12", "16", "24", "32"),
    ).pack(side="left", padx=(8, 0))
    ttk.Label(
        group,
        text="CPU 并行数用于 CPU 专用普通画线实验和【精修画线】多页计算；"
             "精修自动=2；手动值按实际 CPU 核心数及剩余页面数执行，不再固定限 2 或 4 页；"
             "仅主协调进程保存 PDIC。设置过高会同时加载多个版面检测模型，可能耗尽内存。"
             "oneDNN 自动优先尝试启用，初始化不兼容时回退，"
             "若推理出错请改为“关闭”。",
        wraplength=650, justify="left",
    ).pack(anchor="w", pady=(0, 8))
    status = tk.StringVar(master=dialog, value="本机设置单独保存；更改前请完成或停止画线任务。")
    buttons = ttk.Frame(group)
    buttons.pack(fill="x")
    ttk.Label(group, textvariable=status, wraplength=650).pack(anchor="w", pady=(5, 0))

    def save_local() -> None:
        if getattr(dialog.parent, "_batch_active", False):
            messagebox.showwarning(
                "画线性能设置", "请先完成或停止当前画线任务，再修改推理设备或加速参数。",
                parent=dialog,
            )
            return
        try:
            chosen_device, chosen_mkldnn, chosen_workers = validate_draw_inference_values(
                device.get(), mkldnn.get(), workers.get(), cpu_limit=cpu_limit,
            )
        except ValueError as exc:
            messagebox.showerror("画线性能设置无效", str(exc), parent=dialog)
            return
        try:
            save_runtime_setting("paddle_cpu_workers", chosen_workers)
            save_runtime_setting("paddle_device", chosen_device)
            save_runtime_setting("paddle_mkldnn", chosen_mkldnn)
            clear_runtime_caches()
            from ...ocr_channel import clear_ocr_channel_paddle_engine_cache
            from ...layout_detection import clear_text_detection_cache
            clear_ocr_channel_paddle_engine_cache()
            clear_text_detection_cache()
        except Exception as exc:
            messagebox.showerror("保存画线性能设置失败", str(exc), parent=dialog)
            return
        status.set("本机画线性能设置已保存；后续新建的模型将使用新配置。")

    ttk.Button(buttons, text="保存本机画线性能设置", command=save_local).pack(side="left")
    # Keep the values on this settings tab instead of reopening a modal window.
    dialog._draw_inference_vars = (device, mkldnn, workers)
