"""Optional Tesseract raw cache and conservative deferred diagnostics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from picture_capture.models import AppSettings
from picture_capture.ocr_lazy_secondary import can_skip_tesseract_diagnostic_column
from picture_capture.tesseract_raw_cache import TesseractRawCache, tesseract_variant_path
from picture_capture.ui.settings import schema


def _cache(path, signature="image-v1", *, force=False, language="spa", status=None):
    return TesseractRawCache(
        path, signature,
        language=language, executable="/usr/bin/tesseract",
        auto_psm=True, fixed_psm=6, vertical=False,
        engine_status=status or {"version": "5.4"},
        force_refresh=force,
    )


def test_per_psm_raw_cache_roundtrip_and_parser_only_reuse(tmp_path):
    source = tmp_path / "00001.json"
    first = _cache(source)
    sample = [{"text": "hola v.", "confidence": 0.93, "box": [2, 8, 42, 28]}]
    assert first.read(0, 4) is None
    first.record(0, 4, sample, "hola v.")
    first.record(0, 6, [], "")
    first.save()
    assert tesseract_variant_path(source).is_file()
    second = _cache(source)
    assert second.read(0, 4) == (sample, "hola v.")
    assert second.read(0, 6) == ([], "")
    assert second.read(1, 4) is None


def test_tesseract_cache_key_rejects_image_language_version_and_force_change(tmp_path):
    source = tmp_path / "00001.json"
    original = _cache(source)
    original.record(
        0, 6,
        [{"text": "test", "confidence": 0.95, "box": [1, 2, 3, 4]}],
        "test",
    )
    original.save()
    assert _cache(source, "image-v2").read(0, 6) is None
    assert _cache(source, language="fra").read(0, 6) is None
    assert _cache(source, status={"version": "6.0"}).read(0, 6) is None
    assert _cache(source, force=True).read(0, 6) is None


def test_bad_tesseract_raw_records_fail_closed(tmp_path):
    source = tmp_path / "00001.json"
    initial = _cache(source)
    initial.record(0, 4, [{"text": "no", "confidence": 0.3, "box": ["a", 0, 1, 4]}], "")
    initial.save()
    assert _cache(source).read(0, 4) is None
    tesseract_variant_path(source).write_text("invalid JSON", encoding="utf-8")
    assert _cache(source).read(0, 4) is None


def _row(text, *, confidence=0.97, selected=True):
    return {
        "text": text, "accepted": selected, "confidence": confidence,
        "features": {"structural_cue": True, "at_left": True},
        "pos_cue": "v.",
    }


def _lazy(rows, **overrides):
    options = {
        "enabled": True, "paddle_enabled": True,
        "tesseract_enabled": True, "rescue_enabled": False,
        "arbitration_enabled": False, "lens_mode": "off",
    }
    options.update(overrides)
    return can_skip_tesseract_diagnostic_column(rows, **options)


def test_lazy_secondary_only_skips_high_trust_diagnostic_columns():
    valid = [_row("alpha"), _row("beta")]
    assert _lazy(valid)
    assert not _lazy(valid, enabled=False)
    assert not _lazy(valid, rescue_enabled=True)
    assert not _lazy(valid, arbitration_enabled=True)
    assert not _lazy(valid, lens_mode="conflict")
    assert not _lazy(valid, paddle_enabled=False)
    assert not _lazy(valid, tesseract_enabled=False)
    assert not _lazy(valid[:1])
    assert not _lazy(valid + [_row("suspect", selected=False)])
    assert not _lazy(valid + [_row("faint", confidence=0.60)])


def test_ocr_performance_toggles_default_off_and_project_persisted(tmp_path):
    default = AppSettings()
    assert default.ocr_cache_tesseract_raw is False
    assert default.ocr_lazy_tesseract_diagnostics is False
    checks = dict((key, name) for name, key in schema.OCR_ADVANCED_CHECKS)
    assert "ocr_cache_tesseract_raw" in checks
    assert "ocr_lazy_tesseract_diagnostics" in checks
    for key in ("ocr_cache_tesseract_raw", "ocr_lazy_tesseract_diagnostics"):
        assert "默认关闭" in schema.CHECK_HELP[key]
    project = tmp_path / "settings.json"
    AppSettings(
        ocr_cache_tesseract_raw=True,
        ocr_lazy_tesseract_diagnostics=True,
    ).to_json(project)
    reloaded = AppSettings.from_json(project)
    assert reloaded.ocr_cache_tesseract_raw and reloaded.ocr_lazy_tesseract_diagnostics


def test_performance_controls_are_not_misplaced_in_profile_checks():
    from picture_capture.ui.settings import schema

    keys = {
        "ocr_resume_completed_pages",
        "ocr_cache_tesseract_raw",
        "ocr_lazy_tesseract_diagnostics",
    }
    advanced = {name for _title, name in schema.OCR_ADVANCED_CHECKS}
    profile = {name for _title, name in schema.PROFILE_CHECKS}
    assert keys <= advanced
    assert keys.isdisjoint(profile)
    assert all(key in schema.CHECK_HELP for key in keys)
