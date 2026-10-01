from __future__ import annotations

from pathlib import Path


def test_ocr_crop_preview_uses_exact_canonical_crop_helper():
    import picture_capture.ocr_crop_preview_ui as preview

    source = Path(preview.__file__).read_text(encoding="utf-8")
    assert "entry_ocr_crop_box(" in source
    assert "canonical_box_to_source(" in source
    assert "view_scale" in source
    assert 'text="OCR区域预览"' in source


def test_ocr_crop_preview_distinguishes_regular_and_oversized_entries():
    import picture_capture.ocr_crop_preview_ui as preview

    source = Path(preview.__file__).read_text(encoding="utf-8")
    assert 'meta.entry_scale) == "oversized"' in source
    assert 'short_scale = "大" if oversized else "普"' in source
    assert "REGULAR_COLOR" in source
    assert "OVERSIZED_COLOR" in source


def test_ocr_crop_preview_highlights_proofreading_active_entry():
    import picture_capture.ocr_crop_preview_ui as preview

    source = Path(preview.__file__).read_text(encoding="utf-8")
    assert "_review_entry_highlight_target" in source
    assert "ACTIVE_COLOR" in source
    assert "entry_source" in source
    assert "engine_label" in source


def test_launcher_installs_ocr_crop_preview():
    import picture_capture.launcher as launcher

    source = Path(launcher.__file__).read_text(encoding="utf-8")
    assert "from .ocr_crop_preview_ui import install_ocr_crop_preview" in source
    assert "install_ocr_crop_preview(app_module)" in source
