from __future__ import annotations

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
    # Simulate a reviewer correcting an automatic large-head classification to
    # an ordinary row.
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

    assert "classified_entry_crop_height(" in runtime_source
    assert "meta.entry_scale == \"oversized\"" in runtime_source
    assert "classified_entry_crop_height(" in review_source
    assert "_is_single_cjk_review_headword" not in review_source
    assert '("自动", "普通词条", "大字头")' in review_source


def test_launcher_installs_classification_before_app_and_review_ui_after_app():
    import picture_capture.launcher as launcher

    source = Path(launcher.__file__).read_text(encoding="utf-8")
    assert "install_pdic_classification(formats)" in source
    assert "install_processing_entry_classification(processing_module)" in source
    assert "install_review_entry_classification(app_module)" in source
