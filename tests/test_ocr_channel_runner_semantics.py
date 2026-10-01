from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.ocr_channel import OcrChannelSession


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
