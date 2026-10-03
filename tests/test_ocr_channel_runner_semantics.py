from __future__ import annotations

import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.ocr_channel import OcrChannelSession, normalize_paddle_result


def test_channel_paddle_preserves_crop_scaling_and_source_box_coordinates():
    seen: dict[str, object] = {}

    class Engine:
        def predict(self, image, **kwargs):
            seen["shape"] = tuple(image.shape)
            seen["kwargs"] = dict(kwargs)
            return [{
                "res": {
                    "rec_texts": ["Alpha"],
                    "rec_scores": [0.9],
                    "rec_boxes": [[10, 5, 50, 25]],
                }
            }]

    settings = AppSettings(
        paddle_max_input_side=256,
        paddle_preprocessing="grayscale",
    )
    session = OcrChannelSession(settings)

    result = session.run_paddle_records(
        Image.new("RGB", (512, 128), "white"),
        engine=Engine(),
    )

    assert result.error == ""
    assert seen["shape"] == (64, 256, 3)
    assert len(result.records) == 1
    assert result.records[0].text == "Alpha"
    assert result.records[0].confidence == 0.9
    assert result.records[0].box == (20, 10, 100, 50)
    assert result.metadata["input_scale"] == 0.5
    assert result.metadata["preprocessing"] == "grayscale"


def test_channel_paddle_result_normalization_preserves_polygon_fallback():
    records = normalize_paddle_result({
        "res": {
            "rec_texts": ["Alpha"],
            "rec_scores": [0.91],
            "rec_boxes": [],
            "rec_polys": [[[10, 5], [50, 5], [50, 25], [10, 25]]],
        }
    })

    assert len(records) == 1
    assert records[0].text == "Alpha"
    assert records[0].confidence == 0.91
    assert records[0].box == (10, 5, 50, 25)


def test_channel_paddle_engine_preserves_legacy_runtime_bootstrap(monkeypatch):
    import picture_capture.ocr_channel as channel

    events: list[str] = []

    layout_module = ModuleType("picture_capture.layout_detection")
    layout_module.clear_text_detection_cache = lambda: events.append(
        "clear_text_detection_cache"
    )
    monkeypatch.setitem(sys.modules, "picture_capture.layout_detection", layout_module)

    windows_module = ModuleType("picture_capture.windows_gpu_runtime")
    windows_module.configure_windows_nvidia_dlls = lambda: events.append(
        "configure_windows_nvidia_dlls"
    )
    monkeypatch.setitem(sys.modules, "picture_capture.windows_gpu_runtime", windows_module)

    paddle_module = ModuleType("paddleocr")

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            events.append("PaddleOCR")
            self.kwargs = dict(kwargs)

    paddle_module.PaddleOCR = FakePaddleOCR
    monkeypatch.setitem(sys.modules, "paddleocr", paddle_module)
    monkeypatch.setattr(channel, "resolve_paddle_device", lambda: "cpu")
    monkeypatch.setenv("FLAGS_enable_pir_api", "1")

    channel.clear_ocr_channel_paddle_engine_cache()
    settings = AppSettings(
        paddle_language="en",
        paddle_ocr_version="PP-OCRv5",
        paddle_use_textline_orientation=False,
    )

    engine = channel._create_paddle_engine(settings)
    cached = channel._create_paddle_engine(settings)

    assert cached is engine
    assert os.environ["FLAGS_enable_pir_api"] == "0"
    assert events == [
        "clear_text_detection_cache",
        "configure_windows_nvidia_dlls",
        "PaddleOCR",
    ]
    assert engine.kwargs["lang"] == "en"
    assert engine.kwargs["device"] == "cpu"
    assert engine.kwargs["ocr_version"] == "PP-OCRv5"
    assert engine.kwargs["enable_mkldnn"] is False
    channel.clear_ocr_channel_paddle_engine_cache()


def test_legacy_boundary_bridge_no_longer_uses_core_paddle_runner_helpers():
    import picture_capture.ocr_channel_legacy as legacy

    source = Path(legacy.__file__).read_text(encoding="utf-8")
    assert "normalize_paddle_result" in source
    assert "prepare_ocr_input" in source
    assert "_legacy_core.extract_ocr_records" not in source
    assert "_legacy_core.prepare_ocr_band" not in source


def test_channel_tesseract_parses_tsv_by_header_name(monkeypatch):
    import picture_capture.ocr_channel as channel

    monkeypatch.setattr(channel, "find_tesseract", lambda executable: "/fake/tesseract")
    tsv = (
        "text\tconf\theight\twidth\ttop\tleft\tlevel\tword_num\tline_num\t"
        "par_num\tblock_num\tpage_num\n"
        "Alpha\t95\t10\t20\t5\t3\t5\t1\t1\t1\t1\t1\n"
    )
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen["command"] = list(command)
        seen["timeout"] = kwargs.get("timeout")
        return SimpleNamespace(
            returncode=0,
            stdout=tsv.encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(channel.subprocess, "run", fake_run)
    settings = AppSettings(
        tesseract_language="spa",
        ocr_executable="tesseract",
    )
    session = OcrChannelSession(settings)

    result = session.run_tesseract_records(
        Image.new("RGB", (100, 40), "white"),
        7,
    )

    assert result.error == ""
    assert result.text == "Alpha"
    assert len(result.records) == 1
    assert result.records[0].confidence == 0.95
    assert result.records[0].box == (3, 5, 23, 15)
    assert result.metadata["psm"] == 7
    assert seen["timeout"] == 120
    assert seen["command"] == [
        "/fake/tesseract",
        "stdin",
        "stdout",
        "-l",
        "spa",
        "--psm",
        "7",
        "tsv",
    ]
