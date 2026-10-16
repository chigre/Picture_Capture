"""REF box persistence, deterministic template detection and transaction regression."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from picture_capture.models import AppSettings, Entry
from picture_capture.ref_boxes import (
    RefBox, box_intersection_fraction, next_ref_id,
    read_ref_boxes, ref_box_path, ref_box_ticket, write_ref_boxes,
)
from picture_capture.ref_box_detection import (
    add_ref_sample, detect_ref_boxes_page, list_ref_samples, match_ref_templates,
)
from picture_capture.ui.ref_box_controller import RefBoxController
from picture_capture.ui.settings.lifecycle import validate_ref_box_controls
from picture_capture.ui.settings.schema import (
    REF_BOX_STYLE_FIELDS, REF_BOX_GEOMETRY_FIELDS, REF_BOX_CHECKS,
)


def test_ref_box_nine_columns_with_width_based_percent_tsv_roundtrip(tmp_path):
    page = tmp_path / "090001.png"
    Image.new("RGB", (200, 400), "white").save(page)
    box = RefBox(1, 12, 20, 52, 26, 0, "参见\t辞职\nsee also LEAVE")
    assert write_ref_boxes(page, [box], expected_ticket=None)
    target = ref_box_path(page)
    assert target == tmp_path / "data" / "ref_box" / "090001.rbox"
    assert target.read_text(encoding="utf-8").startswith(
        "id\tx\ty\tw\th\tw.ww%\th.hh%\tentry_index\ttext\n"
    )
    assert "26.00%\t13.00%\t0\t" in target.read_text(encoding="utf-8")
    assert read_ref_boxes(page) == [box]
    assert next_ref_id([box, replace(box, id=4)]) == 5
    assert write_ref_boxes(page, [box], expected_ticket=ref_box_ticket(page))
    assert read_ref_boxes(page)[0].entry_index == 0


def test_rbox_does_not_erase_invalid_human_records(tmp_path):
    page = tmp_path / "090001.png"
    Image.new("RGB", (200, 400), "white").save(page)
    path = ref_box_path(page)
    path.parent.mkdir(parents=True)
    source = "id\tx\ty\tw\th\tentry_index\ttext\n1\t10\t12\t20\t25\t0\tA\n2\tmalformed\n"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError):
        read_ref_boxes(page)
    assert path.read_text(encoding="utf-8") == source
    with pytest.raises(ValueError):
        write_ref_boxes(page, [RefBox(2, 1, 1, 10, 10, None, "")],
                        expected_ticket=ref_box_ticket(page))
    assert path.read_text(encoding="utf-8") == source


def test_external_change_rejects_stale_save_without_overwrite(tmp_path):
    page = tmp_path / "090002.png"
    Image.new("RGB", (200, 400), "white").save(page)
    a = RefBox(1, 10, 20, 40, 26, None, "A")
    write_ref_boxes(page, [a], expected_ticket=None)
    ticket = ref_box_ticket(page)
    path = ref_box_path(page)
    path.write_text(path.read_text(encoding="utf-8") + "2\t10\t10\t20\t20\t\toutside\n", encoding="utf-8")
    external = path.read_bytes()
    with pytest.raises(RuntimeError, match="changed"):
        write_ref_boxes(page, [replace(a, text="B")], expected_ticket=ticket)
    assert path.read_bytes() == external


@pytest.mark.parametrize("bad", [
    RefBox(0, 2, 2, 10, 10, None),
    RefBox(1, -1, 2, 10, 10, None),
    RefBox(1, 1, 1, 0, 20, None),
    RefBox(1, 1, 1, 10, 20, -1),
])
def test_bad_ref_record_is_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        write_ref_boxes(tmp_path / "p.png", [bad], expected_ticket=None)


def test_overlap_metric_matches_smaller_box_area():
    a = RefBox(1, 10, 10, 30, 20, None)
    b = RefBox(2, 20, 10, 10, 20, None)
    assert box_intersection_fraction(a, b) == 1.0


class FakeStatus:
    def __init__(self):
        self.messages = []
    def set(self, message):
        self.messages.append(str(message))


class FakeApp:
    def __init__(self, page):
        self.current_page = page
        self.image = Image.new("RGB", (200, 200), "white")
        self.image.save(page)
        self.status_var = FakeStatus()
        self.errors = []
        self.redraws = 0
    def show_error(self, title, error):
        self.errors.append((title, str(error)))
    def redraw(self):
        self.redraws += 1


def test_editor_single_file_undo_redo_and_clear_redo(tmp_path):
    app = FakeApp(tmp_path / "p.png")
    ctl = RefBoxController(app)
    ctl.load_page(app.current_page)
    a = RefBox(1, 10, 10, 20, 20, 0, "A")
    assert ctl._commit([a])
    assert ctl._commit([replace(a, text="B")])
    assert read_ref_boxes(app.current_page)[0].text == "B"
    ctl.undo()
    assert read_ref_boxes(app.current_page)[0].text == "A"
    ctl.redo()
    assert read_ref_boxes(app.current_page)[0].text == "B"
    ctl.undo()
    assert ctl._commit([replace(a, text="C")])
    assert ctl.redo_stack == []
    ctl.redo()
    assert read_ref_boxes(app.current_page)[0].text == "C"


def test_editor_fails_closed_when_source_changes_before_undo(tmp_path):
    app = FakeApp(tmp_path / "p.png")
    ctl = RefBoxController(app)
    ctl.load_page(app.current_page)
    box = RefBox(1, 2, 2, 20, 20, None, "one")
    assert ctl._commit([box])
    assert ctl._commit([replace(box, text="two")])
    path = ref_box_path(app.current_page)
    path.write_text(path.read_text(encoding="utf-8").replace("two", "outside"), encoding="utf-8")
    ctl.undo()
    assert read_ref_boxes(app.current_page)[0].text == "outside"
    assert ctl.undo_stack == ctl.redo_stack == []
    assert app.errors
    assert ctl.boxes == read_ref_boxes(app.current_page)


def test_page_navigation_discards_history_and_reads_saved_state(tmp_path):
    app = FakeApp(tmp_path / "a.png")
    ctl = RefBoxController(app)
    ctl.load_page(app.current_page)
    assert ctl._commit([RefBox(1, 10, 12, 20, 20, None, "first")])
    assert ctl.undo_stack
    app.current_page = tmp_path / "b.png"
    ctl.load_page(app.current_page)
    assert ctl.undo_stack == ctl.redo_stack == []
    assert ctl.boxes == []
    app.current_page = tmp_path / "a.png"
    ctl.load_page(app.current_page)
    assert ctl.boxes[0].text == "first"


def test_template_capture_detects_any_color_not_blue_only(tmp_path):
    # The project's base dependencies do not include OpenCV. This must also
    # pass through the NumPy-only fallback used by default installs.
    page = tmp_path / "012345.png"
    rng = np.random.default_rng(123)
    array = np.full((180, 250, 3), 247, dtype=np.uint8)
    patch = rng.integers(5, 220, (22, 48, 3), dtype=np.uint8)
    array[58:80, 94:142] = patch
    Image.fromarray(array).save(page)
    sample = add_ref_sample(page, (94, 58, 142, 80))
    assert sample in list_ref_samples(page.parent)
    with Image.open(page) as opened:
        matches = match_ref_templates(opened, [sample], threshold=0.96)
    assert (94, 58, 48, 22) in matches
    result = detect_ref_boxes_page(page, AppSettings(ref_match_threshold=0.96), 0)
    assert result["status"] == "changed"
    assert result["added"] == 1
    boxes = read_ref_boxes(page)
    assert len(boxes) == 1
    assert boxes[0].text == ""
    assert (boxes[0].x, boxes[0].w) == (142, 54)
    assert boxes[0].entry_index is None
    assert detect_ref_boxes_page(page, AppSettings(ref_match_threshold=0.96), 0)["added"] == 0



def test_numpy_fallback_returns_same_source_coordinates_without_opencv(tmp_path, monkeypatch):
    import sys
    import picture_capture.ref_box_detection as detection
    monkeypatch.setitem(sys.modules, "cv2", None)
    path = tmp_path / "page.png"
    rng = np.random.default_rng(987)
    pixels = np.full((120, 180, 3), 255, dtype=np.uint8)
    patch = rng.integers(25, 220, (14, 36, 3), dtype=np.uint8)
    pixels[44:58, 62:98] = patch
    Image.fromarray(pixels).save(path)
    sample = add_ref_sample(path, (62, 44, 98, 58))
    with Image.open(path) as image:
        found = detection.match_ref_templates(image, [sample], threshold=0.96)
    assert (62, 44, 36, 14) in found


def test_template_detection_preserves_manual_rectangle_and_does_not_overwrite(tmp_path):
    page = tmp_path / "012345.png"
    rng = np.random.default_rng(123)
    array = np.full((180, 250, 3), 247, dtype=np.uint8)
    array[58:80, 94:142] = rng.integers(5, 220, (22, 48, 3), dtype=np.uint8)
    Image.fromarray(array).save(page)
    add_ref_sample(page, (94,58,142,80))
    # Manual REF is to the right of the matched guide, not ON the guide.
    old = RefBox(21, 142, 56, 54, 27, 0, "人工参见字样")
    write_ref_boxes(page, [old], expected_ticket=None)
    result = detect_ref_boxes_page(page, AppSettings(ref_match_threshold=0.96), 0)
    assert result["added"] == 0
    assert read_ref_boxes(page) == [old]


@pytest.mark.parametrize(("key", "value"), [
    ("ref_box_fill_opacity", "-1"),
    ("ref_box_fill_opacity", "101"),
    ("ref_match_threshold", "0.5"),
    ("ref_match_threshold", "nan"),
    ("ref_match_scale_tolerance_percent", "-1"),
    ("ref_match_scale_tolerance_percent", "51"),
    ("ref_box_font_size", "5"),
    ("ref_box_width_lines", "0"),
    ("ref_box_text_color", "blue"),
    ("ref_box_filled_color", "green"),
    ("ref_box_filled_color", "#12FFXX"),
    ("ref_box_filled_opacity", "-1"),
    ("ref_box_filled_opacity", "101"),
    ("ref_box_filled_opacity", "nan"),
])
def test_ref_settings_validation_fails_before_mutation(key, value):
    with pytest.raises(ValueError):
        validate_ref_box_controls({key: SimpleNamespace(get=lambda: value)})


def test_ref_defaults_and_schema():
    s = AppSettings()
    assert (s.ref_box_fill_color, s.ref_box_fill_opacity) == ("#ffe0b2", 0.0)
    assert (s.ref_box_filled_color, s.ref_box_filled_opacity) == ("#c8e6c9", 0.0)
    assert s.ref_box_show_text is True
    assert (s.ref_box_font_size, s.ref_box_font_bold, s.ref_box_font_italic) == (16, False, False)
    assert (s.ref_box_width_lines, s.ref_box_height_lines) == (2.0, 1.0)
    assert "ref_box_fill_color" in REF_BOX_STYLE_FIELDS
    from picture_capture.ui.settings.schema import REF_TEXT_LABEL_FIELDS
    assert "ref_box_font_family" in REF_TEXT_LABEL_FIELDS
    assert "ref_match_threshold" in REF_BOX_GEOMETRY_FIELDS
    assert "ref_match_scale_tolerance_percent" in REF_BOX_GEOMETRY_FIELDS
    assert "ref_box_show" in dict((name, code) for name, code in REF_BOX_CHECKS).values()
    from picture_capture.ui.settings.schema import REF_TEXT_LABEL_CHECKS
    assert "ref_box_show_text" in dict((name, code) for name, code in REF_TEXT_LABEL_CHECKS).values()
    assert {"ref_box_filled_color", "ref_box_filled_opacity"}.issubset(REF_BOX_STYLE_FIELDS)


def test_ref_recognition_never_saves_or_flushes_pdic(tmp_path, monkeypatch):
    from picture_capture.ui import ref_box_controller as mod

    page = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(page)
    app = FakeApp(page)
    app.project = SimpleNamespace(root=tmp_path, images=(page,))
    app.current_index = 0
    app._batch_active = False
    app.settings = AppSettings()
    app.guard = lambda: True
    app.selected_page_indices = lambda: [0]
    app.save_pdic = lambda **_kwargs: pytest.fail("REF cannot write PDIC")
    app._flush_deferred_page_save = lambda: pytest.fail("REF cannot flush headword edits")
    app._start_batch_task = lambda title, indices, job, **_kwargs: (
        calls.append((title, indices, job))
    )
    calls = []
    monkeypatch.setattr(mod, "list_ref_samples", lambda _root: [tmp_path / "sample.png"])
    monkeypatch.setattr(mod.messagebox, "askyesno", lambda *_a, **_k: True)

    controller = RefBoxController(app)
    controller.load_page(page)
    controller.recognize_selected_scope()
    assert len(calls) == 1
    assert calls[0][0] == "识别 REF"
    assert calls[0][1] == [0]


def test_single_click_ref_defaults_use_character_height_plus_row_spacing(tmp_path):
    app = FakeApp(tmp_path / "a.png")
    app.view_scale = 1.0
    app.settings = AppSettings(
        character_height=20, row_padding=4, ref_box_auto_attach=False,
        ref_box_width_lines=2.0, ref_box_height_lines=1.0,
    )
    app.canvas = SimpleNamespace(
        delete=lambda *_a: None, create_rectangle=lambda *_a, **_k: 1,
    )
    ctl = RefBoxController(app)
    ctl.load_page(app.current_page)
    ctl.editing = True
    ctl.press(10, 12)
    ctl.release(10, 12)
    assert ctl.boxes == [RefBox(1, 10, 12, 48, 24, None, "")]
    assert read_ref_boxes(app.current_page) == ctl.boxes


def test_ref_sample_crop_uses_gui_exif_transposed_coordinates(tmp_path):
    from picture_capture.image_utils import normalize_page_rgb

    page = tmp_path / "rotated.jpg"
    data = np.full((100, 150, 3), (242, 242, 242), dtype=np.uint8)
    data[20:45, 35:68] = (26, 90, 170)
    original = Image.fromarray(data)
    exif = Image.Exif()
    exif[274] = 6  # Exif orientation: 90° clockwise on display
    original.save(page, exif=exif)
    with Image.open(page) as opened:
        display = normalize_page_rgb(opened)
    assert display.size == (100, 150)
    box = (55, 35, 80, 68)
    expected = np.asarray(display.crop(box))
    sample = add_ref_sample(page, box)
    with Image.open(sample) as opened:
        actual = np.asarray(opened.convert("RGB"))
    assert np.array_equal(actual, expected)


def test_rbox_legacy_7_field_file_is_read_without_changes_then_upgraded(tmp_path):
    page = tmp_path / "old.png"
    Image.new("RGB", (1000, 1400), "white").save(page)
    target = ref_box_path(page)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = (
        "id\tx\ty\tw\th\tentry_index\ttext\n"
        "3\t100\t120\t250\t70\t2\t人工参见\n"
    )
    target.write_text(source, encoding="utf-8")
    original = target.read_bytes()
    boxes = read_ref_boxes(page)
    assert boxes == [RefBox(3, 100, 120, 250, 70, 2, "人工参见")]
    assert target.read_bytes() == original  # viewing is strictly read-only
    ticket = ref_box_ticket(page)
    write_ref_boxes(page, boxes, expected_ticket=ticket)
    converted = target.read_text(encoding="utf-8")
    assert converted.startswith("id\tx\ty\tw\th\tw.ww%\th.hh%\tentry_index\ttext")
    assert "25.00%\t7.00%\t2\t人工参见" in converted
    assert read_ref_boxes(page) == boxes


def test_rbox_width_denominator_matches_pdic_for_both_percent_fields(tmp_path):
    page = tmp_path / "ratio.png"
    Image.new("RGB", (200, 800), "white").save(page)
    assert write_ref_boxes(
        page, [RefBox(1, 12, 30, 50, 120, None, "SEE")],
        expected_ticket=None,
    )
    # 50 / 200 = 25%, 120 / 200 = 60%; height is 800 but NOT the
    # denominator, exactly as PDIC Y uses image_width rather than height.
    row = ref_box_path(page).read_text(encoding="utf-8").splitlines()[1]
    assert row.split("\t")[5:7] == ["25.00%", "60.00%"]


def test_rbox_rejects_corrupt_or_stale_nine_field_percent_without_erasing(tmp_path):
    page = tmp_path / "mismatch.png"
    Image.new("RGB", (200, 800), "white").save(page)
    box = RefBox(1, 5, 10, 50, 120, None, "跳转")
    write_ref_boxes(page, [box], expected_ticket=None)
    target = ref_box_path(page)
    source = target.read_text(encoding="utf-8")
    corrupt = source.replace("60.00%", "15.00%")
    target.write_text(corrupt, encoding="utf-8")
    assert target.read_text(encoding="utf-8") == corrupt
    with pytest.raises(ValueError, match="invalid REF"):
        read_ref_boxes(page)
    with pytest.raises(ValueError):
        write_ref_boxes(page, [box], expected_ticket=ref_box_ticket(page))
    assert target.read_text(encoding="utf-8") == corrupt


def test_rbox_exif_rotation_percent_uses_displayed_source_width(tmp_path):
    page = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6  # raw 800×200 rotates to displayed 200×800
    Image.new("RGB", (800, 200), "white").save(page, exif=exif)
    assert write_ref_boxes(
        page, [RefBox(1, 30, 40, 50, 60, None, "")], expected_ticket=None,
    )
    row = ref_box_path(page).read_text(encoding="utf-8").splitlines()[1]
    assert row.split("\t")[5:7] == ["25.00%", "30.00%"]
    assert read_ref_boxes(page)[0].w == 50
