"""Issue #562: separator-position fusion and OCR alphabet warnings extraction."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from picture_capture import processing as processing_public
from picture_capture import processing_core as processing_core
from picture_capture import paddle_headwords as paddle_public
from picture_capture import paddle_headwords_core as paddle_core
from picture_capture.models import Entry
from picture_capture.ordinary import separator_position_policy
from picture_capture.ocr import alphabetical_warnings

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_new_owner_paths_and_unchanged_historical_core_callables():
    assert (PKG / "ordinary/separator_position_policy.py").is_file()
    assert (PKG / "ocr/alphabetical_warnings.py").is_file()
    assert len(list(PKG.glob("*.py"))) == 5
    for fn in (processing_core._is_single_cjk_headword,
               processing_core._separator_whitespace_score,
               processing_core._prefer_ocr_separator_position):
        assert fn.__module__ == "picture_capture.processing_core"
    for fn in (paddle_core._alphabetical_sort_key,
               paddle_core._annotate_alphabetical_warnings,
               paddle_core._apply_alphabetical_warnings_to_entries):
        assert fn.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(processing_core._prefer_ocr_separator_position).parameters) == [
        "image", "ordinary", "ocr", "geometry", "settings", "gray",
    ]
    assert list(inspect.signature(paddle_core._annotate_alphabetical_warnings).parameters) == [
        "report_columns", "page_sections", "top_v", "bottom_v",
    ]


def test_single_cjk_ideograph_and_separator_fallback():
    for token, is_single in [("", False), ("字", True), ("漢字", False),
                              ("あ", False), ("가", False), ("𠀀", True), (" a ", False)]:
        assert processing_core._is_single_cjk_headword(token) is is_single
        assert separator_position_policy.is_single_cjk_headword(token) is is_single
    ordinary = Entry(word="", x=1, y=10)
    for word, expected in (("字", True), ("casa", False)):
        ocr = Entry(word=word, x=1, y=10)
        assert processing_core._prefer_ocr_separator_position(
            None, ordinary, ocr, None, None,
        ) == (expected, None, None)


def test_separator_decision_uses_live_public_scoring_and_cjk_helpers(monkeypatch):
    ordinary = Entry(word="", x=10, y=12)
    ocr = Entry(word="casa", x=10, y=30)
    image = Image.new("RGB", (64, 64), "white")
    original = processing_core._separator_whitespace_score
    monkeypatch.setattr(processing_public, "_separator_whitespace_score",
                        lambda _image, row, *_rest: 0.50 if row is ordinary else 0.99)
    assert processing_core._prefer_ocr_separator_position(
        image, ordinary, ocr, None, None,
    ) == (True, 0.5, 0.99)
    monkeypatch.setattr(processing_public, "_separator_whitespace_score",
                        lambda _image, row, *_rest: 0.99 if row is ordinary else 0.50)
    assert processing_core._prefer_ocr_separator_position(
        image, ordinary, ocr, None, None,
    ) == (False, 0.99, 0.50)
    monkeypatch.setattr(processing_public, "_separator_whitespace_score", original)
    original_cjk = processing_core._is_single_cjk_headword
    monkeypatch.setattr(processing_public, "_is_single_cjk_headword", lambda word: True)
    assert processing_core._prefer_ocr_separator_position(
        None, ordinary, ocr, None, None,
    ) == (True, None, None)
    monkeypatch.setattr(processing_public, "_is_single_cjk_headword", original_cjk)


def test_whitespace_score_numeric_path_and_otsu_patch(monkeypatch):
    image = Image.new("RGB", (128, 64), "white")
    entry = Entry(word="a", x=10, y=20)
    geom = SimpleNamespace(
        transform=SimpleNamespace(kind="identity"), column_widths=[80],
    )
    settings = SimpleNamespace(character_height=26)
    pixel = np.full((64, 128), 255, dtype=np.uint8)
    src = processing_core._ordinary_source_column_edge
    col = processing_core.column_index_for_click
    def stub_score(gray):
        return separator_position_policy.separator_whitespace_score(
            image, entry, geom, settings, gray,
            normalize_rgb_fn=lambda im: im, column_fn=lambda *args: 0,
            source_edge_fn=lambda *args: (10, 1), otsu_fn=lambda g: 127,
        )
    assert stub_score(pixel) == 1.0
    pixel[19:22, 10:45] = 0
    assert stub_score(pixel) == 0.0
    pixel = np.full((64, 128), 255, dtype=np.uint8)
    original = processing_core._ordinary_source_column_edge
    original_col = processing_core.column_index_for_click
    monkeypatch.setattr(processing_public, "_ordinary_source_column_edge", lambda *args: (10, 1))
    monkeypatch.setattr(processing_public, "column_index_for_click", lambda *args: 0)
    assert processing_core._separator_whitespace_score(image, entry, geom, settings, pixel) == 1.0
    monkeypatch.setattr(processing_public, "_left_edge_otsu_threshold", lambda gray: 255)
    assert processing_core._separator_whitespace_score(image, entry, geom, settings, pixel) == 0.0
    monkeypatch.setattr(processing_public, "_ordinary_source_column_edge", original)
    monkeypatch.setattr(processing_public, "column_index_for_click", original_col)


def _columns():
    return [{"column": 0, "candidates": [
        {"accepted": True, "normalized_headword": "amor", "source_y": 10},
        {"accepted": True, "normalized_headword": "zorro", "source_y": 20},
        {"accepted": True, "normalized_headword": "bote", "source_y": 30},
        {"meta": True, "accepted": False},
    ]}]


def test_alphabetical_warning_only_annotates_and_preserves_acceptance():
    report = _columns()
    warnings = paddle_core._annotate_alphabetical_warnings(report)
    assert len(warnings) == 2
    assert warnings[0]["warning"] == "alphabetical_forward_outlier_between:amor|bote"
    assert warnings[1]["warning"] == "alphabetical_backtrack_vs:zorro"
    assert report[0]["candidates"][1]["accepted"] is True
    assert report[0]["candidates"][2]["accepted"] is True
    assert report[0]["candidates"][0]["alphabetical_warning"] == ""
    assert paddle_core._alphabetical_sort_key("Niño") == alphabetical_warnings.alphabetical_sort_key("Niño")
    assert paddle_core._alphabetical_sort_key("Árbol") == "arbol"
    assert paddle_core._alphabetical_sort_key("Niño") == "nin~o"
    entry = Entry(word="zorro", x=5, y=20, ocr_source="paddle")
    paddle_core._apply_alphabetical_warnings_to_entries(report, [entry])
    assert entry.alphabetical_warning == warnings[0]["warning"]


def test_alphabetical_core_calls_current_public_filter(monkeypatch):
    report = _columns()
    original = paddle_core._candidate_rows
    monkeypatch.setattr(paddle_public, "_candidate_rows", lambda rows: [])
    assert paddle_core._annotate_alphabetical_warnings(report) == []
    monkeypatch.setattr(paddle_public, "_candidate_rows", original)
