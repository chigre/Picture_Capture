from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import profile_indent_ui, training_export_ui
from picture_capture.ui.controllers.export import ExportController
from picture_capture.ui_terminology import (
    install_app_tooltip_terminology,
    install_ui_terminology,
    normalize_ui_text,
)


def test_layout_terms_are_canonical_in_profile_controls():
    labels = [label for label, _field in profile_indent_ui.AUTO_LAYOUT_FIELDS]
    assert "普通字/行高" in labels
    assert "行间空" in labels
    assert "单行高" not in labels
    assert "行间参数" not in labels


def test_legacy_ui_terms_normalize_everywhere():
    assert normalize_ui_text("单行高：") == "普通字/行高："
    assert normalize_ui_text("自动检测单行高") == "自动检测普通字/行高"
    assert normalize_ui_text("行间参数") == "行间空"
    assert normalize_ui_text("行间空") == "行间空"


def test_ui_terminology_installers_are_retired_compatibility_noops():
    import tkinter as tk
    from tkinter import ttk

    class DummyApp:
        @staticmethod
        def _attach_tooltip(widget, text):
            return widget, text

    original_descriptor = DummyApp.__dict__["_attach_tooltip"]
    widget_methods = (
        tk.Label.__init__,
        ttk.Label.__init__,
        tk.StringVar.__init__,
        tk.StringVar.set,
    )

    install_ui_terminology()
    install_app_tooltip_terminology(SimpleNamespace(PictureCaptureApp=DummyApp))

    assert (
        tk.Label.__init__,
        ttk.Label.__init__,
        tk.StringVar.__init__,
        tk.StringVar.set,
    ) == widget_methods
    assert DummyApp.__dict__["_attach_tooltip"] is original_descriptor
    assert isinstance(original_descriptor, staticmethod)
    assert DummyApp._attach_tooltip("widget", "单行高") == ("widget", "单行高")

    root = Path(__file__).resolve().parents[1]
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    terminology = (
        root / "src/picture_capture/ui_terminology.py"
    ).read_text(encoding="utf-8")

    assert "install_ui_terminology()" not in gui
    assert "install_app_tooltip_terminology" not in gui
    assert "cls.__init__ = wrapped_init" not in terminology
    assert "tk.StringVar.__init__ = stringvar_init" not in terminology
    assert "tk.StringVar.set = stringvar_set" not in terminology


def test_product_python_sources_use_canonical_ui_terms():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    compatibility = root / "ui_terminology.py"
    legacy_terms = (
        "三、融合 / OCR画线参数",
        "三、OCR画线参数（默认）",
        "默认只启用 PaddleOCR；Tesseract 与 Google Lens 按需手动开启",
        "只对已有画线做局部 PaddleOCR 补文字",
        "只对已有画线做局部 PaddleOCR 文字识别",
        "逐条做局部 PaddleOCR",
        "按 marker 做局部 PaddleOCR 补字",
        "PaddleOCR 当前页识别",
        "单行高",
        "行间参数",
    )

    offenders = {}
    for source in root.rglob("*.py"):
        if source == compatibility:
            continue
        text = source.read_text(encoding="utf-8")
        found = [term for term in legacy_terms if term in text]
        if found:
            offenders[source.relative_to(root).as_posix()] = found

    assert offenders == {}


def test_training_export_reuses_main_window_page_scope_without_second_prompt():
    source = inspect.getsource(ExportController.export_training_package)
    assert "app.selected_page_indices()" in source
    assert "simpledialog.askstring" not in source
    assert "主界面页面范围" in source

    shim = inspect.getsource(training_export_ui.export_training_package_selected_range)
    assert "_export_controller_for_call().export_training_package()" in shim
    assert "_start_batch_task" not in shim
