"""#562: complete OCR candidate filter and diagnostic decision owner."""
from __future__ import annotations

from dataclasses import fields
import inspect
import subprocess
import sys

from PIL import Image

from picture_capture import paddle_headwords_core as core
from picture_capture.models import AppSettings, Entry
from picture_capture.ocr import candidate_filter as owner
from picture_capture.ocr.headword_models import OCRRecord


def test_candidate_filter_owner_import_stays_free_of_core_gui_and_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ocr.candidate_filter import HeadwordFilterDeps
assert 'picture_capture.paddle_headwords_core' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_all_41_old_matching_and_filter_policies_are_live_bound():
    fields_now = {field.name for field in fields(owner.HeadwordFilterDeps)}
    assert len(fields_now) == 41
    assert {
        "group_ocr_records", "_repair_split_headword_lines",
        "_repair_wrapped_headword_structure",
        "_repair_multiline_headword_state_machine", "parse_headword_text",
        "evaluate_headword_filter_rules", "_headword_script_compatibility",
        "_configured_symbol_inventory", "refine_separator_y",
        "refine_separator_y_adaptive", "refine_first_content_y",
        "_recover_oversized_cjk_ocr_records", "_cjk_visual_projection_runs",
        "_cjk_candidate_right_context_metrics", "Entry",
        "_VERIFIED_OVERSIZED_CJK_RECOVERIES", "_BUNDLED_PROFILE",
        "load_dictionary_profile", "_annotate_peer_typography_matches",
    } <= fields_now
    live = core._headword_filter_deps()
    assert live.Entry is Entry
    assert live.group_ocr_records is core.group_ocr_records
    assert live._VERIFIED_OVERSIZED_CJK_RECOVERIES is core._VERIFIED_OVERSIZED_CJK_RECOVERIES


def test_legacy_filter_signature_and_documentation_are_retained():
    sig = inspect.signature(core.filter_headword_records)
    assert list(sig.parameters) == [
        "records", "band", "source_top", "source_column_x", "settings",
        "separator_band", "user_rules", "engine_name", "profile",
        "pixel_scale", "peer_typography_annotator", "separator_y_refiner",
    ]
    assert sig.parameters["engine_name"].default == "paddle"
    assert core.filter_headword_records.__doc__.startswith(
        "Select dictionary headwords using structure"
    )
    assert "deps" not in sig.parameters


def test_empty_ocr_records_preserve_no_candidate_and_no_meta_contract():
    band = Image.new("RGB", (140, 110), "white")
    try:
        entries, diagnostics = core.filter_headword_records(
            [], band, source_top=10, source_column_x=12, settings=AppSettings()
        )
        assert entries == [] and diagnostics == []
    finally:
        band.close()


def test_filter_live_grouping_override_removes_candidates_without_image_analysis(monkeypatch):
    original = core.group_ocr_records
    calls = []
    def grouping(records, ratio):
        calls.append((len(records), ratio))
        return []
    monkeypatch.setattr(core, "group_ocr_records", grouping)
    band = Image.new("RGB", (120, 100), "white")
    records = [OCRRecord("árbol m.", .99, (1, 18, 80, 34))]
    try:
        assert core.filter_headword_records(records, band, 0, 15, AppSettings()) == ([], [])
        assert calls and calls[0][0] == 1
        assert original is not core.group_ocr_records
    finally:
        band.close()


def test_original_adapter_forwards_all_optional_arguments_and_patchable_ops(monkeypatch):
    captured = {}
    marker_entries = []
    marker_diagnostics = [{"meta": {"stub": True}}]
    def filter_spy(deps, *args, **kwargs):
        captured["deps"] = deps
        captured["args"] = args
        captured["kwargs"] = kwargs
        return marker_entries, marker_diagnostics
    monkeypatch.setattr(owner, "filter_headword_records", filter_spy)
    image = Image.new("RGB", (80, 90), "white")
    settings = AppSettings()
    sep = Image.new("RGB", (80, 90), "black")
    annotator = lambda items: 0
    refiner = lambda *args, **kwargs: (0, {})
    try:
        result = core.filter_headword_records(
            [], image, 33, 7, settings, separator_band=sep,
            user_rules=[], engine_name="tesseract", profile=object(),
            pixel_scale=1.25, peer_typography_annotator=annotator,
            separator_y_refiner=refiner,
        )
        assert result == (marker_entries, marker_diagnostics)
        assert captured["args"] == ([], image, 33, 7, settings)
        assert captured["kwargs"] == {
            "separator_band": sep, "user_rules": [],
            "engine_name": "tesseract", "profile": captured["kwargs"]["profile"],
            "pixel_scale": 1.25, "peer_typography_annotator": annotator,
            "separator_y_refiner": refiner,
        }
        assert captured["deps"].Entry is Entry
    finally:
        image.close()
        sep.close()


def test_live_profile_and_recovery_policy_hooks_resolve_after_patching(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(core, "_BUNDLED_PROFILE", sentinel)
    assert core._headword_filter_deps()._BUNDLED_PROFILE is sentinel
    monkeypatch.setattr(core, "_VERIFIED_OVERSIZED_CJK_RECOVERIES",
                        {"image_first_oversized_local_ocr"})
    assert core._headword_filter_deps()._VERIFIED_OVERSIZED_CJK_RECOVERIES == {
        "image_first_oversized_local_ocr",
    }
