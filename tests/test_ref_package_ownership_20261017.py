"""Smoke coverage for physically migrated REF geometry helpers."""
from picture_capture.ref.box_geometry import hit_test, transform_box
from picture_capture.ref.text_label_layout import ref_text_label_rect
from picture_capture.ref.boxes import RefBox
from picture_capture.ref.detection import detect_ref_boxes_page
from picture_capture.ref.ocr import ocr_ref_boxes_page


def test_ref_geometry_and_label_modules_are_owned_by_ref_package():
    assert hit_test.__module__ == "picture_capture.ref.box_geometry"
    assert ref_text_label_rect.__module__ == "picture_capture.ref.text_label_layout"
    box = RefBox(id=1, x=20, y=30, w=40, h=25, entry_index=None)
    found, action = hit_test([box], 40, 42, scale=1.0)
    assert (found, action) == (box, "move")
    moved = transform_box(box, "move", start=(40, 42), current=(45, 48), image_size=(200, 150))
    assert (moved.x, moved.y, moved.w, moved.h) == (25, 36, 40, 25)
    x, y, w, h = ref_text_label_rect((20, 30, 40, 25), (200, 150), text="see also", scale=1, font_size=14)
    assert 0 <= x < 200 and 0 <= y < 150 and x + w <= 200 and y + h <= 150


def test_ref_business_modules_physically_owned_by_ref_package():
    from pathlib import Path
    import picture_capture
    root = Path(picture_capture.__file__).resolve().parent
    for former in ("ref_boxes.py", "ref_box_detection.py", "ref_box_ocr.py"):
        assert not (root / former).exists(), former
    assert RefBox.__module__ == "picture_capture.ref.boxes"
    assert detect_ref_boxes_page.__module__ == "picture_capture.ref.detection"
    assert ocr_ref_boxes_page.__module__ == "picture_capture.ref.ocr"
