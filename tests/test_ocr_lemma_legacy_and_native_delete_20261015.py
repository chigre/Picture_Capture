"""Regress OCR-only bracket extraction and safe native Delete key.

No user scan, project PDIC, or model download is required.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_marker_ocr_text import bracketed_ocr_lemma


@pytest.mark.parametrize(("raw", "expected"), [
    ("4【禾王】太平天国天王洪秀全自称。《太平天国·十", "禾王"),
    ("4【禾王", "禾王"),
    ("禾王】太平天国天王洪秀全自称", "禾王"),
    ("正常词语", None),
])
def test_exact_malformed_cjk_result_only_trims_when_delimited(raw, expected):
    assert bracketed_ocr_lemma(raw, enabled=True) == expected


@pytest.mark.parametrize(("enabled", "expected"), [(True, "禾王"), (False, "4【禾王】太平天国")])
def test_legacy_ocr_entries_uses_profile_gate_and_bracket_cleanup(monkeypatch, enabled, expected):
    from picture_capture import processing_core as core
    from picture_capture import dictionary_profile

    settings = AppSettings(
        dictionary_profile_id="cjk_visual",
        profile_cjk_allow_bracketed_headword=enabled,
        ocr_language="chi_tra",
        ocr_engine="tesseract",
        ocr_replace=False,
        lowercase_ocr=False,
    )
    image = Image.new("RGB", (500, 240), "white")
    geometry = SimpleNamespace()
    monkeypatch.setattr(
        core, "_page_geometry_context",
        lambda *_args: (image, settings, image, geometry),
    )
    monkeypatch.setattr(
        core, "sort_entries_reading_order",
        lambda entries, *_args: entries,
    )
    monkeypatch.setattr(core, "line_box", lambda *_args: (0, 0, 80, 60))
    monkeypatch.setattr(core, "run_tesseract", lambda *_args, **_kwargs: "4【禾王】太平天国")
    monkeypatch.setattr(
        dictionary_profile, "effective_project_profile_id",
        lambda *_args: "cjk_visual",
    )
    monkeypatch.setattr(
        dictionary_profile, "load_dictionary_profile",
        lambda *_args, **_kwargs: SimpleNamespace(
            uses_parser=lambda mode: mode == "cjk_bracketed",
        ),
    )
    out = core.ocr_entries(image, [Entry("", 10, 20)], settings, [])
    assert out == [expected]


