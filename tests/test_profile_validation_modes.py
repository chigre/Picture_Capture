from __future__ import annotations

import inspect

from picture_capture.profile_validation_modes import (
    VALIDATION_MODE_LABELS,
    VALIDATION_MODES,
    mode_uses_ocr,
    normalize_validation_mode,
    build_validation_mode_wizard,
)


def test_profile_validation_exposes_three_user_selectable_modes():
    assert VALIDATION_MODES == (
        ("left_edge", "普通画线"),
        ("paddleocr", "OCR画线"),
        ("combined", "融合画线"),
    )
    assert VALIDATION_MODE_LABELS["combined"] == "融合画线"
    assert normalize_validation_mode("left_edge") == "left_edge"
    assert normalize_validation_mode("unknown") == "paddleocr"
    assert not mode_uses_ocr("left_edge")
    assert mode_uses_ocr("paddleocr")
    assert mode_uses_ocr("combined")


def test_validation_builder_persists_user_default_detection_method():
    source = inspect.getsource(build_validation_mode_wizard)
    assert "validation_default_method_var" in source
    assert "settings.detection_method = normalize_validation_mode" in source
    assert "self.working.detection_method = mode" in source
    assert "软件不会替你评选“最佳模式”" in source


def test_validation_runs_same_representative_pages_for_each_mode():
    source = inspect.getsource(build_validation_mode_wizard)
    assert "indices = list(self.sample_indices)" in source
    assert "settings.detection_method = mode" in source
    assert "force_paddle_refresh=mode_uses_ocr(mode)" in source
    assert "_validation_results_by_mode" in source
    assert "_active_validation_mode" in source


def test_validation_surfaces_page_understanding_and_requires_default_mode_test():
    source = inspect.getsource(build_validation_mode_wizard)
    assert "页面理解（Page Understanding）" in source
    assert "understand_page(" in source
    assert "_understanding_summary(" in source
    assert "_validation_mode_revision" in source
    assert "profile_last_validated_pages = []" in source
    assert "尚未按当前 Profile 完整验证" in source
