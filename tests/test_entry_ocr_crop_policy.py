from __future__ import annotations

import json
from pathlib import Path

from picture_capture.entry_classification import register_entry_classification
from picture_capture.entry_ocr_crop import entry_ocr_content_height, entry_ocr_crop_box
from picture_capture.models import AppSettings, Entry


class _IdentityGeometry:
    def __init__(self):
        self.column_starts = [100, 400]
        self.column_widths = [250, 250]

    def source_to_canonical(self, x: int, y: int):
        return int(x), int(y)

    def x_at(self, column: int, y: int) -> int:
        return int(self.column_starts[column])


def test_regular_ocr_crop_uses_column_gutter_ratio_and_half_row_gap():
    settings = AppSettings(
        character_height=40,
        row_padding=20,
        gutter=50,
        entry_regular_crop_height=0,
        entry_ocr_right_ratio=60.0,
    )
    entry = Entry(word="", x=100, y=200)
    register_entry_classification(entry, entry_source="indent", entry_scale="regular")

    assert entry_ocr_content_height(entry, settings) == 40
    assert entry_ocr_crop_box(entry, _IdentityGeometry(), settings, (1000, 1500)) == (
        75,   # 100 - 1/2 * 50 gutter
        190,  # 200 - 1/2 * 20 row gap
        275,  # 100 + 250 * 0.60 + 25
        250,  # 200 + 40 + 10
    )


def test_oversized_ocr_crop_changes_only_classified_content_height():
    settings = AppSettings(
        character_height=40,
        row_padding=20,
        gutter=50,
        entry_oversized_crop_height=0,
        entry_ocr_right_ratio=60.0,
    )
    entry = Entry(word="", x=100, y=200)
    register_entry_classification(
        entry,
        entry_source="large_head",
        entry_scale="oversized",
        detected_head_height=90,
    )

    assert entry_ocr_content_height(entry, settings) == 90
    assert entry_ocr_crop_box(entry, _IdentityGeometry(), settings, (1000, 1500)) == (
        75,
        190,
        275,
        300,  # 200 + 90 + 10
    )


def test_entry_ocr_right_ratio_is_canonical_alias_for_legacy_paddle_band_width(tmp_path: Path):
    settings = AppSettings(entry_ocr_right_ratio=72.5)
    assert settings.entry_ocr_right_ratio == 72.5
    assert settings.paddle_band_width_ratio == 72.5

    path = tmp_path / "settings.json"
    settings.to_json(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["entry_ocr_right_ratio"] == 72.5
    assert "paddle_band_width_ratio" not in raw

    restored = AppSettings.from_json(path)
    assert restored.entry_ocr_right_ratio == 72.5


def test_marker_ocr_dispatch_honors_configured_engine_and_shared_crop():
    import picture_capture.entry_classification_runtime as runtime

    source = Path(runtime.__file__).read_text(encoding="utf-8")
    assert "entry_ocr_crop_box(" in source
    assert 'engine_name == "paddleocr"' in source
    assert "core.run_tesseract(" in source
    assert "run_paddle_band(" in source
    assert "recognize_paddle_text(" in source


def test_spawn_import_installs_marker_ocr_runtime_package_wide():
    import picture_capture

    source = Path(picture_capture.__file__).read_text(encoding="utf-8")
    assert "install_processing_entry_classification(_processing)" in source
