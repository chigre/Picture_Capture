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


def test_ocr_crop_preview_is_wired_statically():
    import picture_capture.bootstrap.gui as gui_bootstrap
    import picture_capture.ocr_crop_preview_ui as preview

    root = Path(gui_bootstrap.__file__).resolve().parents[2]
    composition = Path(gui_bootstrap.__file__).read_text(encoding="utf-8")
    app_source = (root / "picture_capture" / "app.py").read_text(encoding="utf-8")
    preview_source = Path(preview.__file__).read_text(encoding="utf-8")

    assert "install_ocr_crop_preview(app_module)" not in composition
    assert "add_ocr_crop_preview_control(self, section_row)" in app_source
    assert app_source.count("draw_ocr_crop_preview(self)") == 2
    assert "def add_ocr_crop_preview_control(" in preview_source
    assert "def draw_ocr_crop_preview(" in preview_source
    assert "App.__init__ = init" not in preview_source
    assert "App.redraw = redraw" not in preview_source
    assert "App._draw_ocr_crop_preview =" not in preview_source



def test_crop_preview_early_return_keeps_ocr_preview_overlay():
    import picture_capture.app as app_module

    source = Path(app_module.__file__).read_text(encoding="utf-8")
    start = source.index("    def redraw(self) -> None:")
    end = source.index("\n    def ", start + 10)
    redraw = source[start:end]

    crop_start = redraw.index("        if self.crop_preview_var.get():")
    crop_end = redraw.index("        hidden = bool(self.hide_var.get())", crop_start)
    crop_branch = redraw[crop_start:crop_end]

    assert "draw_ocr_crop_preview(self)" in crop_branch
    assert "draw_layout_visualization_if_enabled(self)" in crop_branch
    assert crop_branch.index("draw_ocr_crop_preview(self)") < crop_branch.index(
        "draw_layout_visualization_if_enabled(self)"
    )
    assert crop_branch.index("draw_layout_visualization_if_enabled(self)") < crop_branch.rindex(
        "return"
    )
    assert redraw.rstrip().endswith("draw_layout_visualization_if_enabled(self)")
    assert redraw.rfind("draw_ocr_crop_preview(self)") < redraw.rfind(
        "draw_layout_visualization_if_enabled(self)"
    )
