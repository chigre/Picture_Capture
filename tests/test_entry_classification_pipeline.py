from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from picture_capture.entry_classification import (
    apply_classification_sidecar,
    classified_entry_crop_height,
    get_entry_classification,
    register_layout_line_classification,
    set_entry_scale_manual,
    write_classification_sidecar,
)
from picture_capture.models import AppSettings, Entry


def test_entry_exposes_canonical_classification_fields():
    entry = Entry(word="", x=10, y=20, ocr_source="ordinary_symbol_evidence")
    assert entry.entry_source == "symbol_sample"
    assert entry.entry_scale == "regular"
    assert entry.detected_head_height == 0.0
    assert entry.entry_scale_manual is False

    entry.entry_scale = "oversized"
    assert entry.entry_scale == "oversized"
    entry.entry_scale_manual = True
    assert entry.entry_scale_manual is True
    entry.entry_scale_manual = False
    assert entry.entry_scale == "oversized"
    assert entry.entry_scale_manual is False


def test_shared_entry_crop_fields_construct_and_persist(tmp_path: Path):
    settings = AppSettings(
        entry_regular_crop_height=42,
        entry_oversized_crop_height=96,
    )
    assert settings.entry_regular_crop_height == 42
    assert settings.entry_oversized_crop_height == 96

    path = tmp_path / "settings.json"
    settings.to_json(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["entry_regular_crop_height"] == 42
    assert raw["entry_oversized_crop_height"] == 96
    assert "review_regular_crop_height" not in raw
    assert "review_single_cjk_line_height" not in raw

    restored = AppSettings.from_json(path)
    assert restored.entry_regular_crop_height == 42
    assert restored.entry_oversized_crop_height == 96


def test_legacy_review_crop_fields_remain_readable(tmp_path: Path):
    settings = AppSettings()
    path = tmp_path / "old-settings.json"
    settings.to_json(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("entry_regular_crop_height", None)
    raw.pop("entry_oversized_crop_height", None)
    raw["review_regular_crop_height"] = 38
    raw["review_single_cjk_line_height"] = 88
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    restored = AppSettings.from_json(path)
    assert restored.entry_regular_crop_height == 38
    assert restored.entry_oversized_crop_height == 88


def test_symbol_and_large_head_evidence_share_one_scale_model():
    symbol_line = SimpleNamespace(role="body")
    large_line = SimpleNamespace(role="body")
    symbol = Entry(
        word="",
        x=10,
        y=20,
        ocr_source="ordinary_symbol_evidence",
        issue_type="ORDINARY_VISUAL_BRACKET_SAMPLE",
    )
    large = Entry(
        word="",
        x=10,
        y=40,
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=84.0,
        ocr_oversized_cjk=True,
    )

    symbol_meta = register_layout_line_classification(symbol_line, symbol)
    large_meta = register_layout_line_classification(large_line, large)

    assert symbol_meta.entry_source == "symbol_sample"
    assert symbol_meta.entry_scale == "regular"
    assert large_meta.entry_source == "large_head"
    assert large_meta.entry_scale == "oversized"
    assert large_meta.detected_head_height == 84.0


def test_oversized_crop_prefers_observed_head_height():
    settings = AppSettings(character_height=30, row_padding=3)
    entry = Entry(
        word="",
        x=10,
        y=20,
        ocr_source="ordinary_large_head_evidence",
        ocr_visual_run_height=82.0,
        ocr_oversized_cjk=True,
    )
    regular = Entry(word="", x=10, y=50, ocr_source="ordinary_symbol_evidence")

    assert classified_entry_crop_height(regular, settings, regular_height=36) == 36
    assert classified_entry_crop_height(entry, settings, regular_height=36) == 88


def test_manual_scale_override_survives_sidecar_round_trip(tmp_path: Path):
    pdic = tmp_path / "page.pdic"
    entry = Entry(word="字", x=40, y=100, ocr_source="ordinary_large_head_evidence")
    set_entry_scale_manual(entry, "regular")
    write_classification_sidecar([entry], pdic)

    restored = Entry(word="字", x=40, y=100)
    apply_classification_sidecar([restored], pdic)
    meta = get_entry_classification(restored)
    assert meta.entry_scale == "regular"
    assert meta.manual_override is True


def test_manual_override_survives_small_separator_y_move(tmp_path: Path):
    pdic = tmp_path / "page.pdic"
    entry = Entry(word="字", x=40, y=100, ocr_source="ordinary_large_head_evidence")
    set_entry_scale_manual(entry, "regular")
    write_classification_sidecar([entry], pdic)

    moved = Entry(word="字", x=40, y=106, ocr_source="ordinary_large_head_evidence")
    apply_classification_sidecar([moved], pdic)
    assert get_entry_classification(moved).manual_override is True
    assert get_entry_classification(moved).entry_scale == "regular"


def test_review_and_marker_ocr_are_wired_to_canonical_classification():
    import picture_capture.entry_classification_runtime as runtime
    import picture_capture.review_entry_classification_ui as review

    runtime_source = Path(runtime.__file__).read_text(encoding="utf-8")
    review_source = Path(review.__file__).read_text(encoding="utf-8")

    # Marker OCR now delegates crop geometry to the shared entry_ocr_crop layer;
    # proofreading retains the same canonical regular/oversized classification.
    assert "entry_ocr_crop_box(" in runtime_source
    assert "resolve_entry_ocr_row_metrics(" in runtime_source
    assert 'meta.entry_scale == "oversized"' in runtime_source
    assert "classified_entry_crop_height(" in review_source
    assert "entry_regular_crop_height" in review_source
    assert "entry_oversized_crop_height" in review_source
    assert "_is_single_cjk_review_headword" not in review_source
    assert '("自动", "普通词条", "大字头")' in review_source


def test_gui_composition_installs_classification_before_app_and_review_ui_after_app():
    import picture_capture.bootstrap.gui as gui_bootstrap

    source = Path(gui_bootstrap.__file__).read_text(encoding="utf-8")
    assert "install_pdic_classification(formats)" in source
    assert "install_processing_entry_classification(processing_module)" in source
    assert "install_review_entry_classification(app_module)" in source
    assert source.index("install_processing_entry_classification(processing_module)") < source.index(
        "from .. import app as app_module"
    )
    assert source.index("from .. import app as app_module") < source.index(
        "install_review_entry_classification(app_module)"
    )


def test_package_installs_pdic_classification_for_non_gui_consumers():
    import picture_capture

    source = Path(picture_capture.__file__).read_text(encoding="utf-8")
    assert "install_entry_crop_settings()" in source
    assert "install_entry_classification_fields()" in source
    assert "install_pdic_classification(_formats)" in source
