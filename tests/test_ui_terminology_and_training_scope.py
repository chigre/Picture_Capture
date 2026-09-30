from __future__ import annotations

import inspect

from picture_capture import profile_indent_ui, training_export_ui
from picture_capture.ui_terminology import normalize_ui_text


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


def test_training_export_reuses_main_window_page_scope_without_second_prompt():
    source = inspect.getsource(training_export_ui.export_training_package_selected_range)
    assert "self.selected_page_indices()" in source
    assert "simpledialog.askstring" not in source
    assert "主界面页面范围" in source
