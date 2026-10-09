from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import profile_indent_ui, training_export_ui
from picture_capture.ui.controllers.export import ExportController
from picture_capture.ui_terminology import (
    install_app_tooltip_terminology,
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


def test_dedicated_app_tooltip_terminology_installer_is_retired():
    class DummyApp:
        @staticmethod
        def _attach_tooltip(widget, text):
            return widget, text

    original_descriptor = DummyApp.__dict__["_attach_tooltip"]
    module = SimpleNamespace(PictureCaptureApp=DummyApp)
    install_app_tooltip_terminology(module)

    # Compatibility calls are now no-ops: no descriptor replacement remains.
    assert DummyApp.__dict__["_attach_tooltip"] is original_descriptor
    assert isinstance(original_descriptor, staticmethod)
    assert DummyApp._attach_tooltip("widget", "单行高") == ("widget", "单行高")

    root = Path(__file__).resolve().parents[1]
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    terminology = (
        root / "src/picture_capture/ui_terminology.py"
    ).read_text(encoding="utf-8")

    # Product GUI still installs the global widget normalizer before app import,
    # and tooltip text is rendered by ttk.Label under that shared owner.
    assert gui.index("install_ui_terminology()") < gui.index(
        "from .. import app as app_module"
    )
    assert "install_app_tooltip_terminology" not in gui
    assert "ttk.Label," in terminology


def test_training_export_reuses_main_window_page_scope_without_second_prompt():
    source = inspect.getsource(ExportController.export_training_package)
    assert "app.selected_page_indices()" in source
    assert "simpledialog.askstring" not in source
    assert "主界面页面范围" in source

    shim = inspect.getsource(training_export_ui.export_training_package_selected_range)
    assert "_export_controller_for_call().export_training_package()" in shim
    assert "_start_batch_task" not in shim
