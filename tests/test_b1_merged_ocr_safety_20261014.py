"""Integration safety contracts for merged #475/#476/#477 (B1/R0.2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from picture_capture.formats import read_pdic, write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.ocr_pdic_preservation import preserve_prior_pdic
from picture_capture.ocr_lazy_secondary import can_skip_tesseract_diagnostic_column
from picture_capture.ui.settings import schema


EXPERIMENTS = (
    "paddle_peer_style_rescue",
    "separator_y_ink_safe_gap",
    "ocr_resume_completed_pages",
    "ocr_cache_tesseract_raw",
    "ocr_lazy_tesseract_diagnostics",
)


def test_new_experiments_are_off_for_new_and_legacy_project(tmp_path):
    default = AppSettings()
    assert all(getattr(default, key) is False for key in EXPERIMENTS)
    raw = tmp_path / "project.json"
    default.to_json(raw)
    config = json.loads(raw.read_text(encoding="utf-8"))
    for key in EXPERIMENTS:
        config.pop(key, None)
    raw.write_text(json.dumps(config), encoding="utf-8")
    legacy = AppSettings.from_json(raw)
    assert all(getattr(legacy, key) is False for key in EXPERIMENTS)


def test_experimental_switches_roundtrip_and_can_all_be_disabled(tmp_path):
    config = AppSettings()
    for key in EXPERIMENTS:
        setattr(config, key, True)
    path = tmp_path / "project.json"
    config.to_json(path)
    restored = AppSettings.from_json(path)
    assert all(getattr(restored, key) is True for key in EXPERIMENTS)
    for key in EXPERIMENTS:
        setattr(restored, key, False)
    restored.to_json(path)
    disabled = AppSettings.from_json(path)
    assert all(getattr(disabled, key) is False for key in EXPERIMENTS)
    assert disabled.paddle_refine_separator_y is True  # existing mature feature stays ON


def test_optional_ocr_switches_remain_documented_in_settings():
    named = {key for _label, key in schema.OCR_ADVANCED_CHECKS}
    assert {
        "ocr_resume_completed_pages", "ocr_cache_tesseract_raw",
        "ocr_lazy_tesseract_diagnostics",
    } <= named
    assert all("默认关闭" in schema.CHECK_HELP[key] for key in named if key in EXPERIMENTS)
    assert "separator_y_ink_safe_gap" in schema.CHECK_HELP


def test_prewrite_pdic_snapshot_preserves_manual_bytes_and_deduplicates(tmp_path):
    page = tmp_path / "003.tif"
    page.write_bytes(b"source")
    pdic = tmp_path / "003.pdic"
    markers = [Entry(word="hand-corrected", x=42, y=61)]
    write_pdic(pdic, markers, 900, ("003", "@", "@"))
    before = pdic.read_bytes()
    first = preserve_prior_pdic(tmp_path, page, pdic)
    assert first is not None and first.read_bytes() == before
    assert preserve_prior_pdic(tmp_path, page, pdic) == first
    assert pdic.read_bytes() == before
    # Later automated output must never mutate the backed-up human version.
    write_pdic(pdic, [Entry(word="automatic", x=50, y=75)], 900, ("003", "@", "@"))
    assert first.read_bytes() == before
    assert read_pdic(pdic)[0].word == "automatic"


def test_corrupted_prewrite_snapshot_aborts_instead_of_replacing_only_backup(tmp_path):
    page = tmp_path / "003.tif"
    pdic = tmp_path / "003.pdic"
    write_pdic(pdic, [Entry(word="manual", x=10, y=20)], 500, ("003", "@", "@"))
    before = pdic.read_bytes()
    target = preserve_prior_pdic(tmp_path, page, pdic)
    assert target is not None
    target.write_bytes(b"tampered")
    with pytest.raises(OSError, match="checksum collision"):
        preserve_prior_pdic(tmp_path, page, pdic)
    assert pdic.read_bytes() == before


def test_lazy_tesseract_never_skips_when_option_off():
    rows = [{"accepted": True, "confidence": 0.99,
             "features": {"structural_cue": True}, "pos_cue": "v."}] * 2
    assert can_skip_tesseract_diagnostic_column(
        rows, enabled=False, paddle_enabled=True,
        tesseract_enabled=True, rescue_enabled=False,
        arbitration_enabled=False, lens_mode="off",
    ) is False


def test_detection_write_order_preserves_prior_pdic_before_final_audit():
    app = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    start = app.index("        def worker(index:", app.index("    def _detect_pages("))
    end = app.index("        def done(", start)
    part = app[start:end]
    assert part.index("preserve_prior_pdic(project.root") < part.index("write_pdic(saved_pdic")
    assert part.index("write_pdic(saved_pdic") < part.index("record_final_decisions(")
    assert "and not force_refresh" in part
