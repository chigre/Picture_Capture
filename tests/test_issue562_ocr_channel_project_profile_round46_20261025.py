"""Issue #562 Round 46: OCR/pagediscovery physical owners and Tk validation."""
from __future__ import annotations
import inspect
import queue
from types import SimpleNamespace
import pytest
from PIL import Image
from picture_capture import models, ocr_channel
from picture_capture.ocr import channel_preparation, channel_results
from picture_capture.project import page_discovery
from picture_capture.profile.setup import ProjectProfileWizard
from picture_capture.profile import wizard_validation_controls


def test_canonical_ocr_owners_retain_root_signatures():
    for name, mod, implementation in (
        ("_paddle_language", channel_preparation, "paddle_language"),
        ("_ocr_input_otsu_threshold", channel_preparation, "otsu_threshold"),
        ("prepare_ocr_input", channel_preparation, "prepare_ocr_input_impl"),
        ("_paddle_json_payload", channel_results, "paddle_json_payload"),
        ("normalize_paddle_result", channel_results, "normalize_paddle_result_impl"),
        ("_rescale_channel_records", channel_results, "rescale_channel_records"),
        ("_candidate_from_records", channel_results, "candidate_from_records"),
    ):
        fn = getattr(ocr_channel, name)
        assert fn.__module__ == "picture_capture.ocr_channel"
        assert "return _channel_" in inspect.getsource(fn)
        assert len(inspect.getsource(getattr(mod, implementation)).splitlines()) >= 9
    assert tuple(inspect.signature(ocr_channel.prepare_ocr_input).parameters) == (
        "image", "max_long_side", "mode",
    )


def test_ocr_binary_pixels_and_live_threshold_hook(monkeypatch):
    monkeypatch.setattr(ocr_channel, "_ocr_input_otsu_threshold", lambda _gray: 0)
    crop, scale = ocr_channel.prepare_ocr_input(
        Image.new("RGB", (5, 5), (100, 100, 100)), mode="binary",
    )
    assert scale == 1.0
    assert crop.getpixel((2, 2)) == (255, 255, 255)
    assert ocr_channel._paddle_language(SimpleNamespace(
        paddle_language="", ocr_language="spa+eng",
    )) == "es"


def test_result_normalization_box_sort_and_live_record_factory(monkeypatch):
    created = []
    original = ocr_channel.OcrChannelRecord
    def factory(*args, **kwargs):
        row = original(*args, **kwargs)
        created.append(row.text)
        return row
    monkeypatch.setattr(ocr_channel, "OcrChannelRecord", factory)
    monkeypatch.setattr(ocr_channel, "_paddle_json_payload", lambda _data: {
        "rec_texts": ["second", "first", "bad"],
        "rec_scores": [0.9, 0.8, 0.1],
        "rec_boxes": [[2, 15, 20, 25], [1, 2, 20, 10], [1, 0, 1, 8]],
    })
    rows = ocr_channel.normalize_paddle_result(object())
    assert created == ["second", "first"]
    assert [row.text for row in rows] == ["first", "second"]
    assert ocr_channel._rescale_channel_records(rows, 0.5)[0].box == (2, 4, 40, 20)
    candidate = ocr_channel._candidate_from_records("paddle", rows)
    assert candidate.text == "first second"
    assert candidate.confidence == pytest.approx(0.85)


def test_project_cover_and_page_list_conventions(monkeypatch, tmp_path):
    for name in ("_cover.JPG", "10.png", "2.PNG", "notes.txt"):
        (tmp_path / name).write_bytes(b"sample")
    assert models.project_cover_path(tmp_path).name == "_cover.JPG"
    assert [p.name for p in models.project_page_images(tmp_path)] == ["2.PNG", "10.png"]
    assert "is_cover_fn(" in inspect.getsource(page_discovery.project_page_images)
    monkeypatch.setattr(models, "is_project_cover_image", lambda _p: True)
    assert models.project_page_images(tmp_path) == []


def test_tk_validation_queue_preview_and_controls_preserve_methods():
    for name in ("_set_feedback_buttons", "_poll_validation_queue", "_set_validation_fit", "_move_validation_preview"):
        assert "return _wizard_validation_controls." in inspect.getsource(getattr(ProjectProfileWizard, name))
    q = queue.Queue()
    q.put(["analysis"])
    events, configured = [], []
    stub = SimpleNamespace(
        _validation_queue=q, _validation_running=True,
        _finish_validation=lambda result: events.append(result),
        winfo_exists=lambda: True, after=lambda *args: events.append(args),
        _validation_results=[1, 2, 3], validation_preview_slot=2,
        _render_validation_result=lambda: events.append("render"),
        right_canvas=SimpleNamespace(yview_moveto=lambda y: events.append(y)),
    )
    ProjectProfileWizard._poll_validation_queue(stub)
    assert stub._validation_queue is None and events == [["analysis"]]
    ProjectProfileWizard._move_validation_preview(stub, 1)
    assert stub.validation_preview_slot == 0 and events[-1] == "render"
    ProjectProfileWizard._set_validation_fit(stub, "width")
    assert stub.validation_fit_mode == "width" and events[-1] == 0.0
    for name in ("feedback_too_many_button", "feedback_good_button", "feedback_too_few_button"):
        setattr(stub, name, SimpleNamespace(configure=lambda **kw: configured.append(kw)))
    ProjectProfileWizard._set_feedback_buttons(stub, "disabled")
    assert configured == [{"state": "disabled"}] * 3
