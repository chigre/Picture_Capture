"""Regression coverage for the fixed active proofreading crop."""
from picture_capture.review_pinned_entry_preview import doubled_crop_box


def test_doubles_crop_height_without_resizing_image():
    assert doubled_crop_box((10, 40, 110, 60), 200) == (10, 30, 110, 70)


def test_clamps_to_page_top_and_bottom_while_preserving_target_height():
    assert doubled_crop_box((10, 0, 110, 20), 200) == (10, 0, 110, 40)
    assert doubled_crop_box((10, 180, 110, 200), 200) == (10, 160, 110, 200)


def test_cannot_extend_past_short_page():
    assert doubled_crop_box((0, 20, 40, 70), 80) == (0, 0, 40, 80)


def test_fixed_preview_does_not_depend_on_typed_text():
    from pathlib import Path
    import picture_capture.review_entry_classification_ui as review
    import picture_capture.review_pinned_entry_preview as preview

    review_source = Path(review.__file__).read_text(encoding="utf-8")
    preview_source = Path(preview.__file__).read_text(encoding="utf-8")
    assert 'text="词条类型："' not in review_source
    assert "ttk.Combobox(" not in review_source.split(
        "def initialize_review_entry_classification", 1
    )[1]
    assert 'before=window.canvas' in preview_source
    assert "ttk.Entry(" not in preview_source
    assert "refresh_pinned_entry_preview(window)" in review_source
