"""Issue #562 page-wide Paddle/Tesseract/Lens OCR detection owner and compatibility."""
from __future__ import annotations

from dataclasses import fields
import inspect
import subprocess
import sys

import pytest
from PIL import Image

from picture_capture import paddle_headwords_core as core
from picture_capture.models import AppSettings, Entry
from picture_capture.ocr import page_detection as owner
from picture_capture.ocr.headword_models import OCRRecord


def test_page_detection_leaf_import_does_not_initialize_core_gui_or_native_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ocr.page_detection import PageDetectionDeps
assert 'picture_capture.paddle_headwords_core' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_original_page_detection_signature_and_docstring_are_unchanged():
    signature = inspect.signature(core.detect_paddle_headwords)
    assert list(signature.parameters) == [
        "image", "geometry", "settings", "cache_path", "force_refresh",
        "engine", "filter_rules_path", "page_sections", "record_filter",
    ]
    assert signature.parameters["cache_path"].default is None
    assert signature.parameters["force_refresh"].default is False
    assert signature.parameters["record_filter"].default is None
    assert core.detect_paddle_headwords.__doc__ == (
        "Run the mature multi-OCR dictionary headword pipeline."
    )


def test_original_monkeypatch_and_cache_contracts_are_live():
    names = {f.name for f in fields(owner.PageDetectionDeps)}
    assert len(names) == 44
    assert {
        "unwrap_column_band", "run_paddle_band", "run_tesseract_band_records",
        "_recover_oversized_cjk_ocr_records",
        "_recover_image_first_oversized_cjk_records",
        "_suppress_raw_records_shadowed_by_verified_cjk_recovery",
        "filter_headword_records", "_pair_ocr_candidates", "_pair_with_lens_candidates",
        "_arbitrate_pair", "_apply_pair_engine_position",
        "_expand_original_y_fallback_candidates",
        "_apply_manual_selection_overrides", "_enforce_position_variant_exclusivity",
        "_deduplicate_selected_cjk_review_candidates",
        "_entries_from_review_candidates", "compact_ocr_cache_payload",
        "_update_project_quality_summary", "OCRRecord", "PROFILE_FILENAME",
        "load_dictionary_profile", "run_google_lens", "normalize_page_rgb",
    } <= names
    deps = core._page_detection_deps()
    assert deps.OCRRecord is OCRRecord
    assert deps.run_paddle_band is core.run_paddle_band
    assert deps.filter_headword_records is core.filter_headword_records
    assert deps._pair_ocr_candidates is core._pair_ocr_candidates


def test_live_override_of_primary_engine_pass_through(monkeypatch):
    replacement = lambda *args, **kwargs: []
    monkeypatch.setattr(core, "run_paddle_band", replacement)
    assert core._page_detection_deps().run_paddle_band is replacement


def test_original_adapter_forwards_all_optional_params_and_live_policy(monkeypatch):
    captured = {}
    answer = [object()]
    def spy(deps, *args, **kwargs):
        captured.update(deps=deps, args=args, kwargs=kwargs)
        return answer
    monkeypatch.setattr(owner, "detect_paddle_headwords", spy)
    im = Image.new("RGB", (20, 20), "white")
    settings = AppSettings()
    geometry = object()
    cache = object()
    rules = object()
    engine = object()
    sections = [object()]
    rf = object()
    try:
        result = core.detect_paddle_headwords(
            im, geometry, settings, cache_path=cache,
            force_refresh=True, engine=engine, filter_rules_path=rules,
            page_sections=sections, record_filter=rf,
        )
        assert result is answer
        assert captured["args"] == (im, geometry, settings)
        assert captured["kwargs"] == {
            "cache_path": cache, "force_refresh": True, "engine": engine,
            "filter_rules_path": rules, "page_sections": sections,
            "record_filter": rf,
        }
        assert captured["deps"].OCRRecord is OCRRecord
    finally:
        im.close()


def test_no_ocr_engine_selected_keeps_original_explicit_failure():
    settings = AppSettings()
    settings.paddle_use_paddleocr = False
    settings.paddle_compare_tesseract = False
    settings.paddle_tesseract_rescue = False
    settings.paddle_enable_lens = False
    settings.paddle_lens_mode = "off"

    class Transform:
        def canonical_size(self, size):
            return size

    class Geometry:
        transform = Transform()
        column_starts = []

    image = Image.new("RGB", (30, 50), "white")
    try:
        with pytest.raises(RuntimeError, match="OCR"):
            core.detect_paddle_headwords(image, Geometry(), settings)
    finally:
        image.close()
