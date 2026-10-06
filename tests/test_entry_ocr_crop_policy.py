from __future__ import annotations

import json
from pathlib import Path

from picture_capture.entry_classification import register_entry_classification
from picture_capture.entry_ocr_crop import (
    EntryOcrRowMetrics,
    entry_ocr_content_height,
    entry_ocr_crop_box,
)
from picture_capture.models import AppSettings, Entry


class _IdentityGeometry:
    def __init__(self):
        self.column_starts = [100, 400]
        self.column_widths = [250, 250]

    def source_to_canonical(self, x: int, y: int):
        return int(x), int(y)

    def x_at(self, column: int, y: int) -> int:
        return int(self.column_starts[column])


def test_regular_ocr_crop_uses_half_gap_above_and_full_gap_below():
    settings = AppSettings(
        character_height=40,
        row_padding=20,
        gutter=50,
        entry_regular_crop_height=0,
        right_ratio=60.0,
    )
    entry = Entry(word="", x=100, y=200)
    register_entry_classification(entry, entry_source="indent", entry_scale="regular")

    assert entry_ocr_content_height(entry, settings) == 40
    assert entry_ocr_crop_box(entry, _IdentityGeometry(), settings, (1000, 1500)) == (
        75,
        190,  # 200 - 1/2 * 20 row gap
        275,  # 100 + 250 * 0.60 + 25 half gutter
        260,  # 200 + 40 content + 20 full trailing row gap
    )


def test_physical_line_pitch_replaces_legacy_row_padding_for_regular_crop():
    settings = AppSettings(
        character_height=49,
        row_padding=1,
        gutter=50,
        entry_regular_crop_height=0,
        right_ratio=60.0,
    )
    entry = Entry(word="", x=100, y=200)
    register_entry_classification(entry, entry_source="symbol_sample", entry_scale="regular")
    metrics = EntryOcrRowMetrics(line_height=49.0, line_pitch=78.0)

    assert entry_ocr_content_height(entry, settings, row_metrics=metrics) == 49
    box = entry_ocr_crop_box(
        entry,
        _IdentityGeometry(),
        settings,
        (1000, 1500),
        row_metrics=metrics,
    )
    # Physical gap = 78 - 49 = 29. Keep 14px above and the full 29px below.
    assert box == (75, 186, 275, 278)
    assert box[3] - box[1] == 92


def test_small_legacy_regular_height_cannot_shrink_below_physical_line():
    settings = AppSettings(
        character_height=24,
        row_padding=1,
        entry_regular_crop_height=20,
    )
    entry = Entry(word="", x=100, y=200)
    register_entry_classification(entry, entry_source="indent", entry_scale="regular")
    metrics = EntryOcrRowMetrics(line_height=49.0, line_pitch=78.0)

    assert entry_ocr_content_height(entry, settings, row_metrics=metrics) == 49


def test_oversized_ocr_crop_changes_only_classified_content_height():
    settings = AppSettings(
        character_height=40,
        row_padding=20,
        gutter=50,
        entry_oversized_crop_height=0,
        right_ratio=60.0,
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
        310,  # 200 + 90 content + 20 full trailing row gap
    )


def test_visible_right_ratio_controls_marker_ocr_without_changing_paddle_band(tmp_path: Path):
    settings = AppSettings(
        character_height=40,
        row_padding=20,
        gutter=50,
        right_ratio=72.5,
        paddle_band_width_ratio=61.0,
    )
    entry = Entry(word="", x=100, y=200)
    register_entry_classification(entry, entry_source="indent", entry_scale="regular")

    box = entry_ocr_crop_box(entry, _IdentityGeometry(), settings, (1000, 1500))
    assert box[2] == 306  # 100 + 250 * 0.725 + 25 half gutter
    assert settings.paddle_band_width_ratio == 61.0

    path = tmp_path / "settings.json"
    settings.to_json(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["right_ratio"] == 72.5
    assert raw["paddle_band_width_ratio"] == 61.0
    assert "entry_ocr_right_ratio" not in raw

    restored = AppSettings.from_json(path)
    assert restored.right_ratio == 72.5
    assert restored.paddle_band_width_ratio == 61.0


def test_transient_entry_ocr_right_ratio_migrates_to_visible_right_ratio(tmp_path: Path):
    path = tmp_path / "settings.json"
    AppSettings(right_ratio=72.5, paddle_band_width_ratio=61.0).to_json(path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("right_ratio", None)
    raw["entry_ocr_right_ratio"] = 67.5
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    restored = AppSettings.from_json(path)
    assert restored.right_ratio == 67.5
    assert restored.paddle_band_width_ratio == 61.0

    # If both keys exist, the established visible setting is authoritative.
    raw["right_ratio"] = 74.0
    raw["entry_ocr_right_ratio"] = 55.0
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    restored = AppSettings.from_json(path)
    assert restored.right_ratio == 74.0
    assert restored.paddle_band_width_ratio == 61.0


def test_marker_ocr_uses_shared_multi_engine_channel_and_shared_crop():
    import picture_capture.processing_core as processing_core

    source = Path(processing_core.__file__).read_text(encoding="utf-8")
    assert "resolve_entry_ocr_row_metrics(" in source
    assert "entry_ocr_crop_box(" in source
    assert "OcrChannelSession" in source
    assert "channel.recognize_crop(" in source
    assert "choose_ocr_text(" in source
    assert 'engine_name == "paddleocr"' not in source
    assert "core.run_tesseract(" not in source


def test_core_composition_exposes_static_marker_ocr_for_non_gui_consumers():
    import picture_capture
    from picture_capture import processing
    from picture_capture.bootstrap.core import build_core_services

    build_core_services()
    package_source = Path(picture_capture.__file__).read_text(encoding="utf-8")
    core_source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "bootstrap"
        / "core.py"
    ).read_text(encoding="utf-8")

    assert "install_processing_entry_classification(_processing)" not in package_source
    assert "install_processing_entry_classification" not in core_source
    assert "entry_classification_runtime" not in core_source
    assert (
        processing.ocr_existing_entry_words_from_markers
        is processing._core.ocr_existing_entry_words_from_markers
    )
