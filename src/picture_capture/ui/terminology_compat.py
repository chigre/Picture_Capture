from __future__ import annotations

"""Pure compatibility helpers for historical UI terminology.

Product UI sources now own the canonical wording directly. The replacement
table remains available for compatibility tests and callers that explicitly
normalize historical text, but GUI bootstrap no longer mutates Tk/ttk widget
constructors or StringVar methods.
"""

from typing import Any


_REPLACEMENTS = (
    ("三、融合 / OCR画线参数", "三、共享 OCR 通道 / OCR画线"),
    ("三、OCR画线参数（默认）", "三、共享 OCR 通道 / OCR画线"),
    (
        "默认只启用 PaddleOCR；Tesseract 与 Google Lens 按需手动开启",
        "共享 OCR 通道默认只启用 PaddleOCR；Tesseract 与 Google Lens 可同时启用；【仅OCR】与【OCR画线】共用这些选择",
    ),
    (
        "只对已有画线做局部 PaddleOCR 补文字",
        "只对已有画线调用共享 OCR 通道补文字，可同时使用多个 OCR",
    ),
    (
        "只对已有画线做局部 PaddleOCR 文字识别",
        "只对已有画线调用共享 OCR 通道做局部文字识别",
    ),
    ("逐条做局部 PaddleOCR", "逐条调用共享 OCR 通道"),
    ("按 marker 做局部 PaddleOCR 补字", "按 marker 调用共享 OCR 通道补字"),
    ("PaddleOCR 当前页识别", "OCR画线 当前页识别"),
    ("单行高", "普通字/行高"),
    ("行间参数", "行间空"),
)


def normalize_ui_text(value: Any) -> Any:
    """Return canonical wording for one historical presentation value."""
    if not isinstance(value, str):
        return value
    text = value
    for old, new in _REPLACEMENTS:
        text = text.replace(old, new)
    return text


def install_ui_terminology() -> None:
    """Compatibility no-op; product terminology is source-native."""
    return None


def install_app_tooltip_terminology(app_module: Any) -> None:
    """Compatibility no-op; product tooltip wording is source-native."""
    _ = app_module


__all__ = [
    "install_app_tooltip_terminology",
    "install_ui_terminology",
    "normalize_ui_text",
]
