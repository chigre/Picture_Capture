"""Offline REF-only OCR, selected-scope wiring and disk protection regressions."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.ocr_channel import (
    OcrChannelCandidate, OcrChannelPlan, OcrChannelResult,
)
from picture_capture.ref_box_ocr import (
    local_ref_ocr_plan, normalize_ref_ocr_text,
    ocr_ref_boxes_job, ocr_ref_boxes_page,
)
from picture_capture.ref_boxes import (
    RefBox, read_ref_boxes, ref_box_path, ref_box_ticket, write_ref_boxes,
)
from picture_capture.ui.ref_box_controller import RefBoxController


def create_page(tmp_path: Path, name: str, boxes=None):
    page = tmp_path / name
    image = Image.new("RGB", (180, 120), "white")
    for xy in ((10, 12, 50, 32), (70, 13, 105, 35)):
        for xx in range(xy[0], xy[2]):
            for yy in range(xy[1], xy[3]):
                image.putpixel((xx, yy), (60, 120, 170))
    image.save(page)
    if boxes is not None:
        write_ref_boxes(page, boxes, expected_ticket=None)
    return page


def engine_session(texts):
    """One channel session reused across every crop on the same page."""
    instances = []

    class FakeSession:
        def __init__(self, settings, *, plan):
            self.settings = settings
            self.plan = plan
            self.calls = []
            instances.append(self)

        def recognize_crop(self, image, *, tesseract_psm=7):
            self.calls.append((image.copy(), tesseract_psm))
            action = texts[len(self.calls) - 1]
            if isinstance(action, Exception):
                raise action
            candidate = OcrChannelCandidate("paddle", text=action)
            return OcrChannelResult(self.plan, (candidate,), False)

    return FakeSession, instances


def test_shared_channel_ref_ocr_disables_network_lens():
    settings = AppSettings(
        paddle_use_paddleocr=True,
        paddle_compare_tesseract=True,
        paddle_enable_lens=True,
        paddle_lens_mode="full",
    )
    plan = local_ref_ocr_plan(settings)
    assert plan.enabled_engines == ("paddle", "tesseract")
    assert plan.voting_engines == ("paddle", "tesseract")
    assert plan.lens_mode == "off"


def test_lens_only_configuration_is_noop(tmp_path):
    page = create_page(tmp_path, "page.png", [RefBox(1, 10, 12, 40, 20, None)])
    before = ref_box_path(page).read_bytes()
    settings = AppSettings(
        paddle_use_paddleocr=False,
        paddle_compare_tesseract=False,
        paddle_enable_lens=True, paddle_lens_mode="full",
        ocr_engine="lens",
    )
    assert local_ref_ocr_plan(settings).enabled_engines == ()
    outcome = ocr_ref_boxes_page(page, settings)
    assert outcome["status"] == "skipped_no_local_engine"
    assert ref_box_path(page).read_bytes() == before


def test_ref_ocr_only_existing_empty_boxes_and_exact_pixel_crops(tmp_path):
    old = [
        RefBox(1, 10, 12, 40, 20, 0, ""),
        RefBox(2, 70, 13, 35, 22, 2, "人工确定的中文"),
        RefBox(3, 120, 25, 25, 17, None, "  "),
    ]
    page = create_page(tmp_path, "080001.png", old)
    session_type, instances = engine_session(["SEE LEAVE", "also"])
    result = ocr_ref_boxes_page(
        page, AppSettings(), session_factory=session_type,
    )
    assert result["filled"] == 2
    assert result["skipped_existing"] == 1
    saved = read_ref_boxes(page)
    assert [(box.id, box.entry_index, box.text) for box in saved] == [
        (1, 0, "SEE LEAVE"),
        (2, 2, "人工确定的中文"),
        (3, None, "also"),
    ]
    assert len(instances) == 1
    crops = instances[0].calls
    assert [crop.size for crop, _psm in crops] == [(40, 20), (25, 17)]
    assert crops[0][0].getpixel((1, 1)) == (60, 120, 170)
    assert all(psm == 7 for _crop, psm in crops)


def test_ref_ocr_skips_missing_rbox_and_never_creates_one(tmp_path):
    page = create_page(tmp_path, "empty.png", None)
    outcome = ocr_ref_boxes_page(page, AppSettings())
    assert outcome["status"] == "skipped_no_ref"
    assert not ref_box_path(page).exists()


def test_ref_ocr_keeps_manual_text_untouched_without_calling_engine(tmp_path):
    text = 'manually typed\nwith a literal "quote"'
    page = create_page(tmp_path, "manual.png", [RefBox(1, 10, 12, 40, 20, 0, text)])
    before = ref_box_path(page).read_bytes()
    outcome = ocr_ref_boxes_page(page, AppSettings())
    assert outcome["status"] == "skipped_filled"
    assert outcome["skipped_existing"] == 1
    assert ref_box_path(page).read_bytes() == before


def test_ref_ocr_ignores_empty_and_engine_failures_and_never_erases_old(tmp_path):
    page = create_page(tmp_path, "fail.png", [
        RefBox(1, 10, 12, 40, 20, None),
        RefBox(2, 70, 13, 35, 22, None),
        RefBox(3, 120, 25, 25, 17, None),
    ])
    fake, _instances = engine_session(["", RuntimeError("engine failed"), "OK"])
    outcome = ocr_ref_boxes_page(page, AppSettings(), session_factory=fake)
    assert outcome["filled"] == 1
    assert outcome["blank"] == 1
    assert outcome["errors"] == 1
    assert [b.text for b in read_ref_boxes(page)] == ["", "", "OK"]


def test_invalid_ref_coordinates_are_skipped_not_cropped_from_neighbor(tmp_path):
    page = create_page(tmp_path, "coords.png", [
        RefBox(1, 170, 10, 20, 20, None),
        RefBox(2, 10, 10, 40, 20, None),
    ])
    fake, _instances = engine_session(["within"])
    outcome = ocr_ref_boxes_page(page, AppSettings(), session_factory=fake)
    assert outcome["errors"] == 1
    assert outcome["filled"] == 1
    assert [b.text for b in read_ref_boxes(page)] == ["", "within"]


def test_ref_ocr_rejects_concurrent_manual_rbox_update(tmp_path):
    page = create_page(tmp_path, "manual_race.png", [RefBox(1, 10, 12, 40, 20, None)])
    source = ref_box_path(page)

    class ConcurrentSession:
        def __init__(self, settings, *, plan):
            self.plan = plan
        def recognize_crop(self, crop, **kwargs):
            source.write_bytes(source.read_bytes() + b"\n")
            return OcrChannelResult(
                self.plan, (OcrChannelCandidate("paddle", text="LEAVE"),),
            )

    with pytest.raises(RuntimeError, match="changed outside editor"):
        ocr_ref_boxes_page(page, AppSettings(), session_factory=ConcurrentSession)
    assert source.read_bytes().endswith(b"\n")
    assert b"LEAVE" not in source.read_bytes()


def test_ref_ocr_rejects_source_image_change_mid_inference(tmp_path):
    page = create_page(tmp_path, "image_race.png", [RefBox(1, 10, 12, 40, 20, None)])
    before = ref_box_path(page).read_bytes()

    class ImageRaceSession:
        def __init__(self, settings, *, plan):
            self.plan = plan
        def recognize_crop(self, crop, **kwargs):
            with Image.open(page) as source:
                changed = source.copy()
            changed.putpixel((0, 0), (0, 0, 0))
            changed.save(page)
            return OcrChannelResult(
                self.plan, (OcrChannelCandidate("paddle", text="YES"),),
            )

    with pytest.raises(RuntimeError, match="image changed"):
        ocr_ref_boxes_page(page, AppSettings(), session_factory=ImageRaceSession)
    assert ref_box_path(page).read_bytes() == before


def test_ref_ocr_job_failure_is_explicit_and_leaves_source_untouched(tmp_path):
    page = create_page(tmp_path, "corrupt.png", [RefBox(1, 10, 12, 40, 20, None)])
    source = ref_box_path(page)
    source.write_bytes(source.read_bytes().replace(b"40\t20", b"oops\t20"))
    before = source.read_bytes()
    outcome = ocr_ref_boxes_job(str(page), AppSettings())
    assert outcome["status"] == "failed"
    assert outcome["filled"] == 0
    assert source.read_bytes() == before


def test_ref_text_normalization_preserves_lines_not_surrounding_whitespace():
    assert normalize_ref_ocr_text("  SEE  \n  LEAVE  ") == "SEE\nLEAVE"


class DummyApp:
    def __init__(self, pages):
        self.project = SimpleNamespace(root=pages[0].parent, images=tuple(pages))
        self.current_page = pages[0]
        self.current_index = 0
        self.settings = AppSettings()
        self._batch_active = False
        self.statuses = []
        self.status_var = SimpleNamespace(set=lambda value: self.statuses.append(value))
        self.batch = None
        self.image = Image.new("RGB", (180, 120), "white")
        self.redraws = 0
        self.errors = []
    def guard(self):
        return True
    def selected_page_indices(self):
        return list(range(len(self.project.images)))
    def _flush_deferred_page_save(self):
        pytest.fail("REF OCR must not save PDIC")
    def save_pdic(self, **_kwargs):
        pytest.fail("REF OCR must not save PDIC")
    def _start_batch_task(self, title, indices, worker, **kwargs):
        self.batch = (title, tuple(indices), worker, kwargs)
        return True
    def redraw(self):
        self.redraws += 1
    def show_error(self, title, exc):
        self.errors.append((title, str(exc)))


def test_ref_ocr_button_selected_scope_skips_missing_pages_and_protects_pdic(tmp_path, monkeypatch):
    import picture_capture.ui.ref_box_controller as ui

    a = create_page(tmp_path, "a.png", [RefBox(1, 10, 12, 40, 20, 0)])
    b = create_page(tmp_path, "b.png", None)
    c = create_page(tmp_path, "c.png", [RefBox(2, 10, 12, 40, 20, 1)])
    app = DummyApp([a, b, c])
    ctl = RefBoxController(app)
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
    ctl.ocr_selected_scope()
    assert app.batch is not None
    title, indices, worker, kwargs = app.batch
    assert title == "OCR REF"
    assert indices == (0, 2)
    assert kwargs["allow_pdic_edits"] is False
    assert kwargs["flush_deferred_save"] is False
    assert kwargs["allow_page_navigation"] is False
    assert kwargs["refresh_page_quality"] is False
    assert not ref_box_path(b).exists()


def test_ref_ocr_button_cancel_has_no_write_and_no_batch(tmp_path, monkeypatch):
    import picture_capture.ui.ref_box_controller as ui

    a = create_page(tmp_path, "a.png", [RefBox(1, 10, 12, 40, 20, 0)])
    before = ref_box_path(a).read_bytes()
    app = DummyApp([a])
    ctl = RefBoxController(app)
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: False)
    ctl.ocr_selected_scope()
    assert app.batch is None
    assert ref_box_path(a).read_bytes() == before


def test_ref_ocr_button_wiring_is_immediately_after_ref_edit():
    from picture_capture.ui.compact_task_menus import ACTION_GROUPS

    ref_group = next(g for g in ACTION_GROUPS if g and
                     ("编辑'REF'", "toggle_ref_box_edit") in g)
    assert list(ref_group) == [
        ("识别'REF'", "recognize_ref_boxes"),
        ("编辑'REF'", "toggle_ref_box_edit"),
        ("OCR 'REF'", "ocr_ref_boxes"),
    ]


def test_ref_ocr_applies_editable_regex_to_new_text_only(tmp_path):
    page = create_page(tmp_path, "custom_regex.png", [
        RefBox(1, 10, 12, 40, 20, None, ""),
        RefBox(2, 70, 13, 35, 22, None, "人工内容"),
        RefBox(3, 120, 25, 25, 17, None, ""),
    ])
    fake_session, _ = engine_session(["参见: apple; please", "no marker"])
    settings = AppSettings(ref_ocr_extract_regex=r"参见:\s*([a-z]+)")
    outcome = ocr_ref_boxes_page(page, settings, session_factory=fake_session)
    assert outcome["status"] == "changed"
    assert outcome["filled"] == 2
    assert [b.text for b in read_ref_boxes(page)] == [
        "apple", "人工内容", "no marker",
    ]
