"""Paddle runtime versions, PP-OCRv6 support, installed GPU backend diagnostics.

Historical app class names and signatures stay stable; current Tk modules,
thread/queue callbacks, and OCR runtime helpers are injected per invocation.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    import tkinter as tk
    from ..models import AppSettings


def paddle_environment_text_impl(self, settings: AppSettings | None = None, *, deps: dict[str, Any]) -> str:
    importlib_util = deps["importlib_util"]
    resolve_paddle_device = deps["resolve_paddle_device"]
    settings = settings or self.settings
    paddleocr_version = self._distribution_version("paddleocr")
    paddlex_version = self._distribution_version("paddlex")
    paddle_gpu_version = self._distribution_version("paddlepaddle-gpu")
    paddle_cpu_version = self._distribution_version("paddlepaddle")
    paddle_available = importlib_util.find_spec("paddleocr") is not None

    if paddleocr_version:
        lines = [f"✓ PaddleOCR {paddleocr_version}"]
    elif paddle_available:
        lines = ["✓ PaddleOCR：已安装（版本未知）"]
    else:
        return "✗ PaddleOCR：未安装\nPP-OCRv6：不可用（需要 PaddleOCR >= 3.7）\nWindows 推荐运行 install_ocr_windows.bat 安装 CPU/GPU OCR 套件。"

    if paddlex_version:
        lines.append(f"✓ PaddleX {paddlex_version}")

    if paddle_gpu_version and paddle_cpu_version:
        lines.append(f"⚠ PaddlePaddle GPU {paddle_gpu_version} + CPU {paddle_cpu_version} 同时安装")
        lines.append("建议仅保留实际使用的一个 PaddlePaddle runtime，避免 CPU/GPU 包冲突。")
    elif paddle_gpu_version:
        lines.append(f"✓ PaddlePaddle GPU {paddle_gpu_version}")
    elif paddle_cpu_version:
        lines.append(f"✓ PaddlePaddle CPU {paddle_cpu_version}")
    else:
        lines.append("✗ PaddlePaddle runtime：未检测到")

    if self._version_at_least(paddleocr_version, (3, 7)):
        lines.append(f"✓ PP-OCRv6：支持（配置：{settings.paddle_ocr_version or 'PP-OCRv6'}）")
    else:
        lines.append(
            f"✗ PP-OCRv6：当前 PaddleOCR {paddleocr_version or '未知'} 不支持；请升级到 >= 3.7"
        )

    runtime_device = resolve_paddle_device()
    lines.append(f"本机运行设备：{runtime_device}（自动；项目不再固定 CPU/GPU）")
    if str(getattr(settings, "paddle_device", "auto") or "auto").lower() not in {"", "auto"}:
        lines.append("提示：项目中的旧 paddle_device 值仅保留兼容读取，当前运行已忽略该项目级设备设置。")
    try:
        import paddle  # type: ignore
        compiled_cuda = bool(paddle.device.is_compiled_with_cuda())
        if compiled_cuda:
            try:
                gpu_count = int(paddle.device.cuda.device_count())
            except Exception:
                gpu_count = 0
            lines.append(f"CUDA：可用（检测到 {gpu_count} 个 GPU）")
        elif paddle_gpu_version:
            lines.append("CUDA：GPU 版 runtime 已安装，但当前进程未检测到可用 CUDA。")
        else:
            lines.append("CUDA：未启用（CPU runtime）")
    except Exception as exc:
        lines.append(f"Paddle runtime 检查失败：{exc}")
    return "\n".join(lines)
