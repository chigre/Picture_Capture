from __future__ import annotations

"""Small runtime terminology normalizer for the legacy monolithic UI.

The application still has several UI surfaces in ``app.py`` whose historical
wording exposes implementation history rather than the current architecture.
This module keeps presentation terminology aligned without changing persisted
field names or algorithm semantics.

Only narrow presentation strings are changed:
* 单行高 -> 普通字/行高
* 行间参数 -> 行间空
* the main OCR section is presented as a shared OCR channel plus an OCR-assisted
  boundary consumer

The OCR wording matters because Paddle/Tesseract/Lens selection is shared by
【仅OCR】 and OCR-assisted boundary detection. Engine selection is no longer a
private sub-feature of “OCR画线”.
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
    (
        "逐条做局部 PaddleOCR",
        "逐条调用共享 OCR 通道",
    ),
    (
        "按 marker 做局部 PaddleOCR 补字",
        "按 marker 调用共享 OCR 通道补字",
    ),
    ("PaddleOCR 当前页识别", "OCR画线 当前页识别"),
    ("单行高", "普通字/行高"),
    ("行间参数", "行间空"),
)
_INSTALLED = False


def normalize_ui_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value
    for old, new in _REPLACEMENTS:
        text = text.replace(old, new)
    return text


def _normalize_values(value: Any) -> Any:
    if isinstance(value, tuple):
        return tuple(normalize_ui_text(item) for item in value)
    if isinstance(value, list):
        return [normalize_ui_text(item) for item in value]
    return value


def install_ui_terminology() -> None:
    """Normalize canonical UI terms on all Tk/ttk text surfaces.

    This runs before any application windows are constructed. It is a
    presentation-only compatibility layer for the large historical ``app.py``;
    new modules should write the canonical labels directly.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    import tkinter as tk
    from tkinter import ttk

    widget_classes = (
        tk.Label,
        tk.Button,
        tk.Checkbutton,
        tk.Radiobutton,
        tk.LabelFrame,
        tk.Message,
        ttk.Label,
        ttk.Button,
        ttk.Checkbutton,
        ttk.Radiobutton,
        ttk.LabelFrame,
        ttk.Menubutton,
        ttk.Combobox,
    )

    for cls in widget_classes:
        original_init = cls.__init__
        if getattr(original_init, "_pc_terminology_wrapped", False):
            continue

        def wrapped_init(self, *args, __original=original_init, **kwargs):
            if "text" in kwargs:
                kwargs["text"] = normalize_ui_text(kwargs["text"])
            if "values" in kwargs:
                kwargs["values"] = _normalize_values(kwargs["values"])
            return __original(self, *args, **kwargs)

        wrapped_init._pc_terminology_wrapped = True  # type: ignore[attr-defined]
        cls.__init__ = wrapped_init  # type: ignore[method-assign]

    original_stringvar_init = tk.StringVar.__init__
    original_stringvar_set = tk.StringVar.set

    if not getattr(original_stringvar_init, "_pc_terminology_wrapped", False):
        def stringvar_init(self, *args, **kwargs):
            if "value" in kwargs:
                kwargs["value"] = normalize_ui_text(kwargs["value"])
            return original_stringvar_init(self, *args, **kwargs)

        stringvar_init._pc_terminology_wrapped = True  # type: ignore[attr-defined]
        tk.StringVar.__init__ = stringvar_init  # type: ignore[method-assign]

    if not getattr(original_stringvar_set, "_pc_terminology_wrapped", False):
        def stringvar_set(self, value):
            return original_stringvar_set(self, normalize_ui_text(value))

        stringvar_set._pc_terminology_wrapped = True  # type: ignore[attr-defined]
        tk.StringVar.set = stringvar_set  # type: ignore[method-assign]


def install_app_tooltip_terminology(app_module: Any) -> None:
    """Normalize tooltip/help text while preserving the original descriptor.

    ``PictureCaptureApp._attach_tooltip`` is a ``@staticmethod`` in the legacy
    monolithic UI. Replacing it with a normal function would make Python bind
    ``self`` on instance access and therefore add one positional argument. The
    wrapper deliberately inspects ``__dict__`` and re-installs the same
    descriptor kind so runtime calling semantics cannot change.
    """
    app_class = getattr(app_module, "PictureCaptureApp", None)
    if app_class is None:
        return

    descriptor = app_class.__dict__.get("_attach_tooltip")
    if descriptor is None:
        return

    if isinstance(descriptor, staticmethod):
        original = descriptor.__func__
        if getattr(original, "_pc_terminology_wrapped", False):
            return

        def wrapped(widget, text, *args, **kwargs):
            return original(widget, normalize_ui_text(text), *args, **kwargs)

        wrapped._pc_terminology_wrapped = True  # type: ignore[attr-defined]
        app_class._attach_tooltip = staticmethod(wrapped)
        return

    if isinstance(descriptor, classmethod):
        original = descriptor.__func__
        if getattr(original, "_pc_terminology_wrapped", False):
            return

        def wrapped(cls, widget, text, *args, **kwargs):
            return original(cls, widget, normalize_ui_text(text), *args, **kwargs)

        wrapped._pc_terminology_wrapped = True  # type: ignore[attr-defined]
        app_class._attach_tooltip = classmethod(wrapped)
        return

    original = descriptor
    if getattr(original, "_pc_terminology_wrapped", False):
        return

    def wrapped(self, widget, text, *args, **kwargs):
        return original(self, widget, normalize_ui_text(text), *args, **kwargs)

    wrapped._pc_terminology_wrapped = True  # type: ignore[attr-defined]
    app_class._attach_tooltip = wrapped
