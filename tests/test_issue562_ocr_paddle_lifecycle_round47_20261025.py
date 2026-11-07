"""Round 47 Paddle lifecycle: physical owner and live cache/constructor hooks."""
from __future__ import annotations

import inspect
import os
import sys
from types import ModuleType, SimpleNamespace

import pytest

from picture_capture import ocr_channel
from picture_capture.ocr import paddle_engine_lifecycle


def test_paddle_factory_has_one_real_owner_and_patchable_historical_api():
    assert "_paddle_engine_lifecycle.create_paddle_engine_impl" in inspect.getsource(
        ocr_channel._create_paddle_engine
    )
    assert "_paddle_engine_lifecycle.clear_cached_engines" in inspect.getsource(
        ocr_channel.clear_ocr_channel_paddle_engine_cache
    )
    assert "FLAGS_enable_pir_api" in inspect.getsource(
        paddle_engine_lifecycle.create_paddle_engine_impl
    )
    assert "clear_text_detection_cache()" in inspect.getsource(
        paddle_engine_lifecycle.create_paddle_engine_impl
    )
    assert tuple(inspect.signature(ocr_channel._create_paddle_engine).parameters) == ("settings",)


def test_live_cache_gpu_bootstrap_and_constructor_fallback(monkeypatch):
    from picture_capture.layout import detection
    from picture_capture.runtime import windows_gpu
    from picture_capture.quality import inference_monitor

    events = []
    class FakeEngine:
        def __init__(self, **kwargs):
            events.append(("constructor", dict(kwargs)))
            if "cpu_threads" in kwargs:
                raise TypeError("unsupported cpu_threads")
            self.kwargs = kwargs

    paddle = ModuleType("paddleocr")
    paddle.PaddleOCR = FakeEngine
    monkeypatch.setitem(sys.modules, "paddleocr", paddle)
    monkeypatch.setattr(detection, "clear_text_detection_cache", lambda: events.append("clear"))
    monkeypatch.setattr(windows_gpu, "configure_windows_nvidia_dlls", lambda: events.append("dlls"))
    monkeypatch.setattr(inference_monitor, "record_model_event", lambda *xs: events.append(("model", xs)))
    monkeypatch.setattr(ocr_channel, "_paddle_language", lambda _: "en")
    monkeypatch.setattr(ocr_channel, "resolve_inference_policy", lambda: SimpleNamespace(
        device="cpu", mkldnn=False, cpu_threads=2,
    ))
    monkeypatch.setattr(ocr_channel, "paddle_constructor_variants", lambda kw, policy: [
        dict(kw, device=policy.device, cpu_threads=2)
    ])
    monkeypatch.setenv("FLAGS_enable_pir_api", "1")
    ocr_channel.clear_ocr_channel_paddle_engine_cache()
    engine=ocr_channel._create_paddle_engine(object())
    assert engine.kwargs["device"] == "cpu"
    assert "cpu_threads" not in engine.kwargs
    assert ocr_channel._create_paddle_engine(object()) is engine
    assert os.environ["FLAGS_enable_pir_api"] == "0"
    assert events[0:2] == ["clear", "dlls"]
    assert [x for x in events if isinstance(x, tuple) and x[0]=="constructor"] == [
        ("constructor", {"lang": "en", "ocr_version": "PP-OCRv5",
          "use_doc_orientation_classify": False, "use_doc_unwarping": False,
          "use_textline_orientation": False, "device": "cpu", "cpu_threads": 2}),
        ("constructor", {"lang": "en", "ocr_version": "PP-OCRv5",
          "use_doc_orientation_classify": False, "use_doc_unwarping": False,
          "use_textline_orientation": False, "device": "cpu"})
    ]
    assert ("model", ("PaddleOCR", "cpu", False, 2)) in events
    ocr_channel.clear_ocr_channel_paddle_engine_cache()
