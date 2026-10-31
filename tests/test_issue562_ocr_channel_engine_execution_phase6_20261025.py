"""Issue #562: shared OCR engine execution has a real domain owner."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from PIL import Image
from picture_capture import ocr_channel
from picture_capture.ocr import channel_engine_execution
from picture_capture.models import AppSettings


def test_five_engine_algorithms_physically_owned_but_session_api_stable():
    names = ("run_paddle_raw", "run_paddle_records", "run_tesseract_records",
             "run_lens_records", "recognize_crop")
    for name in names:
        original = getattr(ocr_channel.OcrChannelSession, name)
        implementation = getattr(channel_engine_execution, name)
        assert original.__module__ == "picture_capture.ocr_channel"
        assert "_channel_engine_execution." + name in inspect.getsource(original)
        assert len(inspect.getsource(implementation).splitlines()) > 15
        old_signature = inspect.signature(original)
        new_signature = inspect.signature(implementation)
        assert list(old_signature.parameters) == [p for p in new_signature.parameters if p != "deps"]
    assert "subprocess.run(" in inspect.getsource(channel_engine_execution.run_tesseract_records)
    assert "lens_attempted" in inspect.getsource(channel_engine_execution.recognize_crop)


def test_paddle_raw_uses_current_legacy_pixel_and_threshold_hooks(monkeypatch):
    image = Image.new("RGB", (3, 2), (7, 11, 13))
    monkeypatch.setattr(ocr_channel, "normalize_page_rgb", lambda _img: Image.new("RGB", (3, 2), (99, 1, 2)))
    monkeypatch.setattr(ocr_channel, "_RAW_OCR_THRESHOLD", 0.37)
    seen = {}
    class Engine:
        def predict(self, pixels, **kwargs):
            seen["pixel"] = tuple(pixels[0, 0])
            seen["kwargs"] = kwargs
            return [{"ok": 1}]
    s = ocr_channel.OcrChannelSession(AppSettings())
    assert s.run_paddle_raw(image, engine=Engine()) == ({"ok": 1},)
    assert seen["pixel"] == (99, 1, 2)
    assert seen["kwargs"]["text_rec_score_thresh"] == 0.37


def test_tesseract_uses_live_public_factory_and_subprocess(monkeypatch):
    monkeypatch.setattr(ocr_channel, "find_tesseract", lambda _name: "/fake/tess")
    seen = []
    tsv = ("level\tleft\ttop\twidth\theight\tconf\ttext\n"
           "5\t4\t6\t12\t8\t91\tword\n")
    monkeypatch.setattr(ocr_channel.subprocess, "run", lambda cmd, **kw: (
        seen.append((cmd, kw["timeout"])) or SimpleNamespace(returncode=0,stdout=tsv.encode(),stderr=b"")
    ))
    s = ocr_channel.OcrChannelSession(AppSettings())
    result = s.run_tesseract_records(Image.new("RGB", (20, 20)), 6)
    assert result.text == "word" and result.records[0].box == (4, 6, 16, 14)
    assert seen[0][0][0] == "/fake/tess" and seen[0][1] == 120


def test_lens_conflict_and_diagnostic_do_not_change_engine_arbitration(monkeypatch):
    called = []
    monkeypatch.setattr(ocr_channel, "run_google_lens", lambda *_a, **_kw: (
        called.append("lens") or ([("Lens", 0.85, (1, 2, 10, 12))], "Lens", "v1")
    ))
    image = Image.new("RGB", (30, 20), "white")
    same = lambda _img: ocr_channel.OcrChannelCandidate(engine="paddle",text="Same")
    other = lambda _img, _psm: ocr_channel.OcrChannelCandidate(engine="tesseract",text="Same")
    plan = ocr_channel.OcrChannelPlan(("paddle","tesseract","lens"),("paddle","tesseract","lens"),"conflict")
    session = ocr_channel.OcrChannelSession(AppSettings(),plan=plan,paddle_runner=same,tesseract_runner=other)
    result = session.recognize_crop(image)
    assert not result.lens_attempted and len(result.candidates) == 2 and not called
    session._tesseract_runner = lambda _img, _psm: ocr_channel.OcrChannelCandidate(engine="tesseract",text="Other")
    result = session.recognize_crop(image)
    assert result.lens_attempted and result.candidate("lens").records[0].box == (1, 2, 10, 12)
    assert called == ["lens"]
    diagnostic = ocr_channel.OcrChannelPlan(("lens",),(),"diagnostic")
    session = ocr_channel.OcrChannelSession(AppSettings(),plan=diagnostic)
    result = session.recognize_crop(image)
    assert result.lens_attempted and not result.candidate("lens").participates_in_fusion


def test_live_candidate_class_and_paddle_preprocessor_patch(monkeypatch):
    image = Image.new("RGB", (4, 4), "white")
    seen = []
    monkeypatch.setattr(ocr_channel, "prepare_ocr_input", lambda *_a, **_kw: (image, 0.5))
    monkeypatch.setattr(ocr_channel, "normalize_paddle_result", lambda _raw: (ocr_channel.OcrChannelRecord("patched",.8,(1,2,3,4)),))
    monkeypatch.setattr(ocr_channel, "_rescale_channel_records", lambda records, scale: (
        seen.append(scale) or records
    ))
    monkeypatch.setattr(ocr_channel, "_candidate_from_records", lambda engine, records, **kw: (
        seen.append((engine, records[0].text)) or ocr_channel.OcrChannelCandidate(engine=engine,text=records[0].text,records=records)
    ))
    s=ocr_channel.OcrChannelSession(AppSettings())
    s.run_paddle_raw=lambda *_a, **_kw: ({"mock":1},)
    result=s.run_paddle_records(image)
    assert result.text=="patched" and seen == [0.5,("paddle","patched")]
