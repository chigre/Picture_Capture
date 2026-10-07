from __future__ import annotations

from pathlib import Path

from picture_capture import app, overlay_layout_helpers as overlay


def test_phase7f_app_reexports_overlay_layout_helpers() -> None:
    for name in (
        "effective_main_overlay_font_size",
        "scaled_overlay_line_width",
        "review_auto_fit_zoom",
        "binary_preview_image",
        "vertical_marker_contact_gap",
        "vertical_overlay_layout",
        "vertical_ocr_menu_layout",
        "transformed_entry_anchor",
        "horizontal_overlay_layout",
        "horizontal_ocr_menu_layout",
        "entry_index_label_layout",
    ):
        assert getattr(app, name) is getattr(overlay, name)


def test_phase7f_overlay_helper_module_is_gui_independent() -> None:
    source = Path(overlay.__file__).read_text(encoding="utf-8")
    assert "tkinter" not in source
    assert "picture_capture.app" not in source
    assert "from .app import" not in source
