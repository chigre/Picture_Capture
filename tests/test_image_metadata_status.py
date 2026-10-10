"""Main-window image dimensions and DPI status regressions."""
from pathlib import Path

from picture_capture.image_metadata_status import image_dpi, image_status


def test_embedded_dpi_and_missing_resolution():
    assert image_status(2400, 3200, (300, 300)) == "2400×3200 px｜DPI 300"
    assert image_status(2400, 3200, (300, 200)) == "2400×3200 px｜DPI 300×200"
    assert image_status(2400, 3200, None) == "2400×3200 px｜DPI 未标注"
    assert image_dpi({}) is None
    assert image_dpi({"dpi": (299.999, 299.999)}) == (299.999, 299.999)
    assert image_dpi({"dpi": (0, 300)}) is None


def test_gui_title_and_right_hand_metadata_status_are_independent():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    controller = (root / "ui" / "controllers" / "page.py").read_text(encoding="utf-8")
    assert 'self.title("Picture Capture")' in app
    assert "OCR 词头定位" not in app[app.index("self.title(\"Picture Capture\")"):app.index("fit_window_to_work_area(self", app.index("self.title(\"Picture Capture\")"))]
    assert "textvariable=self.image_metadata_status_var" in app
    assert "self.image_metadata_status_var.set(image_status(" in app
    assert '"source_dpi": source_dpi' in controller
    assert 'source_dpi = preloaded.get("source_dpi")' in app


def test_real_png_dpi_readback(tmp_path):
    from PIL import Image

    path = tmp_path / "scan.png"
    Image.new("RGB", (24, 36), "white").save(path, dpi=(300, 300))
    with Image.open(path) as scan:
        dpi = image_dpi(scan.info)
        assert scan.size == (24, 36)
    assert dpi is not None
    assert abs(dpi[0] - 300) < 1
    assert abs(dpi[1] - 300) < 1
