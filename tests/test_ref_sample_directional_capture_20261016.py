from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.ref_box_detection import (
    add_ref_sample,
    default_ref_sample_direction,
    delete_ref_sample,
    detect_ref_boxes_page,
    list_ref_samples,
    read_ref_sample_metadata,
    ref_box_after_guide,
    write_ref_sample_metadata,
)
from picture_capture.ref_boxes import read_ref_boxes
from picture_capture.ui.ref_box_controller import RefBoxController
from picture_capture.ui.settings import schema


@pytest.mark.parametrize(
    ("direction", "include", "expected"),
    [
        ("after", False, (120, 44, 40, 20)),
        ("after", True, (100, 44, 60, 20)),
        ("before", False, (60, 44, 40, 20)),
        ("before", True, (60, 44, 60, 20)),
    ],
)
def test_auto_ref_geometry_guide_width_and_direction(direction, include, expected):
    settings = AppSettings(
        character_height=20, row_padding=0, ref_box_width_lines=2,
        ref_box_height_lines=1, ref_box_include_guide_width=include,
    )
    assert ref_box_after_guide((100, 50, 20, 8), (300, 200), settings, direction) == expected


def test_auto_ref_geometry_clipped_and_no_content_room():
    settings = AppSettings(
        character_height=20, row_padding=0, ref_box_width_lines=2,
        ref_box_height_lines=1, ref_box_include_guide_width=True,
    )
    assert ref_box_after_guide((10, 50, 20, 8), (300, 200), settings, "before") == (0, 44, 30, 20)
    assert ref_box_after_guide((280, 50, 20, 8), (300, 200), settings, "after") is None
    assert ref_box_after_guide((0, 50, 20, 8), (300, 200), settings, "before") is None


def test_template_metadata_category_direction_and_deletion(tmp_path):
    page = tmp_path / "00001.png"
    Image.new("RGB", (200, 100), "white").save(page)
    sample = add_ref_sample(page, (10, 10, 30, 30), category="别名", direction="before")
    assert sample in list_ref_samples(tmp_path)
    assert read_ref_sample_metadata(sample) == {"category": "别名", "direction": "before"}
    write_ref_sample_metadata(sample, category="亦作", direction="after")
    assert read_ref_sample_metadata(sample) == {"category": "亦作", "direction": "after"}
    assert sample.with_suffix(".json").exists()
    delete_ref_sample(sample, tmp_path)
    assert not sample.exists()
    assert not sample.with_suffix(".json").exists()


def test_capture_direction_defaults_and_settings_location():
    assert default_ref_sample_direction("别名") == "before"
    assert default_ref_sample_direction("参见") == "after"
    assert AppSettings().ref_box_include_guide_width is False
    assert any(name == "ref_box_include_guide_width" for _, name in schema.REF_BOX_GEOMETRY_CHECKS)


def test_capture_release_stays_active_until_explicit_exit(tmp_path, monkeypatch):
    page = tmp_path / "1.png"
    saved = []
    monkeypatch.setattr(
        "picture_capture.ui.ref_box_controller.add_ref_sample",
        lambda image_path, rect, **kwargs: (
            saved.append((image_path, rect, kwargs)) or Path("sample.png")
        ),
    )
    app = SimpleNamespace(
        current_page=page, image=SimpleNamespace(width=400, height=300),
        canvas=Mock(), redraw=Mock(), show_error=Mock(),
        status_var=SimpleNamespace(set=Mock()),
    )
    controller = RefBoxController(app)
    controller.loaded_page = page
    controller.capture_sample = True
    controller.capture_category = "别名"
    controller.capture_direction = "before"
    controller.drag_start = (10, 20)
    controller.pointer_action = "skip"  # bypass preview; exercise commit + mode state
    assert controller.release(30, 40) == "break"
    assert controller.capture_sample is True
    assert saved[0][2] == {"category": "别名", "direction": "before"}
    assert controller.cancel_capture() == "break"
    assert controller.capture_sample is False


@pytest.mark.parametrize(
    ("direction", "expected_x", "expected_w"),
    [
        ("after", 100, 60),
        ("before", 60, 60),
    ],
)
def test_detect_page_uses_template_metadata_direction(
    tmp_path, monkeypatch, direction, expected_x, expected_w,
):
    import picture_capture.ref_box_detection as detection

    page = tmp_path / "00011.png"
    Image.new("RGB", (300, 200), "white").save(page)
    sample = add_ref_sample(
        page, (20, 20, 50, 40), category="别名",
        direction=direction,
    )
    monkeypatch.setattr(
        detection, "match_ref_templates",
        lambda _image, _samples, **opts: [((100, 50, 20, 8), sample)],
    )
    monkeypatch.setattr(detection, "read_pdic", lambda _path: [])
    monkeypatch.setattr(detection, "read_page_sections", lambda _page: [])
    monkeypatch.setattr(detection, "associate_ref_to_entry", lambda *args: None)
    settings = AppSettings(
        character_height=20, row_padding=0, ref_box_width_lines=2,
        ref_box_height_lines=1, ref_box_include_guide_width=True,
    )
    result = detect_ref_boxes_page(page, settings, 0)
    assert result["status"] == "changed"
    assert result["added"] == 1
    boxes = read_ref_boxes(page)
    assert len(boxes) == 1
    assert (boxes[0].x, boxes[0].w) == (expected_x, expected_w)
