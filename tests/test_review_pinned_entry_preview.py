"""Regression tests for one (and only one) pinned proofreading preview.

The legacy review_pinned_entry_preview widget used to insert a second
image between the black-framed active preview and the ordinary editor rows.
"""
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture.models import AppSettings, Entry


def test_review_has_exactly_one_pinned_preview_owner():
    import picture_capture.app as app
    import picture_capture.review_entry_classification_ui as classification_ui

    app_source = Path(app.__file__).read_text(encoding="utf-8")
    classification_source = Path(classification_ui.__file__).read_text(encoding="utf-8")
    assert app_source.count("self.active_crop_host = ttk.Frame(editor_area") == 1
    assert app_source.count("self.active_crop_label = tk.Label(self.active_crop_frame") == 1
    assert "initialize_review_entry_classification" not in app_source
    assert "initialize_pinned_entry_preview" not in classification_source
    assert "refresh_pinned_entry_preview" not in classification_source
    assert not (Path(app.__file__).parent / "review_pinned_entry_preview.py").exists()


def test_all_inline_crops_ignore_detected_large_head_height(monkeypatch):
    import picture_capture.app as app

    settings = AppSettings(
        character_height=30,
        row_padding=2,
        entry_regular_crop_height=36,
        entry_oversized_crop_height=96,
    )
    entry = Entry(
        word="八階",
        x=12,
        y=70,
        ocr_source="ordinary_large_head_evidence",
        ocr_visual_run_height=110.0,
        ocr_oversized_cjk=True,
    )
    geometry = SimpleNamespace(transform=SimpleNamespace(kind="identity"), top=0)
    image = Image.new("RGB", (180, 400), "white")
    monkeypatch.setattr(app, "line_box", lambda *_args: (10, 70, 110, 100))

    ordinary = app._review_line_box(
        entry, geometry, image, settings, ordinary_height_only=True,
    )
    classified = app._review_line_box(entry, geometry, image, settings)
    assert ordinary[3] - ordinary[1] == 36
    assert classified[3] - classified[1] > 36


def test_pinned_preview_uses_regular_source_box_while_rows_stay_normal():
    import picture_capture.app as app

    source = Path(app.__file__).read_text(encoding="utf-8")
    worker = source.split("        def worker():", 1)[1].split("        def done(payload)", 1)[0]
    pinned = source.split("    def _update_active_crop_preview(", 1)[1].split(
        "    def _ordinary_review_photo(", 1
    )[0]
    assert "ordinary_height_only=True" in worker
    assert "ordinary_height_only=True" in pinned
    assert "2 * crop.height" in pinned
    assert 'themed_display_image(crop, self.parent.appearance_mode)' in source
