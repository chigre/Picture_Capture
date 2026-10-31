"""Issue #562: physical Profile symbol policy and Layout trace ownership."""
from __future__ import annotations

import inspect
from pathlib import Path

from picture_capture.profile import setup, wizard_catalog
from picture_capture.ordinary import debug_stage
from picture_capture import processing
from picture_capture.models import Entry


def test_profile_catalog_owns_data_and_policy_without_changing_setup_api():
    assert setup.OCR_LANGUAGE_LABEL_TO_VALUE is wizard_catalog.OCR_LANGUAGE_LABEL_TO_VALUE
    assert setup.HEADWORD_HELP_LINES is wizard_catalog.HEADWORD_HELP_LINES
    assert setup.BRACKET_ROLE_SYMBOLS is wizard_catalog.BRACKET_ROLE_SYMBOLS
    assert setup._ocr_language_code("中文简体 (chi_sim)") == "chi_sim"
    assert setup._ocr_language_code("xx") == "xx"
    assert "split_symbols(" in inspect.getsource(wizard_catalog._normalize_cjk_visual_symbol_roles)
    assert "return _wizard_catalog._normalize_cjk_visual_symbol_roles(" in inspect.getsource(setup._normalize_cjk_visual_symbol_roles)


def test_cjk_bracket_role_normalization_is_lossless_and_nonmutating():
    samples = [{"role": "entry_marker", "literal": "【", "id": "a"},
               {"role": "entry_marker", "literal": "○", "id": "b"}]
    entry, bracket, normalized = setup._normalize_cjk_visual_symbol_roles(
        "【 ○ 【", "〔", samples,
    )
    assert entry == "○"
    assert bracket == "〔 【"
    assert normalized[0]["role"] == "bracket_open"
    assert normalized[1]["role"] == "entry_marker"
    assert samples[0]["role"] == "entry_marker"
    assert setup._visual_marker_capture_defaults(
        marker_prefix_enabled=True, bracket_enabled=True,
        entry_text="○", bracket_text="【",
    ) == ("entry_marker", "○")
    assert setup._visual_marker_capture_defaults(
        marker_prefix_enabled=False, bracket_enabled=True,
        entry_text="", bracket_text="【",
    ) == ("bracket_open", "【")


def test_profile_symbol_parser_is_resolved_from_setup_at_call_time(monkeypatch):
    calls = []
    def split_symbols(value):
        calls.append(value)
        return tuple(str(value).split())
    monkeypatch.setattr(setup, "split_configured_symbols", split_symbols)
    assert setup._normalize_cjk_visual_symbol_roles("【 ○", "【")[0] == "○"
    assert setup._visual_marker_capture_defaults(
        marker_prefix_enabled=True, bracket_enabled=True,
        entry_text="○", bracket_text="【",
    ) == ("entry_marker", "○")
    assert calls == ["【 ○", "【", "○", "【"]


def test_layout_debug_stage_has_one_physical_owner_and_keeps_facade_patch_seam(monkeypatch):
    assert processing._record_ordinary_debug_stage is debug_stage._record_ordinary_debug_stage
    assert Path(inspect.getsourcefile(debug_stage._record_ordinary_debug_stage)).name == "debug_stage.py"
    entries = [Entry("", 10, 100, ocr_source="layout"),
               Entry("", 10, 140, ocr_source="bracket")]
    trace = {}
    processing._record_ordinary_debug_stage(trace, "before", entries)
    processing._record_ordinary_debug_stage(trace, "after", entries[:1])
    assert [s["count"] for s in trace["stages"]] == [2, 1]
    assert trace["stages"][1]["removed"][0]["y"] == 140
    assert entries[1].y == 140
    seen = []
    monkeypatch.setattr(processing, "_record_ordinary_debug_stage", lambda *a, **k: seen.append(a[1]))
    processing._record_ordinary_debug_stage({}, "patched", [])
    assert seen == ["patched"]
